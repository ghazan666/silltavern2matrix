from collections import deque
import json
import logging
import os
from typing import Set, Tuple

from .matrix_client import MatrixClient
from utils import SingletonMixin


class EventTracker(SingletonMixin):
    """Combined event deduper + progress notifier + cleanup helper."""

    def __init__(self, matrix_client: MatrixClient, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.matrix_client = matrix_client
        self.tracked_events: Set[str] = set()
        self.trash_events: Set[str] = set()
        self.ordered_events: deque[Tuple[str, str]] = deque()
        # 记录每个线程的首条用户消息文本：{thread_id: first_text}
        self.thread: dict[str, str] = {}
        self._storage_path = os.path.join(self.cfg.mx_store_path, "event_tracker.json")
        self._load_state()

    def _load_state(self) -> None:
        try:
            if not os.path.isfile(self._storage_path):
                return

            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            ordered_list = data.get("ordered_events", [])
            self.ordered_events = deque((str(t), str(e)) for t, e in ordered_list)

            tracked_list = data.get("tracked_events")
            if tracked_list is not None:
                self.tracked_events = set(str(e) for e in tracked_list)
            else:
                self.tracked_events = set(e for _, e in self.ordered_events)

            trash_list = data.get("trash_events", [])
            self.trash_events = set(str(e) for e in trash_list)

            thread_meta = data.get("thread", {}) or data.get("thread_first_text", {})
            # 保持插入顺序，便于按创建顺序列出
            self.thread = {str(tid): str(txt) for tid, txt in thread_meta.items()}
        except Exception as e:
            self.logger.error(f"Failed to load event tracker state: {e}")

    def _save_state(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)
            data = {
                "ordered_events": list(self.ordered_events),
                "tracked_events": list(self.tracked_events),
                "trash_events": list(self.trash_events),
                "thread": self.thread,
            }
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Failed to save event tracker state: {e}")

    def register_thread(self, thread_id: str, first_text: str) -> None:
        """注册一个新的线程及其首条文本，用于后续列出线程。

        如果线程已存在，则不会覆盖原有的首条文本。
        """
        if not thread_id:
            return

        if thread_id in self.thread:
            return

        self.thread[thread_id] = first_text
        self._save_state()

    def list_threads_markdown(self) -> str:
        """以 markdown+序号 的形式列出所有已知线程（id + first text）。"""
        if not self.thread:
            return "暂无会话线程。"

        lines: list[str] = []
        for idx, (thread_id, first_text) in enumerate(self.thread.items(), start=1):
            lines.append(f"{idx}. **{thread_id}** - {first_text}")

        return "\n".join(lines)

    def has_tracked(self, event_id: str) -> bool:
        return bool(event_id and event_id in self.tracked_events)

    def track_event_id(self, thread_id: str | None, event_id: str | None):
        if thread_id is None:
            return
        if not event_id or self.has_tracked(event_id):
            return

        self.tracked_events.add(event_id)
        self.ordered_events.append((thread_id, event_id))
        self._save_state()

    def track_trash_event_id(self, event_id: str | None):
        if not event_id or self.has_tracked(event_id) or event_id in self.trash_events:
            return

        self.trash_events.add(event_id)
        self._save_state()

    async def clear_trash_events(self, room_id: str) -> None:
        for e_id in self.trash_events:
            try:
                logging.info("Clearing trash events.")
                await self.matrix_client.delete_text(room_id, e_id)
            except Exception as e:
                self.logger.error(f"Failed to delete event {e_id}: {e}")
        self.trash_events.clear()
        self._save_state()

    async def delete_events_after(
        self, room_id: str, thread_id: str | None, event_id: str | None = None, num: int | None = None
    ) -> int:
        """Delete all events after the given event_id in the room."""
        if thread_id is None:
            logging.info("Conversation not started, skipping deletion.")
            return 0
        index = None

        try:
            # Find the index of the event
            if event_id:
                for i, (t_id, e_id) in enumerate(self.ordered_events):
                    if t_id == thread_id and e_id == event_id:
                        index = i
                        break
            if num and not event_id:
                index = len(self.ordered_events) - num - 1

            if index is None:
                return 0

            # Collect events after this index
            events_to_delete = []
            for t_id, e_id in list(self.ordered_events)[index + 1 :]:
                if t_id == thread_id:
                    events_to_delete.append(e_id)

            # Delete them
            for e_id in events_to_delete:
                try:
                    await self.matrix_client.delete_text(room_id, e_id)
                except Exception as e:
                    self.logger.error(f"Failed to delete event {e_id}: {e}")

            # Remove from tracking
            self.ordered_events = deque(
                (t, e) for t, e in self.ordered_events if not (t == thread_id and e in events_to_delete)
            )
            for e in events_to_delete:
                self.tracked_events.discard(e)

            self._save_state()

            return len(events_to_delete)

        except Exception as e:
            self.logger.error(f"Error deleting events after {event_id}: {e}")
            return 0
