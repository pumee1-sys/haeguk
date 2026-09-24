#!/usr/bin/env python3
"""HAEGUK v473 Battle.net-style lobby + WebSocket relay."""
import asyncio, hashlib, json, os, secrets
from dataclasses import dataclass, field
import websockets

HOST=os.environ.get("HOST","0.0.0.0")
PORT=int(os.environ.get("PORT","8765"))

def pw_hash(s:str)->str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest() if s else ""

@dataclass
class Member:
    ws: object
    client: str
    name: str
    ready: bool=False

@dataclass
class Room:
    room_id: str
    name: str
    map_name: str
    password_hash: str=""
    members: list[Member]=field(default_factory=list)
    started: bool=False

rooms:dict[str,Room]={}
clients:set=set()
client_ids:dict[object,str]={}
client_names:dict[object,str]={}
client_room:dict[object,str]={}

async def send(ws,payload):
    await ws.send(json.dumps(payload,ensure_ascii=False))

def room_public(r:Room):
    return {"id":r.room_id,"name":r.name,"map":r.map_name,"members":len(r.members),"capacity":2,"locked":bool(r.password_hash),"started":r.started}

def public_rooms():
    return [room_public(r) for r in rooms.values() if not r.started and len(r.members)<2]

def room_update_payload(r:Room, your_client:str=""):
    role=-1
    players=[]
    for i,m in enumerate(r.members):
        players.append({"client":m.client,"name":m.name,"ready":m.ready,"role":i})
        if m.client==your_client: role=i
    return {"type":"room_update","room":r.room_id,"name":r.name,"map":r.map_name,
            "locked":bool(r.password_hash),"members":len(r.members),"players":players,
            "your_role":role,"started":r.started,"client":"server"}

async def broadcast_lobby():
    payload={"type":"room_list","rooms":public_rooms(),"client":"server","room":""}
    for ws in list(clients):
        try: await send(ws,payload)
        except Exception: pass

async def broadcast_room_update(r:Room):
    for m in list(r.members):
        try: await send(m.ws,room_update_payload(r,m.client))
        except Exception: pass

async def leave_room(ws):
    rid=client_room.pop(ws,None)
    if not rid or rid not in rooms: return
    r=rooms[rid]
    r.members=[m for m in r.members if m.ws is not ws]
    if not r.members:
        rooms.pop(rid,None)
    else:
        r.started=False
        for m in r.members: m.ready=False
        await broadcast_room_update(r)
        for m in r.members:
            try: await send(m.ws,{"type":"left","room":rid,"client":"server","members":len(r.members)})
            except Exception: pass
    await broadcast_lobby()

async def join_room(ws,rid,password=""):
    r=rooms.get(rid)
    if not r:
        await send(ws,{"type":"error","message":"방을 찾을 수 없습니다."}); return
    if r.started:
        await send(ws,{"type":"error","message":"이미 대국이 시작된 방입니다."}); return
    if len(r.members)>=2:
        await send(ws,{"type":"error","message":"이미 가득 찬 방입니다."}); return
    if r.password_hash and pw_hash(password)!=r.password_hash:
        await send(ws,{"type":"error","message":"비밀번호가 올바르지 않습니다."}); return
    await leave_room(ws)
    cid=client_ids.get(ws,"")
    name=client_names.get(ws,"Player")[:16] or "Player"
    r.members.append(Member(ws,cid,name,False)); client_room[ws]=rid
    role=len(r.members)-1
    await send(ws,{"type":"joined","room":rid,"client":"server","role":role,"members":len(r.members),"name":r.name,"map":r.map_name,"locked":bool(r.password_hash)})
    await broadcast_room_update(r)
    await broadcast_lobby()

async def broadcast_room(rid,payload,skip=None):
    r=rooms.get(rid)
    if not r:return
    for m in list(r.members):
        if m.ws is skip: continue
        try: await send(m.ws,payload)
        except Exception: pass

async def handler(ws):
    clients.add(ws)
    print(f"[connect] clients={len(clients)}",flush=True)
    try:
        await send(ws,{"type":"room_list","rooms":public_rooms(),"client":"server","room":""})
        async for raw in ws:
            try: msg=json.loads(raw)
            except Exception: continue
            typ=str(msg.get("type","")); cid=str(msg.get("client",""))[:80]
            if cid: client_ids[ws]=cid
            pname=str(msg.get("player_name",client_names.get(ws,"Player"))).strip()[:16] or "Player"
            client_names[ws]=pname
            if typ=="list_rooms":
                await send(ws,{"type":"room_list","rooms":public_rooms(),"client":"server","room":""})
            elif typ=="create_room":
                await leave_room(ws)
                rid=secrets.token_hex(4)
                name=str(msg.get("name","해국 대국방")).strip()[:32] or "해국 대국방"
                map_name=str(msg.get("map","기본맵5.map")).strip()[:80] or "기본맵5.map"
                password=str(msg.get("password",""))[:16]
                rooms[rid]=Room(rid,name,map_name,pw_hash(password))
                await join_room(ws,rid,password)
            elif typ=="join_room":
                await join_room(ws,str(msg.get("room","")),str(msg.get("password","")))
            elif typ=="leave_room":
                await leave_room(ws)
            elif typ=="ready":
                rid=client_room.get(ws,""); r=rooms.get(rid)
                if r:
                    for m in r.members:
                        if m.ws is ws: m.ready=bool(msg.get("ready",False))
                    await broadcast_room_update(r)
            elif typ=="start_game":
                rid=client_room.get(ws,""); r=rooms.get(rid)
                if not r: continue
                if not r.members or r.members[0].ws is not ws:
                    await send(ws,{"type":"error","message":"방장만 대국을 시작할 수 있습니다."}); continue
                if len(r.members)!=2 or not all(m.ready for m in r.members):
                    await send(ws,{"type":"error","message":"두 플레이어가 모두 준비해야 합니다."}); continue
                r.started=True
                payload={"type":"game_start","room":rid,"client":"server","map":r.map_name}
                await broadcast_room(rid,payload)
                await broadcast_lobby()
            elif typ=="state":
                rid=client_room.get(ws,"")
                if rid: await broadcast_room(rid,msg,skip=ws)
            elif typ=="ping":
                await send(ws,{"type":"pong","room":client_room.get(ws,""),"client":"server"})
    except (websockets.exceptions.ConnectionClosed,ConnectionResetError):
        pass
    finally:
        await leave_room(ws); clients.discard(ws); client_ids.pop(ws,None); client_names.pop(ws,None)
        print(f"[disconnect] clients={len(clients)}",flush=True)

async def main():
    print(f"HAEGUK v473 lobby listening on {HOST}:{PORT}",flush=True)
    async with websockets.serve(handler,HOST,PORT,max_size=8*1024*1024,ping_interval=20,ping_timeout=20):
        await asyncio.Future()
if __name__=="__main__": asyncio.run(main())
