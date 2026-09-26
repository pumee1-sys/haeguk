# 해국 온라인 릴레이 서버 v479
Render Start Command: `python haeguk_relay_server.py`

v479 핵심:
- P1/P2 양쪽의 `state`를 대칭적으로 릴레이
- `turn_handoff` 메시지 지원: P1→P2→P1 반복 턴 인계를 일반 상태 동기화와 분리
- 서버가 실제 방 슬롯 기준 role을 다시 찍어 잘못된 client role 전파 방지
- `room_update.your_role`을 플레이어별로 개별 전송
