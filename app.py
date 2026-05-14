"""선행기구개발그룹 뉴스 레이더 - Streamlit 메인 앱.

3컬럼 레이아웃:
  좌측  - 실시간 뉴스 피드 (1시간 캐시, 위로 흐르는 애니메이션)
  중간  - Gemma 3 컨트롤러 (채팅)
  우측  - 선택된 기사 요약 + PPT 생성
"""
from __future__ import annotations

import html
import re
from datetime import datetime

import streamlit as st

import gemma_client
import news_crawler
import sentiment_classifier
from ppt_generator import build_pptx


st.set_page_config(
    page_title="선행기구개발그룹 뉴스 레이더",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# 글로벌 스타일 + 뉴스 피드 애니메이션
# ---------------------------------------------------------------------------
GLOBAL_CSS = """
<style>
/* Apple Compare 디자인 톤 매핑 — News_radar */
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root {
    --bg: #ffffff;
    --surface: #f5f5f7;
    --surface-2: #fafafa;
    --ink: #1d1d1f;
    --ink-2: #6e6e73;
    --ink-3: #86868b;
    --line: #d2d2d7;
    --line-soft: rgba(0,0,0,.06);
    --accent: #0071e3;
    --accent-link: #06c;
    --ok-bg: #e8f5ee;
    --ok-ink: #1f7a3a;
    --bad-bg: #fdebeb;
    --bad-ink: #c43e3e;
    --ls-tight: -0.022em;
    --ls-wide: .04em;
    --radius: 14px;
    --radius-s: 10px;
}

/* 베이스 폰트 — SF Pro Display/Text + 한글 폴백 */
html, body, [class*="css"]  {
    font-family: "Inter", "Noto Sans KR", -apple-system, BlinkMacSystemFont,
                 "SF Pro Display", "SF Pro Text", "Pretendard",
                 "Apple SD Gothic Neo", "Nanum Gothic", system-ui, sans-serif !important;
    -webkit-font-smoothing: antialiased;
    letter-spacing: -.005em;
    color: var(--ink);
}

/* 헤더 — 미니멀, 흰 배경 + 가는 하단 라인 */
.main-header {
    background: var(--bg);
    border-bottom: 1px solid var(--line);
    padding: 24px 8px 18px;
    border-radius: 0;
    color: var(--ink);
    margin-bottom: 18px;
}
.main-header h1 {
    margin: 0;
    font-size: 32px;
    font-weight: 700;
    letter-spacing: var(--ls-tight);
    line-height: 1.1;
}
.main-header p  {
    margin: 8px 0 0;
    font-size: 15px;
    color: var(--ink-2);
    letter-spacing: -.005em;
}

/* 컬럼 카드 — 흰 배경 + hairline */
.col-card {
    background: var(--bg);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    padding: 18px;
    color: var(--ink);
}
.col-card h3 {
    margin: 0 0 12px 0;
    color: var(--ink);
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: var(--ls-wide);
    border-bottom: 1px solid var(--line-soft);
    padding-bottom: 10px;
}

/* 뉴스 피드 (티커) — 흰 배경 + subtle border */
.ticker-wrapper {
    height: 520px;
    overflow: hidden;
    position: relative;
    background: var(--bg);
    border: 1px solid var(--line);
    border-radius: var(--radius-s);
    mask-image: linear-gradient(to bottom,
        transparent 0%, #000 8%, #000 92%, transparent 100%);
}
.ticker-track {
    position: absolute;
    bottom: -100%;
    left: 0;
    right: 0;
    animation: scroll-up 60s linear infinite;
}
.ticker-track:hover { animation-play-state: paused; }
@keyframes scroll-up {
    0%   { transform: translateY(0); }
    100% { transform: translateY(-100%); }
}
.ticker-item {
    padding: 12px 14px;
    margin: 8px 10px;
    background: var(--surface);
    border-left: 3px solid var(--accent);
    border-radius: 8px;
    color: var(--ink);
    font-size: 13.5px;
    line-height: 1.5;
    letter-spacing: -.005em;
    transition: background 150ms cubic-bezier(.2,.8,.2,1);
}
.ticker-item:hover { background: var(--bg); box-shadow: 0 1px 3px rgba(0,0,0,.04); }
.ticker-item .kw {
    display: inline-block;
    background: var(--ink);
    color: var(--bg);
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: .04em;
    text-transform: uppercase;
    padding: 3px 8px;
    border-radius: 999px;
    margin-right: 8px;
    vertical-align: middle;
}
.ticker-item .src {
    color: var(--ink-3);
    font-size: 11.5px;
    letter-spacing: -.003em;
}

/* sentiment 색상 토큰 */
:root {
    --sent-pos: #34c759;
    --sent-pos-bg: #e8f9ed;
    --sent-neg: #ff3b30;
    --sent-neg-bg: #ffeceb;
    --sent-neu: #8e8e93;
    --sent-neu-bg: #f5f5f7;
}

/* sentiment 통계 헤더 */
.sent-stats {
    display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
    margin: 8px 0 12px;
}
.sent-pill {
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 12px; font-weight: 600;
    padding: 4px 10px; border-radius: 999px;
    letter-spacing: -.005em;
}
.sent-pill-pos { background: var(--sent-pos-bg); color: #1a8a36; }
.sent-pill-neg { background: var(--sent-neg-bg); color: #c0271f; }
.sent-pill-neu { background: var(--sent-neu-bg); color: var(--ink-2); }
.sent-total { margin-left: auto; font-size: 11px; color: var(--ink-2); }

/* 기사 카드 (카드 그리드) */
.art-card {
    background: var(--bg);
    border: 1px solid var(--line);
    border-left: 3px solid var(--ink-2);
    border-radius: 10px;
    padding: 12px 14px;
    margin: 8px 0;
    transition: transform 150ms cubic-bezier(.2,.8,.2,1), box-shadow 150ms;
    cursor: pointer;
}
.art-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,.06);
}
.art-card.card-sent-positive { border-left-color: var(--sent-pos); }
.art-card.card-sent-negative { border-left-color: var(--sent-neg); }
.art-card.card-sent-neutral  { border-left-color: var(--sent-neu); }
.art-card-selected {
    background: var(--surface);
    border-color: var(--ink);
    box-shadow: 0 0 0 2px rgba(29,29,31,.08);
}
.art-card-head {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 6px;
}
.sent-badge {
    display: inline-flex; align-items: center; gap: 3px;
    font-size: 10.5px; font-weight: 600;
    padding: 2px 8px; border-radius: 999px;
    letter-spacing: -.003em;
}
.sent-badge-positive { background: var(--sent-pos-bg); color: #1a8a36; }
.sent-badge-negative { background: var(--sent-neg-bg); color: #c0271f; }
.sent-badge-neutral  { background: var(--sent-neu-bg); color: var(--ink-2); }
.art-src {
    font-size: 11px; color: var(--ink-3);
    max-width: 60%;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.art-title {
    font-size: 14px; font-weight: 600;
    line-height: 1.35; letter-spacing: -.008em;
    color: var(--ink);
    margin: 4px 0 6px;
}
.art-summary {
    font-size: 12px; color: var(--ink-2);
    line-height: 1.45;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden;
}
.art-meta {
    margin-top: 8px;
    display: flex; justify-content: space-between; align-items: center;
}
.art-kw {
    display: inline-block;
    font-size: 10px; font-weight: 500;
    padding: 2px 8px; border-radius: 999px;
    background: var(--surface); color: var(--ink-2);
    letter-spacing: .02em; text-transform: uppercase;
}

/* sentiment 필터 라디오 가로 정렬 */
[data-testid="stHorizontalBlock"] [data-testid="stRadio"] > div {
    flex-direction: row !important;
    gap: 8px;
}

/* 상태 뱃지 */
.status-pill {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: .02em;
}
.status-ok   { background: var(--ok-bg);  color: var(--ok-ink); }
.status-bad  { background: var(--bad-bg); color: var(--bad-ink); }

/* Streamlit 기본 위젯 정제 */
[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--line);
}
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] .stMarkdown h3 {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: var(--ls-wide);
    color: var(--ink);
    font-weight: 600;
    margin-top: 18px;
}
.stButton > button {
    background: var(--ink);
    color: var(--bg);
    border: 1px solid var(--ink);
    border-radius: 999px;
    padding: 8px 18px;
    font-weight: 500;
    letter-spacing: -.005em;
    transition: opacity 150ms;
}
.stButton > button:hover { opacity: .85; background: var(--ink); color: var(--bg); }
.stTextInput input, .stTextArea textarea, .stSelectbox > div > div {
    border: 1px solid var(--line) !important;
    border-radius: 10px !important;
    background: var(--bg) !important;
    font-family: inherit !important;
    letter-spacing: -.005em;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px rgba(0,113,227,.18) !important;
}

/* 채팅 메시지 카드 (Gemma 컬럼) */
[data-testid="stChatMessage"] {
    background: var(--surface);
    border: 1px solid var(--line-soft);
    border-radius: var(--radius-s);
    padding: 12px 14px;
    margin: 8px 0;
}
[data-testid="stChatMessage"][data-testid*="user"] {
    background: var(--ink);
    color: var(--bg);
}

/* 다운로드 버튼 강조 */
[data-testid="stDownloadButton"] > button {
    background: var(--accent);
    border-color: var(--accent);
}

/* 마크다운 코드 */
code {
    background: var(--surface) !important;
    color: var(--ink) !important;
    border: 1px solid var(--line-soft);
    border-radius: 4px;
    padding: 1px 6px;
    font-size: .92em;
}
</style>
"""
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 세션 상태 초기화
# ---------------------------------------------------------------------------
def _init_state() -> None:
    ss = st.session_state
    ss.setdefault("articles", [])
    ss.setdefault("sources", [
        "google", "geeknews",
        "zdnetkr", "ddaily", "venturesquare",
        "thelec", "irobotnews", "epnc",
    ])
    ss.setdefault("selected_idx", None)
    ss.setdefault("summary", "")
    ss.setdefault("chat_history", [])  # [{role, content}]
    ss.setdefault("model_name", gemma_client.DEFAULT_MODEL)
    ss.setdefault("sentiment_filter", "all")   # all | positive | negative | neutral
    ss.setdefault("ollama_url", gemma_client.OLLAMA_BASE_URL)
    # LLM 백엔드 — Streamlit Cloud 호스트면 'groq' 기본, 로컬이면 'ollama'
    import os
    default_backend = "groq" if os.environ.get("STREAMLIT_SHARING") or os.environ.get("HOSTNAME","").startswith("streamlit") else "ollama"
    ss.setdefault("llm_backend", default_backend)
    ss.setdefault("last_refresh", None)


_init_state()


# ---------------------------------------------------------------------------
# 사이드바: 환경설정
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ 시스템 설정")

    # ---- LLM 백엔드 선택 ----
    backend_options = {
        "Groq (Cloud, llama-3.3-70b)": "groq",
        "Gemini (Cloud, 2.0 Flash)":    "gemini",
        "Ollama (로컬, Gemma 3)":       "ollama",
    }
    current_label = next(
        (l for l, k in backend_options.items() if k == st.session_state.llm_backend),
        list(backend_options.keys())[0]
    )
    selected = st.radio(
        "LLM 엔진",
        list(backend_options.keys()),
        index=list(backend_options.keys()).index(current_label),
        help="Streamlit Cloud에서는 Groq/Gemini 권장. 영채님 PC에서 로컬 테스트는 Ollama.",
    )
    st.session_state.llm_backend = backend_options[selected]
    backend = st.session_state.llm_backend

    # ---- 백엔드별 설정 ----
    if backend == "ollama":
        st.session_state.ollama_url = st.text_input(
            "Ollama Endpoint",
            value=st.session_state.ollama_url,
            help="로컬 Ollama 서버 주소",
        )
        available = gemma_client.is_available("ollama", base_url=st.session_state.ollama_url)
        if available:
            st.markdown("<span class='status-pill status-ok'>● Ollama 연결됨</span>", unsafe_allow_html=True)
            models = gemma_client.list_models("ollama", base_url=st.session_state.ollama_url)
            gemma_models = [m for m in models if "gemma" in m.lower()] or models
            if gemma_models:
                idx = gemma_models.index(st.session_state.model_name) if st.session_state.model_name in gemma_models else 0
                st.session_state.model_name = st.selectbox("모델 선택", gemma_models, index=idx)
            else:
                st.warning("설치된 모델 없음. `ollama pull gemma3` 실행 필요.")
        else:
            st.markdown("<span class='status-pill status-bad'>● Ollama 연결 실패</span>", unsafe_allow_html=True)
            st.caption("`ollama serve` 가 11434 포트에서 실행 중인지 확인. Streamlit Cloud에선 Groq/Gemini 사용 권장.")
            st.session_state.model_name = st.text_input("모델 이름", value=st.session_state.model_name)
        st.session_state.llm_api_key = ""
    else:
        # Groq / Gemini
        secret_name = "GROQ_API_KEY" if backend == "groq" else "GEMINI_API_KEY"
        api_key = ""
        try:
            api_key = st.secrets.get(secret_name, "") or ""
        except Exception:
            pass
        if not api_key:
            # 사용자가 직접 입력 가능 (개발용)
            api_key = st.text_input(
                f"{secret_name} (또는 Streamlit secrets에 추가)",
                type="password",
                value="",
                help=f"Streamlit Cloud 대시보드 → App Settings → Secrets 에 '{secret_name} = ...' 추가 권장.",
            )
        st.session_state.llm_api_key = api_key
        if api_key:
            st.markdown(f"<span class='status-pill status-ok'>● {backend.title()} 연결 준비</span>", unsafe_allow_html=True)
            models = gemma_client.list_models(backend)
            default_model = gemma_client.GROQ_DEFAULT_MODEL if backend == "groq" else gemma_client.GEMINI_DEFAULT_MODEL
            if st.session_state.model_name not in models:
                st.session_state.model_name = default_model
            idx = models.index(st.session_state.model_name) if st.session_state.model_name in models else 0
            st.session_state.model_name = st.selectbox("모델 선택", models, index=idx)
        else:
            st.markdown(f"<span class='status-pill status-bad'>● {backend.title()} API 키 미설정</span>", unsafe_allow_html=True)
            st.caption(f"`.streamlit/secrets.toml` 또는 Cloud 대시보드에 {secret_name} 추가하세요. README 참조.")

    st.markdown("---")
    st.markdown("### 📡 데이터 소스")

    # 카테고리별 그룹 + checkbox. 기본: 한국어 소스 활성, 영문 비활성
    DEFAULT_ACTIVE = {
        "google", "geeknews",
        "zdnetkr", "ddaily", "venturesquare",
        "thelec", "irobotnews", "epnc",
    }

    if "sources" not in st.session_state or not isinstance(st.session_state.sources, list):
        st.session_state.sources = sorted(DEFAULT_ACTIVE)

    col_a, col_b = st.columns(2)
    if col_a.button("전체 선택", use_container_width=True, key="src_all"):
        st.session_state.sources = list(news_crawler.SOURCES.keys())
        st.rerun()
    if col_b.button("모두 해제", use_container_width=True, key="src_none"):
        st.session_state.sources = []
        st.rerun()

    # 카테고리별 그룹화
    by_cat: dict[str, list] = {}
    for k, s in news_crawler.SOURCES.items():
        by_cat.setdefault(s.category, []).append(s)

    new_selection: list[str] = []
    for cat_key, cat_label in news_crawler.CATEGORY_LABELS.items():
        srcs = by_cat.get(cat_key, [])
        if not srcs:
            continue
        active_in_cat = sum(1 for s in srcs if s.key in st.session_state.sources)
        with st.expander(f"{cat_label} ({active_in_cat}/{len(srcs)})", expanded=(cat_key in {"kw","kr-it","kr-component"})):
            for s in srcs:
                checked = s.key in st.session_state.sources
                lang_badge = "한" if s.language == "ko" else "EN"
                if st.checkbox(f"{s.name}  ·  {lang_badge}", value=checked, key=f"src_cb_{s.key}"):
                    new_selection.append(s.key)
    st.session_state.sources = new_selection

    if not new_selection:
        st.warning("최소 1개 소스를 선택하세요.")

    st.markdown("---")
    st.markdown("### 🔍 수집 키워드 (Google News)")
    st.caption("아래 키워드 기반으로 Google News RSS에서 수집합니다. Geeknews는 사이트 자체 큐레이션 사용.")
    for kw in news_crawler.SEARCH_KEYWORDS:
        st.markdown(f"- {kw}")

    st.markdown("---")
    refresh_clicked = st.button("🔄 지금 새로고침", use_container_width=True)


# ---------------------------------------------------------------------------
# 헤더
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div class="main-header">
        <h1>📡 선행기구개발그룹 뉴스 레이더</h1>
        <p>모바일 · 전기차 · 부품 / 신소재 트렌드를 Gemma 3로 실시간 분석합니다.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# 뉴스 새로고침 (1시간 캐시)
# ---------------------------------------------------------------------------
def refresh_articles(force: bool = False) -> None:
    sources = st.session_state.get("sources") or ["google", "geeknews"]
    with st.spinner(f"뉴스 피드를 수집 중입니다... ({', '.join(sources)})"):
        articles = news_crawler.get_cached_articles(force_refresh=force, sources=sources)
    st.session_state.articles = articles
    st.session_state.last_refresh = datetime.now()


if refresh_clicked or not st.session_state.articles:
    refresh_articles(force=refresh_clicked)


# ---------------------------------------------------------------------------
# 3컬럼 레이아웃
# ---------------------------------------------------------------------------
col_left, col_mid, col_right = st.columns([1.0, 1.2, 1.4], gap="medium")


# ===========================================================================
# 좌측: 실시간 뉴스 피드 (애니메이션)
# ===========================================================================
with col_left:
    st.markdown("<div class='col-card'><h3>📰 기사 그리드</h3>", unsafe_allow_html=True)

    age = news_crawler.cache_age_seconds(st.session_state.get("sources"))
    if age is not None:
        mins = int(age // 60)
        st.caption(f"마지막 수집: {mins}분 전 · 자동 갱신 주기 1시간")

    articles = st.session_state.articles

    if not articles:
        st.info("수집된 기사가 없습니다. 사이드바의 새로고침을 눌러주세요.")
    else:
        # sentiment 계산 (캐시)
        if "sentiments" not in st.session_state or len(st.session_state.sentiments) != len(articles):
            st.session_state.sentiments = [
                sentiment_classifier.classify(a.title, a.summary_raw) for a in articles
            ]
        sents = st.session_state.sentiments
        stats = sentiment_classifier.stats(sents)

        # 통계 헤더
        st.markdown(
            f"""<div class='sent-stats'>
                <span class='sent-pill sent-pill-pos'>🟢 긍정 {stats['positive']}</span>
                <span class='sent-pill sent-pill-neg'>🔴 부정 {stats['negative']}</span>
                <span class='sent-pill sent-pill-neu'>⚪ 중립 {stats['neutral']}</span>
                <span class='sent-total'>총 {stats['total']}건</span>
            </div>""",
            unsafe_allow_html=True,
        )

        # sentiment 필터 라디오 (가로)
        sf_options = {
            f"전체 ({stats['total']})": "all",
            f"긍정 ({stats['positive']})": "positive",
            f"부정 ({stats['negative']})": "negative",
            f"중립 ({stats['neutral']})": "neutral",
        }
        cur_label = next((l for l, v in sf_options.items() if v == st.session_state.sentiment_filter), list(sf_options.keys())[0])
        sel_label = st.radio(
            "sentiment",
            list(sf_options.keys()),
            index=list(sf_options.keys()).index(cur_label),
            horizontal=True,
            label_visibility="collapsed",
        )
        st.session_state.sentiment_filter = sf_options[sel_label]

        # 필터링
        filtered = [
            (i, a, s) for i, (a, s) in enumerate(zip(articles, sents))
            if st.session_state.sentiment_filter == "all" or s.label == st.session_state.sentiment_filter
        ]
        st.caption(f"표시 중: {len(filtered)}건")

        # 카드 그리드 — 1열 좌측 컬럼이라 세로 stack, 카드별 select 버튼
        for idx, art, sent in filtered[:50]:   # 최대 50건 표시
            safe_title = html.escape(art.title)
            safe_src = html.escape(art.source or "")
            safe_kw = html.escape(art.matched_keyword)
            safe_summary = html.escape((art.summary_raw or "")[:120])
            sent_class = f"card-sent-{sent.label}"
            is_selected = (st.session_state.get("selected_idx") == idx)
            card_class = "art-card" + (" art-card-selected" if is_selected else "")
            st.markdown(
                f"""<div class='{card_class} {sent_class}' onclick='void(0)'>
                    <div class='art-card-head'>
                        <span class='sent-badge sent-badge-{sent.label}'>{sent.emoji} {sent.label_ko}</span>
                        <span class='art-src'>{safe_src}</span>
                    </div>
                    <div class='art-title'>{safe_title}</div>
                    <div class='art-summary'>{safe_summary}</div>
                    <div class='art-meta'><span class='art-kw'>{safe_kw}</span></div>
                </div>""",
                unsafe_allow_html=True,
            )
            if st.button(f"선택", key=f"select_{idx}", use_container_width=True):
                st.session_state.selected_idx = idx

    st.markdown("</div>", unsafe_allow_html=True)


# ===========================================================================
# 중간: Gemma 3 컨트롤러 (채팅)
# ===========================================================================
with col_mid:
    st.markdown(
        "<div class='col-card'><h3>🤖 Gemma 3 컨트롤러</h3>",
        unsafe_allow_html=True,
    )
    st.caption(
        "기구개발 엔지니어 시스템 프롬프트가 적용되어 있습니다. "
        "분석 방향(예: 구조 분석, 소재 분석, 공법 비교)을 자유롭게 지시하세요."
    )

    quick_cols = st.columns(3)
    quick_prompts = {
        "🔧 구조 분석": "선택한 기사 또는 최신 기사 흐름을 바탕으로 메커니즘 구조 관점에서 분석해줘.",
        "🧪 소재 분석": "소재(합금, 복합재, 폴리머) 관점으로 비교 분석해줘. 등급/규격 포함.",
        "⚙️ 공법 비교": "다이캐스팅 / MIM / 사출 / 프레스 / 본딩 등 공법 관점에서 장단점을 표로 정리해줘.",
    }
    pending_prompt: str | None = None
    for col, (label, prompt) in zip(quick_cols, quick_prompts.items()):
        if col.button(label, use_container_width=True, key=f"qp_{label}"):
            pending_prompt = prompt

    chat_box = st.container(height=420)
    with chat_box:
        if not st.session_state.chat_history:
            st.markdown(
                "_채팅을 시작하세요. 좌측에서 기사를 선택하면 해당 기사 컨텍스트가 자동 포함됩니다._"
            )
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    user_input = st.chat_input("Gemma 3에게 분석 방향을 지시하세요...")
    prompt_to_send = pending_prompt or user_input

    if prompt_to_send:
        # 선택된 기사 컨텍스트
        selected_article = None
        if st.session_state.selected_idx is not None and st.session_state.articles:
            selected_article = st.session_state.articles[st.session_state.selected_idx]

        context_block = ""
        if selected_article:
            context_block = (
                f"[현재 선택된 기사]\n"
                f"제목: {selected_article.title}\n"
                f"출처: {selected_article.source}\n"
                f"키워드: {selected_article.matched_keyword}\n"
                f"링크: {selected_article.link}\n"
                f"개요: {selected_article.summary_raw}\n\n"
            )

        full_user = context_block + prompt_to_send
        st.session_state.chat_history.append({"role": "user", "content": prompt_to_send})

        # 메시지 구성
        api_messages = [{"role": "system", "content": gemma_client.SYSTEM_PROMPT}]
        for m in st.session_state.chat_history[:-1]:
            api_messages.append(m)
        api_messages.append({"role": "user", "content": full_user})

        with chat_box:
            with st.chat_message("user"):
                st.markdown(prompt_to_send)
            with st.chat_message("assistant"):
                placeholder = st.empty()
                acc = ""
                try:
                    # 스트리밍은 Ollama만 지원. Groq/Gemini는 일반 chat (한 번에 응답)
                    if st.session_state.llm_backend == "ollama":
                        chunks_iter = gemma_client.chat_stream(
                            api_messages,
                            model=st.session_state.model_name,
                            base_url=st.session_state.ollama_url,
                        )
                    else:
                        full = gemma_client.chat(
                            api_messages,
                            backend=st.session_state.llm_backend,
                            model=st.session_state.model_name,
                            api_key=st.session_state.get("llm_api_key", ""),
                        )
                        chunks_iter = iter([full])
                    for tok in chunks_iter:
                        acc += tok
                        placeholder.markdown(acc + "▌")
                    placeholder.markdown(acc or "_(응답 없음)_")
                except gemma_client.LLMError as exc:
                    acc = f"⚠️ {exc}"
                    placeholder.error(acc)

        st.session_state.chat_history.append({"role": "assistant", "content": acc})

    if st.session_state.chat_history:
        if st.button("🗑️ 대화 초기화", key="clear_chat"):
            st.session_state.chat_history = []
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# ===========================================================================
# 우측: 요약 및 PPT 생성
# ===========================================================================
with col_right:
    st.markdown(
        "<div class='col-card'><h3>📑 요약 & PPT 리포트</h3>",
        unsafe_allow_html=True,
    )

    if st.session_state.selected_idx is None or not st.session_state.articles:
        st.info("좌측에서 기사를 선택하세요.")
    else:
        article = st.session_state.articles[st.session_state.selected_idx]
        st.markdown(f"**{article.title}**")
        meta = f"출처: `{article.source or 'N/A'}` · 키워드: `{article.matched_keyword}`"
        st.caption(meta)
        st.markdown(f"[원문 보기 ↗]({article.link})")

        extra = st.text_input(
            "요약 시 추가 지시 (선택)",
            placeholder="예: 경쟁사 대비 양산성 리스크에 집중",
            key="extra_instruction",
        )

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🧠 Gemma 3로 요약 생성", use_container_width=True):
                with st.spinner("기사 본문을 가져오는 중..."):
                    body = news_crawler.fetch_article_body(article.link)
                with st.spinner("Gemma 3가 분석 중입니다..."):
                    try:
                        summary = gemma_client.summarize_article(
                            title=selected_article.title,
                            body=body_text,
                            backend=st.session_state.llm_backend,
                            model=st.session_state.model_name,
                            base_url=st.session_state.ollama_url,
                            api_key=st.session_state.get("llm_api_key", ""),
                        )
                        st.session_state.summary = summary
                    except gemma_client.LLMError as exc:
                        st.error(str(exc))

        with col_b:
            if st.button("🧹 요약 초기화", use_container_width=True):
                st.session_state.summary = ""
                st.rerun()

        if st.session_state.summary:
            st.markdown("---")
            st.markdown("#### 요약 결과")
            st.markdown(st.session_state.summary)

            try:
                pptx_bytes = build_pptx(
                    article_title=article.title,
                    article_link=article.link,
                    article_source=article.source,
                    summary_markdown=st.session_state.summary,
                )
                fname_base = re.sub(r"[^\w가-힣]+", "_", article.title)[:50] or "news_report"
                st.download_button(
                    label="⬇️ PPT 리포트 생성 / 다운로드",
                    data=pptx_bytes,
                    file_name=f"{fname_base}.pptx",
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    use_container_width=True,
                )
            except Exception as exc:
                st.error(f"PPT 생성 실패: {exc}")
        else:
            st.caption("요약을 생성하면 이 영역에 결과가 표시되고 PPT 다운로드 버튼이 활성화됩니다.")

    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 푸터
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption(
    "© 선행기구개발그룹 뉴스 레이더 · "
    f"모델: {st.session_state.model_name} · "
    f"엔진: {st.session_state.llm_backend}" + (f" · {st.session_state.ollama_url}" if st.session_state.llm_backend == "ollama" else "")
)
