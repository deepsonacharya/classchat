"""
ClassChat — share a link, people join, chat with everyone or one-on-one.
Run locally:  python app.py   then open http://localhost:8080
"""
import json
import os
import secrets
import time

from aiohttp import web, WSMsgType

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "index.html"), encoding="utf-8") as f:
    PAGE = f.read()

ROOM = r"{room:[A-Za-z0-9_-]{4,32}}"
rooms = {}  # room_id -> {"clients": {ws: name}, "history": [msg, ...]}


async def home(request):
    # Visiting the site creates a brand-new private room
    raise web.HTTPFound(f"/r/{secrets.token_urlsafe(6)}")


async def room_page(request):
    return web.Response(text=PAGE, content_type="text/html")


def unique_name(room, name):
    taken = set(room["clients"].values())
    base, i = name, 2
    while name in taken:
        name = f"{base} {i}"
        i += 1
    return name


async def send(ws, obj):
    try:
        await ws.send_json(obj)
    except Exception:
        pass


async def push_users(room):
    users = sorted(set(room["clients"].values()), key=str.lower)
    for ws in list(room["clients"]):
        await send(ws, {"type": "users", "users": users})


async def ws_handler(request):
    rid = request.match_info["room"]
    ws = web.WebSocketResponse(heartbeat=25)
    await ws.prepare(request)
    room = rooms.setdefault(rid, {"clients": {}, "history": []})
    name = None

    try:
        async for m in ws:
            if m.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(m.data)
            except ValueError:
                continue

            if name is None:  # first message must be a join
                if data.get("type") != "join":
                    continue
                wanted = str(data.get("name", "")).strip()[:30]
                if not wanted:
                    continue
                name = unique_name(room, wanted)
                room["clients"][ws] = name
                visible = [h for h in room["history"]
                           if h["to"] is None or name in (h["from"], h["to"])]
                await send(ws, {"type": "welcome", "name": name, "history": visible[-300:]})
                await push_users(room)
                continue

            if data.get("type") == "msg":
                text = str(data.get("text", "")).strip()[:2000]
                to = data.get("to") or None  # None = everyone, otherwise a name
                if not text:
                    continue
                msg = {"type": "msg", "from": name, "to": to, "text": text,
                       "ts": int(time.time() * 1000)}
                room["history"].append(msg)
                del room["history"][:-1000]
                for client, cname in list(room["clients"].items()):
                    if to is None or cname in (name, to):
                        await send(client, msg)
    finally:
        if room["clients"].pop(ws, None) is not None:
            await push_users(room)
    return ws


app = web.Application()
app.add_routes([
    web.get("/", home),
    web.get(f"/r/{ROOM}", room_page),
    web.get(f"/ws/{ROOM}", ws_handler),
])

if __name__ == "__main__":
    web.run_app(app, port=int(os.environ.get("PORT", 8080)))
