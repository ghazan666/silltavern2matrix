from __future__ import annotations

import asyncio
import mimetypes
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Dict
from mistune import create_markdown
from niobot import NioBot, UploadResponse

from utils import SingletonMixin


@dataclass
class ThumbnailPayload:
    data: bytes
    mime: str | None = None


@dataclass
class MediaPayload:
    data: bytes
    filename: str
    mime: str
    body: str
    msgtype: str
    info: Dict[str, Any] = field(default_factory=dict)
    thumbnail: ThumbnailPayload | None = None


class MatrixClient(SingletonMixin):
    """Upload media bytes to Matrix and send the resulting event."""

    def __init__(self, bot: NioBot, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.matrix_loop = asyncio.new_event_loop()

    def login(self):
        """Run the Matrix NioBot in its own thread."""
        asyncio.set_event_loop(self.matrix_loop)
        try:
            self.matrix_loop.run_until_complete(self.bot.start(password=self.cfg.mx_password))
        except Exception:
            self.logger.exception("Matrix bot crashed")
        finally:
            try:
                if not self.matrix_loop.is_closed():
                    self.matrix_loop.run_until_complete(self.bot.close())
            except Exception:
                self.logger.exception("Matrix bot shutdown experienced an error")
            finally:
                if not self.matrix_loop.is_closed():
                    self.matrix_loop.close()

    async def _run_in_matrix_loop(self, coro):
        """Ensure nio bot coroutines run on the bot's event loop."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if current_loop is self.matrix_loop:
            return await coro

        # Wait until the bot's loop is actually running (startup race guard)
        while not self.matrix_loop.is_running():
            if self.matrix_loop.is_closed():
                raise RuntimeError("Matrix bot loop is not running")
            await asyncio.sleep(0.05)

        future = asyncio.run_coroutine_threadsafe(coro, self.matrix_loop)
        return await asyncio.wrap_future(future)

    async def send_text(self, text: str, room_id: str | None, thread_id: str | None = None, html: str | None = None) -> str | None:
        if room_id is not None:
            return await self._run_in_matrix_loop(self._send_text(text, room_id, thread_id, html))

    async def _send_text(self, text: str, room_id: str, thread_id: str | None = None, html: str | None = None) -> str:
        md = create_markdown(plugins=['table'])
        content = {
            "msgtype": "m.text",
            "body": text,
            "format": "org.matrix.custom.html",
            "formatted_body": html if html else md(text),
        }
        if thread_id:
            content["m.relates_to"] = {
                "rel_type": "m.thread",
                "event_id": thread_id,
                "is_falling_back": True,
                "m.in_reply_to": {
                    "event_id": thread_id
                },
            }

        response = await self.bot.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content=content,
            ignore_unverified_devices=self.cfg.mx_encryption_enabled,
        )

        return getattr(response, "event_id", "")

    async def edit_text(self, text: str, room_id: str | None, event_id: str, html: str | None = None) -> str | None:
        if room_id is not None:
            return await self._run_in_matrix_loop(self._edit_text(text, room_id, event_id, html))

    async def _edit_text(self, text: str, room_id: str, event_id: str, html: str | None = None) -> str:
        md = create_markdown(plugins=['table'])
        response = await self.bot.edit_message(room=room_id, message=event_id, content={
            "msgtype": "m.text",
            "body": text,
            "format": "org.matrix.custom.html",
            "formatted_body": html if html else md(text),
        })

        return getattr(response, "event_id", "")

    async def delete_text(self, room_id: str | None, event_id: str) -> str | None:
        if room_id is not None:
            return await self._run_in_matrix_loop(self._delete_text(room_id, event_id))

    async def _delete_text(self, room_id: str, event_id: str) -> str:
        response = await self.bot.delete_message(
            room=room_id,
            message_id=event_id,
        )

        return getattr(response, "event_id", "")

    async def send_in_loop(self, room_id: str | None, payload: MediaPayload) -> str | None:
        if room_id is not None:
            return await self._run_in_matrix_loop(self._send(room_id, payload))

    async def _send(self, room_id: str, payload: MediaPayload) -> str:
        file_resp, decryption_keys = await self.bot.upload(
            BytesIO(payload.data),
            content_type=payload.mime,
            filename=payload.filename,
            filesize=len(payload.data),
            encrypt=self.cfg.mx_encryption_enabled,
        )
        if not (isinstance(file_resp, UploadResponse) and file_resp.content_uri):
            raise RuntimeError("Matrix upload failed")

        info_block = dict(payload.info)
        info_block.setdefault("mimetype", payload.mime)
        info_block.setdefault("size", len(payload.data))

        content: Dict[str, Any] = {
            "body": payload.body,
            "info": info_block,
            "filename": payload.filename,
            "msgtype": payload.msgtype,
        }

        if self.cfg.mx_encryption_enabled and decryption_keys:
            content["file"] = {
                "mimetype": payload.mime,
                "url": file_resp.content_uri,
                "key": decryption_keys["key"],
                "iv": decryption_keys["iv"],
                "hashes": decryption_keys["hashes"],
                "v": decryption_keys["v"],
            }
        else:
            content["url"] = file_resp.content_uri

        if payload.msgtype == "m.video" and payload.thumbnail:
            await self._attach_thumbnail(info_block, payload.filename, payload.thumbnail)

        response = await self.bot.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content=content,
            ignore_unverified_devices=self.cfg.mx_encryption_enabled,
        )
        return getattr(response, "event_id", "")

    async def _attach_thumbnail(self, info_block: Dict[str, Any], filename: str, thumbnail: ThumbnailPayload) -> None:
        thumb_mime = thumbnail.mime or "image/jpeg"
        thumb_filename = self._thumb_filename(filename, thumb_mime)
        thumb_resp, thumb_keys = await self.bot.upload(
            BytesIO(thumbnail.data),
            content_type=thumb_mime,
            filename=thumb_filename,
            filesize=len(thumbnail.data),
            encrypt=self.cfg.mx_encryption_enabled,
        )
        if not (isinstance(thumb_resp, UploadResponse) and thumb_resp.content_uri):
            self.logger.warning("Failed to upload thumbnail for %s", filename)
            return

        thumb_info = {"mimetype": thumb_mime, "size": len(thumbnail.data)}
        if self.cfg.mx_encryption_enabled and thumb_keys:
            info_block["thumbnail_file"] = {
                "mimetype": thumb_mime,
                "url": thumb_resp.content_uri,
                "key": thumb_keys["key"],
                "iv": thumb_keys["iv"],
                "hashes": thumb_keys["hashes"],
                "v": thumb_keys["v"],
            }
        else:
            info_block["thumbnail_url"] = thumb_resp.content_uri
        info_block["thumbnail_info"] = thumb_info

    def _thumb_filename(self, base_name: str, mime: str) -> str:
        ext = mimetypes.guess_extension(mime) or ".jpg"
        if "." in base_name:
            base = base_name.rsplit(".", 1)[0]
        else:
            base = base_name
        return f"{base}_thumb{ext}"
