"""뉴스 감성 대시보드 차트 컴포넌트 — Plotly 기반.

모든 함수는 articles + sentiments 리스트를 받아 plotly Figure 또는 HTML string 반환.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any

import plotly.graph_objects as go


# ----- 컬러 토큰 -----
COLOR_POS = "#34c759"   # 긍정 그린
COLOR_NEG = "#ff3b30"   # 부정 빨강
COLOR_NEU = "#8e8e93"   # 중립 회색
COLOR_INK = "#1d1d1f"
COLOR_INK_2 = "#555555"
COLOR_LINE = "#e5e5e5"
COLOR_BG_SOFT = "#f7f7f9"


# ============================================================================
# 헬퍼
# ============================================================================
def _count_labels(sentiments):
    pos = sum(1 for s in sentiments if getattr(s, "label", "") == "positive")
    neg = sum(1 for s in sentiments if getattr(s, "label", "") == "negative")
    neu = sum(1 for s in sentiments if getattr(s, "label", "") == "neutral")
    return pos, neg, neu


def _make_layout(height=240, margin=(10, 10, 10, 10), showlegend=False):
    l, r, t, b = margin
    return dict(
        height=height,
        margin=dict(l=l, r=r, t=t, b=b),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=showlegend,
        font=dict(family="Inter, Noto Sans KR, sans-serif", color=COLOR_INK, size=11),
    )


# ============================================================================
# 1) 전체 감성 도넛 — pos ratio 중심
# ============================================================================
def build_total_sentiment_donut(sentiments):
    pos, neg, neu = _count_labels(sentiments)
    total = max(pos + neg + neu, 1)
    pos_pct = round(pos * 100 / total)
    rest = total - pos
    fig = go.Figure(go.Pie(
        values=[pos, rest],
        labels=["긍정", "기타"],
        hole=0.72,
        marker=dict(colors=[COLOR_POS, "#eef1f4"]),
        textinfo="none",
        hoverinfo="label+percent+value",
        direction="clockwise",
        sort=False,
    ))
    fig.add_annotation(
        text=f"<b style='font-size:30px;color:{COLOR_INK}'>{pos_pct}%</b><br>"
             f"<span style='color:{COLOR_INK_2};font-size:11px'>긍정 {pos}건</span>",
        showarrow=False, x=0.5, y=0.5,
    )
    fig.update_layout(**_make_layout(height=220))
    return fig


# ============================================================================
# 2) 전체 뉴스 도넛 — 3색 분포 + 중앙 총건수 + 증감률
# ============================================================================
def build_news_total_donut(sentiments, change_pct=None):
    pos, neg, neu = _count_labels(sentiments)
    total = pos + neg + neu
    fig = go.Figure(go.Pie(
        values=[pos, neg, neu] if total else [1, 1, 1],
        labels=["긍정", "부정", "중립"],
        hole=0.7,
        marker=dict(colors=[COLOR_POS, COLOR_NEG, COLOR_NEU]),
        textinfo="none",
        hoverinfo="label+percent+value",
        direction="clockwise",
        sort=False,
    ))
    sub_html = f"<span style='color:{COLOR_INK_2};font-size:11px'>총 기사</span>"
    if change_pct is not None:
        sign = "+" if change_pct >= 0 else ""
        color = COLOR_POS if change_pct >= 0 else COLOR_NEG
        sub_html = f"<span style='color:{color};font-size:11px;font-weight:600'>{sign}{change_pct:.1f}% 증가</span>"
    fig.add_annotation(
        text=f"<b style='font-size:26px;color:{COLOR_INK}'>{total:,}</b><br>{sub_html}",
        showarrow=False, x=0.5, y=0.5,
    )
    fig.update_layout(**_make_layout(height=220))
    return fig


# ============================================================================
# 3) 감성 추이 라인 — 시간 bucket 별 긍/중/부 카운트
# ============================================================================
def build_sentiment_trend_line(articles, sentiments, hours=24, bucket_minutes=60):
    """published_dt 기반 hours 시간을 bucket_minutes 단위 bucket으로."""
    if not articles or not sentiments:
        fig = go.Figure()
        fig.update_layout(**_make_layout(height=240))
        fig.add_annotation(text="데이터 없음", showarrow=False, x=0.5, y=0.5,
                          xref="paper", yref="paper", font=dict(color=COLOR_INK_2))
        return fig

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    bucket_count = max(1, (hours * 60) // bucket_minutes)
    # 각 bucket: {pos, neg, neu}
    buckets = [{"t": start + timedelta(minutes=i * bucket_minutes), "pos": 0, "neg": 0, "neu": 0}
               for i in range(bucket_count)]

    for a, s in zip(articles, sentiments):
        dt = getattr(a, "published_dt", None)
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt < start or dt > now:
            continue
        idx = min(int((dt - start).total_seconds() // (bucket_minutes * 60)), bucket_count - 1)
        lbl = getattr(s, "label", "")
        if lbl in ("positive", "negative", "neutral"):
            key = {"positive": "pos", "negative": "neg", "neutral": "neu"}[lbl]
            buckets[idx][key] += 1

    times = [b["t"].strftime("%H:%M") for b in buckets]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=times, y=[b["pos"] for b in buckets],
        mode="lines", line=dict(color=COLOR_POS, width=2.5, shape="spline"),
        name="긍정", hovertemplate="%{x} · 긍정 %{y}건<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=times, y=[b["neu"] for b in buckets],
        mode="lines", line=dict(color=COLOR_NEU, width=2, shape="spline"),
        name="중립", hovertemplate="%{x} · 중립 %{y}건<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=times, y=[b["neg"] for b in buckets],
        mode="lines", line=dict(color=COLOR_NEG, width=2.5, shape="spline"),
        name="부정", hovertemplate="%{x} · 부정 %{y}건<extra></extra>",
    ))
    layout = _make_layout(height=260, showlegend=True)
    layout["legend"] = dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10))
    layout["xaxis"] = dict(showgrid=False, color=COLOR_INK_2, tickfont=dict(size=9))
    layout["yaxis"] = dict(showgrid=True, gridcolor=COLOR_LINE, color=COLOR_INK_2, tickfont=dict(size=9))
    fig.update_layout(**layout)
    return fig


# ============================================================================
# 4) 매체 TOP 5 가로 bar
# ============================================================================
def build_source_top5_bar(articles, top_n=5):
    counter = Counter()
    for a in articles:
        src = getattr(a, "source", "") or "Unknown"
        counter[src] += 1
    top = counter.most_common(top_n)
    if not top:
        fig = go.Figure()
        fig.update_layout(**_make_layout(height=220))
        return fig

    names = [n for n, _ in reversed(top)]
    counts = [c for _, c in reversed(top)]
    fig = go.Figure(go.Bar(
        x=counts, y=names, orientation="h",
        marker=dict(color="#5b6cff", line=dict(color="#3a4ad8", width=0)),
        text=counts, textposition="outside",
        textfont=dict(color=COLOR_INK, size=10),
        hovertemplate="%{y} · %{x}건<extra></extra>",
    ))
    layout = _make_layout(height=220, margin=(5, 30, 10, 5))
    layout["xaxis"] = dict(showgrid=False, showticklabels=False, color=COLOR_INK_2)
    layout["yaxis"] = dict(showgrid=False, color=COLOR_INK, tickfont=dict(size=10))
    fig.update_layout(**layout)
    return fig


# ============================================================================
# 5) 키워드 클라우드 — HTML/CSS (Plotly로 wordcloud는 무겁고 plotly에 native X)
# ============================================================================
def build_keyword_cloud_html(sentiments, top_n=20):
    """sentiment pos_hits + neg_hits 빈도 → HTML span 폰트 사이즈 차등."""
    counter = Counter()
    for s in sentiments:
        for tok in (getattr(s, "pos_hits", None) or []):
            counter[(tok, "pos")] += 1
        for tok in (getattr(s, "neg_hits", None) or []):
            counter[(tok, "neg")] += 1
    if not counter:
        return "<div class='kw-cloud-empty'>키워드 없음</div>"

    most = counter.most_common(top_n)
    max_freq = most[0][1]
    min_freq = most[-1][1]

    spans = []
    for (tok, kind), freq in most:
        # 사이즈 12~28px 사이 mapping
        if max_freq == min_freq:
            size = 18
        else:
            size = int(12 + (freq - min_freq) / (max_freq - min_freq) * 16)
        color = COLOR_POS if kind == "pos" else COLOR_NEG
        # 약간의 색 변형 (gradient)
        spans.append(
            f"<span class='kw-cloud-item' style='font-size:{size}px;color:{color};font-weight:{500 + min(freq*50, 300)}'>"
            f"{tok}</span>"
        )
    return "<div class='kw-cloud'>" + " ".join(spans) + "</div>"


# ============================================================================
# 6) 감성 분포 mini-stat (긍정 N / 부정 N / 중립 N + 비율 bar)
# ============================================================================
def build_sentiment_distribution_html(sentiments):
    pos, neg, neu = _count_labels(sentiments)
    total = max(pos + neg + neu, 1)
    pos_pct = pos * 100 // total
    neg_pct = neg * 100 // total
    neu_pct = 100 - pos_pct - neg_pct
    return f"""
    <div class='sent-dist'>
        <div class='sent-dist-row'>
            <span class='sent-dist-dot' style='background:{COLOR_POS}'></span>
            <span class='sent-dist-label'>긍정</span>
            <span class='sent-dist-count'>{pos:,}</span>
        </div>
        <div class='sent-dist-row'>
            <span class='sent-dist-dot' style='background:{COLOR_NEG}'></span>
            <span class='sent-dist-label'>부정</span>
            <span class='sent-dist-count'>{neg:,}</span>
        </div>
        <div class='sent-dist-row'>
            <span class='sent-dist-dot' style='background:{COLOR_NEU}'></span>
            <span class='sent-dist-label'>중립</span>
            <span class='sent-dist-count'>{neu:,}</span>
        </div>
        <div class='sent-dist-bar'>
            <div style='width:{pos_pct}%;background:{COLOR_POS}'></div>
            <div style='width:{neg_pct}%;background:{COLOR_NEG}'></div>
            <div style='width:{neu_pct}%;background:{COLOR_NEU}'></div>
        </div>
    </div>
    """


# ============================================================================
# 7) 실시간 뉴스 피드 — 시간 정렬 + "N분 전"
# ============================================================================
def _humanize_dt(dt):
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    diff = (now - dt).total_seconds()
    if diff < 60:
        return "방금"
    if diff < 3600:
        return f"{int(diff // 60)}분 전"
    if diff < 86400:
        return f"{int(diff // 3600)}시간 전"
    return dt.strftime("%m/%d")


def build_realtime_feed_html(articles, sentiments, limit=8, recent_minutes=30):
    """시간 역순 정렬, 최근 N분 내 항목은 '신규' 라벨."""
    pairs = list(zip(articles, sentiments))
    # 시간 있는 것만 + 정렬
    with_dt = []
    for a, s in pairs:
        dt = getattr(a, "published_dt", None)
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        with_dt.append((a, s, dt))
    with_dt.sort(key=lambda x: x[2], reverse=True)

    if not with_dt:
        return "<div class='rt-feed-empty'>최근 기사 없음</div>"

    now = datetime.now(timezone.utc)
    fresh_cutoff = now - timedelta(minutes=recent_minutes)

    rows = []
    for a, s, dt in with_dt[:limit]:
        is_new = dt >= fresh_cutoff
        lbl = getattr(s, "label_ko", "") or ""
        lbl_class = getattr(s, "label", "neutral")
        title = (getattr(a, "title_localized", None) or getattr(a, "title", "") or "")[:70]
        link = getattr(a, "link", "#") or "#"
        src = getattr(a, "source", "") or ""
        new_badge = "<span class='rt-feed-new'>신규</span>" if is_new else ""
        rows.append(
            f"""<div class='rt-feed-row'>
                <span class='rt-feed-time'>{_humanize_dt(dt)}</span>
                <div class='rt-feed-body'>
                    <div class='rt-feed-title'>
                        <a href='{link}' target='_blank' rel='noopener'>{_safe(title)}</a>
                        {new_badge}
                    </div>
                    <div class='rt-feed-meta'>
                        <span class='rt-feed-src'>{_safe(src)}</span>
                        <span class='rt-feed-sent rt-feed-sent-{lbl_class}'>{_safe(lbl)}</span>
                    </div>
                </div>
            </div>"""
        )
    return "<div class='rt-feed'>" + "".join(rows) + "</div>"


def _safe(s):
    import html as _h
    return _h.escape(s or "")
