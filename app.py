"""선행기구개발그룹 뉴스 레이더 - Streamlit 메인 앱.

3컬럼 레이아웃:
  좌측  - 실시간 뉴스 피드 (1시간 캐시, 위로 흐르는 애니메이션)
  중간  - Gemma 3 컨트롤러 (채팅)
  우측  - 선택된 기사 요약 + PPT 생성
사이드바:
  - Ollama 설정
  - 이메일 알림 설정 (수신자, 발송 주기, 테스트 발송)
"""
from __future__ import annotations

import html
import re
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import dotenv_values, set_key

import analyst
import email_dispatcher
import gemma_client
import news_crawler
from ppt_generator import build_pptx

_ENV_PATH = Path(__file__).parent / ".env"


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
def _load_env_email_config() -> dict:
    """저장된 .env 파일에서 이메일 설정을 읽어 dict 반환."""
    if not _ENV_PATH.exists():
        return {}
    return dotenv_values(_ENV_PATH)


def _save_env_value(key: str, value: str) -> None:
    """특정 환경변수 값을 .env 파일에 저장."""
    set_key(str(_ENV_PATH), key, value)


def _init_state() -> None:
    ss = st.session_state
    ss.setdefault("articles", [])
    ss.setdefault("selected_idx", None)
    ss.setdefault("summary", "")
    ss.setdefault("chat_history", [])  # [{role, content}]
    ss.setdefault("model_name", gemma_client.DEFAULT_MODEL)
    ss.setdefault("ollama_url", gemma_client.OLLAMA_BASE_URL)
    ss.setdefault("last_refresh", None)

    # 이메일 관련 세션 상태
    env = _load_env_email_config()
    ss.setdefault("email_recipients", env.get("EMAIL_RECIPIENTS", ""))
    ss.setdefault("smtp_user", env.get("SMTP_USER", ""))
    ss.setdefault("smtp_password", env.get("SMTP_PASSWORD", ""))
    ss.setdefault("smtp_host", env.get("SMTP_HOST", "smtp.gmail.com"))
    ss.setdefault("smtp_port", int(env.get("SMTP_PORT", "587")))
    ss.setdefault("email_send_hour", 9)
    ss.setdefault("email_enabled", bool(env.get("SMTP_USER")))
    ss.setdefault("last_email_sent_ts", None)
    ss.setdefault("last_trigger_check", None)
    ss.setdefault("email_status_msg", "")
    ss.setdefault("triggered_articles", [])


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

    # ─────────────────────────────────────────────
    # 이메일 알림 설정
    # ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📧 이메일 알림 설정")

    with st.expander("SMTP 계정 설정", expanded=not st.session_state.smtp_user):
        smtp_user_input = st.text_input(
            "Gmail 주소",
            value=st.session_state.smtp_user,
            placeholder="your_gmail@gmail.com",
            key="smtp_user_input",
        )
        smtp_pw_input = st.text_input(
            "Gmail App Password",
            value=st.session_state.smtp_password,
            type="password",
            placeholder="앱 비밀번호 16자리",
            key="smtp_pw_input",
            help="Gmail → 계정설정 → 보안 → 앱 비밀번호에서 생성",
        )
        if st.button("💾 SMTP 설정 저장", use_container_width=True, key="save_smtp"):
            st.session_state.smtp_user = smtp_user_input
            st.session_state.smtp_password = smtp_pw_input
            _save_env_value("SMTP_USER", smtp_user_input)
            _save_env_value("SMTP_PASSWORD", smtp_pw_input)
            _save_env_value("SMTP_HOST", "smtp.gmail.com")
            _save_env_value("SMTP_PORT", "587")
            st.success("SMTP 설정이 .env 에 저장되었습니다.")

    recipients_input = st.text_input(
        "수신 이메일 주소",
        value=st.session_state.email_recipients,
        placeholder="addr1@example.com,addr2@example.com",
        help="쉼표로 여러 주소 입력 가능",
        key="email_recipients_input",
    )
    if recipients_input != st.session_state.email_recipients:
        st.session_state.email_recipients = recipients_input
        _save_env_value("EMAIL_RECIPIENTS", recipients_input)

    send_hour = st.slider(
        "정기 발송 시각 (시)",
        min_value=0,
        max_value=23,
        value=st.session_state.email_send_hour,
        format="%d시",
        key="email_send_hour_slider",
    )
    st.session_state.email_send_hour = send_hour

    # 알림 활성화 토글
    email_enabled = st.toggle(
        "이메일 알림 활성화",
        value=st.session_state.email_enabled,
        key="email_enabled_toggle",
    )
    st.session_state.email_enabled = email_enabled

    if st.session_state.last_email_sent_ts:
        last_sent_dt = datetime.fromtimestamp(st.session_state.last_email_sent_ts)
        st.caption(f"마지막 발송: {last_sent_dt.strftime('%m/%d %H:%M')}")

    if st.session_state.email_status_msg:
        msg = st.session_state.email_status_msg
        if msg.startswith("✅"):
            st.success(msg)
        elif msg.startswith("❌"):
            st.error(msg)
        else:
            st.info(msg)

    col_test, col_now = st.columns(2)
    with col_test:
        test_btn = st.button("✉️ 테스트 발송", use_container_width=True, key="test_email_btn")
    with col_now:
        send_now_btn = st.button("📤 지금 발송", use_container_width=True, key="send_now_btn")


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
def _build_email_config() -> email_dispatcher.EmailConfig:
    """세션 상태에서 EmailConfig 생성."""
    recipients = [
        r.strip()
        for r in st.session_state.email_recipients.split(",")
        if r.strip()
    ]
    return email_dispatcher.EmailConfig(
        smtp_host=st.session_state.smtp_host,
        smtp_port=st.session_state.smtp_port,
        smtp_user=st.session_state.smtp_user,
        smtp_password=st.session_state.smtp_password,
        recipients=recipients,
    )


def _do_send_report(report_type: str = "scheduled", trigger_keyword: str | None = None) -> None:
    """리포트 분석 후 이메일 발송."""
    if not st.session_state.articles:
        st.session_state.email_status_msg = "❌ 수집된 기사가 없습니다. 먼저 새로고침하세요."
        return
    config = _build_email_config()
    summary = analyst.analyze_articles(st.session_state.articles)
    with st.spinner("이메일 발송 중..."):
        ok, msg = email_dispatcher.send_report(
            summary, config, report_type=report_type, trigger_keyword=trigger_keyword
        )
    if ok:
        st.session_state.last_email_sent_ts = time.time()
        st.session_state.email_status_msg = f"✅ {msg}"
    else:
        st.session_state.email_status_msg = f"❌ {msg}"


def _check_triggers(articles: list) -> None:
    """긴급 트리거 키워드 확인 후 조건 충족 시 즉시 발송."""
    if not st.session_state.email_enabled:
        return
    triggered = analyst.find_triggered_articles(articles)
    if not triggered:
        st.session_state.triggered_articles = []
        return

    new_triggered = [
        a for a in triggered
        if a.link not in {t.link for t in st.session_state.triggered_articles}
    ]
    if not new_triggered:
        return

    st.session_state.triggered_articles = triggered
    # 첫 번째 트리거 키워드 추출
    from analyst import _get_urgent_keywords
    urgent_kws = _get_urgent_keywords()
    found_kw = None
    for art in new_triggered:
        text = f"{art.title} {art.summary_raw}".lower()
        for kw in urgent_kws:
            if kw.lower() in text:
                found_kw = kw
                break
        if found_kw:
            break

    config = _build_email_config()
    if config.is_valid():
        summary = analyst.analyze_articles(articles)
        ok, msg = email_dispatcher.send_report(
            summary, config, report_type="urgent", trigger_keyword=found_kw
        )
        if ok:
            st.session_state.last_email_sent_ts = time.time()
            st.session_state.email_status_msg = (
                f"✅ 긴급 트리거 '{found_kw}' 감지 → 즉시 발송 완료"
            )
        else:
            st.session_state.email_status_msg = f"❌ 긴급 발송 실패: {msg}"


def refresh_articles(force: bool = False) -> None:
    with st.spinner("뉴스 피드를 수집 중입니다..."):
        articles = news_crawler.get_cached_articles(force_refresh=force)
    st.session_state.articles = articles
    st.session_state.last_refresh = datetime.now()
    # 새 기사 수집 후 트리거 확인
    if st.session_state.email_enabled:
        _check_triggers(articles)


if refresh_clicked or not st.session_state.articles:
    refresh_articles(force=refresh_clicked)

# ─────────────────────────────────────────────
# 사이드바 버튼 액션 처리 (상태 업데이트 후)
# ─────────────────────────────────────────────
if "test_btn" in st.session_state and test_btn:
    test_addr = st.session_state.email_recipients.split(",")[0].strip()
    if not test_addr:
        st.session_state.email_status_msg = "❌ 수신 이메일 주소를 먼저 입력하세요."
    else:
        config = _build_email_config()
        with st.spinner(f"{test_addr} 으로 테스트 메일 발송 중..."):
            ok, msg = email_dispatcher.send_test_email(test_addr, config)
        st.session_state.email_status_msg = ("✅ " if ok else "❌ ") + msg

if "send_now_btn" in st.session_state and send_now_btn:
    _do_send_report(report_type="scheduled")

# 정기 발송 스케줄 체크 (페이지 렌더링 시마다)
if st.session_state.email_enabled:
    if email_dispatcher.should_send_scheduled(
        st.session_state.email_send_hour,
        0,
        st.session_state.last_email_sent_ts,
    ):
        _do_send_report(report_type="scheduled")


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
        # 무한 루프 효과를 위해 한 번 더 복제
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

        sentiment_bar = (
            f"<div style='display:flex;border-radius:4px;overflow:hidden;height:12px;margin:4px 0 2px;'>"
            f"<div style='width:{pos_pct}%;background:#059669;'></div>"
            f"<div style='width:{neg_pct}%;background:#DC2626;'></div>"
            f"<div style='width:{100-pos_pct-neg_pct}%;background:#374151;'></div>"
            f"</div>"
            f"<div style='font-size:11px;color:#94A3B8;display:flex;gap:10px;'>"
            f"<span style='color:#6EE7B7;'>▲ 긍정 {pos_pct}%</span>"
            f"<span style='color:#FCA5A5;'>▼ 부정 {neg_pct}%</span>"
            f"<span>총 {analysis_summary.total}건</span>"
            f"</div>"
        )
        urgent_badge = ""
        if analysis_summary.urgent_count:
            urgent_badge = (
                f"<span style='background:#DC2626;color:#fff;padding:2px 8px;"
                f"border-radius:4px;font-size:11px;font-weight:700;margin-left:8px;'>"
                f"🚨 긴급 {analysis_summary.urgent_count}건</span>"
            )
        st.markdown(
            f"<div style='background:#0F172A;border-radius:8px;padding:10px 14px;"
            f"margin-bottom:12px;'>"
            f"<div style='font-size:12px;font-weight:600;color:#94A3B8;margin-bottom:4px;'>"
            f"감성 분석 요약{urgent_badge}</div>"
            f"{sentiment_bar}</div>",
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
