"""뉴스 기사 감성 분석 및 우선순위 판별 모듈.

Ollama 없이 키워드 기반으로 동작하므로 항상 즉각 결과를 반환한다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import yaml

from news_crawler import Article

# ─────────────────────────────────────────────
# 설정 로드
# ─────────────────────────────────────────────
_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _get_keyword_lists() -> tuple[list[str], list[str]]:
    cfg = _load_config()
    report_cfg = cfg.get("report", {})
    pos = report_cfg.get("positive_keywords", [
        "출시", "신제품", "혁신", "성장", "개선", "수주", "흑자", "돌파",
        "획득", "성공", "최초", "1위", "협력", "양산",
    ])
    neg = report_cfg.get("negative_keywords", [
        "결함", "리콜", "연기", "화재", "소송", "하락", "단종", "적자",
        "감소", "실패", "취약", "문제", "논란",
    ])
    return pos, neg


def _get_urgent_keywords() -> list[str]:
    cfg = _load_config()
    return cfg.get("email", {}).get("urgent_keywords", [
        "결함", "리콜", "출시 연기", "배터리 화재", "긴급", "단종", "소송",
    ])


# ─────────────────────────────────────────────
# 데이터 클래스
# ─────────────────────────────────────────────
@dataclass
class ArticleAnalysis:
    article: Article
    sentiment: str          # "positive" | "negative" | "neutral"
    sentiment_score: float  # -1.0 ~ +1.0
    priority: str           # "urgent" | "high" | "normal"
    matched_pos: list[str] = field(default_factory=list)
    matched_neg: list[str] = field(default_factory=list)
    is_urgent: bool = False

    @property
    def sentiment_label_ko(self) -> str:
        return {"positive": "긍정", "negative": "부정", "neutral": "중립"}.get(
            self.sentiment, "중립"
        )

    @property
    def priority_label_ko(self) -> str:
        return {"urgent": "긴급", "high": "중요", "normal": "일반"}.get(
            self.priority, "일반"
        )


@dataclass
class AnalysisSummary:
    total: int
    positive_count: int
    negative_count: int
    neutral_count: int
    urgent_count: int
    top_articles: list[ArticleAnalysis]
    urgent_articles: list[ArticleAnalysis]

    @property
    def positive_ratio(self) -> float:
        return self.positive_count / self.total if self.total else 0.0

    @property
    def negative_ratio(self) -> float:
        return self.negative_count / self.total if self.total else 0.0


# ─────────────────────────────────────────────
# 핵심 분석 함수
# ─────────────────────────────────────────────
def analyze_article(article: Article) -> ArticleAnalysis:
    """단일 기사 감성 + 우선순위 분석."""
    pos_keywords, neg_keywords = _get_keyword_lists()
    urgent_keywords = _get_urgent_keywords()

    text = f"{article.title} {article.summary_raw}".lower()

    matched_pos = [kw for kw in pos_keywords if kw.lower() in text]
    matched_neg = [kw for kw in neg_keywords if kw.lower() in text]
    is_urgent = any(kw.lower() in text for kw in urgent_keywords)

    pos_score = len(matched_pos)
    neg_score = len(matched_neg)
    total = pos_score + neg_score

    if total == 0:
        raw_score = 0.0
    else:
        raw_score = (pos_score - neg_score) / total

    if raw_score > 0.1:
        sentiment = "positive"
    elif raw_score < -0.1:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    if is_urgent:
        priority = "urgent"
    elif neg_score >= 2 or pos_score >= 2:
        priority = "high"
    else:
        priority = "normal"

    return ArticleAnalysis(
        article=article,
        sentiment=sentiment,
        sentiment_score=raw_score,
        priority=priority,
        matched_pos=matched_pos,
        matched_neg=matched_neg,
        is_urgent=is_urgent,
    )


def analyze_articles(articles: Sequence[Article]) -> AnalysisSummary:
    """기사 목록 전체 분석 후 요약 반환."""
    results = [analyze_article(a) for a in articles]

    pos = [r for r in results if r.sentiment == "positive"]
    neg = [r for r in results if r.sentiment == "negative"]
    neu = [r for r in results if r.sentiment == "neutral"]
    urgent = [r for r in results if r.is_urgent]

    # 우선순위 정렬: urgent → high → normal, 같은 레벨이면 부정 우선
    priority_order = {"urgent": 0, "high": 1, "normal": 2}
    sorted_results = sorted(
        results,
        key=lambda r: (priority_order[r.priority], -abs(r.sentiment_score)),
    )

    cfg = _load_config()
    top_n = cfg.get("email", {}).get("top_articles_count", 5)

    return AnalysisSummary(
        total=len(results),
        positive_count=len(pos),
        negative_count=len(neg),
        neutral_count=len(neu),
        urgent_count=len(urgent),
        top_articles=sorted_results[:top_n],
        urgent_articles=urgent,
    )


def find_triggered_articles(articles: Sequence[Article]) -> list[Article]:
    """긴급 트리거 키워드가 포함된 기사만 반환."""
    urgent_keywords = _get_urgent_keywords()
    triggered = []
    for art in articles:
        text = f"{art.title} {art.summary_raw}".lower()
        if any(kw.lower() in text for kw in urgent_keywords):
            triggered.append(art)
    return triggered
