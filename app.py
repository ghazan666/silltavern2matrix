import asyncio
import json
import sys
import threading
from niobot import NioBot, Context, MatrixRoom, RoomMessage

from configs import EnvConfig
from services import MatrixClient, SillyTavernServer


logger = EnvConfig.load_logger()
cfg = EnvConfig.load_config()
bot = NioBot(
    homeserver=cfg.mx_homeserver,
    user_id=cfg.mx_user_id,
    device_id=cfg.mx_device_id,
    store_path=cfg.mx_store_path,
    command_prefix="!",
    owner_id=cfg.mx_owner_id,
)
matrix_client = MatrixClient(bot, cfg, logger)
silly_tavern_server = SillyTavernServer(matrix_client, cfg, logger)


@bot.command()
async def ping(ctx: Context) -> None:
    await ctx.respond("Pong!")


@bot.on_event("message")
async def on_message(room: MatrixRoom, event: RoomMessage):
    room_id = room.room_id
    sender = event.sender
    body = event.source["content"]["body"]
    event_id = event.event_id
    # 忽略bot发出的message
    if sender == cfg.mx_user_id:
        return
    if not body:
        return
    # 系统命令由服务器直接处理
    if body.startswith("!"):
        return

    if silly_tavern_server.server and silly_tavern_server.server.state == 1:
        logger.info("New message received from %s", sender)
        payload = json.dumps({
            "type": "user_message",
            "chatId": event_id,
            "text": body
        })
        silly_tavern_server.room_id = room_id
        await silly_tavern_server.server.send(payload)
    else:
        logger.warning("New message received, but SillyTavern server was not connected.")
        await bot.room_send(
            room_id=room_id,
            message_type="m.room.message",
            content={
                "msgtype": "m.text",
                "body": "抱歉，我现在无法连接到SillyTavern。请确保SillyTavern已打开并启用了扩展。"
            },
            ignore_unverified_devices=cfg.mx_encryption_enabled,
        )


async def main() -> None:
    bot_thread = threading.Thread(target=matrix_client.login, daemon=True)
    bot_thread.start()

    await silly_tavern_server.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("Exiting.")
        asyncio.run(silly_tavern_server.stop())
    finally:
        sys.exit(0)
