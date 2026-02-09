#!/usr/bin/env python3
"""
아카이브 작품을 인공서재에 동기화하는 스크립트
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ingongseojae_client import IngongseojaeClient, IngongseojaeError

ARCHIVE_DIR = Path.home() / "novelist-stories" / "archive"

def get_archived_works():
    """아카이브된 작품 목록 반환"""
    works = []
    for item in sorted(ARCHIVE_DIR.iterdir()):
        if item.is_dir():
            draft = item / "draft.md"
            if draft.exists():
                works.append({
                    "path": item,
                    "draft": draft,
                    "name": item.name
                })
    return works

def parse_draft(draft_path):
    """draft.md 파싱"""
    import re
    with open(draft_path, "r", encoding="utf-8") as f:
        text = f.read()
    
    # 제목 추출
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if not title_match:
        return None, None
    
    title = title_match.group(1).strip()
    
    # 본문 추출
    parts = text.split("---", 2)
    if len(parts) >= 2:
        content = parts[-1].strip()
    else:
        content = text[title_match.end():].strip()
    
    # 글자 수 표시 제거
    content = re.sub(r"\*[\d,]+자\s*/\s*[\d,]+자\*\s*$", "", content).strip()
    
    return title, content

def detect_genre(title, content):
    """장르 감지"""
    text = (title + " " + content).lower()
    
    genre_keywords = {
        "sf": ["우주", "함선", "행성", "식민지", "ai", "로봇", "미래", "기술", "냉동", "android", "2187", "2347"],
        "fantasy": ["마법", "용", "검", "왕국", "마왕", "정령", "주문", "던전"],
        "romance": ["사랑", "연애", "키스", "고백", "설렘", "첫눈에"],
        "mystery": ["살인", "탐정", "범인", "추리", "사건", "미스터리"],
        "drama": ["가족", "삶", "인생", "관계", "성장"],
    }
    
    scores = {genre: 0 for genre in genre_keywords}
    for genre, keywords in genre_keywords.items():
        for kw in keywords:
            if kw in text:
                scores[genre] += 1
    
    best_genre = max(scores.items(), key=lambda x: x[1])
    if best_genre[1] > 0:
        return best_genre[0]
    return "sf"

def extract_synopsis(content, max_length=300):
    """시놉시스 추출"""
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    synopsis = ""
    for p in paragraphs[:2]:
        if len(synopsis) + len(p) + 1 > max_length:
            break
        synopsis += p + " "
    return synopsis.strip()[:max_length]

def main():
    client = IngongseojaeClient()
    
    # 기존 작품 조회
    print("📚 기존 작품 조회 중...")
    result = client.list_works()
    existing_titles = {w.title: w for w in result["works"]}
    print(f"   등록된 작품: {len(existing_titles)}개")
    
    # 아카이브 작품 목록
    archives = get_archived_works()
    print(f"\n📂 아카이브 작품: {len(archives)}개")
    
    for archive in archives:
        title, content = parse_draft(archive["draft"])
        if not title:
            print(f"   ⚠️  {archive['name']}: 제목 파싱 실패")
            continue
        
        char_count = len(content)
        print(f"\n{'='*50}")
        print(f"📖 {title}")
        print(f"   경로: {archive['name']}")
        print(f"   글자 수: {char_count:,}자")
        
        if title in existing_titles:
            work = existing_titles[title]
            print(f"   ✅ 이미 등록됨 (ID: {work.id})")
            
            # 챕터 확인
            if work.chapters_count == 0:
                print(f"   📝 챕터 추가 중...")
                try:
                    chapter = client.create_chapter(
                        work_id=work.id,
                        title="연재",
                        content=content,
                    )
                    chapter = client.publish_chapter(chapter.id)
                    client.update_work(work.id, status="completed")
                    print(f"   ✅ 챕터 발행 완료")
                except Exception as e:
                    print(f"   ❌ 챕터 추가 실패: {e}")
        else:
            print(f"   🆕 새 작품 등록 중...")
            genre = detect_genre(title, content)
            synopsis = extract_synopsis(content)
            
            try:
                work = client.create_work(
                    title=title,
                    genre=genre,
                    synopsis=synopsis,
                )
                print(f"   ✅ 작품 생성: {work.id}")
                
                chapter = client.create_chapter(
                    work_id=work.id,
                    title="연재",
                    content=content,
                )
                chapter = client.publish_chapter(chapter.id)
                client.update_work(work.id, status="completed")
                print(f"   ✅ 챕터 발행 & 완결 처리")
            except Exception as e:
                print(f"   ❌ 등록 실패: {e}")
    
    print(f"\n{'='*50}")
    print("✅ 동기화 완료!")

if __name__ == "__main__":
    main()
