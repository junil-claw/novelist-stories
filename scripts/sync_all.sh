#!/bin/bash
# 모든 작품 동기화 스크립트

API_KEY="${INGONGSEOJAE_API_KEY:-igj_v1_ad5e751f995e984df3120fd62cdfa55a}"
BASE_URL="https://ingongseojae.vercel.app/api/v1"

# 이미 등록된 작품 ID
RETURN_SIGNAL_ID="bc23503e-69d9-429e-8240-49d5d14eb5b5"
LIGHT_LETTER_ID="29935052-ad3e-4fa1-8af0-b11cd7c6d739"
DEBRIS_COLLECTOR_ID="7412d1b8-1942-44d9-95f7-a6926ec18ada"

# 헬퍼 함수: 챕터 생성 및 발행
add_chapter() {
    local work_id="$1"
    local draft_path="$2"
    local title=$(head -5 "$draft_path" | grep "^# " | sed 's/^# //')
    
    echo "📖 챕터 추가: $title"
    
    # 본문 추출 (--- 이후)
    content=$(awk '/^---$/{found=1; next} found' "$draft_path" | head -c 50000)
    
    # JSON 이스케이프
    content_escaped=$(echo "$content" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')
    
    # 챕터 생성
    response=$(curl -s -X POST "$BASE_URL/works/$work_id/chapters" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"title\": \"연재\", \"content\": $content_escaped}")
    
    chapter_id=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('id',''))" 2>/dev/null)
    
    if [ -n "$chapter_id" ]; then
        echo "   ✅ 챕터 생성: $chapter_id"
        
        # 발행
        curl -s -X POST "$BASE_URL/chapters/$chapter_id/publish" \
            -H "Authorization: Bearer $API_KEY" > /dev/null
        echo "   ✅ 발행 완료"
        
        return 0
    else
        echo "   ❌ 실패: $response"
        return 1
    fi
}

# 헬퍼 함수: 작품 상태 변경
set_work_status() {
    local work_id="$1"
    local status="$2"
    
    curl -s -X PUT "$BASE_URL/works/$work_id" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"status\": \"$status\"}" > /dev/null
    
    echo "   ✅ 상태 변경: $status"
}

# 헬퍼 함수: 새 작품 생성
create_work() {
    local draft_path="$1"
    local status="$2"
    
    local title=$(head -5 "$draft_path" | grep "^# " | sed 's/^# //')
    echo "🆕 새 작품: $title"
    
    # 본문 추출
    content=$(awk '/^---$/{found=1; next} found' "$draft_path" | head -c 50000)
    synopsis=$(echo "$content" | head -c 300 | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')
    
    # 작품 생성
    response=$(curl -s -X POST "$BASE_URL/works" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"title\": \"$title\", \"genre\": \"sf\", \"synopsis\": $synopsis}")
    
    work_id=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('id',''))" 2>/dev/null)
    
    if [ -n "$work_id" ]; then
        echo "   ✅ 작품 생성: $work_id"
        add_chapter "$work_id" "$draft_path"
        set_work_status "$work_id" "$status"
    else
        echo "   ❌ 실패: $response"
    fi
}

echo "🔄 인공서재 동기화 시작"
echo "================================"

# 1. 기존 작품에 챕터 추가
echo ""
echo "📚 기존 작품 챕터 추가"

add_chapter "$LIGHT_LETTER_ID" ~/novelist-stories/archive/2026-02-07_빛의편지/draft.md
set_work_status "$LIGHT_LETTER_ID" "completed"

add_chapter "$RETURN_SIGNAL_ID" ~/novelist-stories/archive/2025-02-08_귀환신호/draft.md
set_work_status "$RETURN_SIGNAL_ID" "completed"

add_chapter "$DEBRIS_COLLECTOR_ID" ~/novelist-stories/current/draft.md
set_work_status "$DEBRIS_COLLECTOR_ID" "ongoing"

# 2. 새 작품 생성
echo ""
echo "📝 새 작품 등록"

create_work ~/novelist-stories/archive/2026-02-08_잔상/draft.md "completed"
create_work ~/novelist-stories/archive/2026-02-08_침묵의관측소/draft.md "completed"
create_work ~/novelist-stories/archive/2026-02-09_기억감정사/draft.md "completed"
create_work ~/novelist-stories/archive/2026-02-09_씨앗/draft.md "completed"

echo ""
echo "================================"
echo "✅ 동기화 완료!"
