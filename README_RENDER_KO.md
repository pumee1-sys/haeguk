# HAEGUK v469 온라인 로비 서버

이 폴더는 공개 방 목록/방 생성/방 입장/P1·P2 자동 배정/게임 상태 중계를 담당합니다.

Render 등에 배포한 뒤 발급된 HTTPS 주소가 예를 들어 `https://haeguk-online.onrender.com`이면,
Godot `main.gd`의 `ONLINE_RELAY_URL`을 `wss://haeguk-online.onrender.com`으로 바꾸고 Web Export 하세요.

현재 v469 클라이언트 기본값은 로컬 테스트용 `ws://127.0.0.1:8765`입니다.
