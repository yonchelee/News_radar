"""뉴스 기사 sentiment 분류 — 키워드 기반 (한국어 + 영어 + 중국어).

빠르고 외부 호출 없음. 점수: -1.0 (강한 부정) ~ +1.0 (강한 긍정).
경계(-0.2 ~ +0.2)는 중립으로 분류.

옵션: classify_with_llm(articles, api_key) — 경계 점수만 LLM 보강 (배치, 비용 최소화).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal


Sentiment = Literal["positive", "negative", "neutral"]


# ---------------------------------------------------------------------------
# 키워드 사전 — 다국어 (한국어 / 영어 / 중국어)
# ---------------------------------------------------------------------------
POSITIVE_TOKENS: set[str] = {
    # 한국어
    "출시", "성공", "신기록", "호평", "증가", "성장", "흑자", "도약", "혁신",
    "호황", "채택", "수주", "1위", "최고", "최초", "돌파", "확대", "강세",
    "수익", "이익", "호조", "기록", "혁신적", "선보여", "공개", "달성",
    "유치", "투자", "수상", "선정", "선도", "리더십",
    # 영어
    "launch", "launches", "launched", "success", "successful",
    "record", "gain", "gains", "rise", "rises", "rising",
    "growth", "grow", "growing", "profit", "profits", "profitable",
    "innovation", "innovative", "breakthrough", "milestone",
    "leader", "leading", "wins", "won", "winning", "best",
    "improve", "improved", "improvement", "boost", "boosted",
    "upgrade", "upgraded", "expand", "expanded",
    # 중국어 (간체+번체)
    "推出", "成功", "创纪录", "增长", "上涨", "突破", "利润", "创新",
    "领先", "领导", "扩大", "改进", "提升", "升级", "突破",
    "推出", "成功", "創紀錄", "增長", "上漲", "創新", "領先",
}

NEGATIVE_TOKENS: set[str] = {
    # 한국어
    "실패", "하락", "충돌", "리콜", "사고", "손실", "문제", "결함",
    "지연", "위기", "폭락", "적자", "소송", "부진", "우려", "감소",
    "약세", "철수", "단종", "취소", "철회", "타격", "악재", "급락",
    "추락", "정체", "둔화", "위협", "비판", "지적", "사망",
    "화재", "폭발", "리스크", "위험",
    # 영어
    "fail", "failure", "failed", "drop", "drops", "drop", "crash",
    "recall", "recalls", "recalled", "decline", "declined", "declining",
    "lose", "loses", "lost", "loss", "issue", "issues", "problem",
    "defect", "defects", "defective", "delay", "delays", "delayed",
    "crisis", "down", "lawsuit", "sue", "sued", "concerns", "concern",
    "risk", "risks", "warning", "weak", "weakness", "criticism",
    "criticize", "fire", "explosion", "casualty", "die", "death",
    # 중국어 (간체+번체)
    "失败", "下跌", "召回", "缺陷", "损失", "问题", "延迟", "危机",
    "诉讼", "下滑", "担忧", "风险", "起诉", "事故", "火灾", "爆炸",
    "失敗", "下跌", "召回", "缺陷", "損失", "問題", "延遲", "危機",
    "下滑", "擔憂", "風險", "起訴", "事故", "火災", "爆炸",
}


# ---------------------------------------------------------------------------
# 분류
# ---------------------------------------------------------------------------
@dataclass
class SentimentResult:
    label: Sentiment
    score: float          # -1.0 ~ +1.0
    pos_hits: list[str]   # 매칭된 긍정 키워드
    neg_hits: list[str]   # 매칭된 부정 키워드

    @property
    def emoji(self) -> str:
        return {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}[self.label]

    @property
    def label_ko(self) -> str:
        return {"positive": "긍정", "negative": "부정", "neutral": "중립"}[self.label]


def _normalize(text: str) -> str:
    return (text or "").lower()


def _count_hits(text: str, vocab: set[str]) -> list[str]:
    """단어 매칭 (한자/한글은 substring, 영어는 word boundary)."""
    if not text:
        return []
    hits: list[str] = []
    text_norm = _normalize(text)
    for tok in vocab:
        # 영어: word boundary, 그 외: substring (CJK 단어 boundary 없음)
        if re.match(r"^[a-z]+$", tok):
            if re.search(r"\b" + re.escape(tok) + r"\b", text_norm):
                hits.append(tok)
        else:
            if tok in text:   # 한자/한글은 대소문자 무관
                hits.append(tok)
    return hits


def classify(title: str, summary: str = "", neutral_threshold: float = 0.2) -> SentimentResult:
    """제목 + 요약에서 키워드 카운트로 분류.

    스코어 = (pos - neg) / max(pos + neg, 1).
    절댓값이 neutral_threshold 미만이면 중립.
    제목 가중치 1.5배 (제목이 본문보다 톤 결정에 강함).
    """
    text_combined = (title or "") + " " + (summary or "")
    title_pos = _count_hits(title or "", POSITIVE_TOKENS)
    title_neg = _count_hits(title or "", NEGATIVE_TOKENS)
    sum_pos = _count_hits(summary or "", POSITIVE_TOKENS)
    sum_neg = _count_hits(summary or "", NEGATIVE_TOKENS)

    pos_count = 1.5 * len(title_pos) + len(sum_pos)
    neg_count = 1.5 * len(title_neg) + len(sum_neg)

    if pos_count + neg_count == 0:
        return SentimentResult("neutral", 0.0, [], [])

    score = (pos_count - neg_count) / (pos_count + neg_count)
    # tanh로 부드럽게 클램프 (실제론 이미 -1~+1)
    score = math.tanh(score * 1.5)

    label: Sentiment
    if score >= neutral_threshold:
        label = "positive"
    elif score <= -neutral_threshold:
        label = "negative"
    else:
        label = "neutral"

    pos_hits = list(set(title_pos + sum_pos))
    neg_hits = list(set(title_neg + sum_neg))
    return SentimentResult(label, round(score, 3), pos_hits, neg_hits)


# ---------------------------------------------------------------------------
# 통계
# ---------------------------------------------------------------------------
def stats(results: list[SentimentResult]) -> dict:
    """긍정/부정/중립 개수 + 평균 score."""
    pos = sum(1 for r in results if r.label == "positive")
    neg = sum(1 for r in results if r.label == "negative")
    neu = sum(1 for r in results if r.label == "neutral")
    total = len(results)
    avg = sum(r.score for r in results) / total if total else 0.0
    return {"positive": pos, "negative": neg, "neutral": neu, "total": total, "avg_score": round(avg, 3)}



# ---------------------------------------------------------------------------
# LLM 보강 분류 (선택) — 회색지대만 batch 호출
# ---------------------------------------------------------------------------
def classify_with_llm(
    articles: list,
    base_results: list[SentimentResult],
    llm_chat_fn,
    threshold: float = 0.2,
    batch_size: int = 10,
) -> list[SentimentResult]:
    """키워드 점수 |score| < threshold 만 LLM에 batch 분류 위탁.

    llm_chat_fn(messages) -> str (OpenAI 호환 응답 문자열). 실패 시 base_results 그대로.
    Groq/Gemini/Ollama 어떤 백엔드든 messages 인자로 호출 가능한 함수면 됨.
    """
    borderline_idxs = [i for i, r in enumerate(base_results) if abs(r.score) < threshold]
    if not borderline_idxs:
        return base_results

    out = list(base_results)
    for start in range(0, len(borderline_idxs), batch_size):
        chunk = borderline_idxs[start:start + batch_size]
        items = []
        for j, idx in enumerate(chunk):
            a = articles[idx]
            title = getattr(a, "title", "")
            summary = getattr(a, "summary_raw", "") or ""
            items.append(f"[{j+1}] {title[:140]}\n    {summary[:200]}")
        prompt = (
            "다음 뉴스 기사 각각을 sentiment 분류하라. "
            "응답은 정확히 다음 형식의 한 줄씩, 추가 텍스트 없이:\n"
            "[1] positive\n[2] negative\n[3] neutral\n...\n\n"
            "기준: positive (호재/성장/긍정 톤), negative (악재/리스크/하락 톤), neutral (사실 전달/모호).\n\n"
            "기사:\n" + "\n\n".join(items)
        )
        try:
            resp = llm_chat_fn([
                {"role": "system", "content": "You are a sentiment classifier. Reply only with the requested format."},
                {"role": "user", "content": prompt},
            ])
        except Exception:
            continue
        # 파싱
        for line in resp.splitlines():
            m = re.match(r"\s*\[(\d+)\]\s*(positive|negative|neutral)", line.strip(), re.I)
            if not m:
                continue
            j = int(m.group(1)) - 1
            label = m.group(2).lower()
            if 0 <= j < len(chunk):
                idx = chunk[j]
                # Score는 ±0.5 정도로 보정 (LLM 결과 신뢰)
                score = {"positive": 0.5, "negative": -0.5, "neutral": 0.0}[label]
                out[idx] = SentimentResult(label, score,
                                            out[idx].pos_hits, out[idx].neg_hits)
    return out
