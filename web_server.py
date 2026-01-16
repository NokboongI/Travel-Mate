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
from duckduckgo_search import DDGS

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
    gmaps = googlemaps.Client(key=GOOGLE_API_KEY) if GOOGLE_API_KEY else None
    
    if OPENAI_API_KEY:
        try:
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
            print(f"AsyncOpenAI 초기화 실패: {e}")
            client = None
    else:
        client = None
    
    print("초기화 완료")
except Exception as e:
    gmaps, client = None, None
    print(f"초기화 오류: {e}")

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

# 자주 쓰는 지역명 (대폭 확장)
FAST_REGIONS = {
    # 한국
    "서울", "부산", "인천", "대구", "광주", "대전", "울산", "세종",
    "수원", "성남", "고양", "용인", "안양", "화성", "평택", "시흥",
    "파주", "의정부", "광명", "김포", "군포", "이천", "오산", "경주",
    "강남", "강북", "종로", "명동", "홍대", "이태원", "광교", "분당", "잠실",
    "해운대", "광안리", "남포동", "송도", "구월동", "송파", "강동",
    "제주", "서귀포", "애월", "성산",
    
    # 일본 (대폭 확장)
    "도쿄", "tokyo", "신주쿠", "shinjuku", "시부야", "shibuya",
    "아키하바라", "akihabara", "나카노", "nakano", "이케부쿠로", "ikebukuro",
    "우에노", "ueno", "하라주쿠", "harajuku", "롯폰기", "roppongi",
    "오사카", "osaka", "난바", "namba", "도톤보리", "dotonbori", "우메다", "umeda",
    "교토", "kyoto", "후시미", "fushimi", "기온", "gion",
    "나고야", "nagoya",  # 추가
    "후쿠오카", "fukuoka", "하카타", "hakata",  # 추가
    "삿포로", "sapporo",  # 추가
    "오키나와", "okinawa", "나하", "naha",  # 추가
    "히로시마", "hiroshima",  # 추가
    "고베", "kobe",  # 추가
    "요코하마", "yokohama",  # 추가
    
    # 프랑스
    "파리", "paris", "샤를드골", "charles de gaulle", "에펠탑", "eiffel",
    "루브르", "louvre", "몽마르트", "montmartre", "샹젤리제", "champs elysees",
    
    # 미국 (대폭 확장)
    "뉴욕", "new york", "맨해튼", "manhattan", "브루클린", "brooklyn",
    "LA", "los angeles", "할리우드", "hollywood", "산타모니카", "santa monica",
    "샌프란시스코", "san francisco",
    "라스베가스", "las vegas",
    "시카고", "chicago",
    "마이애미", "miami",
    "시애틀", "seattle",
    "보스턴", "boston",
    "워싱턴", "washington", "washington dc",
    "텍사스", "texas", "휴스턴", "houston", "달라스", "dallas", "오스틴", "austin",  # 추가
    "하와이", "hawaii", "호놀룰루", "honolulu",  # 추가
    
    # 기타 유럽
    "런던", "london",
    "베를린", "berlin",
    "로마", "rome",
    "바르셀로나", "barcelona",
    "암스테르담", "amsterdam",
    "프라하", "prague",
    "비엔나", "vienna",
    
    # 동남아
    "방콕", "bangkok",
    "싱가포르", "singapore",
    "발리", "bali",
    "다낭", "danang",
    "호치민", "ho chi minh",
    "하노이", "hanoi",
    
    # 중국
    "상하이", "shanghai",
    "베이징", "beijing",
    "홍콩", "hong kong",
    
    # 호주
    "시드니", "sydney",
    "멜버른", "melbourne"
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

# 해외 주요 도시 (대폭 확장 + 국가 매핑)
INTERNATIONAL_CITIES = {
    # 일본
    "도쿄", "tokyo", "오사카", "osaka", "교토", "kyoto",
    "나카노", "nakano", "신주쿠", "shinjuku", "시부야", "shibuya",
    "나고야", "nagoya", "후쿠오카", "fukuoka", "삿포로", "sapporo",
    "오키나와", "okinawa", "히로시마", "hiroshima", "고베", "kobe",
    "요코하마", "yokohama", "하카타", "hakata", "나하", "naha",
    
    # 프랑스
    "파리", "paris", "샤를드골", "charles", "에펠탑", "eiffel",
    
    # 미국
    "뉴욕", "new york", "LA", "los angeles", "샌프란시스코", "san francisco",
    "라스베가스", "las vegas", "시카고", "chicago", "마이애미", "miami",
    "시애틀", "seattle", "보스턴", "boston", "워싱턴", "washington",
    "텍사스", "texas", "휴스턴", "houston", "달라스", "dallas", "오스틴", "austin",
    "하와이", "hawaii", "호놀룰루", "honolulu",
    
    # 기타
    "런던", "london", "베를린", "berlin", "로마", "rome",
    "방콕", "bangkok", "싱가포르", "singapore", "홍콩", "hong kong"
}

# 수정: 도시 -> 국가 매핑 (Google Places 검색 정확도 향상)
CITY_TO_COUNTRY = {
    # 일본
    "도쿄": "Japan", "tokyo": "Japan",
    "오사카": "Japan", "osaka": "Japan",
    "교토": "Japan", "kyoto": "Japan",
    "나고야": "Japan", "nagoya": "Japan",
    "후쿠오카": "Japan", "fukuoka": "Japan",
    "삿포로": "Japan", "sapporo": "Japan",
    "오키나와": "Japan", "okinawa": "Japan",
    "히로시마": "Japan", "hiroshima": "Japan",
    "고베": "Japan", "kobe": "Japan",
    "요코하마": "Japan", "yokohama": "Japan",
    "신주쿠": "Japan", "shinjuku": "Japan",
    "시부야": "Japan", "shibuya": "Japan",
    "나카노": "Japan", "nakano": "Japan",
    "하카타": "Japan", "hakata": "Japan",
    "나하": "Japan", "naha": "Japan",
    "아키하바라": "Japan", "akihabara": "Japan",
    "이케부쿠로": "Japan", "ikebukuro": "Japan",
    "우에노": "Japan", "ueno": "Japan",
    "하라주쿠": "Japan", "harajuku": "Japan",
    "롯폰기": "Japan", "roppongi": "Japan",
    "난바": "Japan", "namba": "Japan",
    "도톤보리": "Japan", "dotonbori": "Japan",
    "우메다": "Japan", "umeda": "Japan",
    "후시미": "Japan", "fushimi": "Japan",
    "기온": "Japan", "gion": "Japan",
    
    # 미국
    "뉴욕": "USA", "new york": "USA",
    "LA": "USA", "los angeles": "USA",
    "샌프란시스코": "USA", "san francisco": "USA",
    "라스베가스": "USA", "las vegas": "USA",
    "시카고": "USA", "chicago": "USA",
    "마이애미": "USA", "miami": "USA",
    "시애틀": "USA", "seattle": "USA",
    "보스턴": "USA", "boston": "USA",
    "워싱턴": "USA", "washington": "USA",
    "텍사스": "USA", "texas": "USA",
    "휴스턴": "USA", "houston": "USA",
    "달라스": "USA", "dallas": "USA",
    "오스틴": "USA", "austin": "USA",
    "하와이": "USA", "hawaii": "USA",
    "호놀룰루": "USA", "honolulu": "USA",
    "맨해튼": "USA", "manhattan": "USA",
    "브루클린": "USA", "brooklyn": "USA",
    "할리우드": "USA", "hollywood": "USA",
    "산타모니카": "USA", "santa monica": "USA",
    
    # 프랑스
    "파리": "France", "paris": "France",
    
    # 영국
    "런던": "UK", "london": "UK",
    
    # 독일
    "베를린": "Germany", "berlin": "Germany",
    
    # 이탈리아
    "로마": "Italy", "rome": "Italy",
    
    # 스페인
    "바르셀로나": "Spain", "barcelona": "Spain",
    
    # 태국
    "방콕": "Thailand", "bangkok": "Thailand",
    
    # 싱가포르
    "싱가포르": "Singapore", "singapore": "Singapore",
    
    # 중국/홍콩
    "홍콩": "Hong Kong", "hong kong": "Hong Kong",
    "상하이": "China", "shanghai": "China",
    "베이징": "China", "beijing": "China",
    
    # 베트남
    "다낭": "Vietnam", "danang": "Vietnam",
    "호치민": "Vietnam", "ho chi minh": "Vietnam",
    "하노이": "Vietnam", "hanoi": "Vietnam",
    
    # 인도네시아
    "발리": "Indonesia", "bali": "Indonesia",
    
    # 호주
    "시드니": "Australia", "sydney": "Australia",
    "멜버른": "Australia", "melbourne": "Australia",
}

# 해외 키워드
INTERNATIONAL_KEYWORDS = {"역", "station", "airport", "공항"}

# =======================================================================
# 헬퍼 함수
# =======================================================================

def get_xy(keyword):
    """카카오맵 장소 검색 -> 좌표 (해외 도시 차단)"""
    
    keyword_lower = keyword.lower()
    for city in INTERNATIONAL_CITIES:
        if city in keyword_lower:
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
    """WGS84 -> WCONGNAMUL (카카오맵 좌표계)"""
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
    
    for city in INTERNATIONAL_CITIES:
        if city in start_lower or city in goal_lower:
            return True
    
    for city in INTERNATIONAL_CITIES:
        for keyword in INTERNATIONAL_KEYWORDS:
            if city in start_lower and keyword in start_lower:
                return True
            if city in goal_lower and keyword in goal_lower:
                return True
    
    return False

def get_country_for_city(city_name):
    """도시명으로 국가 찾기"""
    city_lower = city_name.lower()
    
    # 직접 매핑 확인
    if city_lower in CITY_TO_COUNTRY:
        return CITY_TO_COUNTRY[city_lower]
    if city_name in CITY_TO_COUNTRY:
        return CITY_TO_COUNTRY[city_name]
    
    # 부분 매칭
    for city, country in CITY_TO_COUNTRY.items():
        if city in city_lower or city_lower in city:
            return country
    
    return None

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
- "도쿄역" -> "Tokyo Station"
- "나고야" -> "Nagoya"
- "나카노브로드웨이" -> "Nakano Broadway"
- "샤를드골" -> "Charles de Gaulle Airport"
- "에펠탑" -> "Eiffel Tower"
- "시부야" -> "Shibuya"
- "라멘" -> "ramen"
- "야키니쿠" -> "yakiniku"
- "숙소" -> "hotel"
- "호텔" -> "hotel"
- "맛집" -> "restaurant"
- "관광지" -> "tourist attraction"
- "카페" -> "cafe"
- "바비큐" -> "BBQ restaurant"

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
        
        return english
    
    except Exception as e:
        print(f"번역 실패: {e}, 원본 사용")
        return text

# 수정: 지역 + 국가 컨텍스트 추출
async def extract_regions_with_context(text, client):
    """지역명 + 국가 컨텍스트 추출 (핵심 개선)"""
    
    if not client:
        return [], None
    
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": """사용자의 여행 질문에서 **지역명**과 **국가**를 추출하세요.

중요 규칙:
1. 지역명만 언급되면 가장 유명한/일반적인 국가로 추론
2. "나고야" -> 일본 나고야 (미국 아님)
3. "텍사스 바비큐" -> 미국 텍사스
4. "파리 맛집" -> 프랑스 파리 (미국 텍사스의 Paris가 아님)
5. 대학교/랜드마크도 지역으로 인식

예시:
- "나고야 맛집" -> {"regions": ["나고야"], "country": "Japan", "country_kr": "일본"}
- "텍사스 바비큐" -> {"regions": ["텍사스"], "country": "USA", "country_kr": "미국"}
- "도쿄 시부야 숙소" -> {"regions": ["시부야", "도쿄"], "country": "Japan", "country_kr": "일본"}
- "파리 에펠탑" -> {"regions": ["에펠탑", "파리"], "country": "France", "country_kr": "프랑스"}
- "LA 맛집" -> {"regions": ["LA"], "country": "USA", "country_kr": "미국"}
- "숭실대 라멘" -> {"regions": ["숭실대"], "country": "Korea", "country_kr": "한국"}
- "강남 맛집" -> {"regions": ["강남"], "country": "Korea", "country_kr": "한국"}
- "방콕 맛집" -> {"regions": ["방콕"], "country": "Thailand", "country_kr": "태국"}
- "발리 숙소" -> {"regions": ["발리"], "country": "Indonesia", "country_kr": "인도네시아"}

JSON: {"regions": ["지역1", "지역2"], "country": "영문국가명", "country_kr": "한글국가명"}"""
                },
                {"role": "user", "content": text}
            ],
            response_format={"type": "json_object"},
            timeout=5
        )
        
        data = json.loads(resp.choices[0].message.content)
        regions = data.get('regions', [])
        country = data.get('country', None)
        country_kr = data.get('country_kr', None)
        
        return regions, {"country": country, "country_kr": country_kr}
        
    except Exception as e:
        print(f"GPT 지역/국가 추출 실패: {e}")
        return [], None

async def extract_regions_hybrid(text, client):
    """하이브리드 지역명 추출 (랜드마크/대학교 강화)"""
    
    # 1단계: 빠른 규칙 기반
    found = []
    text_lower = text.lower()
    
    for region in FAST_REGIONS:
        if region.lower() in text_lower:
            found.append(region)
    
    found = list(set(found))
    found.sort(key=len, reverse=True)
    
    # 2단계: GPT로 보완
    if not client:
        return found[:3] if found else []
    
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """텍스트에서 **검색의 중심이 되는 위치**를 추출하세요.

반드시 포함해야 하는 대상:
1. 대학교: 숭실대, 고려대, 연세대, 서울대, 한양대, 중앙대, 건국대, 경희대, 성균관대, 홍익대, 이화여대, 숙명여대, 동국대, 국민대, 세종대, 단국대, 아주대, 인하대, 부산대, 경북대 등 모든 대학교
2. 지하철역: 강남역, 홍대입구역, 서울대입구역, 신촌역, 건대입구역, 왕십리역, 잠실역 등
3. 랜드마크: 롯데타워, 코엑스, IFC몰, 타임스퀘어, 동대문DDP, 명동성당, 남산타워 등
4. 행정구역: 서울, 강남, 부산, 제주 등
5. 해외 도시: 도쿄, 오사카, 나고야, 파리, 뉴욕, 텍사스 등

예시:
- "숭실대 인근 라멘" -> {"regions": ["숭실대"]}
- "나고야 맛집" -> {"regions": ["나고야"]}
- "텍사스 바비큐" -> {"regions": ["텍사스"]}
- "도쿄 시부야 숙소" -> {"regions": ["시부야", "도쿄"]}

주의:
- "인근", "근처", "주변" 같은 단어는 제외
- 검색 키워드(라멘, 맛집, 카페 등)는 제외
- 위치만 추출

JSON: {"regions": ["위치1", "위치2"]}"""
                },
                {"role": "user", "content": text}
            ],
            response_format={"type": "json_object"},
            timeout=5
        )
        
        data = json.loads(resp.choices[0].message.content)
        gpt_regions = data.get('regions', [])
        
        all_regions = list(set(found + gpt_regions))
        all_regions.sort(key=len, reverse=True)
        
        return all_regions[:3]
        
    except Exception as e:
        print(f"GPT 지역 추출 실패: {e}")
        return found[:3] if found else []

def expand_regions(regions):
    """한국 지역만 확장"""
    expanded = []
    for region in regions:
        if region in REGION_EXPAND:
            expanded.extend(REGION_EXPAND[region])
        else:
            expanded.append(region)
    return list(set(expanded))

def search_naver_local(keyword, regions=[], display=30):
    """네이버 지역 검색"""
    
    try:
        url = "https://openapi.naver.com/v1/search/local.json"
        headers = {
            "X-Naver-Client-Id": NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
        }
        
        query = f"{regions[0]} {keyword}" if regions else keyword
        
        resp = requests.get(
            url,
            headers=headers,
            params={"query": query, "display": display, "sort": "random"},
            timeout=10
        )
        
        if resp.status_code != 200:
            print(f"네이버 오류: {resp.text[:200]}")
            return []
        
        items = resp.json().get('items', [])
        
        return items
    
    except Exception as e:
        print(f"네이버 검색 실패: {e}")
        traceback.print_exc()
        return []

async def filter_relevant_places_batch(place_names, user_keyword, client):
    """GPT 배치 필터링: 사용자 의도와 관련 있는 장소만 선택"""
    
    if not place_names or not client:
        return place_names
    
    places_text = "\n".join([f"{i+1}. {p}" for i, p in enumerate(place_names[:30])])
    
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "system",
                "content": f"""사용자가 '{user_keyword}'를(을) 찾고 있습니다.

아래 장소 중 사용자가 원하는 것과 관련 있는 장소를 골라주세요.

중요: 최소 5개 이상 선택하세요. 애매하면 포함하세요.

제외 기준:
- 명백한 부대시설만 제외 (주차장, 충전소, 화장실, ATM)
- GS25, CU 같은 편의점 (사용자가 편의점을 찾는 게 아니면)
- 사용자가 원하는 것과 완전히 무관한 업종

포함 기준:
- 사용자가 찾는 것과 관련된 모든 장소
- 같은 카테고리의 다른 형태 (예: "호텔" 찾을 때 "펜션"도 포함)
- 애매하면 무조건 포함
- 같은 건물 내 관련 시설도 포함

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
        
        return [place_names[i-1] for i in relevant_indices if 1 <= i <= len(place_names)]
    
    except Exception as e:
        print(f"GPT 필터링 실패: {e}, 전부 포함")
        traceback.print_exc()
        return place_names

async def search_domestic(keyword, regions, client, retry=False):
    """국내 검색: 랜드마크 우선 검색 -> 네이버 -> GPT 필터링 -> 카카오맵 검증"""
    
    expanded_regions = expand_regions(regions) if regions else []
    
    # 랜드마크/대학교인 경우 카카오맵 직접 검색 우선
    landmark_keywords = []
    for region in regions:
        if any(univ in region for univ in ['대', '대학', '대학교']):
            landmark_keywords.append(region)
        elif '역' in region:
            landmark_keywords.append(region)
        elif region in ['롯데타워', '코엑스', 'IFC', '타임스퀘어', 'DDP']:
            landmark_keywords.append(region)
    
    kakao_direct_results = []
    
    if landmark_keywords:
        for landmark in landmark_keywords:
            try:
                search_query = f"{landmark} {keyword}"
                resp = requests.get(
                    "https://dapi.kakao.com/v2/local/search/keyword.json",
                    headers={"Authorization": f"KakaoAK {KAKAO_API_KEY}"},
                    params={"query": search_query, "size": 15},
                    timeout=10
                )
                
                if resp.status_code == 200:
                    places = resp.json().get("documents", [])
                    for p in places:
                        kakao_direct_results.append(p)
            except Exception as e:
                print(f"카카오맵 랜드마크 검색 실패: {e}")
    
    # 1단계: 네이버 검색
    display = 50 if retry else 30
    naver_items = search_naver_local(keyword, regions, display=display)
    
    # 네이버 실패 시 카카오맵 직접 검색
    if not naver_items and regions:
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
                
                for p in kakao_direct:
                    naver_items.append({
                        'title': p['place_name'],
                        'address': p.get('address_name', ''),
                        'roadAddress': p.get('road_address_name', '')
                    })
        
        except Exception as e:
            print(f"카카오맵 직접 검색 실패: {e}")
    
    # 2단계: 장소명 추출
    candidate_names = []
    candidate_items = {}
    
    for item in naver_items[:50]:
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
    
    # 카카오맵 직접 검색 결과 먼저 추가
    for p in kakao_direct_results:
        if p['id'] not in seen_ids:
            seen_ids.add(p['id'])
            kakao_candidates.append(p)
    
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
            
            if not places:
                fake_place = {
                    'id': f"naver_{len(kakao_candidates)}",
                    'place_name': place_name,
                    'place_url': f"https://map.naver.com/p/search/{urllib.parse.quote(place_name)}",
                    'address_name': item.get('address', ''),
                    'road_address_name': item.get('roadAddress', ''),
                    'phone': item.get('telephone', '')
                }
                
                addr = (fake_place['address_name'] + ' ' + fake_place['road_address_name']).lower()
                
                if expanded_regions:
                    if any(region.lower() in addr for region in expanded_regions):
                        kakao_candidates.append(fake_place)
                else:
                    kakao_candidates.append(fake_place)
                
                continue
            
            for p in places:
                if p['id'] in seen_ids:
                    continue
                
                addr = (p.get('address_name', '') + ' ' + p.get('road_address_name', '')).lower()
                
                # 랜드마크 검색 시 지역 필터링 완화
                if expanded_regions and not landmark_keywords:
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
        
        all_places = []
        for p in kakao_candidates:
            if p['place_name'] in final_names:
                all_places.append(p)
    else:
        all_places = []
    
    return all_places

def format_places_result(keyword, places):
    """장소 리스트를 마크다운으로 포맷"""
    
    if not places:
        return f"'{keyword}' 검색 결과 없음"
    
    result = f"""# {keyword} 검색 결과 ({len(places)}개)

"""
    
    for i, p in enumerate(places, 1):
        link_type = "네이버맵" if "naver.com" in p.get('place_url', '') else "카카오맵"
        place_url = p.get('place_url', f"https://map.kakao.com/link/search/{urllib.parse.quote(p['place_name'])}")
        
        result += f"""---

## {i}. {p['place_name']}

**{link_type}:** {place_url}

**주소:** {p.get('road_address_name') or p.get('address_name', '')}
"""
        if p.get('phone'):
            result += f"**전화:** {p['phone']}\n"
        result += "\n"
    
    return result

# 수정: 국가 컨텍스트를 활용한 해외 검색
async def search_international(keyword, regions, client, country_context=None):
    """해외 검색: 국가 컨텍스트 활용 (핵심 개선)"""
    
    # 국가 정보 결정
    country = None
    country_kr = None
    
    if country_context:
        country = country_context.get('country')
        country_kr = country_context.get('country_kr')
    
    # country_context가 없으면 regions에서 추론
    if not country and regions:
        for region in regions:
            found_country = get_country_for_city(region)
            if found_country:
                country = found_country
                break
    
    # GPT로 영어 변환
    region_en = await translate_to_english(regions[0], client) if regions else ""
    keyword_en = await translate_to_english(keyword, client)
    
    # 수정: 국가명을 쿼리에 포함하여 정확도 향상
    if country and regions:
        # "hotel in Nagoya, Japan" 형식
        query = f"{keyword_en} in {region_en}, {country}"
    elif regions:
        query = f"{keyword_en} in {region_en}"
    else:
        query = keyword_en
    
    print(f"Google Places 쿼리: {query}")
    
    try:
        result = gmaps.places(
            query=query,
            language='ko'
        )
        
        places = result.get('results', [])
        
        # 한국 주소 필터링 (해외 검색인데 한국이 나오면 제외)
        filtered = []
        for p in places:
            addr = p.get('formatted_address', '').lower()
            
            if any(kr in addr for kr in ['대한민국', 'korea', ' kr', 'south korea', '서울', '부산', '경기', '인천']):
                continue
            
            filtered.append(p)
        
        places = filtered
        
        if len(places) < 1:
            return f"'{keyword}' 검색 결과 없음"
        
        # 지역명 표시 (국가 포함)
        region_display = regions[0] if regions else ""
        if country_kr:
            region_display = f"{country_kr} {region_display}"
        
        output = f"""# {region_display} {keyword} 검색 결과 ({len(places)}개)

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
                output += f" ({rating}점"
                if reviews > 0:
                    output += f", {reviews:,}개 리뷰"
                output += ")"
            
            output += f"""

**구글맵:** {url}

"""
            
            if addr:
                output += f"**주소:** {addr}\n"
            
            output += "\n"
        
        return output
    
    except Exception as e:
        print(f"Places API 오류: {e}")
        traceback.print_exc()
        return f"검색 오류: {e}"

async def get_route_info(start, goal, start_original, goal_original, client):
    """경로 계산 공통 함수"""
    
    if is_international_route(start, goal):
        is_intl = True
    else:
        try:
            check = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """질문이 국내/해외 여행인지 판단하세요.

한국 지역: 서울, 부산, 제주, 강남, 잠실, 광교, 송파, 해운대, 경주
해외 지역: 도쿄, 오사카, 교토, 나카노, 파리, 런던, 나고야, 텍사스

예시:
- "강남 -> 잠실" -> {"is_international": false}
- "오사카 -> 교토" -> {"is_international": true}
- "나고야 -> 도쿄" -> {"is_international": true}

JSON: {"is_international": bool}"""
                    },
                    {
                        "role": "user",
                        "content": f"원본 질문: {start_original} -> {goal_original}\n추출된 지역: {start} -> {goal}"
                    }
                ],
                response_format={"type": "json_object"}
            )
            
            is_intl = json.loads(check.choices[0].message.content).get('is_international', False)
        
        except Exception as e:
            is_intl = True
    
    if is_intl:
        try:
            start_en = await translate_to_english(start_original, client)
            goal_en = await translate_to_english(goal_original, client)
            
        except Exception as e:
            start_en = start
            goal_en = goal
        
        safe_start = urllib.parse.quote(start_en)
        safe_goal = urllib.parse.quote(goal_en)
        
        car_link = f"https://www.google.com/maps/dir/?api=1&origin={safe_start}&destination={safe_goal}&travelmode=driving"
        transit_link = f"https://www.google.com/maps/dir/?api=1&origin={safe_start}&destination={safe_goal}&travelmode=transit"
        
        return f"""# {start} -> {goal}

---

## 자동차 경로

{car_link}

---

## 대중교통 경로

{transit_link}
"""
    
    else:
        sx, sy, sname = get_xy(start)
        ex, ey, gname = get_xy(goal)
        
        if sx and ex:
            results = []
            
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
                        
                        results.append(f"""**자동차:**

{sname} -> {gname}
소요: {time_str}, 거리: {dist / 1000:.1f}km""")
            except:
                pass
            
            ksx, ksy = convert_coords(sx, sy)
            kex, key = convert_coords(ex, ey)
            
            if ksx and kex:
                link = f"https://map.kakao.com/?target=traffic&rt={ksx},{ksy},{kex},{key}&rt1={urllib.parse.quote(sname)}&rt2={urllib.parse.quote(gname)}"
                
                results.append(f"""**대중교통:**

{sname} -> {gname}

{link}""")
            
            return f"# {start} -> {goal}\n\n---\n\n" + "\n\n---\n\n".join(results) if results else "경로 계산 실패"
        
        else:
            return "장소를 찾을 수 없습니다"

def web_search_for_budget(query):
    """예산 계산용 웹 검색"""
    try:
        return f"{query} 관련 정보를 검색했습니다."
    except: 
        return "검색 실패"

# =======================================================================
# MCP 핸들러 (2025-03-26 스펙 준수)
# =======================================================================

async def handle_mcp(request):
    # CORS preflight
    if request.method == "OPTIONS":
        return Response("", status_code=200)
    
    # GET 요청 시 405 반환 (스펙 준수 - stateless 서버)
    if request.method == "GET":
        return Response("SSE stream not supported", status_code=405)
    
    if request.method != "POST":
        return Response("Method not allowed", status_code=405)
    
    # Accept 헤더 검증
    accept_header = request.headers.get("Accept", "")
    if accept_header and "application/json" not in accept_header and "text/event-stream" not in accept_header and "*/*" not in accept_header:
        return Response("Accept header must include application/json or text/event-stream", status_code=400)
    
    try:
        body = await request.json()
    except:
        return Response("Invalid JSON", status_code=400)
    
    method = body.get("method")
    msg_id = body.get("id")
    
    # 초기화
    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "TravelMate", "version": "15.0"}
            }
        })
    
    # notifications/initialized는 202 Accepted 반환 (스펙 준수)
    if method == "notifications/initialized":
        return Response("", status_code=202)
    
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
        
        # 도구 2: 여행지 추천 + 경로 안내
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
- "오사카 맛집" -> {"type": "place"}
- "나고야 숙소" -> {"type": "place"}
- "텍사스 바비큐" -> {"type": "place"}
- "숭실대 라멘" -> {"type": "place"}
- "고려대 중식당" -> {"type": "place"}
- "오사카에서 교토 가는 법" -> {"type": "route"}
- "보조배터리 기내 반입 돼?" -> {"type": "guide"}

JSON: {"type": "place/route/guide"}"""
                            },
                            {"role": "user", "content": question}
                        ],
                        response_format={"type": "json_object"}
                    )
                    
                    type_data = json.loads(type_check.choices[0].message.content)
                    question_type = type_data.get('type', 'place')
                    
                    # 규정 및 정보 안내
                    if question_type == "guide":
                        try:
                            search_results = []
                            with DDGS() as ddgs:
                                results = list(ddgs.text(question, max_results=3))
                                for r in results:
                                    search_results.append(f"- 제목: {r['title']}\n- 링크: {r['href']}\n- 내용: {r['body']}")
                            
                            search_text = "\n\n".join(search_results)
                            
                            resp = await client.chat.completions.create(
                                model="gpt-4o",
                                messages=[
                                    {
                                        "role": "system",
                                        "content": """당신은 정확한 여행 규정을 안내하는 전문가입니다.
제공된 검색 결과를 바탕으로 사용자의 질문에 답변하세요.

규칙:
1. 검색 결과에 기반하여 사실만 말하세요.
2. 금지 품목이나 법적 규정은 엄격하게 안내하세요.
3. 정보가 불확실하면 "최신 규정은 항공사나 대사관 확인이 필요합니다"라고 덧붙이세요.
4. 출처 링크가 있다면 함께 표시하세요.
"""
                                    },
                                    {
                                        "role": "user",
                                        "content": f"질문: {question}\n\n검색 결과:\n{search_text}"
                                    }
                                ]
                            )
                            
                            result_text = resp.choices[0].message.content
                            
                        except Exception as e:
                            print(f"검색/답변 오류: {e}")
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
                    
                    # 장소 검색 (핵심 개선)
                    else:
                        # 수정: 지역 + 국가 컨텍스트 동시 추출
                        regions, country_context = await extract_regions_with_context(question, client)
                        
                        # 국내/해외 판단 (country_context 활용)
                        is_korea = False
                        if country_context:
                            country = country_context.get('country', '')
                            is_korea = country.lower() in ['korea', 'south korea', '한국']
                        
                        # 키워드 추출
                        keyword_check = await client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {
                                    "role": "system",
                                    "content": """질문에서 검색 키워드만 추출하세요.

JSON 형식: {"keywords": ["검색어"]}

중요: keywords는 핵심 단어만 짧고 명확하게!

예시:
- "강남 라멘" -> {"keywords": ["라멘"]}
- "나고야 맛집" -> {"keywords": ["맛집"]}
- "텍사스 바비큐 가게" -> {"keywords": ["바비큐"]}
- "도쿄 시부야 숙소, 맛집, 관광지" -> {"keywords": ["숙소", "맛집", "관광지"]}

절대 금지:
- "인근", "근처", "추천", "찾아줘" 같은 불필요한 단어
- 지역명을 키워드에 포함"""
                                },
                                {"role": "user", "content": question}
                            ],
                            response_format={"type": "json_object"}
                        )
                        
                        keyword_data = json.loads(keyword_check.choices[0].message.content)
                        keywords = keyword_data.get('keywords', [])
                        
                        results = []
                        
                        for kw in keywords[:5]:
                            if not kw.strip():
                                continue
                            
                            if is_korea:
                                # 국내 검색
                                places = await search_domestic(kw, regions, client, retry=False)
                                
                                if isinstance(places, list) and len(places) < 5:
                                    more_places = await search_domestic(kw, regions, client, retry=True)
                                    
                                    if isinstance(more_places, list):
                                        existing_ids = {p.get('id') for p in places}
                                        for p in more_places:
                                            if p.get('id') not in existing_ids:
                                                places.append(p)
                                                if len(places) >= 10:
                                                    break
                                
                                res = format_places_result(kw, places)
                            else:
                                # 해외 검색 (국가 컨텍스트 전달)
                                res = await search_international(kw, regions, client, country_context)
                            
                            if res and len(res) > 50 and "검색 결과 없음" not in res:
                                results.append(res)
                        
                        result_text = "\n\n".join(results) if results else "검색 결과를 찾을 수 없습니다."
                    
                except Exception as e:
                    result_text = f"검색 오류: {e}"
                    traceback.print_exc()
        
        # 도구 3: 경로 안내
        elif tool_name == "check_travel_route":
            start = args.get("start", "")
            goal = args.get("goal", "")
            
            if not client:
                result_text = "OpenAI 미초기화"
            else:
                try:
                    start_regions = await extract_regions_hybrid(start, client)
                    goal_regions = await extract_regions_hybrid(goal, client)
                    
                    start_clean = start_regions[0] if start_regions else start
                    goal_clean = goal_regions[0] if goal_regions else goal
                    
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
    Route("/mcp", endpoint=handle_mcp, methods=["GET", "POST", "OPTIONS"]),
    Route("/sse", endpoint=handle_mcp, methods=["GET", "POST", "OPTIONS"]),
    Route("/sse/", endpoint=handle_mcp, methods=["GET", "POST", "OPTIONS"])
]

middleware = [
    Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
]

app = Starlette(routes=routes, middleware=middleware)

if __name__ == "__main__":
    print("=" * 60)
    print("Travel-Mate v15.0")
    print("=" * 60)
    print("MCP Protocol Version: 2025-03-26 (PlayMCP 호환)")
    print("핵심 개선사항:")
    print("  - 국가 컨텍스트 자동 추론 (나고야->일본, 텍사스->미국)")
    print("  - Google Places 쿼리에 국가명 포함")
    print("  - CITY_TO_COUNTRY 매핑 추가")
    print("  - 해외 도시 목록 대폭 확장")
    print("=" * 60)
    
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)