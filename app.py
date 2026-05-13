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

import streamlit as st

import analyst
import news_crawler
from news_crawler import (
    SECTORS, MECH_CATEGORIES, MECH_CATEGORY_GENERAL,
    ARTICLE_CATEGORIES, TOP_CATEGORY_GENERAL,
)

st.set_page_config(
    page_title="Mxplorer-news",
    page_icon="🔭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
/* ── Samsung-inspired Design System ──────────────────────────
   Primary  : #1428A0  (Samsung Blue)
   Accent   : #00A9E0  (Samsung Cerulean)
   BG-base  : #05071A  (Deep Samsung Navy)
   BG-card  : #0C1232
   BG-raise : #111A40
   Text     : #F0F2F8 / #8B95B8
   Radius   : 18px (Samsung One UI standard)
──────────────────────────────────────────────────────────── */

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background:#05071A !important; color:#F0F2F8;
    font-family:'Inter', 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
}
[data-testid="stSidebar"]        { background:#030510; }
[data-testid="stAppViewBlockContainer"] { padding-top:8px !important; }
section[data-testid="stMain"] > div { padding-top:0 !important; }

/* ── 헤더 ── */
.mxp-header {
    background: linear-gradient(135deg, #05071A 0%, #0A1240 50%, #1428A0 100%);
    padding: 16px 24px; border-radius: 18px; margin-bottom: 14px;
    border: 1px solid rgba(20,40,160,0.5);
    box-shadow: 0 4px 24px rgba(20,40,160,0.25);
}
.mxp-header h1 {
    margin:0; font-size:20px; font-weight:800; color:#fff;
    letter-spacing:-0.3px;
}
.mxp-header h1 span { color:#00A9E0; }
.mxp-header p  { margin:4px 0 0; font-size:11px; color:rgba(255,255,255,0.55); letter-spacing:.3px; }

/* ── 버튼 (Streamlit 오버라이드) ── */
div[data-testid="stHorizontalBlock"] button {
    border-radius:18px !important;
    font-size:11px !important; font-weight:600 !important;
    padding:4px 8px !important;
    transition: all .15s !important;
}
button[kind="primary"] {
    background:#1428A0 !important;
    border-color:#1428A0 !important;
    color:#fff !important;
}
button[kind="primary"]:hover {
    background:#1E3FCC !important;
    border-color:#1E3FCC !important;
}
button[kind="secondary"] {
    background:#0C1232 !important;
    border-color:rgba(20,40,160,0.35) !important;
    color:#8B95B8 !important;
}
button[kind="secondary"]:hover {
    border-color:#1428A0 !important;
    color:#fff !important;
}
/* 로고-버튼 간격 */
div[data-testid="stHorizontalBlock"] div[data-testid="stMarkdownContainer"] {
    margin-bottom:-10px;
}

/* ── 뉴스 카드 ── */
.news-card {
    background:#0C1232;
    border-radius:14px;
    padding:11px 14px;
    margin-bottom:8px;
    border: 1px solid rgba(20,40,160,0.2);
    border-left: 3px solid rgba(20,40,160,0.4);
    transition: border-color .15s;
}
.news-card.positive { border-left-color:#00B140; }
.news-card.negative { border-left-color:#E4002B; }
.news-card.neutral  { border-left-color:#1428A0; }
.news-card.rumor    { border-left-color:#C800A1; }
.news-card a        { text-decoration:none; color:inherit; }
.news-card:hover    { border-color:rgba(20,40,160,0.5); }
.news-title { font-size:13px; font-weight:600; line-height:1.45; margin-bottom:5px; color:#F0F2F8; }
.news-meta  { font-size:11px; color:#4A5580; display:flex; gap:7px; flex-wrap:wrap; align-items:center; }

/* ── 뱃지 ── */
.badge { display:inline-block; padding:2px 8px; border-radius:99px;
         font-size:10px; font-weight:700; line-height:1.5; }
.b-pos   { background:rgba(0,177,64,0.15);  color:#00D44E; border:1px solid rgba(0,177,64,0.3); }
.b-neg   { background:rgba(228,0,43,0.15);  color:#FF4D6D; border:1px solid rgba(228,0,43,0.3); }
.b-neu   { background:rgba(20,40,160,0.15); color:#6690FF; border:1px solid rgba(20,40,160,0.3); }
.b-rumor { background:rgba(200,0,161,0.15); color:#FF69E2; border:1px solid rgba(200,0,161,0.3); }
.b-src   { background:rgba(255,255,255,0.04); color:#5A6485; border:1px solid rgba(255,255,255,0.08); }

/* ── 루머 카드 ── */
.rumor-card {
    background:#0C1232;
    border: 1px solid rgba(200,0,161,0.2);
    border-top: 2px solid #C800A1;
    border-radius:14px; padding:12px 14px; margin-bottom:8px;
}
.r-title   { font-size:13px; font-weight:600; color:#F0F2F8; line-height:1.4; margin-bottom:4px; }
.r-orig    { font-size:10px; color:#C800A1; margin-bottom:4px; }
.r-summary { font-size:11px; color:#6B7299; line-height:1.5; margin-bottom:5px; }
.r-meta    { font-size:10px; color:#4A5580; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }

/* ── 감성 바 ── */
.ratio-bar { display:flex; border-radius:99px; overflow:hidden; height:8px; margin:8px 0 5px; }

/* ── 스크롤 ── */
.scroll-box { max-height:68vh; overflow-y:auto; padding-right:4px; }
.scroll-box::-webkit-scrollbar { width:3px; }
.scroll-box::-webkit-scrollbar-track { background:transparent; }
.scroll-box::-webkit-scrollbar-thumb { background:rgba(20,40,160,0.4); border-radius:99px; }

/* ── 컬럼 헤더 ── */
.col-header {
    font-size:13px; font-weight:700; color:#00A9E0;
    border-bottom: 1px solid rgba(20,40,160,0.25);
    padding-bottom:8px; margin-bottom:12px;
    letter-spacing:.3px; text-transform:uppercase;
}

/* ── 카테고리 배지 (b-cat) ── */
.b-cat { display:inline-block; padding:2px 7px; border-radius:99px;
         font-size:10px; font-weight:600; line-height:1.5; }
.cat-design    { background:rgba(104,91,199,0.2); color:#A99EF5; border:1px solid rgba(104,91,199,0.35); }
.cat-material  { background:rgba(0,169,224,0.15); color:#5DD3F5; border:1px solid rgba(0,169,224,0.3); }
.cat-spec      { background:rgba(0,177,64,0.15);  color:#5EE89A; border:1px solid rgba(0,177,64,0.3); }
.cat-durability{ background:rgba(255,198,0,0.15); color:#FFD84D; border:1px solid rgba(255,198,0,0.3); }
.cat-mfg       { background:rgba(228,0,43,0.15);  color:#FF7A8A; border:1px solid rgba(228,0,43,0.3); }
.cat-thermal   { background:rgba(255,105,0,0.15); color:#FFB066; border:1px solid rgba(255,105,0,0.3); }
.cat-mech      { background:rgba(200,0,161,0.15); color:#FF88EE; border:1px solid rgba(200,0,161,0.3); }
.cat-general   { background:rgba(255,255,255,0.05); color:#4A5580; border:1px solid rgba(255,255,255,0.08); }

/* ── 카테고리 분포 행 ── */
.cat-row {
    display:flex; align-items:center; gap:8px; margin-bottom:6px;
    padding:6px 10px; background:#0C1232;
    border-radius:12px; border:1px solid rgba(20,40,160,0.15);
}
.cat-bar-bg { flex:1; height:5px; background:rgba(255,255,255,0.05); border-radius:99px; overflow:hidden; }
.cat-bar    { height:5px; border-radius:99px; }
.cat-count  { font-size:11px; color:#4A5580; min-width:30px; text-align:right; font-weight:600; }

/* ── Streamlit 기본 UI 정리 ── */
[data-testid="stDecoration"] { display:none; }
[data-testid="stStatusWidget"] { display:none; }
footer { display:none !important; }
#MainMenu { display:none !important; }
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


def _logo_img(domain: str, size: int = 20) -> str:
    slug = _SIMPLE_ICONS.get(domain)
    if slug:
        si = f"https://cdn.simpleicons.org/{slug}/white"
        fb = f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
        return (
            f'<img src="{si}" width="{size}" height="{size}" '
            f'style="border-radius:3px;object-fit:contain;vertical-align:middle;filter:drop-shadow(0 0 1px #fff4);" '
            f'onerror="this.onerror=null;this.src=\'{fb}\'">'
        )
    # 이니셜 뱃지 (Simple Icons에 없는 브랜드)
    if domain in _BRAND_INITIALS:
        text, bg = _BRAND_INITIALS[domain]
        fs = max(7, size // 3)
        return (
            f'<span style="display:inline-flex;align-items:center;justify-content:center;'
            f'width:{size}px;height:{size}px;background:{bg};border-radius:4px;'
            f'font-size:{fs}px;font-weight:800;color:#fff;vertical-align:middle;'
            f'letter-spacing:-0.5px;">{text}</span>'
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
    "기술·개발":  ("cat-material", "⚙️"),
    "마케팅·출시": ("cat-design",   "📣"),
    "사업·전략":  ("cat-spec",     "📊"),
    TOP_CATEGORY_GENERAL: ("cat-general", "📰"),
}

def _top_cat_badge(cat: str) -> str:
    cls, emoji = _TOP_CAT_CSS.get(cat, ("cat-general", "📰"))
    return f"<span class='badge b-cat {cls}'>{emoji} {cat}</span>"

def _category_badge(cat: str) -> str:
    info = MECH_CATEGORIES.get(cat, {})
    emoji = info.get("emoji", "📰")
    cls   = _CAT_CSS.get(cat, "cat-general")
    return f"<span class='badge b-cat {cls}'>{emoji} {cat}</span>"


def _sentiment_badge(s: str) -> str:
    m = {"positive": ("b-pos","▲ 긍정"), "negative": ("b-neg","▼ 부정"), "neutral": ("b-neu","● 중립")}
    cls, lbl = m.get(s, ("b-neu","● 중립"))
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
    rumor_badge = "<span class='badge b-rumor'>📡 루머</span> " if art.is_rumor else ""
    # 카드에는 상위 분류 + (기술이면) 세부 분류까지 표시
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
        f"<div style='width:{p}%;background:#059669;'></div>"
        f"<div style='width:{neu}%;background:#374151;'></div>"
        f"<div style='width:{n}%;background:#DC2626;'></div>"
        f"</div>"
        f"<div style='font-size:11px;color:#64748B;display:flex;gap:10px;'>"
        f"<span style='color:#6EE7B7;'>▲ {p}% ({pos})</span>"
        f"<span style='color:#94A3B8;'>● {neu}% ({total-pos-neg})</span>"
        f"<span style='color:#FCA5A5;'>▼ {n}% ({neg})</span>"
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
    f'<h1>🔭 Mx<span>plorer</span>-news</h1>'
    f'<p>MOBILE &nbsp;·&nbsp; ROBOTICS &nbsp;·&nbsp; AI &nbsp;│&nbsp; {age_str} &nbsp;·&nbsp; {len(articles)}건 &nbsp;·&nbsp; auto-refresh 5min</p>'
    f'</div>',
    unsafe_allow_html=True,
)

if news_crawler.is_demo_mode:
    st.warning("⚠️ **데모 모드** — 샘플 데이터 표시 중. 로컬 PC / Streamlit Cloud에서 실제 뉴스 수집.", icon="📡")


# ─────────────────────────────────────────────
# ① 섹터 선택 버튼
# ─────────────────────────────────────────────
sel_sector = st.session_state.selected_sector
sec_cols = st.columns(len(SECTORS))
for col, (sector_name, sector_info) in zip(sec_cols, SECTORS.items()):
    count = sum(1 for a in articles if a.sector == sector_name)
    is_sel = sel_sector == sector_name
    if col.button(
        f"{sector_info['emoji']} {sector_name}  ({count})",
        key=f"sec_{sector_name}",
        use_container_width=True,
        type="primary" if is_sel else "secondary",
    ):
        st.session_state.selected_sector = sector_name
        st.session_state.selected_company = "전체"
        st.rerun()


# ─────────────────────────────────────────────
# ② 회사 선택 (로고 + 기사 수 표시, 클릭 가능)
# ─────────────────────────────────────────────
sel_sector = st.session_state.selected_sector
sel_company = st.session_state.selected_company
companies = SECTORS[sel_sector]["companies"]

def _co_count(sector: str, company: str) -> int:
    if company == "전체":
        return sum(1 for a in articles if a.sector == sector)
    return sum(1 for a in articles if a.sector == sector and a.company == company)

all_cos = ["전체"] + list(companies.keys())
per_row = 5
rows = math.ceil(len(all_cos) / per_row)

for row_i in range(rows):
    chunk = all_cos[row_i * per_row : (row_i + 1) * per_row]
    cols_logo = st.columns(len(chunk))
    cols_btn  = st.columns(len(chunk))

    for col_l, col_b, co in zip(cols_logo, cols_btn, chunk):
        cnt = _co_count(sel_sector, co)
        # 로고 이미지 (버튼 위에 표시)
        if co == "전체":
            col_l.markdown(
                "<div style='text-align:center;padding:2px 0;font-size:18px;'>🌐</div>",
                unsafe_allow_html=True,
            )
        else:
            domain = companies[co]["domain"]
            col_l.markdown(
                f"<div style='text-align:center;padding:2px 0;'>{_logo_img(domain, 22)}</div>",
                unsafe_allow_html=True,
            )
        # 클릭 가능한 버튼 (회사명 + 기사 수)
        label = f"{co} ({cnt})"
        if col_b.button(
            label,
            key=f"co_{sel_sector}_{co}",
            use_container_width=True,
            type="primary" if co == sel_company else "secondary",
        ):
            st.session_state.selected_company = co
            st.rerun()


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
    st.markdown(f"<div class='col-header'>📰 {company_label} 뉴스 · {len(filtered)}건</div>",
                unsafe_allow_html=True)

    # 상위 3분류 필터 버튼
    top_cat_opts = ["전체"] + list(ARTICLE_CATEGORIES.keys()) + [TOP_CATEGORY_GENERAL]
    tc_cols = st.columns(len(top_cat_opts))
    for col_tc, tc in zip(tc_cols, top_cat_opts):
        info = ARTICLE_CATEGORIES.get(tc, {})
        emoji = info.get("emoji", "📋") if tc not in ("전체", TOP_CATEGORY_GENERAL) else ("📋" if tc == "전체" else "📰")
        cnt = sum(1 for a in filtered_base if a.top_category == tc) if tc != "전체" else len(filtered_base)
        is_active = sel_top_cat == tc
        if col_tc.button(
            f"{emoji}\n{cnt}",
            key=f"tc_{sel_sector}_{sel_company}_{tc}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
            help=tc,
        ):
            st.session_state.selected_top_cat = tc
            st.session_state.selected_cat = "전체"
            st.rerun()

    # 기술·개발 선택시 세부 카테고리 필터
    if sel_top_cat == "기술·개발":
        mech_opts = ["전체"] + list(MECH_CATEGORIES.keys())
        mc_cols = st.columns(len(mech_opts))
        for col_mc, mc in zip(mc_cols, mech_opts):
            info = MECH_CATEGORIES.get(mc, {})
            emoji = info.get("emoji", "📋") if mc != "전체" else "📋"
            cnt = sum(1 for a in filtered_top if a.mech_category == mc) if mc != "전체" else len(filtered_top)
            is_active = sel_mech_cat == mc
            if col_mc.button(
                f"{emoji}\n{cnt}",
                key=f"mc_{sel_sector}_{sel_company}_{mc}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
                help=mc,
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
    st.markdown(f"<div class='col-header'>📊 카테고리 분석 · {company_label}</div>",
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
            f"<div style='background:#0F172A;border-radius:8px;padding:10px 14px;margin-bottom:10px;'>"
            f"<div style='font-size:11px;color:#64748B;margin-bottom:4px;'>총 {total}건 · 기술개발 비중</div>"
            f"<div style='font-size:24px;font-weight:800;color:#22D3EE;'>{tech_pct}%"
            f"  <span style='font-size:13px;color:#64748B;font-weight:400;'>({tech_cnt}건)</span></div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # 상위 3분류 막대
        top_rows_html = ""
        for tc_name, tc_info in ARTICLE_CATEGORIES.items():
            cnt = top_counts.get(tc_name, 0)
            pct = round(cnt / total * 100)
            color = tc_info["color"]
            _, tc_css = _TOP_CAT_CSS.get(tc_name, ("cat-general", ""))
            cls, _ = _TOP_CAT_CSS.get(tc_name, ("cat-general", ""))
            top_rows_html += (
                f"<div class='cat-row'>"
                f"  <span class='badge b-cat {cls}' style='min-width:88px;text-align:center;'>"
                f"    {tc_info['emoji']} {tc_name}</span>"
                f"  <div class='cat-bar-bg'><div class='cat-bar' style='width:{pct}%;background:{color};'></div></div>"
                f"  <span class='cat-count'>{cnt}건</span>"
                f"</div>"
            )
        # 일반뉴스
        gen_cnt = top_counts.get(TOP_CATEGORY_GENERAL, 0)
        gen_pct = round(gen_cnt / total * 100)
        top_rows_html += (
            f"<div class='cat-row'>"
            f"  <span class='badge b-cat cat-general' style='min-width:88px;text-align:center;'>📰 일반뉴스</span>"
            f"  <div class='cat-bar-bg'><div class='cat-bar' style='width:{gen_pct}%;background:#374151;'></div></div>"
            f"  <span class='cat-count'>{gen_cnt}건</span>"
            f"</div>"
        )
        st.markdown(f"<div style='margin-bottom:12px;'>{top_rows_html}</div>", unsafe_allow_html=True)

        # 기술 세부 카테고리 breakdown
        tech_arts = [a for a in filtered_base if a.top_category == "기술·개발"]
        if tech_arts:
            with st.expander(f"⚙️ 기술·개발 세부 분류  ({len(tech_arts)}건)", expanded=True):
                sub_rows = ""
                for mc_name, mc_info in MECH_CATEGORIES.items():
                    cnt = sum(1 for a in tech_arts if a.mech_category == mc_name)
                    if cnt == 0:
                        continue
                    pct = round(cnt / len(tech_arts) * 100)
                    css = _CAT_CSS.get(mc_name, "cat-general")
                    sub_rows += (
                        f"<div class='cat-row'>"
                        f"  <span class='badge b-cat {css}' style='min-width:88px;text-align:center;'>"
                        f"    {mc_info['emoji']} {mc_name}</span>"
                        f"  <div class='cat-bar-bg'><div class='cat-bar' style='width:{pct}%;background:{mc_info['color']};'></div></div>"
                        f"  <span class='cat-count'>{cnt}건</span>"
                        f"</div>"
                    )
                st.markdown(sub_rows, unsafe_allow_html=True)

        # 감성 분석
        pos = [a for a in filtered_base if analyses[a.link].sentiment == "positive"]
        neg = [a for a in filtered_base if analyses[a.link].sentiment == "negative"]
        with st.expander(f"📊 감성 분석  ({len(pos)}↑ / {len(neg)}↓)", expanded=False):
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
    st.markdown(f"<div class='col-header'>📡 루머 &amp; 전망 · {len(rumors)}건</div>",
                unsafe_allow_html=True)

    # 섹터별 루머 카운트 뱃지
    sector_counts = {s: sum(1 for a in rumors if a.sector == s) for s in SECTORS}
    badges = " ".join(
        f"<span class='badge b-src'>{SECTORS[s]['emoji']} {s} {sector_counts[s]}</span>"
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
            sector_emoji = SECTORS.get(art.sector, {}).get("emoji", "⚙️")
            safe_t   = html.escape(art.display_title)
            safe_sum = html.escape(
                art.display_summary[:130] + "…"
                if len(art.display_summary) > 130 else art.display_summary
            )
            orig_line = ""
            if art.title_ko and art.title_ko != art.title:
                orig_line = f"<div class='r-orig'>原 {html.escape(art.title)}</div>"
            s_badge = _sentiment_badge(analyses[art.link].sentiment)

            rumor_parts.append(
                f"<a href='{art.link}' target='_blank' style='text-decoration:none;'>"
                f"<div class='rumor-card'>"
                f"  <div class='r-meta' style='margin-bottom:5px;'>"
                f"    {logo_html} <span style='color:#C4B5FD;font-size:11px;font-weight:600;'>"
                f"      {sector_emoji} {art.company}</span>"
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
st.caption(f"© 선행기구개발그룹 뉴스 레이더 · {len(RSS_SOURCES) if False else len(news_crawler.RSS_SOURCES)}개 소스 · {len(articles)}건 수집")
