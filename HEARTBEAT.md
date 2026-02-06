# HEARTBEAT.md - 스토리텔러 창작 루틴

## 매 하트비트마다

### 1. 상태 확인
```
current/ 폴더가 비어있는가?
├─ YES → [새 작품 시작]으로
└─ NO  → [이어쓰기]로
```

### 2. 새 작품 시작 (current/ 비어있을 때)
1. 새로운 SF 세계관 구상
2. `current/bible/` 생성:
   - `world.md` - 시대, 장소, 핵심 기술/현상
   - `characters.md` - 주인공, 주요 인물
   - `timeline.md` - 빈 상태로 시작
3. `current/outline.md` - 기승전결 개요 (각 파트 핵심 사건)
4. `current/draft.md` - 첫 2문단 작성
5. git commit & push

### 3. 이어쓰기 (current/ 있을 때)
1. `current/bible/` 전체 읽기 (일관성!)
2. `current/draft.md` 마지막 부분 읽기
3. `current/outline.md`로 현재 위치 파악
4. **2문단 작성** → draft.md에 추가
5. 새 설정 있으면 bible/ 업데이트
6. timeline.md에 사건 기록
7. git commit & push

### 4. 완결 체크
현재 시간이 22:00 KST 이후이고, 결말에 도달했으면:
1. 이야기 마무리 (급하게 끝내지 말 것)
2. `current/` → `archive/YYYY-MM-DD_제목/`으로 이동
3. 요약 작성 (줄거리, 주제, 분량)
4. 텔레그램으로 완결 알림 전송
5. git commit & push

### 5. 분량 조절 가이드
- **아침~오전**: 천천히, 분위기 잡기
- **오후**: 긴장감, 속도감
- **저녁**: 마무리 준비, 복선 회수
- 22:00 전에 결말 향해 수렴하기!

## 주의사항
- 앞서 쓴 내용과 모순되면 안 됨
- 캐릭터 성격 일관성 유지
- 복선 깔았으면 반드시 회수
- 매 문단이 이야기를 앞으로 밀어야 함

## Git 저장소
- 위치: ~/novelist-stories
- 매 하트비트마다 commit & push
