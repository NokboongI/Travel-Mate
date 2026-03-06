# Travel-Mate ✈️

Travel-Mate는 Model Context Protocol(MCP) 규격을 지원하는 여행 보조용 웹 서버입니다. 
사용자의 질문과 텍스트 데이터를 LLM으로 분석하여 국내외 맞춤형 장소 추천, 경로 탐색, 예산 계산, 일정표 작성 등의 기능을 수행합니다.

## 주요 기능 (Features)

* **상황에 맞는 API 자동 분기**: 입력된 텍스트에서 지역과 국가 컨텍스트를 추출하여, 국내 검색은 카카오 및 네이버 API를, 해외 검색은 구글 맵스 API를 사용하도록 자동 분기합니다.
* **LLM 기반 데이터 정제**: OpenAI의 GPT 모델을 활용하여 단순 검색을 넘어 사용자 의도에 맞는 장소만 필터링하고 검색어의 정확도를 높입니다.
* **통합 검색 시스템**: 장소 탐색뿐만 아니라 DuckDuckGo 웹 검색을 활용하여 수하물 규정, 비자, 에티켓 등 최신 여행 정보와 예산 견적을 제공합니다.

## 제공하는 MCP 도구 (Tools)

MCP 클라이언트에서 호출하여 사용할 수 있는 4가지 주요 도구를 제공합니다.

1. `analyze_chat_history`: 텍스트 대화 로그(예: 카카오톡 대화)를 분석하여 여행 일정표를 마크다운 형식으로 작성합니다.
2. `ask_travel_advisor`: 질문의 유형(장소 탐색, 경로 질문, 여행 규정)을 파악하여 알맞은 여행지/숙소/맛집을 추천하거나 규정 및 팁을 안내합니다.
3. `check_travel_route`: 출발지와 도착지를 입력받아 자동차 및 대중교통 이동 소요 시간을 계산하고 카카오맵 또는 구글맵 링크를 제공합니다.
4. `calculate_budget`: 여행지, 인원, 기간 정보를 바탕으로 웹 검색을 진행하여 대략적인 여행 예산 견적서를 산출합니다.

## 환경 변수 (Environment Variables)

이 서버를 정상적으로 구동하려면 다음과 같은 API 키가 필요합니다. 서버 실행 전 시스템 환경 변수로 등록해주세요.

```bash
OPENAI_API_KEY="your_openai_api_key"
KAKAO_API_KEY="your_kakao_api_key"
GOOGLE_API_KEY="your_google_maps_api_key"
NAVER_CLIENT_ID="your_naver_client_id"
NAVER_CLIENT_SECRET="your_naver_client_secret"
PORT="8000" # 기본값 8000
