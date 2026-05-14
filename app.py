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
import company_extractor
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

/* === 기업 모니터 대시보드 === */
.comp-stats-bar {
    display: flex; align-items: baseline; gap: 8px;
    padding: 8px 0 14px;
    border-bottom: 1px solid var(--line);
    margin-bottom: 14px;
    font-size: 13px; color: var(--ink-2);
    letter-spacing: -.003em;
}
.comp-stat-num { font-size: 20px; font-weight: 700; color: var(--ink); letter-spacing: -.012em; }
.comp-stat-lbl { font-size: 12.5px; color: var(--ink-2); }
.comp-stat-sep { color: var(--line); margin: 0 4px; }

/* 기업 카드 */
.comp-card {
    background: var(--bg);
    border: 1px solid var(--line);
    border-left: 4px solid var(--ink-3);
    border-radius: 10px;
    padding: 14px 14px 12px;
    margin: 4px 0;
    transition: background 120ms, box-shadow 120ms;
    min-height: 130px;
}
.comp-card:hover { background: var(--surface-2); box-shadow: 0 2px 8px rgba(0,0,0,.05); }
.comp-strip-pos { border-left-color: var(--sent-pos); }
.comp-strip-neg { border-left-color: var(--sent-neg); }
.comp-strip-neu { border-left-color: var(--sent-neu); }
.comp-card-selected {
    background: #f0fbf4;
    border-left-color: var(--accent);
    box-shadow: 0 0 0 2px rgba(3,199,90,.15);
}
.comp-name {
    font-size: 16px; font-weight: 700; letter-spacing: -.012em;
    color: var(--ink); line-height: 1.2;
}
.comp-cat {
    margin-top: 2px;
    font-size: 11px; color: var(--ink-3);
    letter-spacing: .02em;
}
.comp-ratio {
    display: flex;
    height: 6px; margin: 12px 0 8px;
    border-radius: 3px; overflow: hidden;
    background: var(--surface);
}
.comp-ratio > div { height: 100%; }
.r-pos { background: var(--sent-pos); }
.r-neg { background: var(--sent-neg); }
.r-neu { background: var(--sent-neu); }
.comp-nums {
    display: flex; gap: 8px; align-items: baseline;
    font-size: 12px; color: var(--ink-2);
}
.nb-pos { color: var(--sent-pos); font-weight: 600; }
.nb-neg { color: var(--sent-neg); font-weight: 600; }
.nb-neu { color: var(--ink-3); }
.nb-total { margin-left: auto; color: var(--ink-2); font-size: 11px; }

/* 상세 패널 */
.comp-detail-head {
    margin: 10px 0 14px;
    padding: 16px 0 14px;
    border-bottom: 2px solid var(--accent);
}
.comp-detail-head h2 {
    margin: 0 0 10px;
    font-size: 24px; font-weight: 700; letter-spacing: -.018em;
    color: var(--ink);
}
.comp-detail-cat {
    margin-left: 8px;
    font-size: 12px; font-weight: 500;
    padding: 3px 10px; border-radius: 999px;
    background: var(--surface); color: var(--ink-2);
    vertical-align: 5px;
}
.comp-detail-stats { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.comp-synth {
    margin: 14px 0;
    padding: 16px 18px;
    background: var(--surface);
    border-left: 3px solid var(--accent);
    border-radius: 0 8px 8px 0;
    font-size: 14px; line-height: 1.7;
    color: var(--ink);
    letter-spacing: -.005em;
}
.comp-synth p { margin: 0 0 10px; }
.comp-synth strong { color: var(--accent); }
.art-title a { color: inherit; text-decoration: none; }
.art-title a:hover { color: var(--accent); text-decoration: underline; }

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
# ===========================================================================
# 메인: 기업별 sentiment 모니터 대시보드
# ===========================================================================

articles = st.session_state.articles
sents = st.session_state.get("sentiments", [])

if not articles:
    st.info("수집된 기사가 없습니다. 좌측 사이드바의 새로고침을 눌러주세요.")
else:
    # sentiment 계산 (캐시)
    if not sents or len(sents) != len(articles):
        sents = [sentiment_classifier.classify(a.title, a.summary_raw) for a in articles]
        st.session_state.sentiments = sents

    # 기업별 그룹핑
    company_articles: dict[str, list] = {}   # name -> [(idx, article, sentiment), ...]
    for i, (art, s) in enumerate(zip(articles, sents)):
        for cname in company_extractor.extract_companies(art.title, art.summary_raw):
            company_articles.setdefault(cname, []).append((i, art, s))

    # 카테고리 chip 필터 (기업 카테고리)
    cat_keys_present = sorted({
        company_extractor.category_key(n)
        for n in company_articles.keys()
    } - {""})

    ss_cf = st.session_state.get("company_cat_filter", [])
    cat_cols = st.columns(max(1, min(len(cat_keys_present), 6)))
    for idx, ck in enumerate(cat_keys_present):
        lbl = company_extractor.CATEGORY_LABELS.get(ck, ck)
        is_active = ck in ss_cf
        suffix = "  ✓" if is_active else ""
        if cat_cols[idx % len(cat_cols)].button(lbl + suffix, key=f"ccat_{ck}", use_container_width=True):
            if is_active:
                ss_cf.remove(ck)
            else:
                ss_cf.append(ck)
            st.session_state.company_cat_filter = ss_cf
            st.rerun()

    # 정렬
    sort_options = {
        "부정 비율 높은 순": "neg_ratio",
        "총 기사 수 많은 순": "count",
        "알파벳순": "alpha",
    }
    sort_label = st.selectbox(
        "정렬",
        list(sort_options.keys()),
        index=0,
        label_visibility="collapsed",
    )
    sort_mode = sort_options[sort_label]

    # 카테고리 필터 적용
    if ss_cf:
        company_articles = {
            n: arr for n, arr in company_articles.items()
            if company_extractor.category_key(n) in ss_cf
        }

    # 정렬
    def _stats_for(arr):
        pos = sum(1 for _, _, s in arr if s.label == "positive")
        neg = sum(1 for _, _, s in arr if s.label == "negative")
        neu = sum(1 for _, _, s in arr if s.label == "neutral")
        total = len(arr)
        neg_ratio = neg / total if total else 0
        return pos, neg, neu, total, neg_ratio

    company_list = list(company_articles.items())
    if sort_mode == "neg_ratio":
        company_list.sort(key=lambda kv: (-_stats_for(kv[1])[4], -_stats_for(kv[1])[3]))
    elif sort_mode == "count":
        company_list.sort(key=lambda kv: -_stats_for(kv[1])[3])
    else:
        company_list.sort(key=lambda kv: kv[0].lower())

    # 통계 헤더
    total_articles = sum(len(arr) for _, arr in company_list)
    st.markdown(
        f"""<div class='comp-stats-bar'>
            <span class='comp-stat-num'>{len(company_list)}</span>
            <span class='comp-stat-lbl'>기업</span>
            <span class='comp-stat-sep'>·</span>
            <span class='comp-stat-num'>{total_articles}</span>
            <span class='comp-stat-lbl'>기사</span>
            <span class='comp-stat-sep'>·</span>
            <span class='comp-stat-lbl'>총 {len(articles)} 수집</span>
        </div>""",
        unsafe_allow_html=True,
    )

    if not company_list:
        st.info("선택된 카테고리에 매칭되는 기업이 없습니다.")
    else:
        # 기업 카드 그리드 (4열)
        N_COLS = 4
        rows = [company_list[i:i+N_COLS] for i in range(0, len(company_list), N_COLS)]
        selected_company = st.session_state.get("selected_company")

        for row in rows:
            cols = st.columns(N_COLS, gap="small")
            for col, (cname, arr) in zip(cols, row):
                pos, neg, neu, total, neg_ratio = _stats_for(arr)
                pos_pct = pos * 100 // total if total else 0
                neg_pct = neg * 100 // total if total else 0
                neu_pct = 100 - pos_pct - neg_pct
                cat_lbl = company_extractor.category_label(cname)
                is_sel = (selected_company == cname)
                sel_class = " comp-card-selected" if is_sel else ""
                # neg 비율 높으면 카드 좌측 strip 빨강, 긍정 비율 높으면 초록
                strip = "neg" if neg_ratio >= 0.35 else ("pos" if pos / max(total,1) >= 0.5 else "neu")
                col.markdown(
                    f"""<div class='comp-card comp-strip-{strip}{sel_class}'>
                        <div class='comp-name'>{html.escape(cname)}</div>
                        <div class='comp-cat'>{html.escape(cat_lbl)}</div>
                        <div class='comp-ratio'>
                            <div class='r-pos' style='width:{pos_pct}%'></div>
                            <div class='r-neg' style='width:{neg_pct}%'></div>
                            <div class='r-neu' style='width:{neu_pct}%'></div>
                        </div>
                        <div class='comp-nums'>
                            <span class='nb-pos'>{pos}</span>
                            <span class='nb-neg'>{neg}</span>
                            <span class='nb-neu'>{neu}</span>
                            <span class='nb-total'>{total}건</span>
                        </div>
                    </div>""",
                    unsafe_allow_html=True,
                )
                if col.button("상세", key=f"comp_sel_{cname}", use_container_width=True):
                    st.session_state.selected_company = cname
                    st.rerun()

        # 상세 패널
        if selected_company and selected_company in company_articles:
            st.markdown("---")
            sel_arr = company_articles[selected_company]
            pos, neg, neu, total, _ = _stats_for(sel_arr)
            cat_lbl = company_extractor.category_label(selected_company)
            st.markdown(
                f"""<div class='comp-detail-head'>
                    <h2>{html.escape(selected_company)} <span class='comp-detail-cat'>{html.escape(cat_lbl)}</span></h2>
                    <div class='comp-detail-stats'>
                        <span class='sent-pill sent-pill-pos'><span class='dot'></span>긍정 {pos}</span>
                        <span class='sent-pill sent-pill-neg'><span class='dot'></span>부정 {neg}</span>
                        <span class='sent-pill sent-pill-neu'><span class='dot'></span>중립 {neu}</span>
                        <span class='sent-total'>총 {total}건</span>
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )

            dcol1, dcol2 = st.columns([1, 1])
            if dcol1.button("닫기", key="comp_close", use_container_width=True):
                st.session_state.selected_company = None
                st.rerun()
            if st.session_state.get("llm_active") and dcol2.button(f"{selected_company} 종합 분석", key="comp_synth", use_container_width=True):
                with st.spinner(f"{selected_company} 관련 {total}건을 LLM이 종합 분석 중..."):
                    titles_summary = "\n".join(
                        f"- [{s.label_ko}] {a.title}: {(a.summary_raw or '')[:150]}"
                        for _, a, s in sel_arr[:20]
                    )
                    try:
                        synth = gemma_client.chat(
                            [
                                {"role": "system", "content": (
                                    f"너는 시니어 기구개발 엔지니어로서 {selected_company} 관련 최근 뉴스를 분석한다. "
                                    "긍정/부정 비율과 핵심 이슈를 한국어로 3~4 단락으로 요약. "
                                    "리스크 관점 + 기회 관점 모두 다룬다."
                                )},
                                {"role": "user", "content": f"{selected_company} 관련 최근 기사:\n{titles_summary}"},
                            ],
                            backend=st.session_state.llm_backend,
                            model=st.session_state.model_name,
                            base_url=st.session_state.ollama_url,
                            api_key=st.session_state.get("llm_api_key", ""),
                        )
                        st.session_state[f"comp_synth_{selected_company}"] = synth
                    except Exception as e:
                        st.error(f"분석 실패: {e}")

            synth = st.session_state.get(f"comp_synth_{selected_company}")
            if synth:
                st.markdown(f"<div class='comp-synth'>{synth}</div>", unsafe_allow_html=True)

            # 기사 리스트
            st.markdown("#### 관련 기사")
            for i, art, sent in sel_arr[:30]:
                st.markdown(
                    f"""<div class='art-card card-sent-{sent.label}'>
                        <div class='art-card-head'>
                            <span class='sent-badge sent-badge-{sent.label}'><span class='dot'></span>{sent.label_ko}</span>
                            <span class='art-src'>{html.escape(art.source or "")}</span>
                        </div>
                        <div class='art-title'><a href='{html.escape(art.link)}' target='_blank' rel='noopener'>{html.escape(art.title)}</a></div>
                        <div class='art-summary'>{html.escape((art.summary_raw or "")[:200])}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )

# 푸터
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption(
    "© 선행기구개발그룹 뉴스 레이더 · "
    f"모델: {st.session_state.model_name} · "
    f"엔진: {st.session_state.llm_backend}" + (f" · {st.session_state.ollama_url}" if st.session_state.llm_backend == "ollama" else "")
)