"""선행기구개발그룹 뉴스 레이더 - Streamlit 메인 앱.

3컬럼 레이아웃:
  좌측  - 회사별 뉴스 리스트 (삼성 / 애플 / 기타 필터)
  중간  - 선택 회사의 감성 분석 (긍정 / 중립 / 부정)
  우측  - 루머 & 전망 피드
"""
from __future__ import annotations

import html
from datetime import datetime

import streamlit as st

import analyst
import news_crawler
from news_crawler import COMPANY_PROFILES

st.set_page_config(
    page_title="뉴스 레이더",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────
# 글로벌 CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
:root {
    --navy:  #0B1F3A;
    --blue:  #1F6FEB;
    --cyan:  #22D3EE;
    --card:  #1E293B;
    --bg:    #0F172A;
    --text:  #E2E8F0;
    --muted: #64748B;
}
html, body, [data-testid="stAppViewContainer"] {
    background: var(--bg);
    color: var(--text);
}
[data-testid="stSidebar"] { background: #0B1426; }

/* 헤더 */
.radar-header {
    background: linear-gradient(90deg, var(--navy) 0%, var(--blue) 100%);
    padding: 14px 22px;
    border-radius: 10px;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.radar-header h1 { margin:0; font-size:20px; color:#fff; }
.radar-header p  { margin:0; font-size:12px; color:rgba(255,255,255,0.75); }

/* 컬럼 카드 */
.col-header {
    font-size: 14px;
    font-weight: 700;
    color: var(--cyan);
    border-bottom: 1px solid #1E293B;
    padding-bottom: 8px;
    margin-bottom: 10px;
}

/* 뉴스 아이템 */
.news-item {
    background: var(--card);
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 7px;
    border-left: 3px solid var(--blue);
    cursor: pointer;
    transition: background 0.15s;
}
.news-item:hover { background: #263550; }
.news-item.positive { border-left-color: #059669; }
.news-item.negative { border-left-color: #DC2626; }
.news-item.neutral  { border-left-color: #64748B; }
.news-item.rumor    { border-left-color: #9333EA; }

.news-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
    line-height: 1.4;
    margin-bottom: 4px;
}
.news-meta {
    font-size: 11px;
    color: var(--muted);
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
}

/* 뱃지 */
.badge {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 700;
    line-height: 1.5;
}
.badge-pos { background: #064E3B; color: #6EE7B7; }
.badge-neg { background: #7F1D1D; color: #FCA5A5; }
.badge-neu { background: #1E3A5F; color: #93C5FD; }
.badge-rumor { background: #3B0764; color: #E9D5FF; }
.badge-samsung { background: #1e3a8a; color: #93C5FD; }
.badge-apple   { background: #1C1C1E; color: #D1D5DB; border:1px solid #374151; }
.badge-etc     { background: #134E4A; color: #5EEAD4; }

/* 감성 섹션 헤더 */
.sentiment-section {
    border-radius: 8px;
    padding: 8px 12px;
    margin-bottom: 6px;
}
.s-pos { background: #052E16; border-left: 3px solid #059669; }
.s-neu { background: #0C1A2E; border-left: 3px solid #3B82F6; }
.s-neg { background: #450A0A; border-left: 3px solid #DC2626; }

.s-title { font-size: 13px; font-weight: 700; margin-bottom: 2px; }
.s-count { font-size: 11px; opacity: 0.7; }

/* 루머 카드 */
.rumor-card {
    background: #1A0B2E;
    border: 1px solid #4C1D95;
    border-radius: 8px;
    padding: 11px 13px;
    margin-bottom: 8px;
}
.rumor-card .r-title {
    font-size: 13px;
    font-weight: 600;
    color: #E9D5FF;
    line-height: 1.4;
    margin-bottom: 5px;
}
.rumor-card .r-summary {
    font-size: 11px;
    color: #A78BFA;
    line-height: 1.45;
    margin-bottom: 5px;
}

/* 필터 버튼 (Streamlit 기본 버튼 스타일 오버라이드) */
div[data-testid="stHorizontalBlock"] > div > div > button {
    border-radius: 20px !important;
    font-size: 12px !important;
}

/* 스크롤 영역 */
.scroll-area {
    max-height: 72vh;
    overflow-y: auto;
    padding-right: 4px;
}
.scroll-area::-webkit-scrollbar { width: 4px; }
.scroll-area::-webkit-scrollbar-track { background: transparent; }
.scroll-area::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# 세션 상태
# ─────────────────────────────────────────────
def _init():
    st.session_state.setdefault("articles", [])
    st.session_state.setdefault("selected_company", "삼성")
    st.session_state.setdefault("last_refresh", None)

_init()


# ─────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────
def _company_badge(company: str) -> str:
    cls = {"삼성": "badge-samsung", "애플": "badge-apple"}.get(company, "badge-etc")
    emoji = COMPANY_PROFILES.get(company, {}).get("emoji", "⚙️")
    return f"<span class='badge {cls}'>{emoji} {company}</span>"


def _sentiment_badge(sentiment: str) -> str:
    mapping = {
        "positive": ("badge-pos", "▲ 긍정"),
        "negative": ("badge-neg", "▼ 부정"),
        "neutral":  ("badge-neu", "● 중립"),
    }
    cls, label = mapping.get(sentiment, ("badge-neu", "● 중립"))
    return f"<span class='badge {cls}'>{label}</span>"


def _news_item_html(art: news_crawler.Article, analysis: analyst.ArticleAnalysis) -> str:
    sentiment_cls = analysis.sentiment  # positive / negative / neutral
    rumor_cls = " rumor" if art.is_rumor else ""
    safe_title = html.escape(art.title)
    safe_src = html.escape(art.source or "")
    s_badge = _sentiment_badge(analysis.sentiment)
    c_badge = _company_badge(art.company)
    rumor_tag = "<span class='badge badge-rumor'>📡 루머</span>" if art.is_rumor else ""

    return (
        f"<a href='{art.link}' target='_blank' style='text-decoration:none;'>"
        f"<div class='news-item {sentiment_cls}{rumor_cls}'>"
        f"  <div class='news-title'>{safe_title}</div>"
        f"  <div class='news-meta'>{c_badge}{s_badge}{rumor_tag}"
        f"    <span>{safe_src}</span><span>{art.published_ago}</span>"
        f"  </div>"
        f"</div></a>"
    )


def _ratio_bar(pos: int, neg: int, total: int) -> str:
    if total == 0:
        return ""
    p = int(pos / total * 100)
    n = int(neg / total * 100)
    neu = 100 - p - n
    return (
        f"<div style='display:flex;border-radius:4px;overflow:hidden;height:8px;margin:6px 0;'>"
        f"<div style='width:{p}%;background:#059669;'></div>"
        f"<div style='width:{neu}%;background:#374151;'></div>"
        f"<div style='width:{n}%;background:#DC2626;'></div>"
        f"</div>"
        f"<div style='font-size:11px;color:#64748B;display:flex;gap:10px;'>"
        f"<span style='color:#6EE7B7;'>▲ {p}%</span>"
        f"<span style='color:#94A3B8;'>● {neu}%</span>"
        f"<span style='color:#FCA5A5;'>▼ {n}%</span>"
        f"</div>"
    )


# ─────────────────────────────────────────────
# 데이터 로드
# ─────────────────────────────────────────────
def refresh_articles(force: bool = False) -> None:
    with st.spinner("뉴스 수집 중..."):
        arts = news_crawler.get_cached_articles(force_refresh=force)
    st.session_state.articles = arts
    st.session_state.last_refresh = datetime.now()


if not st.session_state.articles:
    refresh_articles()

articles: list[news_crawler.Article] = st.session_state.articles

# 전체 분석 (캐시 효과: 키워드 기반이라 빠름)
all_analyses: dict[str, analyst.ArticleAnalysis] = {
    a.link: analyst.analyze_article(a) for a in articles
}


# ─────────────────────────────────────────────
# 헤더
# ─────────────────────────────────────────────
age = news_crawler.cache_age_seconds()
age_str = f"{int(age//60)}분 전" if age else "방금"

col_h1, col_h2 = st.columns([4, 1])
with col_h1:
    st.markdown(
        f"""<div class="radar-header">
          <div>
            <h1>📡 선행기구개발그룹 뉴스 레이더</h1>
            <p>삼성 · 애플 모바일 최신 뉴스 · 루머 실시간 분석 &nbsp;|&nbsp; 수집: {age_str} · {len(articles)}건</p>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )
with col_h2:
    if st.button("🔄 새로고침", use_container_width=True):
        refresh_articles(force=True)
        st.rerun()


# ─────────────────────────────────────────────
# 3컬럼
# ─────────────────────────────────────────────
col_left, col_mid, col_right = st.columns([1.1, 1.3, 1.0], gap="medium")


# ═══════════════════════════════════════════
# 좌측: 회사별 뉴스 리스트
# ═══════════════════════════════════════════
with col_left:
    st.markdown("<div class='col-header'>📰 회사별 뉴스</div>", unsafe_allow_html=True)

    # 회사 필터 버튼
    companies = ["전체", "삼성", "애플", "기타"]
    btn_cols = st.columns(len(companies))
    for i, co in enumerate(companies):
        count = len(articles) if co == "전체" else sum(1 for a in articles if a.company == co)
        label = f"{COMPANY_PROFILES.get(co,{}).get('emoji','⚙️')} {co} ({count})" if co != "전체" else f"전체 ({count})"
        if btn_cols[i].button(label, key=f"co_{co}", use_container_width=True):
            st.session_state.selected_company = co
            st.rerun()

    selected = st.session_state.selected_company
    filtered = articles if selected == "전체" else [a for a in articles if a.company == selected]

    st.markdown(
        f"<div style='font-size:11px;color:#64748B;margin:6px 0;'>"
        f"{'전체' if selected == '전체' else selected} · {len(filtered)}건"
        f"</div>",
        unsafe_allow_html=True,
    )

    # 기사 리스트
    items_html = "".join(
        _news_item_html(a, all_analyses[a.link])
        for a in filtered
    )
    st.markdown(
        f"<div class='scroll-area'>{items_html}</div>",
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════
# 중간: 선택 회사 감성 분석
# ═══════════════════════════════════════════
with col_mid:
    selected = st.session_state.selected_company
    target = articles if selected == "전체" else [a for a in articles if a.company == selected]

    co_emoji = COMPANY_PROFILES.get(selected, {}).get("emoji", "📊")
    st.markdown(
        f"<div class='col-header'>{co_emoji} {selected} 감성 분석</div>",
        unsafe_allow_html=True,
    )

    if not target:
        st.info("해당 회사 기사가 없습니다.")
    else:
        pos_arts = [a for a in target if all_analyses[a.link].sentiment == "positive"]
        neg_arts = [a for a in target if all_analyses[a.link].sentiment == "negative"]
        neu_arts = [a for a in target if all_analyses[a.link].sentiment == "neutral"]

        # 비율 바
        st.markdown(
            f"<div style='background:#0F172A;border-radius:8px;padding:10px 14px;margin-bottom:12px;'>"
            f"<div style='font-size:11px;color:#64748B;margin-bottom:2px;'>감성 비율 · 총 {len(target)}건</div>"
            f"{_ratio_bar(len(pos_arts), len(neg_arts), len(target))}"
            f"</div>",
            unsafe_allow_html=True,
        )

        # ── 긍정 ──
        with st.expander(f"▲ 긍정 뉴스  {len(pos_arts)}건", expanded=True):
            if not pos_arts:
                st.caption("해당 기사 없음")
            else:
                for art in pos_arts:
                    rumor_tag = " 📡" if art.is_rumor else ""
                    safe_t = html.escape(art.title)
                    safe_s = html.escape(art.source or "")
                    st.markdown(
                        f"<div class='news-item positive' style='margin-bottom:6px;'>"
                        f"  <a href='{art.link}' target='_blank' style='text-decoration:none;color:inherit;'>"
                        f"    <div class='news-title'>{safe_t}{rumor_tag}</div>"
                        f"  </a>"
                        f"  <div class='news-meta'>{_company_badge(art.company)}"
                        f"    <span>{safe_s}</span><span>{art.published_ago}</span>"
                        f"  </div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

        # ── 중립 ──
        with st.expander(f"● 중립 뉴스  {len(neu_arts)}건", expanded=False):
            if not neu_arts:
                st.caption("해당 기사 없음")
            else:
                for art in neu_arts:
                    safe_t = html.escape(art.title)
                    safe_s = html.escape(art.source or "")
                    st.markdown(
                        f"<div class='news-item neutral' style='margin-bottom:6px;'>"
                        f"  <a href='{art.link}' target='_blank' style='text-decoration:none;color:inherit;'>"
                        f"    <div class='news-title'>{safe_t}</div>"
                        f"  </a>"
                        f"  <div class='news-meta'>{_company_badge(art.company)}"
                        f"    <span>{safe_s}</span><span>{art.published_ago}</span>"
                        f"  </div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

        # ── 부정 ──
        with st.expander(f"▼ 부정 뉴스  {len(neg_arts)}건", expanded=True):
            if not neg_arts:
                st.caption("해당 기사 없음")
            else:
                for art in neg_arts:
                    safe_t = html.escape(art.title)
                    safe_s = html.escape(art.source or "")
                    st.markdown(
                        f"<div class='news-item negative' style='margin-bottom:6px;'>"
                        f"  <a href='{art.link}' target='_blank' style='text-decoration:none;color:inherit;'>"
                        f"    <div class='news-title'>{safe_t}</div>"
                        f"  </a>"
                        f"  <div class='news-meta'>{_company_badge(art.company)}"
                        f"    <span>{safe_s}</span><span>{art.published_ago}</span>"
                        f"  </div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )


# ═══════════════════════════════════════════
# 우측: 루머 & 전망
# ═══════════════════════════════════════════
with col_right:
    rumors = [a for a in articles if a.is_rumor]
    st.markdown(
        f"<div class='col-header'>📡 루머 &amp; 전망 · {len(rumors)}건</div>",
        unsafe_allow_html=True,
    )

    if not rumors:
        st.info("수집된 루머/전망 기사가 없습니다.")
    else:
        # 회사별 루머 카운트
        sam_r = sum(1 for a in rumors if a.company == "삼성")
        apl_r = sum(1 for a in rumors if a.company == "애플")
        etc_r = len(rumors) - sam_r - apl_r
        st.markdown(
            f"<div style='display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;'>"
            f"<span class='badge badge-samsung'>🔵 삼성 {sam_r}</span>"
            f"<span class='badge badge-apple'>🍎 애플 {apl_r}</span>"
            f"<span class='badge badge-etc'>⚙️ 기타 {etc_r}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        rumor_html_parts = []
        for art in rumors:
            safe_t = html.escape(art.title)
            safe_s = html.escape(art.source or "")
            safe_sum = html.escape(
                art.summary_raw[:120] + "…" if len(art.summary_raw) > 120 else art.summary_raw
            )
            c_badge = _company_badge(art.company)
            s_badge = _sentiment_badge(all_analyses[art.link].sentiment)

            rumor_html_parts.append(
                f"<a href='{art.link}' target='_blank' style='text-decoration:none;'>"
                f"<div class='rumor-card'>"
                f"  <div style='display:flex;gap:6px;margin-bottom:5px;flex-wrap:wrap;'>{c_badge}{s_badge}</div>"
                f"  <div class='r-title'>{safe_t}</div>"
                f"  <div class='r-summary'>{safe_sum}</div>"
                f"  <div style='font-size:10px;color:#6D28D9;'>{safe_s} · {art.published_ago}</div>"
                f"</div></a>"
            )

        st.markdown(
            f"<div class='scroll-area'>{''.join(rumor_html_parts)}</div>",
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────
# 푸터
# ─────────────────────────────────────────────
st.markdown("---")
st.caption(f"© 선행기구개발그룹 뉴스 레이더 · Google News RSS · 수집 {len(articles)}건")
