"""오늘 주목 (Top of Mind) — 자동 큐레이션.

스냅샷 기반: 현재 fetch된 기사 묶음에서 다음 4가지 신호로 상위 5개 회사를 선정.

신호:
1. 부정 집중   (negative ratio >= 50% AND total >= 4)
2. 다중 매체   (>= 4개 매체에서 동시 보도)
3. 주요 이벤트 (launch/acquisition/recall/lawsuit/earnings/IPO 등 키워드)
4. 고볼륨     (top 3 most mentioned, total >= 5)

회사당 highlight 1개만 — score 가장 높은 것만 유지.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


HighlightType = Literal["warning", "info", "event", "volume"]


@dataclass
class Highlight:
    company: str
    reason: str            # 짧은 라벨 (예: "부정 집중", "다중 매체 보도")
    detail: str            # 세부 (예: "부정 5건 / 총 8건")
    score: int
    type: HighlightType


# 이벤트 키워드 — 토큰 → 한국어 라벨
EVENT_KEYWORDS: dict[str, str] = {
    # 신제품 출시
    "launch": "신제품 출시", "출시": "신제품 출시", "release": "신제품 출시",
    "unveil": "신제품 출시", "공개": "신제품 출시",
    # 인수합병
    "acquisition": "인수합병", "인수": "인수합병", "merger": "인수합병",
    "합병": "인수합병", "acquire": "인수합병",
    # 리콜
    "recall": "리콜", "리콜": "리콜",
    # 소송
    "lawsuit": "소송", "소송": "소송", "sue": "소송",
    # 실적
    "earnings": "실적 발표", "실적": "실적 발표",
    "profit": "실적", "loss": "적자",
    # IPO
    "ipo": "IPO", "상장": "IPO",
    # 화재/사고
    "fire": "사고", "explosion": "사고", "화재": "사고", "폭발": "사고",
}


def _find_events(arts: list, max_per_article: int = 1) -> set[str]:
    """기사 묶음에서 발견된 이벤트 라벨 집합."""
    out: set[str] = set()
    for a in arts:
        text = ((getattr(a, "title", "") or "") + " " + (getattr(a, "summary_raw", "") or "")).lower()
        hits = 0
        for kw, label in EVENT_KEYWORDS.items():
            if kw in text:
                out.add(label)
                hits += 1
                if hits >= max_per_article:
                    break
    return out


def compute_top_of_mind(
    company_articles: dict[str, list[tuple[int, Any, Any]]],
    limit: int = 5,
) -> list[Highlight]:
    """company_articles: {company_name: [(idx, article, sentiment), ...]}.

    Article 와 Sentiment 객체의 형식은 News_radar 내부 데이터 모델 그대로 사용.
    """
    candidates: list[Highlight] = []

    # 1~3 신호: 각 회사별 검사
    for company, arr in company_articles.items():
        if len(arr) < 2:
            continue
        arts = [a for _, a, _ in arr]
        sents = [s for _, _, s in arr]
        total = len(arts)
        neg = sum(1 for s in sents if getattr(s, "label", "") == "negative")
        pos = sum(1 for s in sents if getattr(s, "label", "") == "positive")
        neg_ratio = neg / total

        # 1) 부정 집중
        if neg_ratio >= 0.5 and total >= 4:
            score = 110 + neg * 10
            candidates.append(Highlight(
                company=company,
                reason="부정 집중",
                detail=f"부정 {neg}건 · 총 {total}건",
                score=score,
                type="warning",
            ))

        # 2) 다중 매체
        sources = {getattr(a, "source", "") for a in arts if getattr(a, "source", "")}
        if len(sources) >= 4:
            score = 80 + len(sources) * 5
            candidates.append(Highlight(
                company=company,
                reason="다중 매체 보도",
                detail=f"{len(sources)}개 매체 · {total}건",
                score=score,
                type="info",
            ))

        # 3) 주요 이벤트
        events = _find_events(arts)
        if events:
            # 부정 이벤트(리콜/소송/사고/적자)는 score 더 높게
            negative_events = {"리콜", "소송", "사고", "적자"}
            has_neg_event = bool(events & negative_events)
            base = 90 if has_neg_event else 70
            score = base + len(events) * 8
            event_label = next(iter(events & negative_events), None) or next(iter(events))
            etype: HighlightType = "warning" if has_neg_event else "event"
            candidates.append(Highlight(
                company=company,
                reason=event_label,
                detail=f"{total}건 · {', '.join(sorted(events))}",
                score=score,
                type=etype,
            ))

    # 4) 고볼륨 — top 3 most mentioned
    by_volume = sorted(company_articles.items(), key=lambda x: -len(x[1]))[:3]
    for company, arr in by_volume:
        if len(arr) >= 5:
            candidates.append(Highlight(
                company=company,
                reason="이슈 집중",
                detail=f"{len(arr)}건 언급",
                score=60 + len(arr),
                type="volume",
            ))

    # 회사당 1개 (score 최대값)
    best: dict[str, Highlight] = {}
    for h in candidates:
        if h.company not in best or h.score > best[h.company].score:
            best[h.company] = h

    return sorted(best.values(), key=lambda h: -h.score)[:limit]
