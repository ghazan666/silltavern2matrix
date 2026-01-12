import asyncio
import json
import sys
import threading
import time
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


async def send_message_sf(payload: str, room_id: str) -> None:
    silly_tavern_server.room_id = room_id
    message = json.loads(payload)
    event_id = message.get("chatId", None)
    if event_id is None:
        return

    if silly_tavern_server.server and silly_tavern_server.server.state == 1:
        await silly_tavern_server.server.send(payload)
        if silly_tavern_server.thread_id is None and message.get("type", "") == "user_message":
            # 记录当前会话所在的 Matrix 线程根 event_id
            first_text = message.get("text", "")
            silly_tavern_server.thread_id = event_id
            # 同时在 EventTracker 中注册该线程，供后续列出
            event_tracker.register_thread(event_id, first_text)
        event_tracker.track_event_id(silly_tavern_server.thread_id, event_id)
    else:
        logger.warning("New message received, but SillyTavern server was not connected.")
        error_event_id = await matrix_client.send_text(
            text="抱歉，我现在无法连接到SillyTavern。请确保SillyTavern已打开并启用了扩展。",
            room_id=room_id,
        )
        event_tracker.track_trash_event_id(event_id)
        event_tracker.track_trash_event_id(error_event_id)


async def delmessages(room_id: str, event_id: str, num: int) -> None:
    payload = json.dumps({"type": "execute_command", "command": "del", "chatId": event_id, "args": num})
    await send_message_sf(payload, room_id)


@bot.command()
async def ping(ctx: Context) -> None:
    bridgeStatus = "Bridge状态：已连接 ✅"
    stStatus = (
        "SillyTavern状态：已连接 ✅"
        if silly_tavern_server.server and silly_tavern_server.server.state == 1
        else "SillyTavern状态：未连接 ❌"
    )

    event_id = await matrix_client.send_text(f"{bridgeStatus}\n{stStatus}", ctx.room.room_id)
    event_tracker.track_trash_event_id(event_id)

    await asyncio.sleep(1)
    await matrix_client.delete_text(ctx.room.room_id, ctx.event.event_id)


@bot.command()
async def imagegen(ctx: Context, text: str) -> None:
    payload = json.dumps(
        {"type": "execute_command", "command": "imagine", "chatId": ctx.event.event_id, "args": text}
    )
    await send_message_sf(payload, ctx.room.room_id)

    await asyncio.sleep(1)
    await matrix_client.delete_text(ctx.room.room_id, ctx.event.event_id)


@bot.command()
async def newchat(ctx: Context) -> None:
    silly_tavern_server.thread_id = None
    payload = json.dumps({"type": "execute_command", "command": "new", "chatId": ctx.event.event_id})
    await send_message_sf(payload, ctx.room.room_id)

    await asyncio.sleep(1)
    await matrix_client.delete_text(ctx.room.room_id, ctx.event.event_id)


@bot.command()
async def listchats(ctx: Context) -> None:
    payload = json.dumps({"type": "execute_command", "command": "listchats", "chatId": ctx.event.event_id})
    await send_message_sf(payload, ctx.room.room_id)

    await asyncio.sleep(1)
    await matrix_client.delete_text(ctx.room.room_id, ctx.event.event_id)


@bot.command()
async def switchchat(ctx: Context, inx: int) -> None:
    silly_tavern_server.thread_id = None
    payload = json.dumps(
        {"type": "execute_command", "command": f"switchchat_{inx}", "chatId": ctx.event.event_id}
    )
    await send_message_sf(payload, ctx.room.room_id)

    await asyncio.sleep(1)
    await matrix_client.delete_text(ctx.room.room_id, ctx.event.event_id)


@bot.command()
async def listchars(ctx: Context) -> None:
    payload = json.dumps({"type": "execute_command", "command": "listchars", "chatId": ctx.event.event_id})
    await send_message_sf(payload, ctx.room.room_id)

    await asyncio.sleep(1)
    await matrix_client.delete_text(ctx.room.room_id, ctx.event.event_id)


@bot.command()
async def switchchar(ctx: Context, inx: int) -> None:
    payload = json.dumps(
        {"type": "execute_command", "command": f"switchchar_{inx}", "chatId": ctx.event.event_id}
    )
    await send_message_sf(payload, ctx.room.room_id)

    await asyncio.sleep(1)
    await matrix_client.delete_text(ctx.room.room_id, ctx.event.event_id)


@bot.command()
async def delmode(ctx: Context, num: int) -> None:
    await event_tracker.delete_events_after(
        ctx.room.room_id,
        silly_tavern_server.thread_id,
        num=num,
    )
    await delmessages(ctx.room.room_id, ctx.event.event_id, num)
    await asyncio.sleep(1)
    await matrix_client.delete_text(ctx.room.room_id, ctx.event.event_id)


@bot.command()
async def cleartrash(ctx: Context) -> None:
    await event_tracker.clear_trash_events(ctx.room.room_id)
    await asyncio.sleep(1)
    await matrix_client.delete_text(ctx.room.room_id, ctx.event.event_id)


@bot.command()
async def listthreads(ctx: Context) -> None:
    threads_md = event_tracker.list_threads_markdown()
    event_id = await matrix_client.send_text(f"已知会话线程列表：\n{threads_md}", ctx.room.room_id)
    event_tracker.track_trash_event_id(event_id)

    await asyncio.sleep(1)
    await matrix_client.delete_text(ctx.room.room_id, ctx.event.event_id)


@bot.command()
async def removethread(ctx: Context, thread_id: str) -> None:
    if not thread_id:
        event_id = await matrix_client.send_text("请提供要删除的线程ID。", ctx.room.room_id)
        event_tracker.track_trash_event_id(event_id)
        return

    if thread_id not in event_tracker.thread:
        event_id = await matrix_client.send_text("未找到线程ID。", ctx.room.room_id)
        event_tracker.track_trash_event_id(event_id)
        return

    await event_tracker.delete_events_after(ctx.room.room_id, thread_id, num=len(event_tracker.ordered_events))
    del event_tracker.thread[thread_id]
    event_tracker._save_state()
    event_id = await matrix_client.send_text("已删除线程ID。", ctx.room.room_id)
    event_tracker.track_trash_event_id(event_id)

    await newchat(ctx)

    await asyncio.sleep(1)
    await matrix_client.delete_text(ctx.room.room_id, ctx.event.event_id)


@bot.on_event("message")
async def on_message(room: MatrixRoom, event: RoomMessage):
    room_id = room.room_id
    sender = event.sender
    content = event.source["content"]
    body = content["body"]
    event_id = event.event_id

    # 忽略bot发出的message
    if sender == cfg.mx_user_id:
        return
    if not body:
        return
    # 系统命令由服务器直接处理
    if body.startswith("!"):
        return
    if content.get("msgtype", "") != "m.text":
        return
    if event_tracker.has_tracked(event_id):
        return
    current_time = int(time.time() * 1000)
    if event.server_timestamp < current_time - 10000:
        return

    replaced_event_id = None
    if (
        content.get("m.relates_to", None)
        and content["m.relates_to"].get("m.rel_type", None)
        and content["m.relates_to"]["rel_type"] == "m.replace"
    ):
        replaced_event_id = content["m.relates_to"]["event_id"]
    if replaced_event_id is not None and event_tracker.has_tracked(replaced_event_id):
        # 如果是重复处理的event，打断并删除后续所有消息
        del_num = await event_tracker.delete_events_after(room_id, silly_tavern_server.thread_id, replaced_event_id)
        await delmessages(room_id, event.event_id, del_num)

    payload = json.dumps({"type": "user_message", "chatId": event_id, "text": body})

    logger.info("New message received from %s", sender)
    await send_message_sf(payload, room_id)


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
