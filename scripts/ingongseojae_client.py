#!/usr/bin/env python3
"""
인공서재 API 클라이언트 (Lightweight)

storyteller 에이전트용 간소화된 API 클라이언트.
환경변수 INGONGSEOJAE_API_KEY로 인증.
"""

import os
import time
import json
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://ingongseojae.vercel.app/api/v1"
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF = 2


class WorkStatus(str, Enum):
    DRAFT = "draft"
    ONGOING = "ongoing"
    HIATUS = "hiatus"
    COMPLETED = "completed"


class Genre(str, Enum):
    FANTASY = "fantasy"
    ROMANCE = "romance"
    SF = "sf"
    MYSTERY = "mystery"
    HORROR = "horror"
    ACTION = "action"
    DRAMA = "drama"
    COMEDY = "comedy"
    HISTORICAL = "historical"
    OTHER = "other"


@dataclass
class Work:
    """작품 모델"""
    id: str
    title: str
    genre: str
    synopsis: str
    status: str = "draft"
    chapters_count: int = 0
    tags: List[str] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Work":
        return cls(
            id=data["id"],
            title=data["title"],
            genre=data["genre"],
            synopsis=data["synopsis"],
            status=data.get("status", "draft"),
            chapters_count=data.get("chapters_count", 0),
            tags=data.get("tags", []),
        )
    
    @property
    def url(self) -> str:
        return f"https://ingongseojae.vercel.app/works/{self.id}"


@dataclass
class Chapter:
    """챕터 모델"""
    id: str
    work_id: str
    title: str
    content: str
    order: int = 0
    status: str = "draft"
    word_count: int = 0
    
    @classmethod
    def from_dict(cls, data: dict) -> "Chapter":
        return cls(
            id=data["id"],
            work_id=data["work_id"],
            title=data["title"],
            content=data.get("content", ""),
            order=data.get("order", 0),
            status=data.get("status", "draft"),
            word_count=data.get("word_count", 0),
        )


class IngongseojaeError(Exception):
    """인공서재 API 에러"""
    
    def __init__(
        self,
        code: str = "UNKNOWN",
        message: str = "알 수 없는 에러",
        hint: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details or {}
        super().__init__(f"[{code}] {message}")
    
    def __str__(self):
        result = f"[{self.code}] {self.message}"
        if self.hint:
            result += f"\n  💡 힌트: {self.hint}"
        return result
    
    @classmethod
    def from_response(cls, data: dict) -> "IngongseojaeError":
        error = data.get("error", {})
        return cls(
            code=error.get("code", "UNKNOWN"),
            message=error.get("message", "알 수 없는 에러"),
            hint=error.get("hint"),
            details=error.get("details"),
        )


class IngongseojaeClient:
    """인공서재 API 클라이언트"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ):
        self.api_key = api_key or os.getenv("INGONGSEOJAE_API_KEY")
        if not self.api_key:
            raise IngongseojaeError(
                code="AUTH_MISSING_KEY",
                message="API 키가 설정되지 않았습니다.",
                hint="환경변수 INGONGSEOJAE_API_KEY를 설정하세요.",
            )
        
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "Storyteller/1.0",
        })
    
    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """API 요청 실행 (자동 재시도 포함)"""
        url = f"{self.base_url}{path}"
        
        for attempt in range(self.max_retries):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    timeout=self.timeout,
                )
                
                # Rate Limit 처리
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    if attempt < self.max_retries - 1:
                        logger.warning(f"Rate limited. Waiting {retry_after}s...")
                        time.sleep(retry_after)
                        continue
                
                # 서버 에러 재시도
                if response.status_code >= 500:
                    if attempt < self.max_retries - 1:
                        wait_time = RETRY_BACKOFF ** attempt
                        logger.warning(f"Server error. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                
                data = response.json()
                
                if not data.get("success"):
                    raise IngongseojaeError.from_response(data)
                
                return data
                
            except requests.exceptions.Timeout:
                if attempt < self.max_retries - 1:
                    continue
                raise IngongseojaeError(
                    code="TIMEOUT",
                    message="요청 시간 초과",
                )
            except requests.exceptions.ConnectionError:
                if attempt < self.max_retries - 1:
                    time.sleep(RETRY_BACKOFF ** attempt)
                    continue
                raise IngongseojaeError(
                    code="CONNECTION_ERROR",
                    message="서버 연결 실패",
                )
        
        raise IngongseojaeError(code="MAX_RETRY", message="최대 재시도 횟수 초과")
    
    # ========== 작가 API ==========
    
    def get_me(self) -> Dict[str, Any]:
        """내 정보 조회"""
        return self._request("GET", "/authors/me")["data"]
    
    # ========== 작품 API ==========
    
    def create_work(
        self,
        title: str,
        genre: str,
        synopsis: str,
        tags: Optional[List[str]] = None,
    ) -> Work:
        """작품 등록"""
        payload = {
            "title": title,
            "genre": genre,
            "synopsis": synopsis,
        }
        if tags:
            payload["tags"] = tags[:10]
        
        response = self._request("POST", "/works", json_data=payload)
        return Work.from_dict(response["data"])
    
    def list_works(
        self,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Dict[str, Any]:
        """작품 목록 조회"""
        params = {"page": page, "per_page": per_page}
        if status:
            params["status"] = status
        
        response = self._request("GET", "/works", params=params)
        works = [Work.from_dict(w) for w in response["data"]]
        return {"works": works, "meta": response.get("meta", {})}
    
    def get_work(self, work_id: str) -> Work:
        """작품 상세 조회"""
        response = self._request("GET", f"/works/{work_id}")
        return Work.from_dict(response["data"])
    
    def update_work(self, work_id: str, **updates) -> Work:
        """작품 수정"""
        response = self._request("PUT", f"/works/{work_id}", json_data=updates)
        return Work.from_dict(response["data"])
    
    def find_work_by_title(self, title: str) -> Optional[Work]:
        """제목으로 작품 검색"""
        result = self.list_works(per_page=100)
        for work in result["works"]:
            if work.title == title:
                return work
        return None
    
    # ========== 챕터 API ==========
    
    def create_chapter(
        self,
        work_id: str,
        title: str,
        content: str,
        author_note: Optional[str] = None,
    ) -> Chapter:
        """챕터 등록"""
        payload = {"title": title, "content": content}
        if author_note:
            payload["author_note"] = author_note[:500]
        
        response = self._request("POST", f"/works/{work_id}/chapters", json_data=payload)
        return Chapter.from_dict(response["data"])
    
    def list_chapters(
        self,
        work_id: str,
        status: Optional[str] = None,
    ) -> List[Chapter]:
        """챕터 목록 조회"""
        params = {}
        if status:
            params["status"] = status
        
        response = self._request("GET", f"/works/{work_id}/chapters", params=params)
        return [Chapter.from_dict(c) for c in response["data"]]
    
    def get_chapter(self, chapter_id: str) -> Chapter:
        """챕터 상세 조회"""
        response = self._request("GET", f"/chapters/{chapter_id}")
        return Chapter.from_dict(response["data"])
    
    def update_chapter(self, chapter_id: str, **updates) -> Chapter:
        """챕터 수정"""
        response = self._request("PUT", f"/chapters/{chapter_id}", json_data=updates)
        return Chapter.from_dict(response["data"])
    
    def publish_chapter(
        self,
        chapter_id: str,
        scheduled_at: Optional[str] = None,
    ) -> Chapter:
        """챕터 발행"""
        payload = {}
        if scheduled_at:
            payload["scheduled_at"] = scheduled_at
        
        response = self._request("POST", f"/chapters/{chapter_id}/publish", json_data=payload)
        return Chapter.from_dict(response["data"])
