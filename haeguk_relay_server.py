#!/usr/bin/env python3
"""HAEGUK WebSocket lobby/relay server v480.
Explicitly relays state from BOTH P1 and P2 and turn_handoff messages.
"""
import asyncio, json, os, secrets, string
import websockets
HOST=os.environ.get('HOST','0.0.0.0'); PORT=int(os.environ.get('PORT','10000'))
rooms={}; client_room={}

def room_public(r):
    return {'id':r['id'],'name':r['name'],'map':r['map'],'locked':bool(r['password']),'members':len(r['players']),'started':r['started']}
def players_public(r):
    return [{'client':p['client'],'name':p['name'],'ready':p['ready'],'role':i} for i,p in enumerate(r['players'])]
async def send(ws,p): await ws.send(json.dumps(p,ensure_ascii=False))
async def broadcast_room(r,p,skip=None):
    dead=[]
    for pl in list(r['players']):
        ws=pl['ws']
        if ws is skip: continue
        try: await send(ws,p)
        except: dead.append(ws)
    for ws in dead: await remove_ws(ws)
async def broadcast_lists():
    listing=[room_public(r) for r in rooms.values() if not r['started'] and len(r['players'])<2]
    for r in list(rooms.values()):
        for p in list(r['players']):
            try: await send(p['ws'],{'type':'room_list','rooms':listing})
            except: pass
async def room_update(r):
    # your_role is personalized; never broadcast one player's role to the other.
    for i,p in enumerate(list(r['players'])):
        try: await send(p['ws'],{'type':'room_update','room':r['id'],'name':r['name'],'map':r['map'],'locked':bool(r['password']),'members':len(r['players']),'players':players_public(r),'your_role':i})
        except: pass
async def remove_ws(ws):
    rid=client_room.pop(ws,None)
    if not rid or rid not in rooms: return
    r=rooms[rid]; r['players']=[p for p in r['players'] if p['ws'] is not ws]
    if not r['players']: rooms.pop(rid,None)
    else: await room_update(r)
async def handler(ws):
    try:
        async for raw in ws:
            try: m=json.loads(raw)
            except: continue
            typ=str(m.get('type','')); client=str(m.get('client',''))[:80]
            if typ=='list_rooms':
                await send(ws,{'type':'room_list','rooms':[room_public(r) for r in rooms.values() if not r['started'] and len(r['players'])<2]}); continue
            if typ=='create_room':
                await remove_ws(ws)
                rid=''.join(secrets.choice(string.ascii_uppercase+string.digits) for _ in range(6))
                while rid in rooms: rid=''.join(secrets.choice(string.ascii_uppercase+string.digits) for _ in range(6))
                r={'id':rid,'name':str(m.get('name','해국 대국방'))[:32],'map':str(m.get('map','기본맵5.map')),'password':str(m.get('password',''))[:32],'started':False,'current_turn':0,'turn_seq':0,'round_no':1,'players':[{'ws':ws,'client':client,'name':str(m.get('player_name','Player'))[:16],'ready':False}]}
                rooms[rid]=r; client_room[ws]=rid
                await send(ws,{'type':'joined','room':rid,'name':r['name'],'map':r['map'],'locked':bool(r['password']),'members':1,'players':players_public(r),'your_role':0})
                await room_update(r); await broadcast_lists(); continue
            if typ=='join_room':
                rid=str(m.get('room',''))
                r=rooms.get(rid)
                if not r or r['started'] or len(r['players'])>=2: await send(ws,{'type':'error','message':'입장할 수 없는 방입니다.'}); continue
                if r['password'] and str(m.get('password',''))!=r['password']: await send(ws,{'type':'error','message':'비밀번호가 맞지 않습니다.'}); continue
                await remove_ws(ws); r['players'].append({'ws':ws,'client':client,'name':str(m.get('player_name','Player'))[:16],'ready':False}); client_room[ws]=rid
                await send(ws,{'type':'joined','room':rid,'name':r['name'],'map':r['map'],'locked':bool(r['password']),'members':len(r['players']),'players':players_public(r),'your_role':len(r['players'])-1})
                await room_update(r); await broadcast_lists(); continue
            rid=str(m.get('room',client_room.get(ws,''))); r=rooms.get(rid)
            if not r or client_room.get(ws)!=rid: continue
            idx=next((i for i,p in enumerate(r['players']) if p['ws'] is ws),-1)
            if typ=='ready' and idx>=0:
                r['players'][idx]['ready']=bool(m.get('ready',False)); await room_update(r); continue
            if typ=='start_game':
                if idx!=0 or len(r['players'])!=2 or not all(p['ready'] for p in r['players']): continue
                r['started']=True; r['current_turn']=0; r['turn_seq']=0; r['round_no']=1; await broadcast_room(r,{'type':'game_start','room':rid,'map':r['map'],'current_player':0}); await broadcast_lists(); continue
            if typ=='turn_end':
                # v480: the server is the single authority for whose turn it is.
                # Only the player whose slot equals current_turn may end the turn.
                if idx != r.get('current_turn',0):
                    await send(ws,{'type':'turn_rejected','room':rid,'current_player':r.get('current_turn',0),'message':'턴 종료 거부: 현재 서버 턴과 플레이어가 일치하지 않습니다.'}); continue
                r['current_turn']=1-r['current_turn']
                r['turn_seq']=int(r.get('turn_seq',0))+1
                if r['current_turn']==0: r['round_no']=int(r.get('round_no',1))+1
                out={'type':'turn_set','room':rid,'client':'server','ended_by':idx,'current_player':r['current_turn'],'seq':r['turn_seq'],'round_no':r['round_no'],'state':m.get('state',{})}
                # Both clients receive the same authoritative turn result.
                await broadcast_room(r,out); continue
            if typ=='state':
                # Gameplay state may only be published by the server-authorized active player.
                if idx != r.get('current_turn',0): continue
                out=dict(m); out['room']=rid; out['client']=r['players'][idx]['client']; out['role']=idx
                await broadcast_room(r,out,skip=ws); continue
            if typ=='leave_room':
                await remove_ws(ws); await broadcast_lists(); continue
    finally:
        await remove_ws(ws); await broadcast_lists()
async def main():
    print(f'HAEGUK relay v480 listening on {HOST}:{PORT}')
    async with websockets.serve(handler,HOST,PORT,max_size=16*1024*1024,ping_interval=20,ping_timeout=20): await asyncio.Future()
if __name__=='__main__': asyncio.run(main())
