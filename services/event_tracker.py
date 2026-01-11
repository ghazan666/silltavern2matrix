from collections import deque
import logging
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

    def has_tracked(self, event_id: str) -> bool:
        return bool(event_id and event_id in self.tracked_events)

    def track_event_id(self, room_id: str, event_id: str):
        if not event_id or self.has_tracked(event_id):
            return

        self.tracked_events.add(event_id)
        self.ordered_events.append((room_id, event_id))

    def track_trash_event_id(self, event_id: str):
        if not event_id or self.has_tracked(event_id) or event_id in self.trash_events:
            return

        self.trash_events.add(event_id)

    async def clear_trash_events(self, room_id: str)  -> None:
        for e_id in self.trash_events:
            try:
                logging.info("Clearing trash events.")
                await self.matrix_client.delete_text(room_id, e_id)
            except Exception as e:
                self.logger.error(f"Failed to delete event {e_id}: {e}")

    async def delete_events_after(self, room_id: str, event_id: str = "", num: int|None = None)  -> int:
        """Delete all events after the given event_id in the room."""
        index = None
        try:
            # Find the index of the event
            if event_id:
                for i, (r_id, e_id) in enumerate(self.ordered_events):
                    if r_id == room_id and e_id == event_id:
                        index = i
                        break
            if num:
                index = len(self.ordered_events) - num - 1

            if index is None:
                return 0

            # Collect events after this index
            events_to_delete = []
            for r_id, e_id in list(self.ordered_events)[index + 1:]:
                if r_id == room_id:
                    events_to_delete.append(e_id)

            # Delete them
            for e_id in events_to_delete:
                try:
                    await self.matrix_client.delete_text(room_id, e_id)
                except Exception as e:
                    self.logger.error(f"Failed to delete event {e_id}: {e}")

            # Remove from tracking
            self.ordered_events = deque((r, e) for r, e in self.ordered_events if not (r == room_id and e in events_to_delete))
            for e in events_to_delete:
                self.tracked_events.discard(e)

            return len(events_to_delete)

        except Exception as e:
            self.logger.error(f"Error deleting events after {event_id}: {e}")
            return 0
