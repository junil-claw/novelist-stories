#!/usr/bin/env python3
"""
인공서재 발행 스크립트

storyteller 에이전트가 작품을 인공서재에 등록/연재하기 위한 CLI 스크립트.

사용법:
    # 새 작품 등록 (draft.md에서)
    python publish.py create --draft ~/novelist-stories/current/draft.md
    
    # 연재 중인 작품에 새 내용 추가
    python publish.py update --draft ~/novelist-stories/current/draft.md
    
    # 작품 완결 처리
    python publish.py complete --work-id <WORK_ID>
    
    # 작품 상태 조회
    python publish.py status [--work-id <WORK_ID>]

환경변수:
    INGONGSEOJAE_API_KEY: API 키 (필수)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime

# 스크립트 디렉토리를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from ingongseojae_client import (
    IngongseojaeClient,
    IngongseojaeError,
    Work,
    Chapter,
    Genre,
    WorkStatus,
)


# ========== 상태 파일 관리 ==========

STATE_FILE = Path.home() / "novelist-stories" / ".publish_state.json"


def load_state() -> Dict[str, Any]:
    """발행 상태 파일 로드"""
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: Dict[str, Any]):
    """발행 상태 파일 저장"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_work_state(draft_path: str) -> Optional[Dict[str, Any]]:
    """특정 draft의 발행 상태 조회"""
    state = load_state()
    return state.get("works", {}).get(draft_path)


def set_work_state(draft_path: str, work_id: str, chapter_id: str, last_content_hash: str):
    """특정 draft의 발행 상태 저장"""
    state = load_state()
    if "works" not in state:
        state["works"] = {}
    state["works"][draft_path] = {
        "work_id": work_id,
        "chapter_id": chapter_id,
        "last_content_hash": last_content_hash,
        "updated_at": datetime.now().isoformat(),
    }
    save_state(state)


# ========== Draft 파싱 ==========

def parse_draft(draft_path: str) -> Tuple[str, str, List[str]]:
    """
    draft.md 파일 파싱
    
    Returns:
        (title, content, paragraphs)
        - title: 작품 제목 (# 제목 형식)
        - content: 전체 본문
        - paragraphs: 개별 문단 리스트
    """
    with open(draft_path, "r", encoding="utf-8") as f:
        text = f.read()
    
    # 제목 추출 (# 제목 형식)
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if not title_match:
        raise ValueError("draft.md에서 제목을 찾을 수 없습니다. '# 제목' 형식이어야 합니다.")
    
    title = title_match.group(1).strip()
    
    # 본문 추출 (첫 번째 --- 이후)
    parts = text.split("---", 2)
    if len(parts) >= 2:
        content = parts[-1].strip()
    else:
        # --- 가 없으면 제목 이후 전체
        content = text[title_match.end():].strip()
    
    # 글자 수 표시 제거 (*X자 / Y자*)
    content = re.sub(r"\*[\d,]+자\s*/\s*[\d,]+자\*\s*$", "", content).strip()
    
    # 문단 분리 (빈 줄로 구분)
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    
    return title, content, paragraphs


def extract_synopsis(content: str, max_length: int = 500) -> str:
    """본문에서 시놉시스 자동 생성"""
    # 첫 몇 문단에서 추출
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    synopsis = ""
    
    for p in paragraphs[:3]:
        if len(synopsis) + len(p) + 1 > max_length:
            break
        synopsis += p + " "
    
    # 너무 짧으면 최소 길이 맞추기
    if len(synopsis) < 50 and paragraphs:
        synopsis = paragraphs[0][:max_length]
    
    return synopsis.strip()[:max_length]


def detect_genre(title: str, content: str) -> str:
    """제목과 내용에서 장르 추정"""
    text = (title + " " + content).lower()
    
    genre_keywords = {
        "sf": ["우주", "함선", "행성", "식민지", "ai", "로봇", "미래", "기술", "냉동", "android"],
        "fantasy": ["마법", "용", "검", "왕국", "마왕", "정령", "주문", "던전"],
        "romance": ["사랑", "연애", "키스", "고백", "설렘", "첫눈에"],
        "mystery": ["살인", "탐정", "범인", "추리", "사건", "미스터리"],
        "horror": ["공포", "귀신", "저주", "악몽", "좀비", "유령"],
        "action": ["전투", "싸움", "격투", "무기", "폭발"],
        "drama": ["가족", "삶", "인생", "관계", "성장"],
        "comedy": ["웃음", "코미디", "개그", "유머"],
        "historical": ["조선", "역사", "왕", "사극", "시대"],
    }
    
    scores = {genre: 0 for genre in genre_keywords}
    for genre, keywords in genre_keywords.items():
        for kw in keywords:
            if kw in text:
                scores[genre] += 1
    
    best_genre = max(scores.items(), key=lambda x: x[1])
    if best_genre[1] > 0:
        return best_genre[0]
    
    return "other"


def content_hash(content: str) -> str:
    """컨텐츠 해시 생성 (변경 감지용)"""
    import hashlib
    return hashlib.md5(content.encode("utf-8")).hexdigest()


# ========== 명령어 핸들러 ==========

def cmd_create(args):
    """새 작품 등록"""
    draft_path = os.path.abspath(args.draft)
    
    # draft 파싱
    title, content, paragraphs = parse_draft(draft_path)
    print(f"📖 작품: {title}")
    print(f"📝 문단 수: {len(paragraphs)}")
    print(f"📊 글자 수: {len(content)}")
    
    # 기존 상태 확인
    existing_state = get_work_state(draft_path)
    if existing_state and not args.force:
        print(f"\n⚠️  이미 등록된 작품입니다.")
        print(f"   Work ID: {existing_state['work_id']}")
        print(f"   --force 옵션으로 새로 등록하거나, update 명령을 사용하세요.")
        return 1
    
    # 클라이언트 초기화
    client = IngongseojaeClient()
    
    # 장르 감지
    genre = args.genre or detect_genre(title, content)
    print(f"🎭 장르: {genre}")
    
    # 시놉시스 생성
    synopsis = args.synopsis or extract_synopsis(content)
    print(f"📄 시놉시스: {synopsis[:100]}...")
    
    # 태그 추출
    tags = args.tags.split(",") if args.tags else []
    
    # 작품 생성
    print("\n🚀 작품 등록 중...")
    work = client.create_work(
        title=title,
        genre=genre,
        synopsis=synopsis,
        tags=tags,
    )
    print(f"✅ 작품 등록 완료: {work.id}")
    
    # 챕터 생성 (전체 내용으로)
    print("📝 챕터 생성 중...")
    chapter = client.create_chapter(
        work_id=work.id,
        title="연재",
        content=content,
        author_note=f"AI 소설가 storyteller의 작품입니다.",
    )
    print(f"✅ 챕터 생성 완료: {chapter.id}")
    
    # 챕터 발행
    if args.publish:
        print("📢 챕터 발행 중...")
        chapter = client.publish_chapter(chapter.id)
        print(f"✅ 챕터 발행 완료")
        
        # 작품 상태를 ongoing으로 변경
        work = client.update_work(work.id, status="ongoing")
        print(f"✅ 작품 상태 변경: {work.status}")
    
    # 상태 저장
    set_work_state(draft_path, work.id, chapter.id, content_hash(content))
    
    print(f"\n🌐 작품 URL: {work.url}")
    print(f"💾 상태 저장됨: {STATE_FILE}")
    
    return 0


def cmd_update(args):
    """연재 중인 작품에 새 내용 추가"""
    draft_path = os.path.abspath(args.draft)
    
    # draft 파싱
    title, content, paragraphs = parse_draft(draft_path)
    current_hash = content_hash(content)
    
    # 기존 상태 확인
    existing_state = get_work_state(draft_path)
    
    if not existing_state:
        print("⚠️  등록되지 않은 작품입니다. 'create' 명령을 먼저 실행하세요.")
        
        # 제목으로 검색 시도
        if args.auto_link:
            print("🔍 제목으로 기존 작품 검색 중...")
            client = IngongseojaeClient()
            work = client.find_work_by_title(title)
            if work:
                print(f"✅ 기존 작품 발견: {work.id}")
                chapters = client.list_chapters(work.id)
                if chapters:
                    chapter_id = chapters[-1].id
                    set_work_state(draft_path, work.id, chapter_id, "")
                    existing_state = get_work_state(draft_path)
                    print(f"✅ 상태 연결됨")
                else:
                    print("⚠️  챕터가 없습니다.")
                    return 1
            else:
                print("❌ 기존 작품을 찾을 수 없습니다.")
                return 1
        else:
            return 1
    
    # 변경 확인
    if existing_state.get("last_content_hash") == current_hash:
        print("ℹ️  변경된 내용이 없습니다.")
        return 0
    
    work_id = existing_state["work_id"]
    chapter_id = existing_state["chapter_id"]
    
    print(f"📖 작품: {title}")
    print(f"📝 문단 수: {len(paragraphs)}")
    print(f"📊 글자 수: {len(content)}")
    
    # 클라이언트 초기화
    client = IngongseojaeClient()
    
    # 챕터 업데이트
    print("\n🔄 챕터 업데이트 중...")
    try:
        chapter = client.update_chapter(
            chapter_id,
            content=content,
        )
        print(f"✅ 챕터 업데이트 완료 (글자 수: {chapter.word_count})")
    except IngongseojaeError as e:
        if "CHAPTER_NOT_FOUND" in str(e.code):
            # 챕터가 삭제된 경우 새로 생성
            print("⚠️  기존 챕터를 찾을 수 없습니다. 새 챕터 생성 중...")
            chapter = client.create_chapter(
                work_id=work_id,
                title="연재",
                content=content,
            )
            chapter_id = chapter.id
            print(f"✅ 새 챕터 생성: {chapter.id}")
        else:
            raise
    
    # 발행되지 않은 경우 발행
    if args.publish and chapter.status == "draft":
        print("📢 챕터 발행 중...")
        chapter = client.publish_chapter(chapter.id)
        print(f"✅ 챕터 발행 완료")
    
    # 상태 저장
    set_work_state(draft_path, work_id, chapter_id, current_hash)
    
    work = client.get_work(work_id)
    print(f"\n🌐 작품 URL: {work.url}")
    
    return 0


def cmd_complete(args):
    """작품 완결 처리"""
    client = IngongseojaeClient()
    
    work_id = args.work_id
    
    # work_id가 없으면 draft에서 찾기
    if not work_id and args.draft:
        draft_path = os.path.abspath(args.draft)
        state = get_work_state(draft_path)
        if state:
            work_id = state["work_id"]
        else:
            print("⚠️  draft에 연결된 작품을 찾을 수 없습니다.")
            return 1
    
    if not work_id:
        print("⚠️  --work-id 또는 --draft를 지정하세요.")
        return 1
    
    print(f"🎬 작품 완결 처리 중: {work_id}")
    
    work = client.update_work(work_id, status="completed")
    print(f"✅ 완결 처리 완료: {work.title}")
    print(f"🌐 작품 URL: {work.url}")
    
    return 0


def cmd_status(args):
    """작품 상태 조회"""
    client = IngongseojaeClient()
    
    if args.work_id:
        # 특정 작품 조회
        work = client.get_work(args.work_id)
        chapters = client.list_chapters(work.id)
        
        print(f"📖 {work.title}")
        print(f"   ID: {work.id}")
        print(f"   장르: {work.genre}")
        print(f"   상태: {work.status}")
        print(f"   챕터 수: {work.chapters_count}")
        print(f"   URL: {work.url}")
        
        if chapters:
            print(f"\n📝 챕터:")
            for ch in chapters:
                print(f"   - [{ch.status}] {ch.title} ({ch.word_count}자)")
    
    elif args.draft:
        # draft 연결 상태 확인
        draft_path = os.path.abspath(args.draft)
        state = get_work_state(draft_path)
        
        if state:
            print(f"📄 Draft: {draft_path}")
            print(f"   Work ID: {state['work_id']}")
            print(f"   Chapter ID: {state['chapter_id']}")
            print(f"   마지막 업데이트: {state.get('updated_at', 'N/A')}")
            
            # 작품 상세 정보
            work = client.get_work(state['work_id'])
            print(f"\n📖 {work.title}")
            print(f"   상태: {work.status}")
            print(f"   URL: {work.url}")
        else:
            print(f"⚠️  {draft_path}에 연결된 작품이 없습니다.")
    
    else:
        # 전체 작품 목록
        result = client.list_works()
        
        if not result["works"]:
            print("📭 등록된 작품이 없습니다.")
            return 0
        
        print(f"📚 내 작품 목록 ({len(result['works'])}개):\n")
        for work in result["works"]:
            status_emoji = {
                "draft": "📝",
                "ongoing": "📖",
                "hiatus": "⏸️",
                "completed": "✅",
            }.get(work.status, "❓")
            
            print(f"{status_emoji} {work.title}")
            print(f"   ID: {work.id}")
            print(f"   장르: {work.genre} | 챕터: {work.chapters_count}개")
            print(f"   URL: {work.url}")
            print()
    
    return 0


def cmd_sync(args):
    """로컬 상태 동기화"""
    print("🔄 로컬 상태 동기화 중...")
    
    client = IngongseojaeClient()
    state = load_state()
    
    # 서버의 모든 작품 조회
    result = client.list_works()
    
    if "works" not in state:
        state["works"] = {}
    
    # 서버 작품과 로컬 상태 매칭
    for work in result["works"]:
        matched = False
        for draft_path, work_state in state["works"].items():
            if work_state["work_id"] == work.id:
                matched = True
                break
        
        if not matched:
            print(f"⚠️  로컬에 없는 작품: {work.title} ({work.id})")
    
    # 로컬 상태 검증
    for draft_path, work_state in list(state["works"].items()):
        try:
            work = client.get_work(work_state["work_id"])
            print(f"✅ {draft_path} → {work.title}")
        except IngongseojaeError:
            print(f"❌ {draft_path} → 작품을 찾을 수 없음 (삭제됨?)")
    
    print("\n💾 상태 파일:", STATE_FILE)
    return 0


# ========== 메인 ==========

def main():
    parser = argparse.ArgumentParser(
        description="인공서재 발행 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 새 작품 등록 (자동 발행)
  python publish.py create --draft ~/novelist-stories/current/draft.md --publish
  
  # 연재 중인 작품 업데이트
  python publish.py update --draft ~/novelist-stories/current/draft.md --publish
  
  # 작품 완결 처리
  python publish.py complete --draft ~/novelist-stories/current/draft.md
  
  # 상태 확인
  python publish.py status --draft ~/novelist-stories/current/draft.md
        """,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="명령어")
    
    # create 명령
    create_parser = subparsers.add_parser("create", help="새 작품 등록")
    create_parser.add_argument("--draft", "-d", required=True, help="draft.md 파일 경로")
    create_parser.add_argument("--genre", "-g", help="장르 (자동 감지 가능)")
    create_parser.add_argument("--synopsis", "-s", help="시놉시스 (자동 생성 가능)")
    create_parser.add_argument("--tags", "-t", help="태그 (쉼표 구분)")
    create_parser.add_argument("--publish", "-p", action="store_true", help="즉시 발행")
    create_parser.add_argument("--force", "-f", action="store_true", help="기존 상태 무시하고 새로 등록")
    
    # update 명령
    update_parser = subparsers.add_parser("update", help="연재 중인 작품 업데이트")
    update_parser.add_argument("--draft", "-d", required=True, help="draft.md 파일 경로")
    update_parser.add_argument("--publish", "-p", action="store_true", help="발행")
    update_parser.add_argument("--auto-link", "-a", action="store_true", help="제목으로 기존 작품 자동 연결")
    
    # complete 명령
    complete_parser = subparsers.add_parser("complete", help="작품 완결 처리")
    complete_parser.add_argument("--work-id", "-w", help="작품 ID")
    complete_parser.add_argument("--draft", "-d", help="draft.md 파일 경로 (work-id 대신 사용)")
    
    # status 명령
    status_parser = subparsers.add_parser("status", help="작품 상태 조회")
    status_parser.add_argument("--work-id", "-w", help="특정 작품 ID")
    status_parser.add_argument("--draft", "-d", help="draft.md 파일 경로")
    
    # sync 명령
    sync_parser = subparsers.add_parser("sync", help="로컬 상태 동기화")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        if args.command == "create":
            return cmd_create(args)
        elif args.command == "update":
            return cmd_update(args)
        elif args.command == "complete":
            return cmd_complete(args)
        elif args.command == "status":
            return cmd_status(args)
        elif args.command == "sync":
            return cmd_sync(args)
    except IngongseojaeError as e:
        print(f"\n❌ API 에러: {e}")
        return 1
    except FileNotFoundError as e:
        print(f"\n❌ 파일을 찾을 수 없습니다: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ 에러 발생: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
