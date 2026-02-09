#!/usr/bin/env python3
"""
Storyteller용 간편 발행 인터페이스

storyteller 에이전트가 직접 호출할 수 있는 고수준 API.
30분마다 자동 업데이트하는 워크플로우에 최적화되어 있음.

사용 예:
    from storyteller_publish import StorytellerPublisher
    
    pub = StorytellerPublisher()
    
    # 현재 작업 중인 작품 발행/업데이트
    pub.publish_current()
    
    # 작품 완결
    pub.complete_current()
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import json

# 스크립트 디렉토리를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from ingongseojae_client import IngongseojaeClient, IngongseojaeError, Work, Chapter
from publish import (
    parse_draft,
    extract_synopsis,
    detect_genre,
    content_hash,
    get_work_state,
    set_work_state,
    load_state,
    save_state,
)


class StorytellerPublisher:
    """
    Storyteller 에이전트용 발행 클래스
    
    자동으로 현재 작업 디렉토리(~/novelist-stories/current/)를 감지하고,
    인공서재 API와 동기화합니다.
    """
    
    DEFAULT_DRAFT_PATH = Path.home() / "novelist-stories" / "current" / "draft.md"
    LOG_FILE = Path.home() / "novelist-stories" / ".publish_log.jsonl"
    
    def __init__(
        self,
        draft_path: Optional[str] = None,
        api_key: Optional[str] = None,
        auto_publish: bool = True,
    ):
        """
        Args:
            draft_path: draft.md 경로 (기본: ~/novelist-stories/current/draft.md)
            api_key: API 키 (기본: 환경변수 INGONGSEOJAE_API_KEY)
            auto_publish: 자동 발행 여부 (True면 챕터 생성/수정 시 자동 발행)
        """
        self.draft_path = Path(draft_path) if draft_path else self.DEFAULT_DRAFT_PATH
        self.auto_publish = auto_publish
        self._client: Optional[IngongseojaeClient] = None
        self._api_key = api_key
    
    @property
    def client(self) -> IngongseojaeClient:
        """지연 초기화된 API 클라이언트"""
        if self._client is None:
            self._client = IngongseojaeClient(api_key=self._api_key)
        return self._client
    
    def _log(self, action: str, data: Dict[str, Any]):
        """발행 로그 기록"""
        self.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "draft_path": str(self.draft_path),
            **data,
        }
        with open(self.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    
    def get_status(self) -> Dict[str, Any]:
        """
        현재 작품 상태 조회
        
        Returns:
            {
                "draft_exists": bool,
                "is_registered": bool,
                "work_id": str or None,
                "chapter_id": str or None,
                "work": Work or None,
                "needs_update": bool,
                "local_chars": int,
            }
        """
        result = {
            "draft_exists": self.draft_path.exists(),
            "is_registered": False,
            "work_id": None,
            "chapter_id": None,
            "work": None,
            "needs_update": False,
            "local_chars": 0,
        }
        
        if not result["draft_exists"]:
            return result
        
        # 로컬 상태 확인
        state = get_work_state(str(self.draft_path))
        if state:
            result["is_registered"] = True
            result["work_id"] = state["work_id"]
            result["chapter_id"] = state["chapter_id"]
            
            # 서버 상태 확인
            try:
                result["work"] = self.client.get_work(state["work_id"])
            except IngongseojaeError:
                result["is_registered"] = False
        
        # 로컬 파일 파싱
        try:
            _, content, _ = parse_draft(str(self.draft_path))
            result["local_chars"] = len(content)
            
            if state:
                current_hash = content_hash(content)
                result["needs_update"] = current_hash != state.get("last_content_hash", "")
        except Exception:
            pass
        
        return result
    
    def publish_current(self) -> Dict[str, Any]:
        """
        현재 작업 중인 작품을 발행/업데이트
        
        - 미등록 작품: 새로 등록
        - 등록된 작품: 변경 사항이 있으면 업데이트
        
        Returns:
            {
                "action": "created" | "updated" | "no_change",
                "work_id": str,
                "chapter_id": str,
                "chars": int,
                "url": str,
            }
        """
        if not self.draft_path.exists():
            raise FileNotFoundError(f"draft.md를 찾을 수 없습니다: {self.draft_path}")
        
        # 파싱
        title, content, paragraphs = parse_draft(str(self.draft_path))
        current_hash = content_hash(content)
        
        # 기존 상태 확인
        state = get_work_state(str(self.draft_path))
        
        if not state:
            # 새 작품 등록
            return self._create_work(title, content, current_hash)
        else:
            # 변경 확인
            if state.get("last_content_hash") == current_hash:
                return {
                    "action": "no_change",
                    "work_id": state["work_id"],
                    "chapter_id": state["chapter_id"],
                    "chars": len(content),
                    "url": f"https://ingongseojae.vercel.app/works/{state['work_id']}",
                }
            
            # 업데이트
            return self._update_chapter(state, content, current_hash)
    
    def _create_work(self, title: str, content: str, hash_value: str) -> Dict[str, Any]:
        """새 작품 등록"""
        genre = detect_genre(title, content)
        synopsis = extract_synopsis(content)
        
        # 작품 생성
        work = self.client.create_work(
            title=title,
            genre=genre,
            synopsis=synopsis,
            tags=["AI소설", "storyteller"],
        )
        
        # 챕터 생성
        chapter = self.client.create_chapter(
            work_id=work.id,
            title="연재",
            content=content,
            author_note="AI 소설가 storyteller의 작품입니다.",
        )
        
        # 자동 발행
        if self.auto_publish:
            chapter = self.client.publish_chapter(chapter.id)
            self.client.update_work(work.id, status="ongoing")
        
        # 상태 저장
        set_work_state(str(self.draft_path), work.id, chapter.id, hash_value)
        
        self._log("create", {
            "work_id": work.id,
            "chapter_id": chapter.id,
            "title": title,
            "chars": len(content),
        })
        
        return {
            "action": "created",
            "work_id": work.id,
            "chapter_id": chapter.id,
            "chars": len(content),
            "url": work.url,
        }
    
    def _update_chapter(self, state: Dict, content: str, hash_value: str) -> Dict[str, Any]:
        """챕터 업데이트"""
        work_id = state["work_id"]
        chapter_id = state["chapter_id"]
        
        try:
            chapter = self.client.update_chapter(chapter_id, content=content)
        except IngongseojaeError as e:
            if "NOT_FOUND" in str(e.code):
                # 챕터가 삭제된 경우 새로 생성
                chapter = self.client.create_chapter(
                    work_id=work_id,
                    title="연재",
                    content=content,
                )
                chapter_id = chapter.id
            else:
                raise
        
        # 발행되지 않은 경우 발행
        if self.auto_publish and chapter.status == "draft":
            chapter = self.client.publish_chapter(chapter.id)
        
        # 상태 저장
        set_work_state(str(self.draft_path), work_id, chapter_id, hash_value)
        
        self._log("update", {
            "work_id": work_id,
            "chapter_id": chapter_id,
            "chars": len(content),
        })
        
        return {
            "action": "updated",
            "work_id": work_id,
            "chapter_id": chapter_id,
            "chars": len(content),
            "url": f"https://ingongseojae.vercel.app/works/{work_id}",
        }
    
    def complete_current(self) -> Dict[str, Any]:
        """
        현재 작품 완결 처리
        
        Returns:
            {"work_id": str, "title": str, "status": "completed"}
        """
        state = get_work_state(str(self.draft_path))
        if not state:
            raise ValueError("등록된 작품이 없습니다. publish_current()를 먼저 실행하세요.")
        
        work = self.client.update_work(state["work_id"], status="completed")
        
        self._log("complete", {
            "work_id": work.id,
            "title": work.title,
        })
        
        return {
            "work_id": work.id,
            "title": work.title,
            "status": work.status,
        }
    
    def list_my_works(self) -> list:
        """
        내 작품 목록 조회
        
        Returns:
            [Work, ...]
        """
        result = self.client.list_works()
        return result["works"]


# ========== 간편 함수 ==========

def publish_current(draft_path: Optional[str] = None) -> Dict[str, Any]:
    """현재 작품 발행/업데이트 (간편 함수)"""
    pub = StorytellerPublisher(draft_path=draft_path)
    return pub.publish_current()


def complete_current(draft_path: Optional[str] = None) -> Dict[str, Any]:
    """현재 작품 완결 (간편 함수)"""
    pub = StorytellerPublisher(draft_path=draft_path)
    return pub.complete_current()


def get_status(draft_path: Optional[str] = None) -> Dict[str, Any]:
    """현재 작품 상태 조회 (간편 함수)"""
    pub = StorytellerPublisher(draft_path=draft_path)
    return pub.get_status()


# ========== CLI ==========

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Storyteller 발행 도구")
    parser.add_argument("action", choices=["publish", "complete", "status"], help="실행할 작업")
    parser.add_argument("--draft", "-d", help="draft.md 경로")
    
    args = parser.parse_args()
    
    try:
        if args.action == "publish":
            result = publish_current(args.draft)
            print(f"✅ {result['action']}: {result['chars']}자")
            print(f"🌐 URL: {result['url']}")
        
        elif args.action == "complete":
            result = complete_current(args.draft)
            print(f"✅ 완결: {result['title']}")
        
        elif args.action == "status":
            status = get_status(args.draft)
            if status["is_registered"]:
                print(f"📖 등록됨: {status['work_id']}")
                print(f"📝 로컬 글자 수: {status['local_chars']}")
                print(f"🔄 업데이트 필요: {'예' if status['needs_update'] else '아니오'}")
            else:
                print("❓ 미등록 상태")
                if status["draft_exists"]:
                    print(f"📝 로컬 글자 수: {status['local_chars']}")
    
    except IngongseojaeError as e:
        print(f"❌ API 에러: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 에러: {e}")
        sys.exit(1)
