# 📡 선행기구개발그룹 뉴스 레이더

모바일 / 전기차 / 부품·신소재 기술 뉴스를 자동 수집하여
로컬 **Gemma 3 (Ollama)** 로 기구개발 엔지니어 관점에서 요약하고,
PPT 리포트로 자동 변환해주는 Streamlit 웹 애플리케이션.

## 🧱 구성

```
News_radar/
├── app.py              # Streamlit 메인 (3컬럼 레이아웃)
├── news_crawler.py     # Google News RSS + BeautifulSoup
├── gemma_client.py     # Ollama / Gemma 3 클라이언트
├── ppt_generator.py    # python-pptx 기반 슬라이드 빌더
└── requirements.txt
```

## ⚙️ 사전 요구사항

1) **Ollama** 설치 후 Gemma 3 모델 풀

```bash
# https://ollama.com 에서 설치
ollama serve                 # 11434 포트에서 실행
ollama pull gemma3           # (또는 gemma3:4b / gemma3:12b 등)
```

2) **Python 패키지 설치**

```bash
pip install streamlit requests beautifulsoup4 lxml python-pptx feedparser
# 또는
pip install -r requirements.txt
```

## ▶️ 실행

```bash
streamlit run app.py
```

브라우저가 자동으로 열리며 3컬럼 대시보드가 표시됩니다.

## 🖼️ 화면 구성

| 컬럼 | 기능 |
|------|------|
| 좌측 | 키워드별 실시간 뉴스 피드(아래→위 스크롤 애니메이션, 1시간 캐시) |
| 중간 | Gemma 3 채팅 컨트롤러 (구조/소재/공법 분석 퀵 프롬프트 포함) |
| 우측 | 선택 기사 요약 + `.pptx` 리포트 다운로드 |

## 🔍 수집 키워드 (기본)

`모바일 힌지`, `폴더블 힌지`, `EV 배터리 케이스`, `전기차 배터리 팩`,
`전기차 부품`, `신소재 부품`, `마그네슘 합금 부품`, `탄소복합소재 부품`,
`갤럭시 폴드 힌지`, `스마트폰 방열`

`news_crawler.py` 의 `SEARCH_KEYWORDS` / `FILTER_TOKENS` 를 수정해 그룹 관심
영역에 맞게 커스터마이즈할 수 있습니다.

## 📝 시스템 프롬프트

`gemma_client.SYSTEM_PROMPT` 에 정의되어 있으며, 다음 5개 항목을 반드시
포함하도록 강제합니다:

1. 핵심 기술 사양 (수치 위주)
2. 사용 소재 (등급/규격)
3. 가공/조립 공법
4. 경쟁사 동향 / 차별 포인트
5. 양산 적용 가능성 / 리스크

## 📤 PPT 리포트

- 슬라이드 1: 표지 (브랜드 헤더 + 기사 제목 + 출처)
- 슬라이드 2: Executive Summary - 핵심 5개 불릿
- 슬라이드 3..N: 기술 분석 상세 불릿 (페이지당 7개)
- 마지막 슬라이드: 원문 링크
