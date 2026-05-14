"""기사 대분류 (multi-label) — 모바일 / AI / 로봇.

키워드 기반, 다국어. 한 기사가 여러 토픽에 속할 수 있음 (예: 'Tesla Optimus humanoid AI' → robot + ai).
"""
from __future__ import annotations

import re


TOPIC_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "mobile": {
        "ko": ["스마트폰", "휴대폰", "폴더블", "갤럭시", "아이폰", "픽셀",
               "힌지", "디스플레이", "안드로이드", "iOS", "단말", "Z 폴드",
               "Z 플립", "노트북", "태블릿", "워치"],
        "en": ["smartphone", "smartphones", "phone", "mobile", "foldable",
               "iphone", "galaxy", "pixel", "hinge", "android",
               "5G", "6G", "AMOLED", "OLED", "USB-C", "iOS"],
        "zh": ["手机", "智能手机", "折叠屏", "iPhone", "安卓", "鸿蒙", "屏幕"],
    },
    "ai": {
        "ko": ["AI", "인공지능", "LLM", "생성형", "거대언어모델", "GPT",
               "제미니", "Claude", "Gemini", "ChatGPT", "딥러닝", "머신러닝",
               "신경망", "트랜스포머", "에이전트", "코파일럿", "Copilot",
               "추론", "RAG", "GenAI", "오픈AI", "엔비디아", "GPU"],
        "en": ["AI", "artificial intelligence", "LLM", "generative",
               "ChatGPT", "GPT-", "Gemini", "Claude", "Llama",
               "machine learning", "neural network", "deep learning",
               "transformer", "agent", "copilot", "OpenAI", "Anthropic",
               "DeepSeek", "Grok", "inference", "Stable Diffusion"],
        "zh": ["人工智能", "AI", "生成式", "大模型", "深度学习", "神经网络",
               "智能体", "通义", "文心", "Kimi"],
    },
    "robot": {
        "ko": ["로봇", "로보틱스", "휴머노이드", "협동로봇", "코봇",
               "AGV", "AMR", "자율주행로봇", "산업용 로봇", "보스턴 다이내믹스",
               "옵티머스", "테슬라 봇", "Optimus", "Atlas"],
        "en": ["robot", "robots", "robotics", "humanoid", "humanoids",
               "automation", "AGV", "AMR", "cobot",
               "Boston Dynamics", "Optimus", "Tesla Bot", "Atlas",
               "Figure AI", "Agility Robotics", "Unitree"],
        "zh": ["机器人", "人形机器人", "协作机器人", "工业机器人",
               "宇树", "波士顿动力"],
    },
}

TOPIC_LABELS: dict[str, str] = {
    "mobile": "모바일",
    "ai":     "AI",
    "robot":  "로봇",
}


# 컴파일된 패턴 캐시
_PATTERNS: dict[str, list[re.Pattern]] = {}


def _patterns_for(topic: str) -> list[re.Pattern]:
    if topic in _PATTERNS:
        return _PATTERNS[topic]
    pats: list[re.Pattern] = []
    for lang, words in TOPIC_KEYWORDS[topic].items():
        for w in words:
            w = w.strip()
            if not w:
                continue
            # 영문/숫자 시작이면 word boundary, 그 외 (CJK/한글) substring
            if re.match(r"^[A-Za-z0-9]", w):
                pats.append(re.compile(r"\b" + re.escape(w) + r"\b", re.IGNORECASE))
            else:
                pats.append(re.compile(re.escape(w)))
    _PATTERNS[topic] = pats
    return pats


def classify_topic(title: str, summary: str = "") -> set[str]:
    """기사가 속한 토픽 (multi-label). title + summary 검사.

    매치 0건이면 빈 set 반환 (none 토픽).
    """
    text = ((title or "") + " " + (summary or ""))
    if not text.strip():
        return set()
    matched: set[str] = set()
    for topic in TOPIC_KEYWORDS:
        for pat in _patterns_for(topic):
            if pat.search(text):
                matched.add(topic)
                break
    return matched
