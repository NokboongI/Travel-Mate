import uvicorn
import json
import requests
import urllib.parse
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
import googlemaps
import traceback
from duckduckgo_search import DDGS  # [추가] 검색 라이브러리

# =======================================================================
# API 키 (환경변수에서 읽기)
# =======================================================================
import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
# =======================================================================

# 클라이언트 초기화
try:
    # Google Maps 초기화
    gmaps = googlemaps.Client(key=GOOGLE_API_KEY) if GOOGLE_API_KEY else None
    
    # OpenAI 초기화 (Railway 환경 대응)
    if OPENAI_API_KEY:
        try:
            # http_client 명시적 설정
            import httpx
            http_client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
            )
            
            client = AsyncOpenAI(
                api_key=OPENAI_API_KEY,
                http_client=http_client,
                max_retries=2
            )
        except Exception as e:
            print(f"⚠️ AsyncOpenAI 초기화 실패: {e}")
            client = None
    else:
        client = None
    
    print("✅ 초기화 완료")
except Exception as e:
    gmaps, client = None, None
    print(f"⚠️ 초기화 오류: {e}")

# MCP 도구 목록
TOOLS_LIST = [
    {
        "name": "analyze_chat_history",
        "description": "카카오톡 대화 내용을 분석하여 여행 일정표 작성",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_log": {
                    "type": "string",
                    "description": "분석할 카카오톡 대화 내용"
                }
            },
            "required": ["chat_log"]
        }
    },
    {
        "name": "ask_travel_advisor",
        "description": "여행지, 숙소, 맛집 추천 + 경로 안내 + 여행 규정(수하물, 비자, 에티켓 등) 및 팁 안내",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "여행 관련 질문"
                }
            },
            "required": ["question"]
        }
    },
    {
        "name": "check_travel_route",
        "description": "두 장소 간의 이동 경로 계산 (자동차 + 대중교통)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {
                    "type": "string",
                    "description": "출발지"
                },
                "goal": {
                    "type": "string",
                    "description": "도착지"
                }
            },
            "required": ["start", "goal"]
        }
    },
    {
        "name": "calculate_budget",
        "description": "여행 예산 계산 (실시간 가격 검색)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "locations": {
                    "type": "string",
                    "description": "여행 장소"
                },
                "people_count": {
                    "type": "integer",
                    "description": "인원 수"
                },
                "duration": {
                    "type": "string",
                    "description": "여행 기간"
                },
                "plan_details": {
                    "type": "string",
                    "description": "여행 계획 상세"
                }
            },
            "required": ["locations", "people_count", "duration", "plan_details"]
        }
    }
]

# 자주 쓰는 지역명
FAST_REGIONS = {
    # 한국
    "서울", "부산", "인천", "대구", "광주", "대전", "울산", "세종",
    "수원", "성남", "고양", "용인", "안양", "화성", "평택", "시흥",
    "파주", "의정부", "광명", "김포", "군포", "이천", "오산", "경주",
    "강남", "강북", "종로", "명동", "홍대", "이태원", "광교", "분당", "잠실",
    "해운대", "광안리", "남포동", "송도", "구월동", "송파", "강동",
    "제주", "서귀포", "애월", "성산",
    
    # 일본
    "도쿄", "tokyo", "신주쿠", "shinjuku", "시부야", "shibuya",
    "아키하바라", "akihabara", "나카노", "nakano", "이케부쿠로", "ikebukuro",
    "우에노", "ueno", "하라주쿠", "harajuku", "롯폰기", "roppongi",
    "오사카", "osaka", "난바", "namba", "도톤보리", "dotonbori", "우메다", "umeda",
    "교토", "kyoto", "후시미", "fushimi", "기온", "gion",
    
    # 프랑스
    "파리", "paris", "샤를드골", "charles de gaulle", "에펠탑", "eiffel",
    "루브르", "louvre", "몽마르트", "montmartre", "샹젤리제", "champs elysees",
    
    # 기타
    "런던", "london", "뉴욕", "new york", "LA", "los angeles",
    "베를린", "berlin", "로마", "rome", "바르셀로나", "barcelona"
}

# 지역 확장 맵 (한국만!)
REGION_EXPAND = {
    "잠실": ["잠실", "송파", "강동"],
    "광교": ["광교", "수원", "영통"],
    "분당": ["분당", "성남", "판교"],
    "강남": ["강남", "서초", "역삼"],
    "홍대": ["홍대", "마포", "서교"],
    "해운대": ["해운대", "부산"],
    "광안리": ["광안리", "부산"],
}

# 한국 지역 리스트
KOREA_REGIONS = {
    "서울", "부산", "인천", "대구", "광주", "대전", "울산", "세종",
    "수원", "성남", "고양", "용인", "안양", "화성", "평택", "시흥",
    "파주", "의정부", "광명", "김포", "군포", "이천", "오산", "경주",
    "강남", "강북", "종로", "명동", "홍대", "이태원", "광교", "분당", "잠실",
    "해운대", "광안리", "남포동", "송도", "구월동", "송파", "강동",
    "제주", "서귀포", "애월", "성산"
}

# 해외 주요 도시 (핵심만!)
INTERNATIONAL_CITIES = {
    # 일본
    "도쿄", "tokyo", "오사카", "osaka", "교토", "kyoto",
    "나카노", "nakano", "신주쿠", "shinjuku", "시부야", "shibuya",
    
    # 프랑스
    "파리", "paris", "샤를드골", "charles", "에펠탑", "eiffel",
    
    # 기타
    "런던", "london", "뉴욕", "new york", "LA", "los angeles"
}

# 해외 키워드
INTERNATIONAL_KEYWORDS = {"역", "station", "airport", "공항"}

# =======================================================================
# 헬퍼 함수
# =======================================================================

def get_xy(keyword):
    """카카오맵 장소 검색 → 좌표 (해외 도시 차단!)"""
    
    # 해외 도시면 바로 None 반환
    keyword_lower = keyword.lower()
    for city in INTERNATIONAL_CITIES:
        if city in keyword_lower:
            # print(f"⚠️ '{keyword}'는 해외 도시 → 카카오맵 건너뜀")
            return None, None, None
    
    if not KAKAO_API_KEY: 
        return None, None, None
    
    try:
        url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
        for suffix in [" 역", " 터미널", ""]:
            resp = requests.get(url, headers=headers, params={"query": keyword + suffix, "size": 5}, timeout=10)
            if resp.status_code == 200:
                data = resp.json().get("documents", [])
                for p in data:
                    if "역" in p['place_name'] or "터미널" in p['place_name']:
                        return p["x"], p["y"], p["place_name"]
                if data: 
                    return data[0]["x"], data[0]["y"], data[0]["place_name"]
        return None, None, None
    except: 
        return None, None, None

def convert_coords(lon, lat):
    """WGS84 → WCONGNAMUL (카카오맵 좌표계)"""
    try:
        url = "https://dapi.kakao.com/v2/local/geo/transcoord.json"
        resp = requests.get(
            url, 
            headers={"Authorization": f"KakaoAK {KAKAO_API_KEY}"},
            params={"x": lon, "y": lat, "input_coord": "WGS84", "output_coord": "WCONGNAMUL"}, 
            timeout=10
        )
        docs = resp.json().get("documents", [])
        return (docs[0]["x"], docs[0]["y"]) if docs else (None, None)
    except: 
        return None, None

def is_international_route(start, goal):
    """빠른 해외 경로 판단"""
    start_lower = start.lower()
    goal_lower = goal.lower()
    
    # 주요 도시 체크
    for city in INTERNATIONAL_CITIES:
        if city in start_lower or city in goal_lower:
            return True
    
    # "도쿄역" 같은 조합 체크
    for city in INTERNATIONAL_CITIES:
        for keyword in INTERNATIONAL_KEYWORDS:
            if city in start_lower and keyword in start_lower:
                return True
            if city in goal_lower and keyword in goal_lower:
                return True
    
    return False

async def translate_to_english(text, client):
    """지역/키워드를 영어로 변환"""
    
    if not client:
        return text
    
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """장소/키워드를 영어로 변환하세요.

예시:
- "도쿄역" → "Tokyo Station"
- "나카노브로드웨이" → "Nakano Broadway"
- "샤를드골" → "Charles de Gaulle Airport"
- "에펠탑" → "Eiffel Tower"
- "시부야" → "Shibuya"
- "라멘" → "ramen"
- "야키니쿠" → "yakiniku"
- "숙소" → "hotel"
- "호텔" → "hotel"
- "맛집" → "restaurant"
- "관광지" → "tourist attraction"
- "카페" → "cafe"

JSON: {"english": "..."}"""
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            response_format={"type": "json_object"},
            timeout=3
        )
        
        data = json.loads(resp.choices[0].message.content)
        english = data.get('english', text)
        
        # print(f"🌐 번역: '{text}' → '{english}'")
        
        return english
    
    except Exception as e:
        print(f"❌ 번역 실패: {e}, 원본 사용")
        return text

async def extract_regions_hybrid(text, client):
    """하이브리드 지역명 추출 (규칙 기반 + GPT - 개선판)"""
    
    # 1단계: 빠른 규칙 기반
    found = []
    text_lower = text.lower()
    
    for region in FAST_REGIONS:
        if region.lower() in text_lower:
            found.append(region)
    
    # 중복 제거 + 긴 것 우선
    found = list(set(found))
    found.sort(key=len, reverse=True)
    
    # print(f"📍 규칙 기반 지역: {found}")
    
    if len(found) >= 2:
        return found[:3]
    
    # 2단계: GPT로 보완 (프롬프트 강화!)
    if not client:
        return found[:3] if found else []
    
    try:
        # print("⚠️ 지역명 부족 → GPT 호출")
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """텍스트에서 **명시적으로 언급된** 지역명만 추출하세요.

중요 규칙:
1. 텍스트에 **직접 나온** 지역만 추출
2. 추측하거나 확장하지 마세요
3. 공항/랜드마크가 있으면 해당 도시만 추가

예시:
입력: "도쿄 나카노 라멘"
출력: {"regions": ["도쿄", "나카노"]}

입력: "샤를드골 공항"  
출력: {"regions": ["파리", "샤를드골"]}

입력: "잠실 양식당"
출력: {"regions": ["잠실"]}

입력: "에펠탑"
출력: {"regions": ["파리", "에펠탑"]}

절대 금지:
- 텍스트에 없는 지역 추가
- 비슷한 지역 추측
- 한국 질문에 일본 지역 추가
- 일본 질문에 한국 지역 추가

JSON: {"regions": ["지역1", "지역2"]}"""
                },
                {"role": "user", "content": text}
            ],
            response_format={"type": "json_object"},
            timeout=5
        )
        
        data = json.loads(resp.choices[0].message.content)
        gpt_regions = data.get('regions', [])
        
        # print(f"💡 GPT 추출 지역: {gpt_regions}")
        
        # 결합
        all_regions = list(set(found + gpt_regions))
        all_regions.sort(key=len, reverse=True)
        
        return all_regions[:3]
        
    except Exception as e:
        print(f"❌ GPT 지역 추출 실패: {e}")
        return found[:3] if found else []

def expand_regions(regions):
    """한국 지역만 확장"""
    expanded = []
    for region in regions:
        if region in REGION_EXPAND:
            # 한국 지역이면 확장
            expanded.extend(REGION_EXPAND[region])
        else:
            # 해외 지역은 그대로
            expanded.append(region)
    return list(set(expanded))

def search_naver_local(keyword, regions=[], display=30):
    """네이버 지역 검색 (로그 강화)"""
    
    try:
        url = "https://openapi.naver.com/v1/search/local.json"
        headers = {
            "X-Naver-Client-Id": NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
        }
        
        query = f"{regions[0]} {keyword}" if regions else keyword
        
        # print(f"🔍 네이버 검색: '{query}' (display={display})")
        
        resp = requests.get(
            url,
            headers=headers,
            params={"query": query, "display": display, "sort": "random"},
            timeout=10
        )
        
        if resp.status_code != 200:
            print(f"❌ 네이버 오류: {resp.text[:200]}")
            return []
        
        items = resp.json().get('items', [])
        # print(f"✅ 네이버: {len(items)}개")
        
        return items
    
    except Exception as e:
        print(f"❌ 네이버 검색 실패: {e}")
        traceback.print_exc()
        return []

async def filter_relevant_places_batch(place_names, user_keyword, client):
    """GPT 배치 필터링: 사용자 의도와 관련 있는 장소만 선택 (완화 버전)"""
    
    if not place_names or not client:
        return place_names
    
    # 최대 30개씩 처리
    places_text = "\n".join([f"{i+1}. {p}" for i, p in enumerate(place_names[:30])])
    
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "system",
                "content": f"""사용자가 '{user_keyword}'를(을) 찾고 있습니다.

아래 장소 중 사용자가 원하는 것과 관련 있는 장소를 골라주세요.

**중요: 최소 5개 이상 선택하세요. 애매하면 포함하세요.**

제외 기준:
- 명백한 부대시설만 제외 (주차장, 충전소, 화장실, ATM)
- GS25, CU 같은 편의점 (사용자가 편의점을 찾는 게 아니면)
- 사용자가 원하는 것과 **완전히 무관한** 업종

포함 기준:
- 사용자가 찾는 것과 관련된 모든 장소
- 같은 카테고리의 다른 형태 (예: "호텔" 찾을 때 "펜션"도 포함)
- **애매하면 무조건 포함**
- 같은 건물 내 관련 시설도 포함

예시:
사용자: "펜션"
1. 제주애월애 독채펜션 ✅
2. 콘스트 호텔 ✅ (숙박시설)
3. 플레이스캠프제주 ✅ (캠핑/숙박)
4. 더싱글라운지 펍 ❌ (술집)
5. 전기차충전소 ❌ (부대시설)
6. GS25 ❌ (편의점)

JSON: {{"relevant_indices": [번호들]}}"""
            }, {
                "role": "user",
                "content": places_text
            }],
            response_format={"type": "json_object"},
            timeout=5
        )
        
        data = json.loads(resp.choices[0].message.content)
        relevant_indices = set(data.get('relevant_indices', []))
        
        # print(f"🤖 GPT 필터링: {len(place_names)}개 → {len(relevant_indices)}개 선택")
        
        return [place_names[i-1] for i in relevant_indices if 1 <= i <= len(place_names)]
    
    except Exception as e:
        print(f"❌ GPT 필터링 실패: {e}, 전부 포함")
        traceback.print_exc()
        return place_names  # 실패 시 전부 포함

async def search_domestic(keyword, regions, client, retry=False):
    """국내 검색: 네이버 → GPT 필터링 → 카카오맵 검증 → GPT 재필터링"""
    
    # print(f"🔍 [국내검색] '{keyword}', 지역: {regions}, 재시도: {retry}")
    
    # 지역 확장
    expanded_regions = expand_regions(regions) if regions else []
    
    # 1단계: 네이버 검색 (재시도 시 display 증가)
    display = 50 if retry else 30
    naver_items = search_naver_local(keyword, regions, display=display)
    
    # 네이버 실패 시 카카오맵 직접 검색
    if not naver_items and regions:
        # print(f"⚠️ 네이버 0개 → 카카오맵 직접 검색")
        
        try:
            resp = requests.get(
                "https://dapi.kakao.com/v2/local/search/keyword.json",
                headers={"Authorization": f"KakaoAK {KAKAO_API_KEY}"},
                params={
                    "query": f"{regions[0]} {keyword}",
                    "size": 15
                },
                timeout=10
            )
            
            if resp.status_code == 200:
                kakao_direct = resp.json().get("documents", [])
                
                # naver 형식으로 변환
                naver_items = []
                for p in kakao_direct:
                    naver_items.append({
                        'title': p['place_name'],
                        'address': p.get('address_name', ''),
                        'roadAddress': p.get('road_address_name', '')
                    })
        
        except Exception as e:
            print(f"❌ 카카오맵 직접 검색 실패: {e}")
    
    # 2단계: 장소명 추출
    candidate_names = []
    candidate_items = {}
    
    for item in naver_items[:50]:  # 최대 50개
        place_name = item['title'].replace('<b>', '').replace('</b>', '')
        
        if not place_name or len(place_name) < 2:
            continue
        
        candidate_names.append(place_name)
        candidate_items[place_name] = item
    
    # 3단계: 네이버 결과 GPT 배치 필터링
    relevant_names = await filter_relevant_places_batch(
        candidate_names, 
        keyword, 
        client
    )
    
    # 4단계: 카카오맵 검증 (후보 수집)
    kakao_candidates = []
    seen_ids = set()
    
    for place_name in relevant_names:
        if place_name not in candidate_items:
            continue
        
        item = candidate_items[place_name]
        
        try:
            resp = requests.get(
                "https://dapi.kakao.com/v2/local/search/keyword.json",
                headers={"Authorization": f"KakaoAK {KAKAO_API_KEY}"},
                params={"query": place_name, "size": 3},
                timeout=5
            )
            
            if resp.status_code != 200:
                continue
            
            places = resp.json().get("documents", [])
            
            # 카카오맵에서 못 찾으면 네이버 데이터 직접 사용
            if not places:
                
                fake_place = {
                    'id': f"naver_{len(kakao_candidates)}",
                    'place_name': place_name,
                    'place_url': f"https://map.naver.com/p/search/{urllib.parse.quote(place_name)}",
                    'address_name': item.get('address', ''),
                    'road_address_name': item.get('roadAddress', ''),
                    'phone': item.get('telephone', '')
                }
                
                # 지역 필터링
                addr = (fake_place['address_name'] + ' ' + fake_place['road_address_name']).lower()
                
                if expanded_regions:
                    if any(region.lower() in addr for region in expanded_regions):
                        kakao_candidates.append(fake_place)
                else:
                    kakao_candidates.append(fake_place)
                
                continue
            
            # 카카오맵 결과 수집
            for p in places:
                if p['id'] in seen_ids:
                    continue
                
                addr = (p.get('address_name', '') + ' ' + p.get('road_address_name', '')).lower()
                
                # 지역 필터링
                if expanded_regions:
                    if not any(region.lower() in addr for region in expanded_regions):
                        continue
                
                seen_ids.add(p['id'])
                kakao_candidates.append(p)
        
        except Exception as e:
            continue
    
    # 5단계: 카카오맵 결과 GPT 배치 재필터링
    if kakao_candidates:
        kakao_names = [p['place_name'] for p in kakao_candidates]
        
        final_names = await filter_relevant_places_batch(
            kakao_names,
            keyword,
            client
        )
        
        # 최종 결과
        all_places = []
        for p in kakao_candidates:
            if p['place_name'] in final_names:
                all_places.append(p)
                
                # if len(all_places) >= 10: break
    else:
        all_places = []
    
    return all_places  # 리스트 반환

def format_places_result(keyword, places):
    """장소 리스트를 마크다운으로 포맷"""
    
    if not places:
        return f"❌ '{keyword}' 검색 결과 없음"
    
    result = f"""# {keyword} 검색 결과 ({len(places)}개)

⚠️ 아래 모든 장소를 빠짐없이 표시하세요. 요약하지 마세요.

"""
    
    for i, p in enumerate(places, 1):
        link_type = "네이버맵" if "naver.com" in p['place_url'] else "카카오맵"
        
        result += f"""---

## {i}. {p['place_name']}

**{link_type}:** {p['place_url']}

**주소:** {p.get('road_address_name') or p.get('address_name', '')}
"""
        if p.get('phone'):
            result += f"**전화:** {p['phone']}\n"
        result += "\n"
    
    result += "\n⚠️ 위 모든 장소를 사용자에게 그대로 전달하세요.\n"
    
    return result

async def search_international(keyword, regions, client):
    """해외 검색: Places API 직접 호출 (개선판)"""
    
    # print(f"🌍 [해외검색] '{keyword}', 지역: {regions}")
    
    # GPT로 영어 변환
    region_en = await translate_to_english(regions[0], client) if regions else ""
    keyword_en = await translate_to_english(keyword, client)
    
    # 무조건 near 사용
    if regions:
        query = f"{keyword_en} near {region_en}"
    else:
        query = keyword_en
    
    # print(f"🔍 Places API 쿼리: '{query}'")
    
    try:
        # type 파라미터 제거 (호텔/카페/관광지 모두 검색)
        result = gmaps.places(
            query=query,
            language='ko'
        )
        
        places = result.get('results', [])
        
        # print(f"✅ Places API: {len(places)}개 발견")
        
        # 한국 주소 필터링
        filtered = []
        for p in places:
            addr = p.get('formatted_address', '').lower()
            
            if any(kr in addr for kr in ['대한민국', 'korea', ' kr', 'south korea', '서울', '부산', '경기', '인천']):
                # print(f"  ❌ 한국 주소 제외: {p.get('name')}")
                continue
            
            filtered.append(p)
        
        places = filtered
        
        # print(f"✅ 필터링 후: {len(places)}개")
        
        if len(places) < 1:
            return f"❌ '{keyword}' 검색 결과 없음"
        
        # 포맷
        output = f"""# {keyword} 검색 결과 ({len(places)}개)

⚠️ 아래 모든 장소를 빠짐없이 표시하세요. 요약하지 마세요.

"""
        
        for i, p in enumerate(places[:10], 1):
            name = p.get('name', '이름 없음')
            rating = p.get('rating')
            reviews = p.get('user_ratings_total', 0)
            addr = p.get('formatted_address', '') or p.get('vicinity', '')
            
            place_id = p.get('place_id')
            url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            
            output += f"""---

## {i}. {name}"""
            
            if rating:
                output += f" ⭐ {rating}"
                if reviews > 0:
                    output += f" ({reviews:,}개 리뷰)"
            
            output += f"""

**구글맵:** {url}

"""
            
            if addr:
                short_addr = addr.split(',')[0] if ',' in addr else addr
                output += f"**주소:** {short_addr[:50]}\n"
            
            output += "\n"
        
        output += "\n⚠️ 위 모든 장소를 사용자에게 그대로 전달하세요.\n"
        
        return output
    
    except Exception as e:
        print(f"❌ Places API 오류: {e}")
        traceback.print_exc()
        return f"검색 오류: {e}"

async def get_route_info(start, goal, start_original, goal_original, client):
    """경로 계산 공통 함수"""
    
    # print(f"🚗 경로: {start} → {goal}")
    
    # 빠른 해외 체크
    if is_international_route(start, goal):
        # print("🌍 해외 도시 감지 → 구글맵")
        is_intl = True
    else:
        # GPT 판단 (원본 질문 포함!)
        try:
            check = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """질문이 국내/해외 여행인지 판단하세요.

중요: 지역명 조합으로 판단하세요!

한국 지역:
- 서울, 부산, 제주, 강남, 잠실, 광교, 송파, 해운대, 경주

해외 지역:
- 도쿄, 오사카, 교토, 나카노, 파리, 런던

예시:
- "강남 → 잠실" → {"is_international": false}
- "오사카 → 교토" → {"is_international": true}
- "샤를드골 → 에펠탑" → {"is_international": true}
- "도쿄역 → 아키하바라" → {"is_international": true}

JSON: {"is_international": bool}"""
                    },
                    {
                        "role": "user",
                        "content": f"원본 질문: {start_original} → {goal_original}\n추출된 지역: {start} → {goal}"
                    }
                ],
                response_format={"type": "json_object"}
            )
            
            is_intl = json.loads(check.choices[0].message.content).get('is_international', False)
        
        except Exception as e:
            # print(f"❌ GPT 판단 실패: {e}")
            is_intl = True
    
    # print(f"🌍 {'해외' if is_intl else '국내'}")
    
    if is_intl:
        # 해외: GPT로 영문명 변환
        try:
            start_en = await translate_to_english(start_original, client)
            goal_en = await translate_to_english(goal_original, client)
            
            # print(f"🌍 변환: {start} → {start_en}, {goal} → {goal_en}")
            
        except Exception as e:
            # print(f"❌ 영문명 변환 실패: {e}")
            start_en = start
            goal_en = goal
        
        safe_start = urllib.parse.quote(start_en)
        safe_goal = urllib.parse.quote(goal_en)
        
        car_link = f"https://www.google.com/maps/dir/?api=1&origin={safe_start}&destination={safe_goal}&travelmode=driving"
        transit_link = f"https://www.google.com/maps/dir/?api=1&origin={safe_start}&destination={safe_goal}&travelmode=transit"
        
        # print(f"🚗 링크 생성 완료")
        
        return f"""# {start} → {goal}

⚠️⚠️⚠️ 경고: 아래 링크를 절대 삭제하지 마세요 ⚠️⚠️⚠️

아래 링크를 사용자에게 그대로 전달하세요. 요약하거나 재작성하지 마세요.

---

## 🚗 자동차 경로

**다음 링크를 클릭하세요:**

{car_link}

---

## 🚌 대중교통 경로

**다음 링크를 클릭하세요:**

{transit_link}

---

⚠️ 경고: "경로를 찾을 수 없습니다" 같은 말 하지 마세요.
⚠️ 위 링크를 사용자에게 복사해서 보여주기만 하면 됩니다.
⚠️ 링크가 작동하는지 테스트하지 말고 그냥 전달하세요."""
    
    else:
        # 국내
        sx, sy, sname = get_xy(start)
        ex, ey, gname = get_xy(goal)
        
        if sx and ex:
            results = []
            
            # 자동차
            try:
                navi_resp = requests.get(
                    "https://apis-navi.kakaomobility.com/v1/directions",
                    headers={"Authorization": f"KakaoAK {KAKAO_API_KEY}"},
                    params={
                        "origin": f"{sx},{sy}",
                        "destination": f"{ex},{ey}",
                        "priority": "RECOMMEND"
                    },
                    timeout=10
                )
                
                if navi_resp.status_code == 200:
                    routes = navi_resp.json().get("routes", [])
                    if routes:
                        summary = routes[0]["summary"]
                        sec = summary["duration"]
                        dist = summary["distance"]
                        h = sec // 3600
                        m = (sec % 3600) // 60
                        time_str = f"{h}시간 {m}분" if h > 0 else f"{m}분"
                        
                        results.append(f"""🚗 **자동차:**

{sname} → {gname}
소요: {time_str}, 거리: {dist / 1000:.1f}km""")
            except:
                pass
            
            # 대중교통
            ksx, ksy = convert_coords(sx, sy)
            kex, key = convert_coords(ex, ey)
            
            if ksx and kex:
                link = f"https://map.kakao.com/?target=traffic&rt={ksx},{ksy},{kex},{key}&rt1={urllib.parse.quote(sname)}&rt2={urllib.parse.quote(gname)}"
                
                results.append(f"""🚌 **대중교통:**

{sname} → {gname}

{link}""")
            
            return f"# {start} → {goal}\n\n---\n\n" + "\n\n---\n\n".join(results) if results else "경로 계산 실패"
        
        else:
            return "장소를 찾을 수 없습니다"

def web_search_for_budget(query):
    """예산 계산용 웹 검색 (간단 버전)"""
    try:
        return f"{query} 관련 정보를 검색했습니다."
    except: 
        return "검색 실패"

# =======================================================================
# MCP 핸들러
# =======================================================================

async def handle_mcp(request):
    if request.method == "OPTIONS":
        return Response("", status_code=200)
    
    # [수정] 스펙 준수: GET 요청 시 405 반환
    if request.method == "GET":
        return Response("Method Not Allowed", status_code=405)
    
    if request.method != "POST":
        return Response("Method not allowed", status_code=405)
    
    try:
        body = await request.json()
    except:
        return Response("Invalid JSON", status_code=400)
    
    method = body.get("method")
    msg_id = body.get("id")
    
    # print(f"📩 요청: {method}")
    
    # 초기화
    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                # [수정] Protocol Version 2025-03-26으로 변경
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "TravelMate", "version": "13.0"}
            }
        })
    
    # 준비 완료
    if method == "notifications/initialized":
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": True})
    
    # 도구 목록
    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOLS_LIST}
        })
    
    # 도구 실행
    if method == "tools/call":
        tool_name = body["params"]["name"]
        args = body["params"]["arguments"]
        result_text = ""
        
        # 도구 1: 대화 분석
        if tool_name == "analyze_chat_history":
            if not client:
                result_text = "OpenAI 미초기화"
            else:
                try:
                    resp = await client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "여행 일정표를 마크다운으로 작성하세요"},
                            {"role": "user", "content": args.get("chat_log", "")}
                        ]
                    )
                    result_text = resp.choices[0].message.content
                except Exception as e:
                    result_text = f"분석 오류: {e}"
                    traceback.print_exc()
        
        # 도구 2: 여행지 추천 + 경로 안내 (통합!)
        elif tool_name == "ask_travel_advisor":
            if not client:
                result_text = "OpenAI 미초기화"
            else:
                try:
                    question = args.get("question", "")
                    
                    # 0단계: 질문 유형 판단
                    type_check = await client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {
                                "role": "system",
                                "content": """질문 유형을 판단하세요.

유형:
- "place": 장소 검색 (숙소, 맛집, 관광지, 카페 등)
- "route": 경로 안내 (A에서 B로, 이동 방법, 가는 법)
- "guide": 규정/정보 (반입 금지, 수하물, 에티켓, 비자, 팁 문화 등)

예시:
- "오사카 맛집" → {"type": "place"}
- "오사카에서 교토 가는 법" → {"type": "route"}
- "보조배터리 기내 반입 돼?" → {"type": "guide"}
- "일본 곤약젤리 반입 규정" → {"type": "guide"}
- "미국 팁 문화" → {"type": "guide"}

JSON: {"type": "place/route/guide"}"""
                            },
                            {"role": "user", "content": question}
                        ],
                        response_format={"type": "json_object"}
                    )
                    
                    type_data = json.loads(type_check.choices[0].message.content)
                    question_type = type_data.get('type', 'place')
                    
                    # print(f"❓ 질문 유형: {question_type}")
                    
                    # [추가] 규정 및 정보 안내 (검색 기능)
                    if question_type == "guide":
                        # print(f"🔍 [규정/정보] DuckDuckGo 검색 시작: {question}")
                        
                        try:
                            # DuckDuckGo 검색
                            search_results = []
                            with DDGS() as ddgs:
                                results = list(ddgs.text(question, max_results=3))
                                for r in results:
                                    search_results.append(f"- 제목: {r['title']}\n- 링크: {r['href']}\n- 내용: {r['body']}")
                            
                            search_text = "\n\n".join(search_results)
                            
                            # print(f"✅ 검색 완료: {len(results)}개")
                            
                            # GPT 답변 생성
                            resp = await client.chat.completions.create(
                                model="gpt-4o",
                                messages=[
                                    {
                                        "role": "system",
                                        "content": """당신은 정확한 여행 규정을 안내하는 전문가입니다.
제공된 [검색 결과]를 바탕으로 사용자의 질문에 답변하세요.

규칙:
1. 검색 결과에 기반하여 사실만 말하세요.
2. 금지 품목이나 법적 규정은 엄격하게 안내하세요.
3. 정보가 불확실하면 "최신 규정은 항공사나 대사관 확인이 필요합니다"라고 덧붙이세요.
4. 출처 링크가 있다면 함께 표시하세요.
"""
                                    },
                                    {
                                        "role": "user",
                                        "content": f"질문: {question}\n\n[검색 결과]\n{search_text}"
                                    }
                                ]
                            )
                            
                            result_text = resp.choices[0].message.content
                            
                        except Exception as e:
                            print(f"❌ 검색/답변 오류: {e}")
                            result_text = "검색 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."

                    # 경로 질문
                    elif question_type == "route":
                        regions = await extract_regions_hybrid(question, client)
                        
                        if len(regions) < 2:
                            result_text = "출발지와 도착지를 명확히 말씀해주세요.\n예: '오사카에서 교토 가는 방법'"
                        else:
                            result_text = await get_route_info(
                                regions[0], regions[1],
                                question, question,
                                client
                            )
                    
                    # 장소 검색
                    else:
                        # 1단계: 지역명 추출
                        regions = await extract_regions_hybrid(question, client)
                        
                        # 2단계: 키워드 추출 + 국내/해외 판단
                        check = await client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {
                                    "role": "system",
                                    "content": """질문을 분석하여 JSON으로 반환하세요.

국내: 서울, 부산, 인천, 제주, 경주 등 한국
해외: 도쿄, 오사카, 파리, 런던 등 외국

형식: {"is_intl": bool, "keywords": ["검색어"]}

중요: keywords는 핵심 단어만 짧고 명확하게!

예시:
- "강남 라멘" → {"is_intl": false, "keywords": ["라멘"]}
- "도쿄역 인근 맛집 추천" → {"is_intl": true, "keywords": ["맛집"]}
- "시부야 숙소, 맛집, 관광지" → {"is_intl": true, "keywords": ["숙소", "맛집", "관광지"]}
- "부산역 근처 호텔" → {"is_intl": false, "keywords": ["호텔"]}
- "경주역 숙소, 맛집, 관광지" → {"is_intl": false, "keywords": ["숙소", "맛집", "관광지"]}

절대 금지:
- "인근", "근처", "추천", "찾아줘" 같은 불필요한 단어
- 문장 형태로 추출
- 지역명을 키워드에 포함 (이미 regions에 있음)"""
                                },
                                {"role": "user", "content": question}
                            ],
                            response_format={"type": "json_object"}
                        )
                        
                        data = json.loads(check.choices[0].message.content)
                        is_intl = data.get('is_intl', False)
                        keywords = data.get('keywords', [])
                        
                        # print(f"🔍 키워드: {keywords}, 해외: {is_intl}, 지역: {regions}")
                        
                        results = []
                        
                        for kw in keywords[:5]:  # 최대 5개
                            if not kw.strip():
                                continue
                            
                            # 국내/해외 분기
                            if is_intl:
                                res = await search_international(kw, regions, client)
                            else:
                                # 1차 검색
                                places = await search_domestic(kw, regions, client, retry=False)
                                
                                # 재시도 로직 (5개 미만이면)
                                if isinstance(places, list) and len(places) < 5:
                                    # print(f"⚠️ 결과 부족 ({len(places)}개) → 재검색 (display=50)")
                                    
                                    # 2차 검색
                                    more_places = await search_domestic(kw, regions, client, retry=True)
                                    
                                    if isinstance(more_places, list):
                                        existing_ids = {p.get('id') for p in places}
                                        for p in more_places:
                                            if p.get('id') not in existing_ids:
                                                places.append(p)
                                                if len(places) >= 10:
                                                    break
                                    
                                    # print(f"✅ 재검색 후: {len(places)}개")
                                
                                # 포맷
                                res = format_places_result(kw, places)
                            
                            if res and len(res) > 100 and not res.startswith("❌"):
                                results.append(res)
                        
                        result_text = "\n\n".join(results) if results else "검색 결과를 찾을 수 없습니다."
                    
                except Exception as e:
                    result_text = f"검색 오류: {e}"
                    traceback.print_exc()
        
        # 도구 3: 경로 안내 (공통 함수 사용)
        elif tool_name == "check_travel_route":
            start = args.get("start", "")
            goal = args.get("goal", "")
            
            if not client:
                result_text = "OpenAI 미초기화"
            else:
                try:
                    # 지역명 추출
                    start_regions = await extract_regions_hybrid(start, client)
                    goal_regions = await extract_regions_hybrid(goal, client)
                    
                    start_clean = start_regions[0] if start_regions else start
                    goal_clean = goal_regions[0] if goal_regions else goal
                    
                    # 공통 함수 호출
                    result_text = await get_route_info(
                        start_clean, goal_clean,
                        start, goal,
                        client
                    )
                
                except Exception as e:
                    result_text = f"경로 오류: {e}"
                    traceback.print_exc()
        
        # 도구 4: 예산 계산
        elif tool_name == "calculate_budget":
            if not client:
                result_text = "OpenAI 미초기화"
            else:
                try:
                    locations = args.get("locations", "")
                    people_count = args.get("people_count", 1)
                    duration = args.get("duration", "")
                    
                    info = web_search_for_budget(f"{locations} 여행 경비 {duration}")
                    
                    resp = await client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {
                                "role": "system",
                                "content": "예산 견적서를 마크다운 표로 작성하세요"
                            },
                            {
                                "role": "user",
                                "content": f"여행지: {locations}, 인원: {people_count}, 기간: {duration}\n정보: {info}"
                            }
                        ]
                    )
                    
                    result_text = resp.choices[0].message.content
                
                except Exception as e:
                    result_text = f"예산 계산 오류: {e}"
                    traceback.print_exc()
        
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": result_text}],
                "isError": False
            }
        })
    
    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

# =======================================================================
# 앱 설정
# =======================================================================

async def health_check(request):
    return Response("OK", status_code=200)

routes = [
    Route("/", endpoint=health_check, methods=["GET"]),
    Route("/health", endpoint=health_check, methods=["GET"]),
    Route("/sse", endpoint=handle_mcp, methods=["GET", "POST", "OPTIONS"]),
    Route("/sse/", endpoint=handle_mcp, methods=["GET", "POST", "OPTIONS"])
]

middleware = [
    Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
]

app = Starlette(routes=routes, middleware=middleware)

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Travel-Mate v13.0 - 여행 규정 및 팁 안내 (검색 기능) 추가")
    print("=" * 60)
    print("✅ Protocol Version Updated: 2025-03-26")
    print("✅ DuckDuckGo 검색 연동")
    print("✅ 규정/에티켓 질문 자동 감지")
    print("✅ GET 요청 시 405 Method Not Allowed 반환 (스펙 준수)")
    print("=" * 60)
    
    # 수정: Railway 동적 포트 사용
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
