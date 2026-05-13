"""선행기구개발그룹 뉴스 레이더.

레이아웃:
  ① 섹터 선택 (모바일 / 로보틱스 / AI)
  ② 회사 로고 그리드 (Clearbit 로고)
  ③ 3열: 뉴스 리스트 | 감성 분석 | 루머 피드
"""
from __future__ import annotations

import html
import math
from datetime import datetime
from urllib.parse import quote

import streamlit as st
import streamlit.components.v1 as components

import analyst
import news_crawler
from news_crawler import (
    SECTORS, MECH_CATEGORIES, MECH_CATEGORY_GENERAL,
    ARTICLE_CATEGORIES, TOP_CATEGORY_GENERAL,
)

st.set_page_config(
    page_title="Mxplorer-news",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
/* ══════════════════════════════════════════════════════
   Mxplorer-news — Samsung.com Light Theme
   ──────────────────────────────────────────────────────
   BG        : #FFFFFF / #F4F4F4
   Text      : #1C1C1C / #535353 / #999999
   Blue      : #1428A0  (Samsung Blue)
   Blue-lite : #0089D0
   Green     : #00B140  (Samsung Green)
   Red       : #E4002B  (Samsung Red)
   Magenta   : #C800A1  (Samsung Magenta)
   Border    : #E6E6E6
   Radius    : 4px cards · 999px pills
   Font      : SamsungOne → Apple SD Gothic Neo → system
══════════════════════════════════════════════════════ */

@font-face {
  font-family:'SamsungOne';
  src:url('https://cdn.jsdelivr.net/gh/Samsung/SamsungOne@main/SamsungOne-400.woff2') format('woff2');
  font-weight:400; font-style:normal;
}

html, body,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background:#F4F4F4 !important;
    color:#1C1C1C !important;
    font-family:'SamsungOne','Apple SD Gothic Neo','Malgun Gothic',
                'Noto Sans KR','Helvetica Neue',Arial,sans-serif;
}
[data-testid="stSidebar"] { background:#FFFFFF; border-right:1px solid #E6E6E6; }
[data-testid="stAppViewBlockContainer"] { padding-top:12px !important; }
[data-testid="stDecoration"], [data-testid="stStatusWidget"],
footer, #MainMenu { display:none !important; }

/* ── 헤더 ─────────────────────────────── */
.mxp-header {
    background:#FFFFFF;
    padding:18px 28px 16px;
    border-bottom:2px solid #1428A0;
    margin-bottom:16px;
    box-shadow:0 2px 12px rgba(0,0,0,0.06);
}
.mxp-header h1 {
    margin:0; font-size:22px; font-weight:700;
    color:#1C1C1C; letter-spacing:-0.5px;
}
.mxp-header h1 span { color:#1428A0; }
.mxp-header p {
    margin:4px 0 0; font-size:11px;
    color:#999999; letter-spacing:.2px;
}

/* ── Streamlit 버튼 (카테고리 필터 전용) ─ */
div[data-testid="stHorizontalBlock"] button {
    border-radius:4px !important;
    font-size:11px !important;
    font-weight:600 !important;
    padding:4px 6px !important;
    transition:all .12s !important;
}
button[kind="primary"] {
    background:#1428A0 !important;
    border-color:#1428A0 !important;
    color:#FFFFFF !important;
}
button[kind="primary"]:hover  { background:#1034C8 !important; }
button[kind="secondary"] {
    background:#FFFFFF !important;
    border-color:#D0D0D0 !important;
    color:#535353 !important;
}
button[kind="secondary"]:hover {
    border-color:#1428A0 !important;
    color:#1428A0 !important;
}


/* ── 뉴스 카드 ─────────────────────────── */
.news-card {
    background:#FFFFFF;
    border-radius:4px;
    padding:12px 14px;
    margin-bottom:8px;
    border:1px solid #E6E6E6;
    border-left:3px solid #D0D0D0;
    box-shadow:0 1px 4px rgba(0,0,0,0.05);
    transition:box-shadow .12s, border-left-color .12s;
}
.news-card:hover    { box-shadow:0 4px 16px rgba(0,0,0,0.10); }
.news-card.positive { border-left-color:#00B140; }
.news-card.negative { border-left-color:#E4002B; }
.news-card.neutral  { border-left-color:#1428A0; }
.news-card.rumor    { border-left-color:#C800A1; }
.news-card a        { text-decoration:none; color:inherit; }
.news-title {
    font-size:13px; font-weight:600;
    line-height:1.5; margin-bottom:6px; color:#1C1C1C;
}
.news-meta {
    font-size:11px; color:#999999;
    display:flex; gap:7px; flex-wrap:wrap; align-items:center;
}

/* ── 뱃지 ─────────────────────────────── */
.badge {
    display:inline-block; padding:2px 9px;
    border-radius:999px;
    font-size:10px; font-weight:700; line-height:1.6;
}
.b-pos   { background:#E6F7EC; color:#00873A; border:1px solid #B3E6C8; }
.b-neg   { background:#FDECEA; color:#C00020; border:1px solid #F5B8BE; }
.b-neu   { background:#EEF1FB; color:#1428A0; border:1px solid #C4CDEE; }
.b-rumor { background:#FCE8F8; color:#A0007E; border:1px solid #EAB3DC; }
.b-src   { background:#F4F4F4; color:#767676; border:1px solid #E0E0E0; }

/* ── 루머 카드 ─────────────────────────── */
.rumor-card {
    background:#FFFFFF;
    border:1px solid #E6E6E6;
    border-top:3px solid #C800A1;
    border-radius:4px;
    padding:12px 14px; margin-bottom:8px;
    box-shadow:0 1px 4px rgba(0,0,0,0.05);
}
.r-title   { font-size:13px; font-weight:600; color:#1C1C1C; line-height:1.45; margin-bottom:4px; }
.r-orig    { font-size:10px; color:#C800A1; margin-bottom:4px; }
.r-summary { font-size:11px; color:#535353; line-height:1.55; margin-bottom:6px; }
.r-meta    { font-size:10px; color:#999999; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }

/* ── 감성 바 ─────────────────────────── */
.ratio-bar {
    display:flex; border-radius:999px;
    overflow:hidden; height:7px; margin:8px 0 6px;
}

/* ── 스크롤 ─────────────────────────── */
.scroll-box { max-height:68vh; overflow-y:auto; padding-right:4px; }
.scroll-box::-webkit-scrollbar { width:4px; }
.scroll-box::-webkit-scrollbar-track { background:#F4F4F4; }
.scroll-box::-webkit-scrollbar-thumb { background:#D0D0D0; border-radius:999px; }

/* ── 컬럼 헤더 ─────────────────────── */
.col-header {
    font-size:12px; font-weight:700; color:#1428A0;
    border-bottom:1px solid #E6E6E6;
    padding-bottom:8px; margin-bottom:12px;
    letter-spacing:.5px; text-transform:uppercase;
}

/* ── 카테고리 배지 ─────────────────── */
.b-cat {
    display:inline-block; padding:2px 8px;
    border-radius:999px; font-size:10px;
    font-weight:600; line-height:1.6;
}
.cat-design    { background:#F0EEFF; color:#4B3BBF; border:1px solid #CEC8F5; }
.cat-material  { background:#E6F5FC; color:#005B8A; border:1px solid #B3D9EE; }
.cat-spec      { background:#E6F7EC; color:#00612A; border:1px solid #B3E0C8; }
.cat-durability{ background:#FFF8E1; color:#8A6000; border:1px solid #FFE599; }
.cat-mfg       { background:#FDECEA; color:#A0001A; border:1px solid #F5B8BE; }
.cat-thermal   { background:#FFF0E6; color:#8A3200; border:1px solid #FFCBA8; }
.cat-mech      { background:#FCE8F8; color:#7A0060; border:1px solid #EAB3DC; }
.cat-general   { background:#F4F4F4; color:#767676; border:1px solid #E0E0E0; }

/* ── 카테고리 분포 행 ─────────────── */
.cat-row {
    display:flex; align-items:center; gap:8px;
    margin-bottom:6px; padding:7px 10px;
    background:#FFFFFF; border-radius:4px;
    border:1px solid #E6E6E6;
    box-shadow:0 1px 3px rgba(0,0,0,0.04);
}
.cat-bar-bg {
    flex:1; height:5px;
    background:#F4F4F4; border-radius:999px; overflow:hidden;
}
.cat-bar    { height:5px; border-radius:999px; }
.cat-count  { font-size:11px; color:#999999; min-width:30px; text-align:right; font-weight:600; }

/* ── Expander 스타일 ─────────────── */
[data-testid="stExpander"] {
    border:1px solid #E6E6E6 !important;
    border-radius:4px !important;
    background:#FFFFFF !important;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# 세션 상태
# ─────────────────────────────────────────────
def _init():
    st.session_state.setdefault("articles", [])
    st.session_state.setdefault("selected_sector", "모바일")
    st.session_state.setdefault("selected_company", "전체")
    st.session_state.setdefault("selected_top_cat", "기술·개발")   # 기구개발 기본값
    st.session_state.setdefault("selected_cat", "전체")
    st.session_state.setdefault("last_refresh", None)
_init()

# ── Query param 처리 (섹터/회사 HTML 링크 버튼 지원) ──
_qp_sec = st.query_params.get("sec")
_qp_co  = st.query_params.get("co")
if _qp_sec or _qp_co:
    if _qp_sec and _qp_sec in SECTORS:
        st.session_state.selected_sector = _qp_sec
        st.session_state.selected_company = "전체"
    if _qp_co:
        st.session_state.selected_company = _qp_co
    st.query_params.clear()
    st.rerun()


# ─────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────
# Simple Icons slug 매핑 (https://simpleicons.org)
# 없는 브랜드는 initials fallback 사용
_SIMPLE_ICONS: dict[str, str] = {
    "samsung.com":          "samsung",
    "apple.com":            "apple",
    "huawei.com":           "huawei",
    "oppo.com":             "oppo",
    "xiaomi.com":           "xiaomi",
    "google.com":           "google",
    "sony.com":             "sony",
    "hyundai.com":          "hyundai",
    "tesla.com":            "tesla",
    "openai.com":           "openai",
    "anthropic.com":        "anthropic",
    "meta.com":             "meta",
    "microsoft.com":        "microsoft",
    "nvidia.com":           "nvidia",
    "mistral.ai":           "mistral",
    # xAI — Simple Icons에 없음, 이니셜로 대체
    # Boston Dynamics / Figure AI / Agility / Unitree / 1X / Apptronik — 이니셜로 대체
}

# Simple Icons에 없는 브랜드 이니셜 + 색상
_BRAND_INITIALS: dict[str, tuple[str, str]] = {
    "x.ai":                 ("xAI",  "#1DA1F2"),
    "bostondynamics.com":   ("BD",   "#F97316"),
    "figure.ai":            ("FIG",  "#8B5CF6"),
    "agilityrobotics.com":  ("AR",   "#10B981"),
    "unitree.com":          ("UNI",  "#EF4444"),
    "1x.tech":              ("1X",   "#F59E0B"),
    "apptronik.com":        ("APT",  "#6366F1"),
}


def _logo_img(domain: str, size: int = 20, force_white: bool = False) -> str:
    slug = _SIMPLE_ICONS.get(domain)
    if slug:
        color_suffix = "/ffffff" if force_white else ""
        si = f"https://cdn.simpleicons.org/{slug}{color_suffix}"
        fb = f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
        return (
            f'<img src="{si}" width="{size}" height="{size}" '
            f'style="border-radius:3px;object-fit:contain;vertical-align:middle;" '
            f'onerror="this.onerror=null;this.src=\'{fb}\'">'
        )
    # 이니셜 뱃지 (Simple Icons에 없는 브랜드)
    if domain in _BRAND_INITIALS:
        text, bg = _BRAND_INITIALS[domain]
        fs = max(7, size // 3)
        badge_bg = "rgba(255,255,255,0.2)" if force_white else bg
        return (
            f'<span style="display:inline-flex;align-items:center;justify-content:center;'
            f'width:{size}px;height:{size}px;background:{badge_bg};border-radius:3px;'
            f'font-size:{fs}px;font-weight:800;color:#fff;vertical-align:middle;'
            f'letter-spacing:-0.5px;box-shadow:0 1px 3px rgba(0,0,0,0.15);">{text}</span>'
        )
    fb = f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
    return (
        f'<img src="{fb}" width="{size}" height="{size}" '
        f'style="border-radius:3px;object-fit:contain;vertical-align:middle;">'
    )


_CAT_CSS = {
    "디자인·폼팩터":  "cat-design",
    "소재·재질":      "cat-material",
    "사양·치수":      "cat-spec",
    "내구성·신뢰성":  "cat-durability",
    "제조·공정":      "cat-mfg",
    "열관리·냉각":    "cat-thermal",
    "힌지·메커니즘":  "cat-mech",
    MECH_CATEGORY_GENERAL: "cat-general",
}

_TOP_CAT_CSS = {
    "기술·개발":   "cat-material",
    "마케팅·출시": "cat-design",
    "사업·전략":   "cat-spec",
    TOP_CATEGORY_GENERAL: "cat-general",
}

def _top_cat_badge(cat: str) -> str:
    cls = _TOP_CAT_CSS.get(cat, "cat-general")
    return f"<span class='badge b-cat {cls}'>{cat}</span>"

def _category_badge(cat: str) -> str:
    cls = _CAT_CSS.get(cat, "cat-general")
    return f"<span class='badge b-cat {cls}'>{cat}</span>"


def _sentiment_badge(s: str) -> str:
    m = {"positive": ("b-pos","긍정"), "negative": ("b-neg","부정"), "neutral": ("b-neu","중립")}
    cls, lbl = m.get(s, ("b-neu","중립"))
    return f"<span class='badge {cls}'>{lbl}</span>"


def _source_badge(name: str) -> str:
    return f"<span class='badge b-src'>{html.escape(name)}</span>"


def _news_card_html(art: news_crawler.Article, an: analyst.ArticleAnalysis) -> str:
    extra = " rumor" if art.is_rumor else ""
    safe_t = html.escape(art.display_title)
    logo = ""
    if art.logo_url:
        logo = _logo_img(
            SECTORS.get(art.sector, {}).get("companies", {}).get(art.company, {}).get("domain", ""),
            size=16
        ) + " "
    rumor_badge = "<span class='badge b-rumor'>루머</span> " if art.is_rumor else ""
    cat_badge = _top_cat_badge(art.top_category)
    if art.top_category == "기술·개발" and art.mech_category != MECH_CATEGORY_GENERAL:
        cat_badge += " " + _category_badge(art.mech_category)
    return (
        f"<div class='news-card {an.sentiment}{extra}'>"
        f"<a href='{art.link}' target='_blank'>"
        f"  <div class='news-title'>{logo}{safe_t}</div>"
        f"</a>"
        f"<div class='news-meta'>"
        f"  {cat_badge} {rumor_badge}{_sentiment_badge(an.sentiment)}"
        f"  {_source_badge(art.source)}"
        f"  <span>{art.published_ago}</span>"
        f"</div></div>"
    )


def _ratio_bar_html(pos: int, neg: int, total: int) -> str:
    if not total:
        return ""
    p = round(pos / total * 100)
    n = round(neg / total * 100)
    neu = 100 - p - n
    return (
        f"<div class='ratio-bar'>"
        f"<div style='width:{p}%;background:#00B140;'></div>"
        f"<div style='width:{neu}%;background:#E0E0E0;'></div>"
        f"<div style='width:{n}%;background:#E4002B;'></div>"
        f"</div>"
        f"<div style='font-size:11px;color:#999;display:flex;gap:10px;'>"
        f"<span style='color:#00873A;'>긍정 {p}% ({pos})</span>"
        f"<span style='color:#767676;'>중립 {neu}% ({total-pos-neg})</span>"
        f"<span style='color:#C00020;'>부정 {n}% ({neg})</span>"
        f"</div>"
    )


# ─────────────────────────────────────────────
# 데이터 로드 + 5분 자동 새로고침
# ─────────────────────────────────────────────
_AUTO_REFRESH_SEC = 300   # 5분

# 메타 태그로 브라우저 자동 새로고침
st.markdown(
    f'<meta http-equiv="refresh" content="{_AUTO_REFRESH_SEC}">',
    unsafe_allow_html=True,
)

def _load():
    with st.spinner("뉴스 수집 중..."):
        st.session_state.articles = news_crawler.get_cached_articles(force_refresh=False)
    st.session_state.last_refresh = datetime.now()

if not st.session_state.articles:
    _load()

articles: list[news_crawler.Article] = st.session_state.articles
analyses: dict[str, analyst.ArticleAnalysis] = {a.link: analyst.analyze_article(a) for a in articles}


# ─────────────────────────────────────────────
# 헤더
# ─────────────────────────────────────────────
age = news_crawler.cache_age_seconds()
age_str = f"{int(age//60)}분 전" if age else "방금"

st.markdown(
    f'<div class="mxp-header">'
    f'<h1>Mx<span>plorer</span>-news</h1>'
    f'<p>MOBILE &nbsp;·&nbsp; ROBOTICS &nbsp;·&nbsp; AI &nbsp;│&nbsp; {age_str} &nbsp;·&nbsp; {len(articles)}건 &nbsp;·&nbsp; 5분 자동 갱신</p>'
    f'</div>',
    unsafe_allow_html=True,
)

if news_crawler.is_demo_mode:
    st.warning("데모 모드 — 샘플 데이터 표시 중. Streamlit Cloud에서 실제 뉴스 수집.")


# ── 버튼 컴포넌트 공통 CSS (iframe 내부용) ──────
_BTN_CSS = """
<style>
* { box-sizing:border-box; }
body { margin:0; padding:0; background:transparent;
       font-family:'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',Arial,sans-serif; }
.row { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:0; }
.btn {
    display:inline-flex; align-items:center; gap:5px;
    padding:6px 10px; border-radius:4px;
    font-size:12px; font-weight:600; line-height:1.4;
    border:1px solid #D0D0D0; background:#FFFFFF; color:#535353;
    cursor:pointer; transition:all .12s; white-space:nowrap; flex:1;
    justify-content:center; user-select:none;
}
.btn:hover { border-color:#1428A0; color:#1428A0; }
.btn.active { background:#1428A0; color:#FFFFFF !important; border-color:#1428A0; }
img { border-radius:3px; object-fit:contain; vertical-align:middle; }
</style>
"""


# ─────────────────────────────────────────────
# ① 섹터 선택 (components.html — JS 확실히 실행)
# ─────────────────────────────────────────────
sel_sector = st.session_state.selected_sector

def _co_count(sector: str, company: str) -> int:
    if company == "전체":
        return sum(1 for a in articles if a.sector == sector)
    return sum(1 for a in articles if a.sector == sector and a.company == company)

_sec_items = []
for _sn in SECTORS:
    _cnt = sum(1 for a in articles if a.sector == _sn)
    _cls = "btn active" if _sn == sel_sector else "btn"
    _url = f"?sec={quote(_sn)}"
    _sec_items.append(
        f"<div class='{_cls}' onclick=\"window.parent.location.href='{_url}'\">"
        f"{_sn} ({_cnt})</div>"
    )
components.html(
    f"{_BTN_CSS}<div class='row'>{''.join(_sec_items)}</div>",
    height=48, scrolling=False,
)


# ─────────────────────────────────────────────
# ② 회사 선택 (로고 + 텍스트 인라인, components.html)
# ─────────────────────────────────────────────
sel_company = st.session_state.selected_company
companies = SECTORS[sel_sector]["companies"]
all_cos = ["전체"] + list(companies.keys())
per_row = 5
n_rows = math.ceil(len(all_cos) / per_row)

_co_rows_html = ""
for row_i in range(n_rows):
    chunk = all_cos[row_i * per_row : (row_i + 1) * per_row]
    _co_rows_html += "<div class='row' style='margin-bottom:6px;'>"
    for co in chunk:
        cnt = _co_count(sel_sector, co)
        is_active = co == sel_company
        cls = "btn active" if is_active else "btn"
        logo_html = ""
        if co != "전체":
            domain = companies[co]["domain"]
            logo_html = _logo_img(domain, 14, force_white=is_active)
        url = f"?co={quote(co)}"
        _co_rows_html += (
            f"<div class='{cls}' onclick=\"window.parent.location.href='{url}'\">"
            f"{logo_html} {co} ({cnt})</div>"
        )
    _co_rows_html += "</div>"

components.html(
    f"{_BTN_CSS}{_co_rows_html}",
    height=n_rows * 48 + 4, scrolling=False,
)


# ─────────────────────────────────────────────
# 필터링
# ─────────────────────────────────────────────
def _filtered(
    sector: str,
    company: str,
    top_cat: str = "전체",
    mech_cat: str = "전체",
) -> list[news_crawler.Article]:
    arts = [
        a for a in articles
        if a.sector == sector and (company == "전체" or a.company == company)
    ]
    if top_cat != "전체":
        arts = [a for a in arts if a.top_category == top_cat]
    if mech_cat != "전체":
        arts = [a for a in arts if a.mech_category == mech_cat]
    return arts


company_label  = sel_company if sel_company != "전체" else f"{sel_sector} 전체"
sel_top_cat    = st.session_state.selected_top_cat
sel_mech_cat   = st.session_state.selected_cat
filtered_base  = _filtered(sel_sector, sel_company)                       # 전체 (필터 없음)
filtered_top   = _filtered(sel_sector, sel_company, sel_top_cat)          # 상위 카테고리만 적용
filtered       = _filtered(sel_sector, sel_company, sel_top_cat, sel_mech_cat)  # 전부 적용
rumors         = [a for a in articles if a.is_rumor]


# ─────────────────────────────────────────────
# ③ 3열 레이아웃
# ─────────────────────────────────────────────
col_l, col_m, col_r = st.columns([1.1, 1.3, 1.0], gap="medium")


# ── 좌: 뉴스 리스트 ──────────────────────────
with col_l:
    st.markdown(f"<div class='col-header'>{company_label} 뉴스 · {len(filtered)}건</div>",
                unsafe_allow_html=True)

    # 상위 3분류 필터 버튼
    top_cat_opts = ["전체"] + list(ARTICLE_CATEGORIES.keys()) + [TOP_CATEGORY_GENERAL]
    tc_cols = st.columns(len(top_cat_opts))
    for col_tc, tc in zip(tc_cols, top_cat_opts):
        cnt = sum(1 for a in filtered_base if a.top_category == tc) if tc != "전체" else len(filtered_base)
        if col_tc.button(
            f"{tc}\n({cnt})",
            key=f"tc_{sel_sector}_{sel_company}_{tc}",
            use_container_width=True,
            type="primary" if sel_top_cat == tc else "secondary",
        ):
            st.session_state.selected_top_cat = tc
            st.session_state.selected_cat = "전체"
            st.rerun()

    # 기술·개발 선택시 세부 카테고리 필터
    if sel_top_cat == "기술·개발":
        mech_opts = ["전체"] + list(MECH_CATEGORIES.keys())
        mc_cols = st.columns(len(mech_opts))
        for col_mc, mc in zip(mc_cols, mech_opts):
            cnt = sum(1 for a in filtered_top if a.mech_category == mc) if mc != "전체" else len(filtered_top)
            if col_mc.button(
                f"{mc}\n({cnt})",
                key=f"mc_{sel_sector}_{sel_company}_{mc}",
                use_container_width=True,
                type="primary" if sel_mech_cat == mc else "secondary",
            ):
                st.session_state.selected_cat = mc
                st.rerun()

    if not filtered:
        st.info("해당 카테고리 기사가 없습니다.")
    else:
        cards = "".join(_news_card_html(a, analyses[a.link]) for a in filtered)
        st.markdown(f"<div class='scroll-box'>{cards}</div>", unsafe_allow_html=True)


# ── 중: 카테고리 분석 ─────────────────────────
with col_m:
    st.markdown(f"<div class='col-header'>카테고리 분석 · {company_label}</div>",
                unsafe_allow_html=True)

    total = len(filtered_base)
    if not total:
        st.info("기사 없음")
    else:
        # 상위 3분류 분포 (항상 표시)
        top_counts = {
            tc: sum(1 for a in filtered_base if a.top_category == tc)
            for tc in list(ARTICLE_CATEGORIES.keys()) + [TOP_CATEGORY_GENERAL]
        }
        tech_cnt = top_counts.get("기술·개발", 0)
        tech_pct = round(tech_cnt / total * 100)

        st.markdown(
            f"<div style='background:#F4F4F4;border-radius:4px;padding:12px 16px;"
            f"margin-bottom:12px;border:1px solid #E6E6E6;'>"
            f"<div style='font-size:11px;color:#999;margin-bottom:4px;'>총 {total}건 · 기술개발 비중</div>"
            f"<div style='font-size:26px;font-weight:700;color:#1428A0;'>{tech_pct}%"
            f"  <span style='font-size:13px;color:#999;font-weight:400;'>({tech_cnt}건)</span></div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # 상위 3분류 막대
        top_rows_html = ""
        for tc_name, tc_info in ARTICLE_CATEGORIES.items():
            cnt = top_counts.get(tc_name, 0)
            pct = round(cnt / total * 100)
            cls = _TOP_CAT_CSS.get(tc_name, "cat-general")
            top_rows_html += (
                f"<div class='cat-row'>"
                f"  <span class='badge b-cat {cls}' style='min-width:76px;text-align:center;'>{tc_name}</span>"
                f"  <div class='cat-bar-bg'><div class='cat-bar' style='width:{pct}%;background:{tc_info['color']};'></div></div>"
                f"  <span class='cat-count'>{cnt}건</span>"
                f"</div>"
            )
        gen_cnt = top_counts.get(TOP_CATEGORY_GENERAL, 0)
        gen_pct = round(gen_cnt / total * 100)
        top_rows_html += (
            f"<div class='cat-row'>"
            f"  <span class='badge b-cat cat-general' style='min-width:76px;text-align:center;'>일반뉴스</span>"
            f"  <div class='cat-bar-bg'><div class='cat-bar' style='width:{gen_pct}%;background:#D0D0D0;'></div></div>"
            f"  <span class='cat-count'>{gen_cnt}건</span>"
            f"</div>"
        )
        st.markdown(f"<div style='margin-bottom:12px;'>{top_rows_html}</div>", unsafe_allow_html=True)

        # 기술 세부 카테고리 breakdown
        tech_arts = [a for a in filtered_base if a.top_category == "기술·개발"]
        if tech_arts:
            with st.expander(f"기술·개발 세부 분류  ({len(tech_arts)}건)", expanded=True):
                sub_rows = ""
                for mc_name, mc_info in MECH_CATEGORIES.items():
                    cnt = sum(1 for a in tech_arts if a.mech_category == mc_name)
                    if cnt == 0:
                        continue
                    pct = round(cnt / len(tech_arts) * 100)
                    css = _CAT_CSS.get(mc_name, "cat-general")
                    sub_rows += (
                        f"<div class='cat-row'>"
                        f"  <span class='badge b-cat {css}' style='min-width:76px;text-align:center;'>{mc_name}</span>"
                        f"  <div class='cat-bar-bg'><div class='cat-bar' style='width:{pct}%;background:{mc_info['color']};'></div></div>"
                        f"  <span class='cat-count'>{cnt}건</span>"
                        f"</div>"
                    )
                st.markdown(sub_rows, unsafe_allow_html=True)

        # 감성 분석
        pos = [a for a in filtered_base if analyses[a.link].sentiment == "positive"]
        neg = [a for a in filtered_base if analyses[a.link].sentiment == "negative"]
        with st.expander(f"감성 분석  (긍정 {len(pos)} / 부정 {len(neg)})", expanded=False):
            st.markdown(_ratio_bar_html(len(pos), len(neg), total), unsafe_allow_html=True)
            for art in (pos + neg):
                an = analyses[art.link]
                safe_t = html.escape(art.display_title)
                st.markdown(
                    f"<div class='news-card {an.sentiment}' style='margin-bottom:5px;'>"
                    f"  <a href='{art.link}' target='_blank'>"
                    f"    <div class='news-title' style='font-size:12px;'>{safe_t}</div>"
                    f"  </a>"
                    f"  <div class='news-meta'>{_top_cat_badge(art.top_category)}"
                    f"    {_sentiment_badge(an.sentiment)} {_source_badge(art.source)}"
                    f"    <span>{art.published_ago}</span></div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


# ── 우: 루머 피드 (전 섹터) ──────────────────
with col_r:
    st.markdown(f"<div class='col-header'>루머 &amp; 전망 · {len(rumors)}건</div>",
                unsafe_allow_html=True)

    # 섹터별 루머 카운트 뱃지
    sector_counts = {s: sum(1 for a in rumors if a.sector == s) for s in SECTORS}
    badges = " ".join(
        f"<span class='badge b-src'>{s} {sector_counts[s]}</span>"
        for s in SECTORS if sector_counts[s]
    )
    st.markdown(f"<div style='margin-bottom:10px;'>{badges}</div>", unsafe_allow_html=True)

    if not rumors:
        st.info("수집된 루머/전망 기사가 없습니다.")
    else:
        rumor_parts = []
        for art in rumors:
            domain = SECTORS.get(art.sector, {}).get("companies", {}).get(art.company, {}).get("domain", "")
            logo_html = _logo_img(domain, 18) if domain else ""
            safe_t   = html.escape(art.display_title)
            safe_sum = html.escape(
                art.display_summary[:130] + "…"
                if len(art.display_summary) > 130 else art.display_summary
            )
            orig_line = ""
            if art.title_ko and art.title_ko != art.title:
                orig_line = f"<div class='r-orig'>원문: {html.escape(art.title)}</div>"
            s_badge = _sentiment_badge(analyses[art.link].sentiment)

            rumor_parts.append(
                f"<a href='{art.link}' target='_blank' style='text-decoration:none;'>"
                f"<div class='rumor-card'>"
                f"  <div class='r-meta' style='margin-bottom:5px;'>"
                f"    {logo_html} <span style='color:#535353;font-size:11px;font-weight:600;margin-left:4px;'>"
                f"      {art.company}</span>"
                f"    {s_badge}"
                f"  </div>"
                f"  <div class='r-title'>{safe_t}</div>"
                f"  {orig_line}"
                f"  <div class='r-summary'>{safe_sum}</div>"
                f"  <div class='r-meta'>{_source_badge(art.source)}"
                f"    <span>{art.published_ago}</span></div>"
                f"</div></a>"
            )

        st.markdown(
            f"<div class='scroll-box'>{''.join(rumor_parts)}</div>",
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────
# 푸터
# ─────────────────────────────────────────────
st.markdown("---")
st.caption(f"Mxplorer-news · {len(news_crawler.RSS_SOURCES)}개 소스 · {len(articles)}건 수집")
