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
from news_crawler import SECTORS, MECH_CATEGORIES, MECH_CATEGORY_GENERAL

st.set_page_config(
    page_title="뉴스 레이더",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"] { background:#0F172A; color:#E2E8F0; }
[data-testid="stSidebar"] { background:#0B1426; }

.radar-header {
    background: linear-gradient(90deg,#0B1F3A,#1F6FEB);
    padding:12px 22px; border-radius:10px; margin-bottom:10px;
    display:flex; align-items:center; justify-content:space-between;
}
.radar-header h1 { margin:0; font-size:19px; color:#fff; }
.radar-header p  { margin:0; font-size:11px; color:rgba(255,255,255,.75); }

/* 회사 로고 그리드 */
.company-grid { display:flex; flex-wrap:wrap; gap:6px; padding:8px 0 12px; }
.company-pill {
    display:flex; align-items:center; gap:6px;
    background:#1E293B; border:1px solid #334155;
    border-radius:8px; padding:5px 10px; cursor:pointer;
    font-size:12px; color:#CBD5E1; transition:all .15s;
}
.company-pill.active {
    background:#1E3A5F; border-color:#1F6FEB; color:#fff;
}
.company-pill img { border-radius:3px; width:20px; height:20px; object-fit:contain; }

/* 섹터·회사 탭 버튼 */
div[data-testid="stHorizontalBlock"] button {
    border-radius:8px !important; font-size:12px !important;
    padding-top:3px !important; padding-bottom:3px !important;
}
/* 로고-버튼 간격 최소화 */
div[data-testid="stHorizontalBlock"] div[data-testid="stMarkdownContainer"] {
    margin-bottom:-8px;
}

/* 뉴스 카드 */
.news-card {
    background:#1E293B; border-radius:8px; padding:10px 12px;
    margin-bottom:7px; border-left:3px solid #334155;
}
.news-card.positive { border-left-color:#059669; }
.news-card.negative { border-left-color:#DC2626; }
.news-card.neutral  { border-left-color:#3B82F6; }
.news-card.rumor    { border-left-color:#7C3AED; }
.news-card a        { text-decoration:none; color:inherit; }
.news-title { font-size:13px; font-weight:600; line-height:1.4; margin-bottom:4px; }
.news-meta  { font-size:11px; color:#64748B; display:flex; gap:8px; flex-wrap:wrap; align-items:center; }

/* 뱃지 */
.badge { display:inline-block; padding:1px 7px; border-radius:4px;
         font-size:10px; font-weight:700; line-height:1.6; }
.b-pos   { background:#064E3B; color:#6EE7B7; }
.b-neg   { background:#7F1D1D; color:#FCA5A5; }
.b-neu   { background:#1E3A5F; color:#93C5FD; }
.b-rumor { background:#3B0764; color:#E9D5FF; }
.b-src   { background:#1E293B; color:#94A3B8; border:1px solid #334155; }

/* 루머 카드 */
.rumor-card {
    background:#1A0B2E; border:1px solid #4C1D95;
    border-radius:8px; padding:11px 13px; margin-bottom:8px;
}
.r-title   { font-size:13px; font-weight:600; color:#E9D5FF; line-height:1.4; margin-bottom:4px; }
.r-orig    { font-size:10px; color:#7C3AED; margin-bottom:4px; }
.r-summary { font-size:11px; color:#A78BFA; line-height:1.45; margin-bottom:5px; }
.r-meta    { font-size:10px; color:#6D28D9; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }

/* 감성 바 */
.ratio-bar { display:flex; border-radius:4px; overflow:hidden; height:10px; margin:6px 0 4px; }

/* 스크롤 */
.scroll-box { max-height:68vh; overflow-y:auto; padding-right:3px; }
.scroll-box::-webkit-scrollbar { width:3px; }
.scroll-box::-webkit-scrollbar-thumb { background:#334155; border-radius:3px; }

.col-header { font-size:14px; font-weight:700; color:#22D3EE;
              border-bottom:1px solid #1E293B; padding-bottom:7px; margin-bottom:10px; }

/* 기구개발 카테고리 배지 */
.b-cat { display:inline-block; padding:1px 6px; border-radius:4px;
         font-size:10px; font-weight:700; line-height:1.6; }
.cat-design    { background:#3B0764; color:#DDD6FE; }
.cat-material  { background:#083344; color:#67E8F9; }
.cat-spec      { background:#064E3B; color:#6EE7B7; }
.cat-durability{ background:#451A03; color:#FDE68A; }
.cat-mfg       { background:#450A0A; color:#FCA5A5; }
.cat-thermal   { background:#450A0A; color:#FCA5A5; }
.cat-mech      { background:#2E1065; color:#E9D5FF; }
.cat-general   { background:#1E293B; color:#94A3B8; }

/* 카테고리 분포 행 */
.cat-row { display:flex; align-items:center; gap:6px; margin-bottom:5px; padding:5px 8px;
           background:#1E293B; border-radius:6px; cursor:default; }
.cat-bar-bg { flex:1; height:6px; background:#0F172A; border-radius:3px; overflow:hidden; }
.cat-bar    { height:6px; border-radius:3px; }
.cat-count  { font-size:11px; color:#64748B; min-width:24px; text-align:right; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# 세션 상태
# ─────────────────────────────────────────────
def _init():
    st.session_state.setdefault("articles", [])
    st.session_state.setdefault("selected_sector", "모바일")
    st.session_state.setdefault("selected_company", "전체")
    st.session_state.setdefault("last_refresh", None)
_init()


# ─────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────
# Simple Icons slug 매핑 (https://simpleicons.org)
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
    "x.ai":                 "xai",
    "nvidia.com":           "nvidia",
    "mistral.ai":           "mistral",
    "bostondynamics.com":   "bostondynamics",
}


def _logo_img(domain: str, size: int = 20) -> str:
    slug = _SIMPLE_ICONS.get(domain)
    fb   = f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
    if slug:
        si = f"https://cdn.simpleicons.org/{slug}/white"
        return (
            f'<img src="{si}" width="{size}" height="{size}" '
            f'style="border-radius:3px;object-fit:contain;vertical-align:middle;filter:drop-shadow(0 0 1px #fff4);" '
            f'onerror="this.onerror=null;this.src=\'{fb}\'">'
        )
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
    cat_badge = _category_badge(art.mech_category)
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
# 데이터 로드
# ─────────────────────────────────────────────
def refresh(force: bool = False):
    with st.spinner("뉴스 수집 중..."):
        st.session_state.articles = news_crawler.get_cached_articles(force_refresh=force)
    st.session_state.last_refresh = datetime.now()

if not st.session_state.articles:
    refresh()

articles: list[news_crawler.Article] = st.session_state.articles
analyses: dict[str, analyst.ArticleAnalysis] = {a.link: analyst.analyze_article(a) for a in articles}


# ─────────────────────────────────────────────
# 헤더
# ─────────────────────────────────────────────
age = news_crawler.cache_age_seconds()
age_str = f"{int(age//60)}분 전" if age else "방금"

hcol1, hcol2 = st.columns([5, 1])
with hcol1:
    st.markdown(
        f'<div class="radar-header">'
        f'<div><h1>📡 선행기구개발그룹 뉴스 레이더</h1>'
        f'<p>모바일 · 로보틱스 · AI 실시간 뉴스 분석 &nbsp;|&nbsp; {age_str} · {len(articles)}건</p></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
with hcol2:
    st.write("")
    if st.button("🔄 새로고침", use_container_width=True):
        refresh(force=True)
        st.rerun()

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
# 필터링된 기사
# ─────────────────────────────────────────────
def _filtered(sector: str, company: str, cat: str = "전체") -> list[news_crawler.Article]:
    arts = [
        a for a in articles
        if a.sector == sector and (company == "전체" or a.company == company)
    ]
    if cat != "전체":
        arts = [a for a in arts if a.mech_category == cat]
    return arts

# 카테고리 필터 상태
if "selected_cat" not in st.session_state:
    st.session_state.selected_cat = "전체"

company_label = sel_company if sel_company != "전체" else f"{sel_sector} 전체"
filtered_all  = _filtered(sel_sector, sel_company)           # 카테고리 필터 없는 전체
filtered      = _filtered(sel_sector, sel_company, st.session_state.selected_cat)
rumors        = [a for a in articles if a.is_rumor]


# ─────────────────────────────────────────────
# ③ 3열 레이아웃
# ─────────────────────────────────────────────
col_l, col_m, col_r = st.columns([1.1, 1.3, 1.0], gap="medium")


# ── 좌: 뉴스 리스트 + 카테고리 필터 ──────────
with col_l:
    st.markdown(f"<div class='col-header'>📰 {company_label} 뉴스 · {len(filtered)}건</div>",
                unsafe_allow_html=True)

    # 카테고리 필터 버튼
    all_cats = ["전체"] + list(MECH_CATEGORIES.keys())
    cat_counts = {c: sum(1 for a in filtered_all if a.mech_category == c) for c in MECH_CATEGORIES}
    cat_cols = st.columns(len(all_cats))
    for col, cat in zip(cat_cols, all_cats):
        info = MECH_CATEGORIES.get(cat, {})
        emoji = info.get("emoji", "📰") if cat != "전체" else "📋"
        cnt   = cat_counts.get(cat, len(filtered_all)) if cat == "전체" else cat_counts.get(cat, 0)
        is_active = st.session_state.selected_cat == cat
        if col.button(
            f"{emoji}\n{cnt}",
            key=f"cat_{sel_sector}_{sel_company}_{cat}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
            help=cat,
        ):
            st.session_state.selected_cat = cat
            st.rerun()

    if not filtered:
        st.info("해당 카테고리 기사가 없습니다.")
    else:
        cards = "".join(_news_card_html(a, analyses[a.link]) for a in filtered)
        st.markdown(f"<div class='scroll-box'>{cards}</div>", unsafe_allow_html=True)


# ── 중: 기구개발 카테고리 분석 ───────────────
with col_m:
    st.markdown(f"<div class='col-header'>🔩 기구개발 분석 · {company_label}</div>",
                unsafe_allow_html=True)

    if not filtered_all:
        st.info("기사 없음")
    else:
        total = len(filtered_all)
        mech_arts = [a for a in filtered_all if a.mech_category != MECH_CATEGORY_GENERAL]
        mech_ratio = round(len(mech_arts) / total * 100) if total else 0

        # 기구개발 관련 비율 헤더
        st.markdown(
            f"<div style='background:#0F172A;border-radius:8px;padding:10px 14px;margin-bottom:12px;'>"
            f"<div style='font-size:11px;color:#64748B;margin-bottom:4px;'>총 {total}건 중 기구개발 관련</div>"
            f"<div style='font-size:22px;font-weight:800;color:#22D3EE;'>{mech_ratio}%"
            f"  <span style='font-size:13px;color:#64748B;font-weight:400;'>({len(mech_arts)}건)</span></div>"
            f"{_ratio_bar_html(len(mech_arts), 0, total)}"
            f"</div>",
            unsafe_allow_html=True,
        )

        # 카테고리별 분포 바
        cat_rows_html = ""
        for cat_name, cat_info in MECH_CATEGORIES.items():
            cnt = sum(1 for a in filtered_all if a.mech_category == cat_name)
            if cnt == 0:
                continue
            pct = round(cnt / total * 100)
            css = _CAT_CSS.get(cat_name, "cat-general")
            color = cat_info["color"]
            cat_rows_html += (
                f"<div class='cat-row'>"
                f"  <span class='badge b-cat {css}' style='min-width:90px;text-align:center;'>"
                f"    {cat_info['emoji']} {cat_name}</span>"
                f"  <div class='cat-bar-bg'><div class='cat-bar' style='width:{pct}%;background:{color};'></div></div>"
                f"  <span class='cat-count'>{cnt}건</span>"
                f"</div>"
            )
        st.markdown(f"<div style='margin-bottom:12px;'>{cat_rows_html}</div>", unsafe_allow_html=True)

        # 감성 분석 (접을 수 있게)
        pos = [a for a in filtered_all if analyses[a.link].sentiment == "positive"]
        neg = [a for a in filtered_all if analyses[a.link].sentiment == "negative"]

        with st.expander(f"📊 감성 분석  ({len(pos)}↑ / {len(neg)}↓)", expanded=False):
            st.markdown(
                f"{_ratio_bar_html(len(pos), len(neg), total)}",
                unsafe_allow_html=True,
            )
            for art in (pos + neg):
                an = analyses[art.link]
                safe_t = html.escape(art.display_title)
                cls = an.sentiment
                st.markdown(
                    f"<div class='news-card {cls}' style='margin-bottom:5px;'>"
                    f"  <a href='{art.link}' target='_blank'>"
                    f"    <div class='news-title' style='font-size:12px;'>{safe_t}</div>"
                    f"  </a>"
                    f"  <div class='news-meta'>{_sentiment_badge(an.sentiment)}"
                    f"    {_source_badge(art.source)}"
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
