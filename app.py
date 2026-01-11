import asyncio
import json
import sys
import threading
from niobot import NioBot, Context, MatrixRoom, RoomMessage

from configs import EnvConfig
from services import MatrixClient, SillyTavernServer, EventTracker


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
event_tracker = EventTracker(matrix_client, cfg, logger)
silly_tavern_server = SillyTavernServer(matrix_client, event_tracker, cfg, logger)


async def send_message_sf(payload: str, room_id: str, event_id: str="") -> None:
    silly_tavern_server.room_id = room_id
    if silly_tavern_server.server and silly_tavern_server.server.state == 1:
        await silly_tavern_server.server.send(payload)
        event_tracker.track_event_id(room_id, event_id)
    else:
        logger.warning("New message received, but SillyTavern server was not connected.")
        error_event_id = await matrix_client.send_text(
            text="抱歉，我现在无法连接到SillyTavern。请确保SillyTavern已打开并启用了扩展。",
            room_id=room_id,
        )
        event_tracker.track_trash_event_id(event_id)
        event_tracker.track_trash_event_id(error_event_id)

async def delmessages(room_id: str, event_id: str, num: int) -> None:
    payload = json.dumps({
            "type": 'execute_command',
            "command": 'del',
            "chatId": event_id,
            "args": num
        })
    await send_message_sf(payload, room_id, event_id)

@bot.command()
async def ping(ctx: Context) -> None:
    bridgeStatus = 'Bridge状态：已连接 ✅'
    stStatus = 'SillyTavern状态：已连接 ✅' if silly_tavern_server.server and silly_tavern_server.server.state == 1 else 'SillyTavern状态：未连接 ❌'

    await ctx.respond(f"{bridgeStatus}\n{stStatus}")

@bot.command()
async def listchats(ctx: Context) -> None:
    payload = json.dumps({
        "type": 'execute_command',
        "command": 'listchats',
        "chatId": ctx.event.event_id
    })
    await send_message_sf(payload, ctx.room.room_id, ctx.event.event_id)

@bot.command()
async def delmode(ctx: Context, num: int) -> None:
    await event_tracker.delete_events_after(ctx.room.room_id, num = num)
    await delmessages(ctx.room.room_id, ctx.event.event_id, num)
    await asyncio.sleep(1)
    await matrix_client.delete_text(ctx.room.room_id, ctx.event.event_id)

@bot.command()
async def cleartrash(ctx: Context) -> None:
    await event_tracker.clear_trash_events(ctx.room.room_id)
    await asyncio.sleep(1)
    await matrix_client.delete_text(ctx.room.room_id, ctx.event.event_id)

@bot.on_event("message")
async def on_message(room: MatrixRoom, event: RoomMessage):
    room_id = room.room_id
    sender = event.sender

    content = event.source["content"]
    body = content["body"]
    event_id = event.event_id
    replaced_event_id = ""
    if content.get("m.relates_to", "") and content["m.relates_to"]["rel_type"] == "m.replace":
        replaced_event_id = content["m.relates_to"]["event_id"]

    # 忽略bot发出的message
    if sender == cfg.mx_user_id:
        return
    if not body:
        return
    # 系统命令由服务器直接处理
    if body.startswith("!"):
        return
    if event_tracker.has_tracked(event_id):
        return

    if replaced_event_id and event_tracker.has_tracked(replaced_event_id):
        # 如果是重复处理的event，打断并删除后续所有消息
        del_num = await event_tracker.delete_events_after(room_id, replaced_event_id)
        await delmessages(room_id, event.event_id, del_num)

    payload = json.dumps({
        "type": "user_message",
        "chatId": event_id,
        "text": body
    })

    logger.info("New message received from %s", sender)
    await send_message_sf(payload, room_id, event_id)


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
