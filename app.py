"""선행기구개발그룹 뉴스 레이더 - Streamlit 메인 앱.

3컬럼 레이아웃:
  좌측  - 실시간 뉴스 피드 (1시간 캐시, 위로 흐르는 애니메이션)
  중간  - Gemma 3 컨트롤러 (채팅)
  우측  - 감성 분석 요약 + 선택 기사 요약 + PPT 생성
"""
from __future__ import annotations

import html
import re
from datetime import datetime

import streamlit as st

import analyst
import gemma_client
import news_crawler
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
:root {
    --brand-navy: #0B1F3A;
    --brand-blue: #1F6FEB;
    --brand-cyan: #22D3EE;
}
.main-header {
    background: linear-gradient(90deg, var(--brand-navy) 0%, var(--brand-blue) 100%);
    padding: 18px 24px;
    border-radius: 12px;
    color: #fff;
    margin-bottom: 14px;
}
.main-header h1 { margin: 0; font-size: 24px; letter-spacing: 0.5px; }
.main-header p  { margin: 4px 0 0; font-size: 13px; opacity: 0.85; }

.col-card {
    background: #0F172A;
    border: 1px solid #1E293B;
    border-radius: 12px;
    padding: 14px;
    color: #E2E8F0;
}
.col-card h3 {
    margin: 0 0 10px 0;
    color: var(--brand-cyan);
    font-size: 16px;
    border-bottom: 1px solid #1E293B;
    padding-bottom: 6px;
}

/* 뉴스 피드 애니메이션 */
.ticker-wrapper {
    height: 520px;
    overflow: hidden;
    position: relative;
    background: #0F172A;
    border: 1px solid #1E293B;
    border-radius: 10px;
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
    padding: 10px 14px;
    margin: 6px 8px;
    background: #1E293B;
    border-left: 3px solid var(--brand-cyan);
    border-radius: 6px;
    color: #E2E8F0;
    font-size: 13px;
    line-height: 1.45;
}
.ticker-item .kw {
    display: inline-block;
    background: var(--brand-blue);
    color: #fff;
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 4px;
    margin-right: 6px;
    vertical-align: middle;
}
.ticker-item .src { color: #94A3B8; font-size: 11px; }

.status-pill {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
}
.status-ok   { background: #064E3B; color: #6EE7B7; }
.status-bad  { background: #7F1D1D; color: #FCA5A5; }
</style>
"""
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 세션 상태 초기화
# ---------------------------------------------------------------------------
def _init_state() -> None:
    ss = st.session_state
    ss.setdefault("articles", [])
    ss.setdefault("selected_idx", None)
    ss.setdefault("summary", "")
    ss.setdefault("chat_history", [])
    ss.setdefault("model_name", gemma_client.DEFAULT_MODEL)
    ss.setdefault("ollama_url", gemma_client.OLLAMA_BASE_URL)
    ss.setdefault("last_refresh", None)


_init_state()


# ---------------------------------------------------------------------------
# 사이드바: 환경설정
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ 시스템 설정")

    st.session_state.ollama_url = st.text_input(
        "Ollama Endpoint",
        value=st.session_state.ollama_url,
        help="로컬 Ollama 서버 주소",
    )

    available = gemma_client.is_available(st.session_state.ollama_url)
    if available:
        st.markdown(
            "<span class='status-pill status-ok'>● Ollama 연결됨</span>",
            unsafe_allow_html=True,
        )
        models = gemma_client.list_models(st.session_state.ollama_url)
        gemma_models = [m for m in models if "gemma" in m.lower()] or models
        if gemma_models:
            default_idx = (
                gemma_models.index(st.session_state.model_name)
                if st.session_state.model_name in gemma_models
                else 0
            )
            st.session_state.model_name = st.selectbox(
                "모델 선택", gemma_models, index=default_idx
            )
        else:
            st.warning("설치된 모델이 없습니다. `ollama pull gemma3` 실행 필요.")
    else:
        st.markdown(
            "<span class='status-pill status-bad'>● Ollama 연결 실패</span>",
            unsafe_allow_html=True,
        )
        st.caption("`ollama serve` 가 11434 포트에서 실행 중인지 확인하세요.")
        st.session_state.model_name = st.text_input(
            "모델 이름", value=st.session_state.model_name
        )

    st.markdown("---")
    st.markdown("### 🔍 수집 키워드")
    st.caption("아래 키워드 기반으로 Google News RSS에서 수집합니다.")
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
    with st.spinner("뉴스 피드를 수집 중입니다..."):
        articles = news_crawler.get_cached_articles(force_refresh=force)
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
    st.markdown("<div class='col-card'><h3>📰 실시간 뉴스 피드</h3>", unsafe_allow_html=True)

    age = news_crawler.cache_age_seconds()
    if age is not None:
        mins = int(age // 60)
        st.caption(f"마지막 수집: {mins}분 전 · 자동 갱신 주기 1시간")

    articles = st.session_state.articles

    if not articles:
        st.info("수집된 기사가 없습니다. 사이드바의 새로고침을 눌러주세요.")
    else:
        items_html_parts = []
        for art in articles:
            safe_title = html.escape(art.title)
            safe_kw = html.escape(art.matched_keyword)
            safe_src = html.escape(art.source or "")
            items_html_parts.append(
                f"""<div class='ticker-item'>
                    <span class='kw'>{safe_kw}</span>
                    <div>{safe_title}</div>
                    <div class='src'>{safe_src}</div>
                </div>"""
            )
        items_html = "".join(items_html_parts) * 2
        st.markdown(
            f"<div class='ticker-wrapper'><div class='ticker-track'>{items_html}</div></div>",
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.markdown("**기사 선택** — 우측 컬럼에서 분석/요약")
        options = [f"{i+1}. {a.title[:60]}" for i, a in enumerate(articles)]
        sel = st.selectbox(
            "기사 선택",
            options=list(range(len(articles))),
            format_func=lambda i: options[i],
            label_visibility="collapsed",
        )
        st.session_state.selected_idx = sel

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
                    for tok in gemma_client.chat_stream(
                        api_messages,
                        model=st.session_state.model_name,
                        base_url=st.session_state.ollama_url,
                    ):
                        acc += tok
                        placeholder.markdown(acc + "▌")
                    placeholder.markdown(acc or "_(응답 없음)_")
                except gemma_client.OllamaError as exc:
                    acc = f"⚠️ {exc}"
                    placeholder.error(acc)

        st.session_state.chat_history.append({"role": "assistant", "content": acc})

    if st.session_state.chat_history:
        if st.button("🗑️ 대화 초기화", key="clear_chat"):
            st.session_state.chat_history = []
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# ===========================================================================
# 우측: 감성 분석 요약 + 기사 요약 및 PPT 생성
# ===========================================================================
with col_right:
    st.markdown(
        "<div class='col-card'><h3>📑 요약 & PPT 리포트</h3>",
        unsafe_allow_html=True,
    )

    # 감성 분석 미니 대시보드
    if st.session_state.articles:
        analysis_summary = analyst.analyze_articles(st.session_state.articles)
        pos_pct = int(analysis_summary.positive_ratio * 100)
        neg_pct = int(analysis_summary.negative_ratio * 100)

        urgent_badge = ""
        if analysis_summary.urgent_count:
            urgent_badge = (
                f"<span style='background:#DC2626;color:#fff;padding:2px 8px;"
                f"border-radius:4px;font-size:11px;font-weight:700;margin-left:8px;'>"
                f"🚨 긴급 {analysis_summary.urgent_count}건</span>"
            )

        st.markdown(
            f"""<div style='background:#0F172A;border-radius:8px;padding:10px 14px;margin-bottom:12px;'>
              <div style='font-size:12px;font-weight:600;color:#94A3B8;margin-bottom:6px;'>
                감성 분석 요약{urgent_badge}
              </div>
              <div style='display:flex;border-radius:4px;overflow:hidden;height:12px;margin-bottom:5px;'>
                <div style='width:{pos_pct}%;background:#059669;'></div>
                <div style='width:{neg_pct}%;background:#DC2626;'></div>
                <div style='width:{100-pos_pct-neg_pct}%;background:#374151;'></div>
              </div>
              <div style='font-size:11px;color:#94A3B8;display:flex;gap:12px;'>
                <span style='color:#6EE7B7;'>▲ 긍정 {pos_pct}% ({analysis_summary.positive_count}건)</span>
                <span style='color:#FCA5A5;'>▼ 부정 {neg_pct}% ({analysis_summary.negative_count}건)</span>
                <span>총 {analysis_summary.total}건</span>
              </div>
            </div>""",
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
                            article.title,
                            body,
                            model=st.session_state.model_name,
                            extra_instruction=extra or "",
                        )
                        st.session_state.summary = summary
                    except gemma_client.OllamaError as exc:
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
    f"엔드포인트: {st.session_state.ollama_url}"
)
