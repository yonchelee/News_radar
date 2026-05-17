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
import top_of_mind
import topic_classifier
import translator
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
    --bg: #f5f7fb;
    --surface: #ffffff;
    --surface-2: #f8fafc;
    --ink: #111827;
    --ink-2: #475569;
    --ink-3: #7b8794;
    --line: #dbe3ef;
    --line-soft: rgba(15,23,42,.07);
    --accent: #0f766e;
    --accent-dark: #115e59;
    --accent-link: #2563eb;
    --ok-bg: #e7f6ef;
    --ok-ink: #137a3f;
    --bad-bg: #fff1f2;
    --bad-ink: #be123c;
    --warn-bg: #fff7ed;
    --warn-ink: #b45309;
    --ls-tight: 0;
    --ls-wide: 0;
    --radius: 8px;
    --radius-s: 8px;
}

/* 베이스 폰트 — SF Pro Display/Text + 한글 폴백 */
html, body, [class*="css"]  {
    font-family: "Inter", "Noto Sans KR", -apple-system, BlinkMacSystemFont,
                 "SF Pro Display", "SF Pro Text", "Pretendard",
                 "Apple SD Gothic Neo", "Nanum Gothic", system-ui, sans-serif !important;
    -webkit-font-smoothing: antialiased;
    letter-spacing: 0;
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

/* 언어 토글 (KO/EN) — 헤더 우측 */
.lang-toggle {
    display: inline-flex;
    gap: 0;
    background: var(--bg-2, #f7f7f7);
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 2px;
    margin-right: 6px;
    vertical-align: middle;
}
.lang-pill {
    display: inline-flex; align-items: center;
    padding: 3px 12px;
    font-size: 11.5px; font-weight: 600;
    border-radius: 999px;
    letter-spacing: -.003em;
    cursor: pointer;
    text-decoration: none;
    transition: background .15s, color .15s;
}
.lang-pill:hover { filter: brightness(0.97); }
.lang-pill-active {
    background: var(--accent);
    color: #fff;
}
.lang-pill-inactive {
    background: transparent;
    color: var(--ink-2);
}

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

/* 기업 카드 (일반 그리드 — compact) */
.comp-card {
    position: relative;
    background: var(--bg);
    border: 1px solid var(--line);
    border-left: 4px solid var(--ink-3);
    border-radius: 10px;
    padding: 10px 11px 10px;
    margin: 4px 0;
    transition: background 120ms, box-shadow 120ms;
    min-height: 130px;
}
.comp-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,.05); }
.comp-strip-pos { border-left-color: var(--sent-pos); }
.comp-strip-neg { border-left-color: var(--sent-neg); }
.comp-strip-neu { border-left-color: var(--sent-neu); }
/* 배경 틴트 — neg ratio 높으면 옅은 빨강, pos 높으면 옅은 그린 */
.comp-tint-neg { background: #fef2f1; }
.comp-tint-pos { background: #f0fbf4; }
.comp-card-selected {
    background: #e8f9ed;
    border-left-color: var(--accent);
    box-shadow: 0 0 0 2px rgba(3,199,90,.15);
}
.comp-name {
    font-size: 15px; font-weight: 700; letter-spacing: -.012em;
    color: var(--ink); line-height: 1.2;
    display: flex; align-items: center; gap: 6px;
}
.comp-cat {
    margin-top: 2px;
    font-size: 11px; color: var(--ink-3);
    letter-spacing: .02em;
}

/* 상태 아이콘 — ▲ ▼ ! (이모지 X, 텍스트 글리프) */
.comp-status-icon {
    display: inline-flex; align-items: center; justify-content: center;
    width: 18px; height: 18px;
    font-size: 13px; font-weight: 700;
    border-radius: 999px;
    line-height: 1;
}
.comp-status-warn  { background: var(--sent-neg); color: #fff; }
.comp-status-down  { color: var(--sent-neg); font-size: 14px; }
.comp-status-up    { color: var(--sent-pos); font-size: 14px; }

/* 키워드 chip (sentiment matched tokens) */
.kw-row { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.kw-chip {
    display: inline-block;
    font-size: 10px; font-weight: 500;
    padding: 2px 7px; border-radius: 6px;
    background: var(--bg);
    letter-spacing: -.003em;
    border: 1px solid var(--line);
    color: var(--ink-2);
}
.kw-chip-pos { border-color: rgba(26,138,54,.45); color: #1a8a36; }
.kw-chip-neg { border-color: rgba(196,62,62,.45); color: var(--sent-neg); }
.kw-more { font-size: 10px; color: var(--ink-3); padding: 2px 4px; }

/* === TOP 3 hero 카드 === */
.hero-card {
    position: relative;
    background: var(--bg);
    border: 1px solid var(--line);
    border-left: 6px solid var(--ink-3);
    border-radius: 14px;
    padding: 18px 20px 16px;
    min-height: 220px;
    margin: 4px 0;
    transition: box-shadow 120ms;
}
.hero-card:hover { box-shadow: 0 4px 14px rgba(0,0,0,.07); }
.hero-card.hero-warn { border-left-color: var(--sent-neg); background: #fef2f1; }
.hero-card.hero-event { border-left-color: var(--accent); background: #f0fbf4; }
.hero-card.hero-volume { border-left-color: #ff9500; background: #fff7ec; }
.hero-card.hero-info { border-left-color: #0071e3; background: #f0f7ff; }
.hero-reason {
    font-size: 10.5px; font-weight: 700;
    text-transform: uppercase; letter-spacing: .07em;
    color: var(--ink-2);
}
.hero-warn  .hero-reason { color: var(--sent-neg); }
.hero-event .hero-reason { color: var(--accent-dark); }
.hero-volume .hero-reason { color: #d97000; }
.hero-info  .hero-reason { color: #0071e3; }
.hero-company {
    display: flex; align-items: center; gap: 8px;
    margin-top: 6px;
    font-size: 22px; font-weight: 800; letter-spacing: -.018em;
    color: var(--ink); line-height: 1.15;
}
.hero-status-icon {
    display: inline-flex; align-items: center; justify-content: center;
    width: 26px; height: 26px;
    font-size: 17px; font-weight: 800;
    border-radius: 999px; line-height: 1;
}
.hero-status-warn { background: var(--sent-neg); color: #fff; }
.hero-status-down { color: var(--sent-neg); }
.hero-status-up   { color: var(--sent-pos); }
.hero-ratio-row { display: flex; align-items: center; gap: 10px; margin: 12px 0 8px; }
.hero-ratio-bar { flex: 1; height: 8px; border-radius: 4px; background: var(--surface); display: flex; overflow: hidden; }
.hero-ratio-bar > div { height: 100%; }
.hero-counts { font-size: 12px; color: var(--ink-2); white-space: nowrap; }
.hero-counts .hc-pos { color: var(--sent-pos); font-weight: 700; }
.hero-counts .hc-neg { color: var(--sent-neg); font-weight: 700; }
.hero-counts .hc-neu { color: var(--ink-3); }
.hero-preview {
    margin: 8px 0 6px; padding: 8px 10px;
    background: rgba(255,255,255,.6);
    border: 1px solid var(--line);
    border-radius: 8px;
    font-size: 12px; line-height: 1.5; color: var(--ink-2);
}
.hero-preview .hp-title { color: var(--ink); font-weight: 500; }

/* === 섹션 라벨 + hairline === */
.section-label {
    display: flex; align-items: baseline; justify-content: space-between;
    margin: 22px 0 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--line);
}
.section-label .sl-title {
    font-size: 13px; font-weight: 700;
    text-transform: uppercase; letter-spacing: .08em;
    color: var(--ink);
}
.section-label .sl-sub {
    font-size: 11px; color: var(--ink-3);
    letter-spacing: -.003em;
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


/* === 오늘 주목 (Top of Mind) === */
.tom-section-head {
    display: flex; align-items: baseline; justify-content: space-between;
    margin: 6px 0 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--line-soft);
}
.tom-section-head h2 {
    margin: 0;
    font-size: 18px; font-weight: 700;
    letter-spacing: -.012em; color: var(--ink);
}
.tom-section-head h2::before {
    content: ""; display: inline-block;
    width: 4px; height: 16px;
    background: var(--accent);
    margin-right: 8px; vertical-align: -2px;
    border-radius: 2px;
}
.tom-sub {
    font-size: 11.5px; color: var(--ink-3);
    letter-spacing: -.003em;
}

.tom-card {
    background: var(--bg);
    border: 1px solid var(--line);
    border-left: 4px solid var(--ink-3);
    border-radius: 8px;
    padding: 12px 14px;
    margin: 4px 0;
    transition: background 120ms, box-shadow 120ms;
    min-height: 92px;
}
.tom-card:hover {
    background: var(--surface-2);
    box-shadow: 0 2px 8px rgba(0,0,0,.06);
}
.tom-card-warning { border-left-color: var(--sent-neg); }
.tom-card-info    { border-left-color: #0071e3; }
.tom-card-event   { border-left-color: var(--accent); }
.tom-card-volume  { border-left-color: #ff9500; }

.tom-reason {
    font-size: 10.5px; font-weight: 600;
    text-transform: uppercase; letter-spacing: .05em;
    color: var(--ink-2);
    margin-bottom: 4px;
}
.tom-card-warning .tom-reason { color: var(--sent-neg); }
.tom-card-info    .tom-reason { color: #0071e3; }
.tom-card-event   .tom-reason { color: var(--accent); }
.tom-card-volume  .tom-reason { color: #d97000; }

.tom-company {
    font-size: 16px; font-weight: 700;
    letter-spacing: -.012em; color: var(--ink);
    line-height: 1.2;
    margin-bottom: 4px;
}
.tom-detail {
    font-size: 12px; color: var(--ink-2);
    letter-spacing: -.003em;
    line-height: 1.4;
}


/* === 3단계 필터 라벨 === */
.filter-row-label {
    font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: .05em;
    color: var(--ink-3);
    margin: 10px 0 6px;
}


/* 회사 카드 산업 chip — 통일 베이스 */
.comp-inds { display: flex; flex-wrap: wrap; gap: 4px; margin: 6px 0 6px; }
.comp-ind-chip, .country-chip, .filter-chip-base {
    display: inline-block;
    font-size: 9.5px; font-weight: 500;
    padding: 2px 6px; border-radius: 6px;
    background: var(--surface); color: var(--ink-2);
    letter-spacing: -.003em;
    border: 1px solid var(--line);
}

/* === 2026 UI refresh: operational news room === */
.stApp {
    background:
        linear-gradient(180deg, rgba(15,118,110,.09), rgba(245,247,251,0) 260px),
        var(--bg);
}
[data-testid="stHeader"] {
    background: rgba(245,247,251,.86);
    backdrop-filter: blur(16px);
    border-bottom: 1px solid rgba(219,227,239,.75);
}
.block-container {
    max-width: 1360px;
    padding-top: 1.6rem;
    padding-bottom: 3rem;
}
* {
    letter-spacing: 0 !important;
}
.main-header {
    background: rgba(255,255,255,.88);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 20px 22px;
    box-shadow: 0 18px 42px rgba(15,23,42,.07);
}
.main-header h1 {
    font-size: 28px;
    font-weight: 800;
}
.main-header h1::before {
    width: 5px;
    height: 23px;
    background: linear-gradient(180deg, var(--accent), #d97706);
}
.main-header .hdr-sub {
    font-size: 13px;
    color: var(--ink-2);
}
.lang-toggle,
.llm-pill {
    border: 1px solid var(--line);
    box-shadow: 0 6px 18px rgba(15,23,42,.05);
}
.llm-pill {
    background: #12343b;
}
.llm-pill-off {
    background: var(--ink-3);
}
.lang-pill-active {
    background: var(--accent);
}
.radar-summary {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px;
    margin: 14px 0 18px;
}
.radar-kpi {
    background: rgba(255,255,255,.9);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 14px 16px;
    box-shadow: 0 10px 28px rgba(15,23,42,.05);
}
.radar-kpi .k-label {
    display: block;
    color: var(--ink-3);
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
}
.radar-kpi .k-value {
    display: block;
    color: var(--ink);
    font-size: 24px;
    font-weight: 800;
    line-height: 1.2;
    margin-top: 5px;
}
.radar-kpi .k-note {
    display: block;
    color: var(--ink-2);
    font-size: 12px;
    margin-top: 4px;
}
[data-testid="stSidebar"] {
    background: #eef3f8 !important;
}
[data-testid="stSidebar"] section {
    padding-top: 1.4rem;
}
.stTextInput input,
.stTextArea textarea,
.stSelectbox > div > div,
div[data-baseweb="select"] > div {
    border-radius: 8px !important;
    background: #fff !important;
}
.stButton > button,
[data-testid="stDownloadButton"] > button {
    border-radius: 8px !important;
    min-height: 38px;
    font-weight: 700;
}
.section-label {
    background: transparent;
    border-bottom: 1px solid var(--line);
    margin-top: 24px;
}
.section-label .sl-title {
    color: var(--ink);
    font-size: 14px;
}
.section-label .sl-sub {
    color: var(--ink-2);
}
.hero-card,
.comp-card,
.art-card,
.source-row,
.ticker-wrapper,
.ticker-item,
.col-card,
.tom-card {
    border-radius: 8px !important;
}
.hero-card {
    background: #fff;
    box-shadow: 0 16px 36px rgba(15,23,42,.07);
    min-height: 236px;
}
.hero-card.hero-warn {
    background: linear-gradient(180deg, #fff7f7, #fff);
}
.hero-card.hero-event {
    background: linear-gradient(180deg, #effaf7, #fff);
}
.hero-card.hero-volume {
    background: linear-gradient(180deg, #fff7ed, #fff);
}
.hero-card.hero-info {
    background: linear-gradient(180deg, #eff6ff, #fff);
}
.hero-company {
    font-size: 24px;
}
.hero-preview {
    background: rgba(248,250,252,.92);
}
.comp-card {
    background: rgba(255,255,255,.94);
    border: 1px solid var(--line);
    box-shadow: 0 10px 24px rgba(15,23,42,.045);
    min-height: 142px;
}
.comp-card:hover {
    transform: translateY(-1px);
    box-shadow: 0 16px 34px rgba(15,23,42,.08);
}
.comp-tint-neg {
    background: linear-gradient(180deg, #fff5f5, #fff);
}
.comp-tint-pos {
    background: linear-gradient(180deg, #effaf7, #fff);
}
.comp-card-selected {
    box-shadow: 0 0 0 2px rgba(15,118,110,.2), 0 16px 34px rgba(15,23,42,.08);
}
.comp-ind-chip,
.kw-chip,
.art-kw,
.comp-detail-cat {
    background: #f8fafc;
}
.comp-detail-head {
    background: #fff;
    border: 1px solid var(--line);
    border-left: 5px solid var(--accent);
    border-radius: 8px;
    padding: 18px 20px;
}
.art-card {
    background: #fff;
    border: 1px solid var(--line);
    margin-bottom: 8px;
}
.art-card:hover {
    background: #f8fafc;
}
.sent-pill-pos,
.sent-badge-positive { background: #e7f6ef; color: #137a3f; }
.sent-pill-neg,
.sent-badge-negative { background: #fff1f2; color: #be123c; }
.sent-pill-neu,
.sent-badge-neutral { background: #eef2f7; color: #64748b; }
@media (max-width: 900px) {
    .main-header .hdr-row {
        align-items: flex-start;
        flex-direction: column;
    }
    .radar-summary {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}
@media (max-width: 560px) {
    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
    }
    .main-header h1 {
        font-size: 22px;
    }
    .radar-summary {
        grid-template-columns: 1fr;
    }
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
        # 한국어 기본 (8)
        "google", "geeknews",
        "zdnetkr", "ddaily", "venturesquare",
        "thelec", "irobotnews", "epnc",
        # 미국 메이저 비즈니스/테크 (5 — 기업 sentiment 핵심)
        "bloomberg_business", "bloomberg_tech",
        "bbc_business", "cnbc_business",
        "nyt_business",
    ])
    ss.setdefault("selected_idx", None)
    ss.setdefault("summary", "")
    ss.setdefault("chat_history", [])  # [{role, content}]
    ss.setdefault("model_name", gemma_client.DEFAULT_MODEL)
    ss.setdefault("sentiment_filter", "all")   # all | positive | negative | neutral
    ss.setdefault("sort_mode", "latest")        # latest | sentiment_strong | by_source
    ss.setdefault("cat_filter", [])             # 카테고리 다중 선택 (빈 = 전체)
    ss.setdefault("llm_boost_done", False)
    ss.setdefault("target_lang", "ko")     # ko | en
    ss.setdefault("translation_cache", {})  # {hash: translated_text}
    ss.setdefault("translated_signature", "")
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

    # 데이터 소스 — 모든 소스 자동 활성 (UI 노출 없음)
    st.session_state.sources = list(news_crawler.SOURCES.keys())

    st.markdown("### 검색")
    search_query = st.text_input(
        "회사명/키워드",
        key="search_query",
        placeholder="예: 삼성, AI, 리콜",
        label_visibility="collapsed",
    )

    st.markdown("### 정렬")
    sort_options_sidebar = {
        "부정 비율 높은 순": "neg_ratio",
        "총 기사 수 많은 순": "count",
        "알파벳순": "alpha",
    }
    sort_label_sidebar = st.selectbox(
        "정렬 기준",
        list(sort_options_sidebar.keys()),
        index=0,
        key="sort_mode_select",
        label_visibility="collapsed",
    )
    st.session_state.sort_mode = sort_options_sidebar[sort_label_sidebar]

    st.markdown("---")
    refresh_clicked = st.button("새로고침 ↻", use_container_width=True)

    with st.expander("수집 키워드 (Google News)", expanded=False):
        st.caption("아래 키워드 기반으로 Google News RSS에서 수집합니다.")
        for kw in news_crawler.SEARCH_KEYWORDS:
            st.markdown(f"- {kw}")


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

# 언어 토글 — query_params 기반 (헤더 HTML pill만 사용, 중복 native button 제거)
try:
    _qp = st.query_params
    if "lang" in _qp:
        _new_lang = _qp.get("lang", "ko")
        if _new_lang in ("ko", "en") and st.session_state.get("target_lang") != _new_lang:
            st.session_state.target_lang = _new_lang
            # 쿼리 파라미터 제거 후 rerun (URL 깔끔히, 무한 루프 방지)
            try:
                _qp.clear()
            except Exception:
                pass
            st.rerun()
except Exception:
    pass

_target_lang = st.session_state.get("target_lang", "ko")
# href 링크형 토글 (Streamlit iframe 내에서 ?lang=xx로 reload — query_params 트리거)
_lang_toggle_html = (
    "<div class='lang-toggle'>"
    f"<a class='lang-pill {('lang-pill-active' if _target_lang == 'ko' else 'lang-pill-inactive')}' "
    "href='?lang=ko' target='_self'>한국어</a>"
    f"<a class='lang-pill {('lang-pill-active' if _target_lang == 'en' else 'lang-pill-inactive')}' "
    "href='?lang=en' target='_self'>English</a>"
    "</div>"
)

st.markdown(
    f"""
    <div class="main-header">
        <div class="hdr-row">
            <div>
                <h1>선행기구개발 뉴스 레이더</h1>
                <p class="hdr-sub">모바일 · 전기차 · 부품·신소재 — 실시간 큐레이션</p>
            </div>
            <div class="hdr-meta">{_lang_toggle_html}<span style='display:inline-block;width:10px'></span>{_llm_status}</div>
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

# === 자동 번역 (target_lang 으로) ===
target_lang = st.session_state.get("target_lang", "ko")
llm_active = st.session_state.get("llm_active", False)
backend = st.session_state.get("llm_backend", "")

# Lazy translation: 한 번에 최대 N 건만 번역, 나머지는 원문 노출 (cache가 다음 reload에서 채움)
# Title 우선 (제목만 보면 70% 이해 가능), summary는 차순위
LAZY_TRANSLATE_MAX = 120   # 한 페이지 load당 최대 번역 항목 (Groq TPM 보호)

if articles and llm_active and backend:
    sig = f"{len(articles)}:{target_lang}"
    if st.session_state.get("translated_signature") != sig:
        cache = st.session_state.translation_cache
        # title 먼저 모으고, summary 뒤로 (cap 안에서 title 우선 처리)
        title_items: list[dict] = []
        summary_items: list[dict] = []
        for i, a in enumerate(articles):
            for field in ("title", "summary_raw"):
                txt = getattr(a, field, "") or ""
                if not txt.strip():
                    continue
                lang = translator.detect_lang(txt)
                if lang == target_lang:
                    continue
                h = translator.text_hash(txt, target_lang)
                if h in cache:
                    continue
                bucket = title_items if field == "title" else summary_items
                bucket.append({"id": f"{i}_{field}", "text": txt[:400], "_hash": h})

        to_translate = (title_items + summary_items)[:LAZY_TRANSLATE_MAX]

        if to_translate:
            def _chat_fn(messages):
                return gemma_client.chat(
                    messages,
                    backend=backend,
                    model=st.session_state.get("model_name", ""),
                    base_url=st.session_state.get("ollama_url", ""),
                    api_key=st.session_state.get("llm_api_key", ""),
                    temperature=0.2,
                )
            _spinner_msg = (
                f"기사 {len(to_translate)}건 {translator.LANG_NAME[target_lang]}로 번역 중... "
                f"(나머지 {max(0, len(title_items)+len(summary_items) - LAZY_TRANSLATE_MAX)}건은 다음 로드에서)"
            )
            with st.spinner(_spinner_msg):
                try:
                    results = translator.translate_batch(
                        to_translate, target_lang, _chat_fn, batch_size=5,
                        sleep_between_batches=0.3,
                    )
                except Exception as _e:
                    # 번역 실패해도 앱 진행
                    st.warning(f"일부 번역 실패 (rate limit 가능성): 원문으로 표시. {_e}")
                    results = [{"id": it["id"], "text": it["text"]} for it in to_translate]
            id_to_result = {r["id"]: r["text"] for r in results}
            for it in to_translate:
                translated = id_to_result.get(it["id"], it["text"])
                cache[it["_hash"]] = translated
            st.session_state.translation_cache = cache

        # 각 article에 _localized 필드 부여 (캐시 있으면 번역, 없으면 원문)
        for i, a in enumerate(articles):
            for field in ("title", "summary_raw"):
                txt = getattr(a, field, "") or ""
                if not txt.strip():
                    continue
                lang = translator.detect_lang(txt)
                if lang == target_lang:
                    setattr(a, f"{field}_localized", txt)
                else:
                    h = translator.text_hash(txt, target_lang)
                    setattr(a, f"{field}_localized", cache.get(h, txt))
        st.session_state.translated_signature = sig
else:
    # LLM 비활성이면 원문 그대로
    for a in (articles or []):
        a.title_localized = getattr(a, "title", "")
        a.summary_raw_localized = getattr(a, "summary_raw", "")

if not articles:
    st.info("수집된 기사가 없습니다. 좌측 사이드바의 새로고침을 눌러주세요.")
else:
    # sentiment 계산 (캐시)
    if not sents or len(sents) != len(articles):
        sents = [sentiment_classifier.classify(a.title, a.summary_raw) for a in articles]
        st.session_state.sentiments = sents

    pos_total = sum(1 for s in sents if s.label == "positive")
    neg_total = sum(1 for s in sents if s.label == "negative")
    neu_total = sum(1 for s in sents if s.label == "neutral")
    sources_total = len({getattr(a, "source", "") for a in articles if getattr(a, "source", "")})
    last_refresh = st.session_state.get("last_refresh")
    last_refresh_label = last_refresh.strftime("%H:%M") if last_refresh else "대기"
    st.markdown(
        f"""
        <div class="radar-summary">
            <div class="radar-kpi">
                <span class="k-label">Collected</span>
                <span class="k-value">{len(articles)}</span>
                <span class="k-note">최근 수집 기사</span>
            </div>
            <div class="radar-kpi">
                <span class="k-label">Risk Signals</span>
                <span class="k-value">{neg_total}</span>
                <span class="k-note">부정 이슈 후보</span>
            </div>
            <div class="radar-kpi">
                <span class="k-label">Positive Signals</span>
                <span class="k-value">{pos_total}</span>
                <span class="k-note">긍정/기회 신호</span>
            </div>
            <div class="radar-kpi">
                <span class="k-label">Sources</span>
                <span class="k-value">{sources_total}</span>
                <span class="k-note">업데이트 {last_refresh_label} · 중립 {neu_total}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 기업별 그룹핑
    company_articles: dict[str, list] = {}   # name -> [(idx, article, sentiment), ...]
    for i, (art, s) in enumerate(zip(articles, sents)):
        for cname in company_extractor.extract_companies(art.title, art.summary_raw):
            company_articles.setdefault(cname, []).append((i, art, s))

    # === 3단계 분류 필터 ===
    # 대분류 (topic) — 단일 선택
    TOPIC_OPTIONS = {"전체": "all", "모바일": "mobile", "AI": "ai", "로봇": "robot"}
    cur_topic = st.session_state.get("topic_filter", "all")
    cur_topic_label = next((l for l, v in TOPIC_OPTIONS.items() if v == cur_topic), "전체")
    sel_topic = st.radio(
        "대분류",
        list(TOPIC_OPTIONS.keys()),
        index=list(TOPIC_OPTIONS.keys()).index(cur_topic_label),
        horizontal=True,
        label_visibility="collapsed",
    )
    st.session_state.topic_filter = TOPIC_OPTIONS[sel_topic]
    selected_topic = st.session_state.topic_filter

    # 대분류 적용 — 회사 industries 기준 (회사 사업 영위로 필터)
    # 'mobile' / 'ai' / 'robot' 산업을 가진 회사만 통과
    # 회사 카드 노출은 회사 단위. 기사 단위 topic 매칭은 보조 (배지 표시용)
    if selected_topic != "all":
        company_articles_filtered = {
            cname: arr for cname, arr in company_articles.items()
            if selected_topic in company_extractor.industries_of(cname)
        }
    else:
        company_articles_filtered = dict(company_articles)

    # 중분류 (country) — 다중 선택 chip
    countries_present = sorted({
        company_extractor.country_of(n)
        for n in company_articles_filtered.keys()
    } - {""})
    cur_countries = st.session_state.get("country_filter", [])
    if countries_present:
        st.markdown("<div class='filter-row-label'>국가</div>", unsafe_allow_html=True)
        cn_cols = st.columns(max(1, min(len(countries_present), 7)))
        for idx, ck in enumerate(countries_present):
            lbl = company_extractor.COUNTRY_LABELS.get(ck, ck)
            is_active = ck in cur_countries
            suffix = "  ✓" if is_active else ""
            if cn_cols[idx % len(cn_cols)].button(lbl + suffix, key=f"cn_{ck}", use_container_width=True):
                if is_active:
                    cur_countries.remove(ck)
                else:
                    cur_countries.append(ck)
                st.session_state.country_filter = cur_countries
                st.rerun()

    if cur_countries:
        company_articles_filtered = {
            n: arr for n, arr in company_articles_filtered.items()
            if company_extractor.country_of(n) in cur_countries
        }

    # 소분류 (회사) — 다중 선택 chip (현재 필터 결과 회사들만 노출)
    companies_present = sorted(company_articles_filtered.keys())
    cur_companies = st.session_state.get("company_select_filter", [])
    if companies_present and len(companies_present) <= 30:
        st.markdown("<div class='filter-row-label'>회사</div>", unsafe_allow_html=True)
        per_row = 7
        rows = [companies_present[i:i+per_row] for i in range(0, len(companies_present), per_row)]
        for row in rows:
            row_cols = st.columns(per_row)
            for idx, cn in enumerate(row):
                is_active = cn in cur_companies
                suffix = "  ✓" if is_active else ""
                if row_cols[idx].button(cn + suffix, key=f"sel_{cn}", use_container_width=True):
                    if is_active:
                        cur_companies.remove(cn)
                    else:
                        cur_companies.append(cn)
                    st.session_state.company_select_filter = cur_companies
                    st.rerun()

    if cur_companies:
        company_articles_filtered = {
            n: arr for n, arr in company_articles_filtered.items()
            if n in cur_companies
        }

    # 이후 모든 처리 (Top of Mind / 통계 / 카드 그리드)는 company_articles_filtered 사용
    company_articles = company_articles_filtered

    # === Helper: 회사별 핵심 키워드 추출 (sentiment 매칭 토큰 top N) ===
    def _company_keywords(arr, top_n=3):
        from collections import Counter
        pos_c, neg_c = Counter(), Counter()
        for _, _a, s in arr:
            for tok in (getattr(s, "pos_hits", None) or []):
                pos_c[tok] += 1
            for tok in (getattr(s, "neg_hits", None) or []):
                neg_c[tok] += 1
        out = []
        # 부정 토큰 우선 (more actionable), 빈도순
        for tok, _cnt in neg_c.most_common(top_n):
            out.append((tok, "neg"))
        for tok, _cnt in pos_c.most_common(top_n):
            if len(out) >= top_n:
                break
            out.append((tok, "pos"))
        return out[:top_n], sum(pos_c.values()) + sum(neg_c.values())

    def _status_icon_html(pos_pct, neg_pct, scale="comp"):
        prefix = scale  # "comp" or "hero"
        if neg_pct >= 50:
            return f"<span class='{prefix}-status-icon {prefix}-status-warn' title='경고: 부정 비율 매우 높음'>!</span>"
        if neg_pct >= 30:
            return f"<span class='{prefix}-status-icon {prefix}-status-down' title='하락 신호: 부정 비율 30%+'>▼</span>"
        if pos_pct >= 60:
            return f"<span class='{prefix}-status-icon {prefix}-status-up' title='상승 신호: 긍정 비율 60%+'>▲</span>"
        return ""

    def _kw_chips_html(kws, max_chips=3):
        if not kws:
            return ""
        chips = "".join(
            f"<span class='kw-chip kw-chip-{kind}' title='매칭 키워드'>{html.escape(tok)}</span>"
            for tok, kind in kws[:max_chips]
        )
        return f"<div class='kw-row'>{chips}</div>"

    # === 오늘 주목 (TOP 3 hero) ===
    highlights = top_of_mind.compute_top_of_mind(company_articles, limit=10)
    top3 = highlights[:3]
    if top3:
        st.markdown(
            "<div class='section-label'><span class='sl-title'>오늘 주목</span>"
            "<span class='sl-sub'>자동 큐레이션 · 부정 집중 · 다중 매체 · 주요 이벤트</span></div>",
            unsafe_allow_html=True,
        )
        hero_cols = st.columns(len(top3), gap="medium")
        for col, h in zip(hero_cols, top3):
            arr = company_articles.get(h.company, [])
            pos = sum(1 for _, _, s in arr if s.label == "positive")
            neg = sum(1 for _, _, s in arr if s.label == "negative")
            neu = sum(1 for _, _, s in arr if s.label == "neutral")
            total = len(arr) or 1
            pos_pct = pos * 100 // total
            neg_pct = neg * 100 // total
            neu_pct = 100 - pos_pct - neg_pct
            kws, _ = _company_keywords(arr, top_n=5)
            sicon = _status_icon_html(pos_pct, neg_pct, scale="hero")
            # 관련 기사 미리보기 (제목 1-2건)
            preview_arts = arr[:2]
            preview_html = ""
            for _, a, _ in preview_arts:
                t = html.escape((getattr(a, "title_localized", None) or a.title or "")[:80])
                preview_html += f"<div class='hero-preview'><span class='hp-title'>{t}</span></div>"
            kw_chips = "".join(
                f"<span class='kw-chip kw-chip-{kind}'>{html.escape(tok)}</span>"
                for tok, kind in kws[:4]
            )
            kw_block = f"<div class='kw-row'>{kw_chips}</div>" if kw_chips else ""
            col.markdown(
                f"""<div class='hero-card hero-{h.type}'>
                    <div class='hero-reason'>{html.escape(h.reason)} · {html.escape(h.detail)}</div>
                    <div class='hero-company'>{sicon}<span>{html.escape(h.company)}</span></div>
                    <div class='hero-ratio-row'>
                        <div class='hero-ratio-bar'>
                            <div class='r-pos' style='width:{pos_pct}%'></div>
                            <div class='r-neg' style='width:{neg_pct}%'></div>
                            <div class='r-neu' style='width:{neu_pct}%'></div>
                        </div>
                        <div class='hero-counts'>
                            <span class='hc-pos'>{pos}</span> ·
                            <span class='hc-neg'>{neg}</span> ·
                            <span class='hc-neu'>{neu}</span> /{total}
                        </div>
                    </div>
                    {kw_block}
                    {preview_html}
                </div>""",
                unsafe_allow_html=True,
            )
            if col.button(f"{h.company} 상세 분석", key=f"hero_{h.company}", use_container_width=True):
                st.session_state.selected_company = h.company
                st.rerun()
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # 사이드바에서 정렬 모드 가져오기
    sort_mode = st.session_state.get("sort_mode", "neg_ratio")

    # 검색 필터 적용 (회사명 또는 기사 제목에 매치)
    _q = (st.session_state.get("search_query") or "").strip().lower()
    if _q:
        company_articles = {
            c: arr for c, arr in company_articles.items()
            if (_q in c.lower())
               or any(_q in ((a.title or "") + " " + (a.summary_raw or "")).lower()
                      for _, a, _s in arr)
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
        selected_company = st.session_state.get("selected_company")
        # 최신 기사 회사 — 최근 6시간 내 published_dt 가진 article 보유 회사
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        _cutoff = _dt.now(_tz.utc) - _td(hours=6)

        def _has_recent(arr):
            for _, a, _s in arr:
                dt = getattr(a, "published_dt", None)
                if dt is not None and dt >= _cutoff:
                    return True
            return False

        # 섹션별 분류
        all_companies = company_list  # already sorted by neg_ratio
        neg_focus = [(c, arr) for c, arr in all_companies
                     if _stats_for(arr)[4] >= 0.4 and _stats_for(arr)[3] >= 3][:8]
        most_mentioned = sorted(all_companies, key=lambda kv: -_stats_for(kv[1])[3])[:8]
        recent_companies = [(c, arr) for c, arr in all_companies if _has_recent(arr)][:8]

        # 이미 hero에서 노출된 회사는 섹션에서 dim 처리 안하고 그냥 노출 — 사용자 메모리 유지

        def _render_card_grid(items, n_cols=5, section_key=""):
            """items: [(cname, arr), ...] → compact 카드 그리드."""
            if not items:
                return
            rows = [items[i:i+n_cols] for i in range(0, len(items), n_cols)]
            for row_i, row in enumerate(rows):
                cols = st.columns(n_cols, gap="small")
                for ci, item in enumerate(row):
                    cname, arr = item
                    col = cols[ci]
                    pos, neg, neu, total, neg_ratio = _stats_for(arr)
                    pos_pct = pos * 100 // total if total else 0
                    neg_pct = neg * 100 // total if total else 0
                    neu_pct = 100 - pos_pct - neg_pct
                    pos_ratio = pos / total if total else 0
                    cat_lbl = company_extractor.category_label(cname)
                    is_sel = (selected_company == cname)
                    sel_class = " comp-card-selected" if is_sel else ""
                    strip = "neg" if neg_ratio >= 0.35 else ("pos" if pos_ratio >= 0.5 else "neu")
                    # 배경 틴트
                    tint_class = ""
                    if neg_ratio >= 0.4:
                        tint_class = " comp-tint-neg"
                    elif pos_ratio >= 0.6:
                        tint_class = " comp-tint-pos"
                    ind_lbls = company_extractor.industry_labels(cname)[:3]
                    ind_chips = "".join(f"<span class='comp-ind-chip'>{html.escape(l)}</span>" for l in ind_lbls)
                    # 상태 아이콘
                    sicon = _status_icon_html(pos_pct, neg_pct, scale="comp")
                    # 키워드 chip
                    kws, _kw_total = _company_keywords(arr, top_n=3)
                    kw_html = _kw_chips_html(kws, max_chips=3)
                    # tooltip: 비중 큰 뉴스 제목 (max 2)
                    title_hints = []
                    for _, a, _s in arr[:2]:
                        t = (getattr(a, "title_localized", None) or a.title or "")[:80]
                        if t:
                            title_hints.append(t)
                    tooltip = " · ".join(title_hints).replace('"', "&quot;").replace("'", "&#39;")
                    col.markdown(
                        f"""<div class='comp-card comp-strip-{strip}{tint_class}{sel_class}' title="{html.escape(tooltip)}">
                            <div class='comp-name'><span>{html.escape(cname)}</span>{sicon}</div>
                            <div class='comp-cat'>{html.escape(cat_lbl)}</div>
                            <div class='comp-inds'>{ind_chips}</div>
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
                            {kw_html}
                        </div>""",
                        unsafe_allow_html=True,
                    )
                    if col.button("상세", key=f"comp_sel_{section_key}_{cname}", use_container_width=True):
                        st.session_state.selected_company = cname
                        st.rerun()

        # --- 부정 집중 섹션 ---
        if neg_focus:
            st.markdown(
                "<div class='section-label'><span class='sl-title'>부정 집중</span>"
                "<span class='sl-sub'>부정 비율 40%+ · 기사 3건+</span></div>",
                unsafe_allow_html=True,
            )
            _render_card_grid(neg_focus, n_cols=5, section_key="neg")

        # --- 최다 언급 ---
        if most_mentioned:
            st.markdown(
                "<div class='section-label'><span class='sl-title'>가장 많이 언급된 회사</span>"
                f"<span class='sl-sub'>전체 {len(all_companies)}개 기업 중 상위 8</span></div>",
                unsafe_allow_html=True,
            )
            _render_card_grid(most_mentioned, n_cols=5, section_key="vol")

        # --- 최신 이슈 ---
        if recent_companies:
            st.markdown(
                "<div class='section-label'><span class='sl-title'>최신 이슈</span>"
                "<span class='sl-sub'>최근 6시간 신규 기사 회사</span></div>",
                unsafe_allow_html=True,
            )
            _render_card_grid(recent_companies, n_cols=5, section_key="rec")

        # --- 전체 ---
        st.markdown(
            f"<div class='section-label'><span class='sl-title'>전체</span>"
            f"<span class='sl-sub'>{len(all_companies)}개 기업</span></div>",
            unsafe_allow_html=True,
        )
        _render_card_grid(all_companies, n_cols=5, section_key="all")

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
                # 균형 선택: pos top 3 + neg top 3 + neu top 4 = 10건 (sentiment score 절대값 큰 순)
                _pos_arts = sorted(
                    [(i, a, s) for i, a, s in sel_arr if s.label == "positive"],
                    key=lambda x: -abs(x[2].score),
                )[:3]
                _neg_arts = sorted(
                    [(i, a, s) for i, a, s in sel_arr if s.label == "negative"],
                    key=lambda x: -abs(x[2].score),
                )[:3]
                _neu_arts = [(i, a, s) for i, a, s in sel_arr if s.label == "neutral"][:4]
                picked = _pos_arts + _neg_arts + _neu_arts
                if not picked:
                    picked = sel_arr[:10]

                with st.spinner(f"{selected_company} 관련 핵심 {len(picked)}건을 LLM이 분석 중..."):
                    titles_summary = "\n".join(
                        f"- [{s.label_ko}] {(getattr(a, 'title_localized', None) or a.title)[:120]}: "
                        f"{(getattr(a, 'summary_raw_localized', None) or a.summary_raw or '')[:100]}"
                        for _, a, s in picked
                    )
                    try:
                        synth = gemma_client.chat(
                            [
                                {"role": "system", "content": (
                                    f"{selected_company} 관련 최근 뉴스 핵심 분석. "
                                    "한국어 3단락: ①핵심 동향, ②리스크, ③기회. 각 단락 2-3문장."
                                )},
                                {"role": "user", "content": f"{selected_company} 기사:\n{titles_summary}"},
                            ],
                            backend=st.session_state.llm_backend,
                            model=st.session_state.model_name,
                            base_url=st.session_state.ollama_url,
                            api_key=st.session_state.get("llm_api_key", ""),
                            temperature=0.3,
                        )
                        st.session_state[f"comp_synth_{selected_company}"] = synth
                    except Exception as e:
                        _msg = str(e)
                        if "429" in _msg or "rate" in _msg.lower():
                            st.error(
                                f"AI 요청량이 많아 잠시 후 다시 시도해 주세요. "
                                f"(Groq Rate Limit — 30초 후 자동 가능)"
                            )
                        else:
                            st.error(f"분석 실패: {_msg[:200]}")

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
                        <div class='art-title'><a href='{html.escape(art.link)}' target='_blank' rel='noopener'>{html.escape(getattr(art, "title_localized", None) or art.title)}</a></div>
                        <div class='art-summary'>{html.escape((getattr(art, "summary_raw_localized", None) or art.summary_raw or "")[:200])}</div>
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
