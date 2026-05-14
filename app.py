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
    --surface: #f7f7f7;
    --surface-2: #fafafa;
    --ink: #1d1d1f;
    --ink-2: #555555;
    --ink-3: #8a8a8a;
    --line: #e5e5e5;
    --line-soft: rgba(0,0,0,.05);
    --accent: #03C75A;          /* 네이버 그린 */
    --accent-dark: #02b350;
    --accent-link: #06c;
    --ok-bg: #e8f9ed;
    --ok-ink: #1a8a36;
    --bad-bg: #fdebeb;
    --bad-ink: #c43e3e;
    --ls-tight: -0.022em;
    --ls-wide: .04em;
    --radius: 12px;
    --radius-s: 8px;
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
    padding: 16px 4px 14px;
    border-radius: 0;
    color: var(--ink);
    margin-bottom: 14px;
}
.main-header .hdr-row {
    display: flex; justify-content: space-between; align-items: flex-end;
    gap: 12px;
}
.main-header h1 {
    margin: 0;
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -.015em;
    line-height: 1.2;
    color: var(--ink);
}
.main-header h1::before {
    content: ""; display: inline-block;
    width: 4px; height: 18px; background: var(--accent);
    margin-right: 8px; vertical-align: -3px; border-radius: 2px;
}
.main-header .hdr-sub {
    margin: 4px 0 0;
    font-size: 12.5px;
    color: var(--ink-3);
    letter-spacing: -.003em;
}
.main-header .hdr-meta {
    font-size: 12px; color: var(--ink-2);
}
.llm-pill {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px;
    font-size: 11.5px; font-weight: 600;
    background: var(--accent); color: #fff;
    border-radius: 999px;
    letter-spacing: -.003em;
}
.llm-pill .dot { width: 6px; height: 6px; border-radius: 50%; background: #fff; display: inline-block; }
.llm-pill-off { background: var(--ink-3); color: #fff; }
.llm-pill-off .dot { background: #fff; opacity: .7; }

/* 컬럼 카드 — 흰 배경 + hairline */
.col-card {
    background: var(--bg);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    padding: 4px 0 0;
    color: var(--ink);
    overflow: hidden;
}
.col-card h3 {
    margin: 0;
    padding: 14px 16px 10px;
    color: var(--ink);
    font-size: 14px;
    font-weight: 700;
    letter-spacing: -.005em;
    border-bottom: 1px solid var(--line);
    text-transform: none;
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
/* sentiment dot (이모지 대체) — 6px solid circle */
.sent-pill .dot, .sent-badge .dot {
    display: inline-block;
    width: 7px; height: 7px;
    border-radius: 50%;
    background: currentColor;
    margin-right: 5px;
    vertical-align: 0px;
}
.sent-pill-pos .dot { background: var(--sent-pos); }
.sent-pill-neg .dot { background: var(--sent-neg); }
.sent-pill-neu .dot { background: var(--sent-neu); }
.sent-badge-positive .dot { background: var(--sent-pos); }
.sent-badge-negative .dot { background: var(--sent-neg); }
.sent-badge-neutral  .dot { background: var(--sent-neu); }

/* 카테고리 필터 chip 행 */
.cat-chip-row { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 10px; }
.cat-chip {
    display: inline-flex; align-items: center;
    font-size: 11px; font-weight: 500;
    padding: 4px 10px; border-radius: 999px;
    background: var(--surface); color: var(--ink-2);
    border: 1px solid var(--line);
    letter-spacing: -.003em;
}
.cat-chip-active {
    background: var(--ink); color: var(--bg); border-color: var(--ink);
}
.sent-total { margin-left: auto; font-size: 11px; color: var(--ink-2); }

/* 기사 리스트 카드 — 네이버 뉴스 스타일 (행 단위, hairline divider) */
.art-card {
    background: var(--bg);
    border: 0;
    border-bottom: 1px solid var(--line);
    border-left: 3px solid transparent;
    border-radius: 0;
    padding: 14px 16px 14px 14px;
    margin: 0;
    transition: background 120ms;
    cursor: pointer;
}
.art-card:hover {
    background: var(--surface-2);
}
.art-card.card-sent-positive { border-left-color: var(--sent-pos); }
.art-card.card-sent-negative { border-left-color: var(--sent-neg); }
.art-card.card-sent-neutral  { border-left-color: var(--sent-neu); }
.art-card-selected {
    background: #f0fbf4;        /* 네이버 그린 hover tint */
    border-left-color: var(--accent);
}
.art-card-head {
    display: flex; justify-content: space-between; align-items: center;
    gap: 8px;
    margin-bottom: 4px;
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
    font-size: 16px; font-weight: 600;
    line-height: 1.4; letter-spacing: -.012em;
    color: var(--ink);
    margin: 4px 0 6px;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden;
}
.art-summary {
    font-size: 13px; color: var(--ink-2);
    line-height: 1.5;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden;
    letter-spacing: -.003em;
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
[data-testid="stHorizontalBlock"] [data-testid="stRadio"] > div,
[data-testid="stRadio"] > div[role="radiogroup"] {
    flex-direction: row !important;
    gap: 2px;
    border-bottom: 1px solid var(--line);
}
[data-testid="stRadio"] label {
    position: relative;
    padding: 8px 12px 10px !important;
    border-radius: 0 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    color: var(--ink-2) !important;
    letter-spacing: -.003em;
}
[data-testid="stRadio"] label:hover { color: var(--ink) !important; }
[data-testid="stRadio"] label[data-checked="true"] {
    color: var(--accent) !important;
    font-weight: 700 !important;
}
[data-testid="stRadio"] label[data-checked="true"]::after {
    content: ""; position: absolute; left: 12px; right: 12px; bottom: -1px;
    height: 2px; background: var(--accent);
}
/* 라디오 원형 아이콘 숨김 (탭처럼 보이게) */
[data-testid="stRadio"] label > div:first-child { display: none !important; }

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
    background: var(--accent);
    color: #fff;
    border: 1px solid var(--accent);
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 500;
    letter-spacing: -.003em;
    font-size: 13px;
    transition: background 120ms;
}
.stButton > button:hover { background: var(--accent-dark); color: #fff; border-color: var(--accent-dark); }
/* 보조 버튼 (선택/원문 등 카드 내) — 흰 배경 */
.stButton:has(button[kind="secondary"]) > button { background: #fff; color: var(--ink); border-color: var(--line); }
.stButton:has(button[kind="secondary"]) > button:hover { background: var(--surface); }
.stTextInput input, .stTextArea textarea, .stSelectbox > div > div {
    border: 1px solid var(--line) !important;
    border-radius: 10px !important;
    background: var(--bg) !important;
    font-family: inherit !important;
    letter-spacing: -.005em;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px rgba(3,199,90,.18) !important;
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
    ss.setdefault("sort_mode", "latest")        # latest | sentiment_strong | by_source
    ss.setdefault("cat_filter", [])             # 카테고리 다중 선택 (빈 = 전체)
    ss.setdefault("llm_boost_done", False)
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

    # ---- LLM 백엔드 자동 감지 (UI 노출 없음) ----
    def _detect_backend():
        try:
            if st.secrets.get("GROQ_API_KEY", "").strip():
                return "groq", st.secrets["GROQ_API_KEY"].strip(), gemma_client.GROQ_DEFAULT_MODEL
        except Exception:
            pass
        try:
            if st.secrets.get("GEMINI_API_KEY", "").strip():
                return "gemini", st.secrets["GEMINI_API_KEY"].strip(), gemma_client.GEMINI_DEFAULT_MODEL
        except Exception:
            pass
        try:
            if gemma_client.is_available("ollama", base_url=gemma_client.OLLAMA_BASE_URL):
                models = gemma_client.list_models("ollama")
                model = next((m for m in models if "gemma" in m.lower()), models[0] if models else gemma_client.OLLAMA_DEFAULT_MODEL)
                return "ollama", "", model
        except Exception:
            pass
        return "none", "", ""

    if "llm_auto_detected" not in st.session_state:
        backend, key, model = _detect_backend()
        st.session_state.llm_backend = backend if backend != "none" else "groq"
        st.session_state.llm_api_key = key
        st.session_state.model_name = model or gemma_client.GROQ_DEFAULT_MODEL
        st.session_state.llm_active = (backend != "none")
        st.session_state.llm_auto_detected = True

    st.markdown("---")
    st.markdown("### 데이터 소스")

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
    st.markdown("### 수집 키워드 (Google News)")
    st.caption("아래 키워드 기반으로 Google News RSS에서 수집합니다. Geeknews는 사이트 자체 큐레이션 사용.")
    for kw in news_crawler.SEARCH_KEYWORDS:
        st.markdown(f"- {kw}")

    st.markdown("---")
    refresh_clicked = st.button("새로고침 ↻", use_container_width=True)


# ---------------------------------------------------------------------------
# 헤더
# ---------------------------------------------------------------------------
# 네이버 스타일 미니멀 헤더
_llm_status = ""
if st.session_state.get("llm_active"):
    _b = st.session_state.get("llm_backend", "")
    _b_label = {"groq": "Groq", "gemini": "Gemini", "ollama": "Ollama"}.get(_b, _b)
    _llm_status = f'<span class="llm-pill"><span class="dot"></span>AI {_b_label}</span>'
else:
    _llm_status = '<span class="llm-pill llm-pill-off"><span class="dot"></span>키워드</span>'

st.markdown(
    f"""
    <div class="main-header">
        <div class="hdr-row">
            <div>
                <h1>선행기구개발 뉴스 레이더</h1>
                <p class="hdr-sub">모바일 · 전기차 · 부품·신소재 — 실시간 큐레이션</p>
            </div>
            <div class="hdr-meta">{_llm_status}</div>
        </div>
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
    st.markdown("<div class='col-card'><h3>기사 그리드</h3>", unsafe_allow_html=True)

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
                <span class='sent-pill sent-pill-pos'><span class='dot'></span>긍정 {stats['positive']}</span>
                <span class='sent-pill sent-pill-neg'><span class='dot'></span>부정 {stats['negative']}</span>
                <span class='sent-pill sent-pill-neu'><span class='dot'></span>중립 {stats['neutral']}</span>
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

        # 카테고리 chip 필터 (다중 선택)
        cat_options = list(news_crawler.CATEGORY_LABELS.values())
        # 기사별 카테고리 매핑 (source_category 기반)
        cat_label_by_key = news_crawler.CATEGORY_LABELS
        article_cats = [cat_label_by_key.get(getattr(a, "source_category", "kw"), "") for a in articles]
        present_cats = sorted(set(c for c in article_cats if c))
        if present_cats:
            with st.container():
                st.caption("카테고리 (다중)")
                cat_cols = st.columns(min(len(present_cats), 5))
                for i, c in enumerate(present_cats):
                    is_active = c in st.session_state.cat_filter
                    label = c + (" ✓" if is_active else "")
                    if cat_cols[i % len(cat_cols)].button(label, key=f"cat_{c}", use_container_width=True):
                        if is_active:
                            st.session_state.cat_filter.remove(c)
                        else:
                            st.session_state.cat_filter.append(c)
                        st.rerun()

        # 정렬 + LLM 보강 (한 줄)
        sc1, sc2 = st.columns([2, 1])
        sort_options = {
            "최신순": "latest",
            "Sentiment 강한순": "sentiment_strong",
            "출처별": "by_source",
        }
        cur_sort_label = next((l for l, v in sort_options.items() if v == st.session_state.sort_mode), "최신순")
        sel_sort = sc1.selectbox(
            "정렬", list(sort_options.keys()),
            index=list(sort_options.keys()).index(cur_sort_label),
            label_visibility="collapsed",
        )
        st.session_state.sort_mode = sort_options[sel_sort]

        # LLM 보강 버튼 (Groq/Gemini/Ollama 있고 회색지대 있을 때)
        backend = st.session_state.get("llm_backend", "ollama")
        api_key = st.session_state.get("llm_api_key", "")
        can_boost = (backend == "ollama") or bool(api_key)
        borderline_n = sum(1 for s in sents if abs(s.score) < 0.2)
        if can_boost and borderline_n > 0 and not st.session_state.llm_boost_done:
            if sc2.button(f"LLM 보강 ({borderline_n})", use_container_width=True,
                          help="키워드 분류가 모호한 기사만 LLM으로 재분류"):
                with st.spinner(f"LLM이 회색지대 {borderline_n}건 재분류 중..."):
                    def _llm_call(messages):
                        return gemma_client.chat(
                            messages,
                            backend=backend,
                            model=st.session_state.model_name,
                            base_url=st.session_state.ollama_url,
                            api_key=api_key,
                        )
                    try:
                        st.session_state.sentiments = sentiment_classifier.classify_with_llm(
                            articles, sents, _llm_call
                        )
                        st.session_state.llm_boost_done = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"LLM 보강 실패: {e}")
        elif st.session_state.llm_boost_done:
            sc2.caption("LLM 보강 완료")

        # 필터링 (sentiment + category)
        filtered = []
        for i, (a, s) in enumerate(zip(articles, sents)):
            if st.session_state.sentiment_filter != "all" and s.label != st.session_state.sentiment_filter:
                continue
            if st.session_state.cat_filter:
                a_cat = cat_label_by_key.get(getattr(a, "source_category", "kw"), "")
                if a_cat not in st.session_state.cat_filter:
                    continue
            filtered.append((i, a, s))

        # 정렬
        if st.session_state.sort_mode == "sentiment_strong":
            filtered.sort(key=lambda t: (-abs(t[2].score), -t[2].score))
        elif st.session_state.sort_mode == "by_source":
            filtered.sort(key=lambda t: (t[1].source or "", -t[2].score))
        # latest: 이미 published_dt desc로 와있음
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
                        <span class='sent-badge sent-badge-{sent.label}'><span class='dot'></span>{sent.label_ko}</span>
                        <span class='art-src'>{safe_src}</span>
                    </div>
                    <div class='art-title'>{safe_title}</div>
                    <div class='art-summary'>{safe_summary}</div>
                    <div class='art-meta'><span class='art-kw'>{safe_kw}</span></div>
                </div>""",
                unsafe_allow_html=True,
            )
            bcol1, bcol2 = st.columns([1, 1])
            if bcol1.button("선택", key=f"select_{idx}", use_container_width=True):
                st.session_state.selected_idx = idx
                st.session_state[f"expand_{idx}"] = True
            if bcol2.button("원문 ↗", key=f"open_{idx}", use_container_width=True):
                pass  # 링크는 마크다운에서
            if st.session_state.get(f"expand_{idx}"):
                with st.expander("상세 보기", expanded=True):
                    st.markdown(f"**원문:** [{html.escape(art.link[:70])}]({html.escape(art.link)})")
                    if art.summary_raw:
                        st.markdown("**요약 (RSS 원문):**")
                        st.write(art.summary_raw[:500])
                    pos = sent.pos_hits
                    neg = sent.neg_hits
                    if pos or neg:
                        st.caption(f"매칭 키워드 — 긍정: {', '.join(pos) if pos else '—'} / 부정: {', '.join(neg) if neg else '—'}")
                    if st.button("접기", key=f"collapse_{idx}"):
                        st.session_state[f"expand_{idx}"] = False
                        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# ===========================================================================
# 중간: Gemma 3 컨트롤러 (채팅)
# ===========================================================================
with col_mid:
    st.markdown(
        "<div class='col-card'><h3>LLM 컨트롤러</h3>",
        unsafe_allow_html=True,
    )
    st.caption(
        "기구개발 엔지니어 시스템 프롬프트가 적용되어 있습니다. "
        "분석 방향(예: 구조 분석, 소재 분석, 공법 비교)을 자유롭게 지시하세요."
    )

    quick_cols = st.columns(3)
    quick_prompts = {
        "구조 분석": "선택한 기사 또는 최신 기사 흐름을 바탕으로 메커니즘 구조 관점에서 분석해줘.",
        "소재 분석": "소재(합금, 복합재, 폴리머) 관점으로 비교 분석해줘. 등급/규격 포함.",
        "공법 비교": "다이캐스팅 / MIM / 사출 / 프레스 / 본딩 등 공법 관점에서 장단점을 표로 정리해줘.",
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
                    acc = f"오류: {exc}"
                    placeholder.error(acc)

        st.session_state.chat_history.append({"role": "assistant", "content": acc})

    if st.session_state.chat_history:
        if st.button("대화 초기화", key="clear_chat"):
            st.session_state.chat_history = []
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# ===========================================================================
# 우측: 요약 및 PPT 생성
# ===========================================================================
with col_right:
    st.markdown(
        "<div class='col-card'><h3>요약 · PPT 리포트</h3>",
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
            if st.button("LLM 요약 생성", use_container_width=True):
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
            if st.button("요약 초기화", use_container_width=True):
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