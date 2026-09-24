#!/usr/bin/env python3
"""HAEGUK lobby + WebSocket relay server v472."""
import asyncio, json, os, secrets
from dataclasses import dataclass, field
import websockets

HOST=os.environ.get('HOST','0.0.0.0')
PORT=int(os.environ.get('PORT','8765'))

@dataclass
class Room:
    room_id:str
    name:str
    members:list=field(default_factory=list)

rooms:dict[str,Room]={}
clients:set=set()
client_id:dict[object,str]={}
client_room:dict[object,str]={}

async def send(ws,payload):
    await ws.send(json.dumps(payload,ensure_ascii=False))

def public_rooms():
    return [{"id":r.room_id,"name":r.name,"members":len(r.members),"capacity":2}
            for r in rooms.values() if len(r.members)<2]

async def broadcast_lobby():
    payload={"type":"room_list","rooms":public_rooms(),"client":"server","room":""}
    dead=[]
    for ws in list(clients):
        try: await send(ws,payload)
        except Exception: dead.append(ws)
    for ws in dead: clients.discard(ws)

async def leave_room(ws):
    rid=client_room.pop(ws,None)
    if not rid or rid not in rooms: return
    r=rooms[rid]
    if ws in r.members: r.members.remove(ws)
    if not r.members:
        rooms.pop(rid,None)
    else:
        # Remaining player becomes P1 after opponent leaves.
        await send(r.members[0],{"type":"role","room":rid,"client":"server","role":0})
        await send(r.members[0],{"type":"left","room":rid,"client":"server","members":1})
    await broadcast_lobby()

async def join_room(ws,rid):
    if rid not in rooms:
        await send(ws,{"type":"error","room":"","client":"server","message":"방을 찾을 수 없습니다."}); return
    r=rooms[rid]
    if ws in r.members: return
    if len(r.members)>=2:
        await send(ws,{"type":"error","room":"","client":"server","message":"이미 가득 찬 방입니다."}); return
    await leave_room(ws)
    r.members.append(ws); client_room[ws]=rid
    role=len(r.members)-1
    await send(ws,{"type":"joined","room":rid,"client":"server","role":role,"members":len(r.members),"name":r.name})
    for other in list(r.members):
        if other is not ws:
            await send(other,{"type":"joined","room":rid,"client":client_id.get(ws,''),"role":role,"members":len(r.members),"name":r.name})
    await broadcast_lobby()

async def broadcast_room(rid,payload,skip=None):
    r=rooms.get(rid)
    if not r:return
    for ws in list(r.members):
        if ws is skip:continue
        try: await send(ws,payload)
        except Exception: pass

async def handler(ws):
    clients.add(ws)
    print(f"[connect] clients={len(clients)}", flush=True)
    try:
        await send(ws,{"type":"room_list","rooms":public_rooms(),"client":"server","room":""})
        async for raw in ws:
            try: msg=json.loads(raw)
            except Exception: continue
            typ=str(msg.get('type','')); cid=str(msg.get('client',''))[:80]
            if cid: client_id[ws]=cid
            if typ=='list_rooms': await send(ws,{"type":"room_list","rooms":public_rooms(),"client":"server","room":""})
            elif typ=='create_room':
                await leave_room(ws)
                rid=secrets.token_hex(4)
                name=str(msg.get('name','해국 대국방')).strip()[:32] or '해국 대국방'
                rooms[rid]=Room(rid,name)
                await join_room(ws,rid)
            elif typ=='join_room': await join_room(ws,str(msg.get('room','')))
            elif typ=='leave_room': await leave_room(ws)
            elif typ=='state':
                rid=client_room.get(ws,'')
                if rid: await broadcast_room(rid,msg,skip=ws)
            elif typ=='ping': await send(ws,{"type":"pong","room":client_room.get(ws,''),"client":"server"})
    except (websockets.exceptions.ConnectionClosed, ConnectionResetError):
        pass
    finally:
        await leave_room(ws); clients.discard(ws); client_id.pop(ws,None)
        print(f"[disconnect] clients={len(clients)}", flush=True)

async def main():
    print(f'HAEGUK v472 lobby listening on {HOST}:{PORT}', flush=True)
    async with websockets.serve(handler,HOST,PORT,max_size=8*1024*1024,ping_interval=None):
        await asyncio.Future()
if __name__=='__main__': asyncio.run(main())
