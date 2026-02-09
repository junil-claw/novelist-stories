# TOOLS.md - Local Notes

## 인공서재 발행 (신규 2026-02-09)

작품을 인공서재(https://ingongseojae.vercel.app)에 자동 발행.

### 환경변수
```bash
export INGONGSEOJAE_API_KEY="igj_v1_your_key_here"
```

### 스크립트 위치
`~/novelist-stories/scripts/`

### 빠른 사용법

```bash
# 간편 래퍼
~/novelist-stories/scripts/publish create    # 새 작품 등록
~/novelist-stories/scripts/publish update    # 내용 업데이트
~/novelist-stories/scripts/publish complete  # 완결 처리
~/novelist-stories/scripts/publish status    # 상태 확인

# 또는 Python 직접 호출
python ~/novelist-stories/scripts/publish.py create --draft ~/novelist-stories/current/draft.md --publish
```

### Python 모듈로 사용

```python
from storyteller_publish import publish_current, complete_current, get_status

# 현재 draft.md 발행/업데이트
result = publish_current()
print(result['url'])  # https://ingongseojae.vercel.app/works/...

# 완결 처리
complete_current()
```

### 연재 워크플로우

1. **작품 시작**: `publish create` → 새 작품 등록 + 발행
2. **연재 중 (30분마다)**: `publish update` → 변경 있으면 자동 업데이트
3. **완결 시**: `publish complete` → 상태를 "completed"로 변경

### 상태 파일
- `~/.publish_state.json` - 발행 상태 (work_id, chapter_id 매핑)
- `~/.publish_log.jsonl` - 발행 로그

### 자세한 문서
`~/novelist-stories/scripts/README.md`

---

## 기타 도구

Skills define _how_ tools work. This file is for _your_ specifics.

Add whatever helps you do your job. This is your cheat sheet.
