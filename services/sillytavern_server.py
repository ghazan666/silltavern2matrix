import asyncio
import json
import logging
from typing import Dict, Any

import websockets
from websockets.asyncio.server import ServerConnection

from services import MatrixClient
from utils.singleton import SingletonMixin


class SillyTavernServer(SingletonMixin):
    def __init__(self, matrix_client: MatrixClient, cfg, logger: logging.Logger):
        super().__init__(cfg, logger)
        self.server = None
        self.wss_port = cfg.wss_port
        self.matrix_client = matrix_client
        self.room_id = ""
        self.ongoing_streams: Dict[str, Dict[str, Any]] = {}

    async def start(self):
        self.logger.info(f"Starting WebSocket server on port {self.wss_port}")
        async with websockets.serve(self.handle_connection, "localhost", self.wss_port):
            await asyncio.Future()

    async def handle_connection(self, ws: ServerConnection):
        self.logger.info("SillyTavern extension connected!")
        self.server = ws
        try:
            async for message in ws:
                await self.handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            self.logger.info("SillyTavern extension disconnected.")
            self.server = None
            self.ongoing_streams.clear()
        except Exception as e:
            self.logger.error(f"WebSocket error: {e}")
            self.server = None
            self.ongoing_streams.clear()

    async def handle_message(self, message: str):
        try:
            data = json.loads(message)
            text = data.get('text', '').rstrip('\n')
            msg_type = data.get('type')
            chat_id = data.get('chatId')

            # 处理最终渲染后的消息更新
            if msg_type == 'final_message_update' and chat_id:
                await self.handle_final_message_update(text, chat_id)
            else:
                await self.handle_other_message_type(msg_type, text, chat_id)

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse message: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            await self.matrix_client.send_text(f"Unexpected error: {e}", self.room_id)

    async def handle_final_message_update(self, text: str, chat_id: str):
        session = self.ongoing_streams.get(chat_id, {})
        if session:
            event_id = session["event_id"]
            await self.matrix_client.edit_text(text, self.room_id, event_id)
        else:
            await self.matrix_client.send_text(text, self.room_id)
        del self.ongoing_streams[chat_id]
        self.logger.info(f"Sent message {text}")

    async def handle_other_message_type(self, msg_type: str, text: str, chat_id: str):
        # 错误报告
        if msg_type == 'error_message':
            self.logger.error("Receive error message from SillyTavern.")
            await self.matrix_client.send_text(text, self.room_id)
        # 输入中
        if msg_type == 'typing_action':
            event_id = await self.matrix_client.send_text("思考中...", self.room_id)
            if chat_id not in self.ongoing_streams:
                self.ongoing_streams[chat_id] = {
                    'event_id': event_id,
                }

    async def stop(self):
        if self.server:
            await self.server.close()
        self.logger.info("WebSocket server stopped")
