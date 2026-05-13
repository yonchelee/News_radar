"""뉴스 크롤링 모듈.

회사별(삼성/애플/기타) 키워드로 Google News RSS를 수집하고,
루머 여부와 회사를 자동 태깅한다.
"""
from __future__ import annotations

import html
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

import requests
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# 회사별 프로파일
# ─────────────────────────────────────────────
COMPANY_PROFILES: dict[str, dict] = {
    "삼성": {
        "search_keywords": [
            "삼성 갤럭시 신제품",
            "삼성전자 스마트폰",
            "갤럭시 Z 폴드",
            "갤럭시 S 시리즈",
            "삼성 모바일 루머",
            "갤럭시 폴드 힌지",
        ],
        "match_tokens": ["삼성", "samsung", "갤럭시", "galaxy"],
        "color": "#1F6FEB",
        "emoji": "🔵",
    },
    "애플": {
        "search_keywords": [
            "아이폰 신제품",
            "Apple iPhone 루머",
            "아이폰 출시 예정",
            "아이패드 신제품",
            "애플 iOS 업데이트",
            "맥북 신제품",
        ],
        "match_tokens": ["애플", "apple", "아이폰", "iphone", "아이패드", "ipad", "맥북", "macbook"],
        "color": "#94A3B8",
        "emoji": "🍎",
    },
}

# 루머/전망 감지 키워드
RUMOR_TOKENS: list[str] = [
    "루머", "유출", "예상", "전망", "출시 예정", "소문",
    "leak", "rumor", "확인되지", "알려진", "예측",
    "렌더링", "알려졌", "전해졌", "계획 중", "소식통",
    "업계 관계자", "예고", "관측", "예정", "기대",
]

# 수집할 모든 키워드 (회사별 자동 생성)
SEARCH_KEYWORDS: list[str] = [
    kw
    for profile in COMPANY_PROFILES.values()
    for kw in profile["search_keywords"]
]

# 필터 통과 토큰 (회사명 + 제품명 포함)
FILTER_TOKENS: list[str] = [
    "삼성", "samsung", "갤럭시", "galaxy",
    "애플", "apple", "아이폰", "iphone", "아이패드", "ipad", "맥북",
    "모바일", "스마트폰", "폴더블", "힌지",
    "배터리", "방열", "부품", "소재", "신소재",
]

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"


# ─────────────────────────────────────────────
# 데이터 클래스
# ─────────────────────────────────────────────
@dataclass
class Article:
    title: str
    link: str
    source: str
    published: str
    summary_raw: str = ""
    matched_keyword: str = ""
    company: str = "기타"      # "삼성" | "애플" | "기타"
    is_rumor: bool = False
    content: str = field(default="", repr=False)

    @property
    def published_dt(self) -> datetime:
        try:
            return datetime.strptime(self.published, "%a, %d %b %Y %H:%M:%S %Z")
        except Exception:
            return datetime.now(tz=timezone.utc)

    @property
    def published_ago(self) -> str:
        try:
            dt = self.published_dt.replace(tzinfo=None)
            diff = datetime.now() - dt
            h = int(diff.total_seconds() // 3600)
            if h < 1:
                return f"{int(diff.total_seconds() // 60)}분 전"
            if h < 24:
                return f"{h}시간 전"
            return f"{h // 24}일 전"
        except Exception:
            return self.published[:10] if self.published else ""


# ─────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────
def _clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _matches_filter(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(tok.lower() in lowered for tok in FILTER_TOKENS)


def _detect_company(text: str) -> str:
    lowered = text.lower()
    for company, profile in COMPANY_PROFILES.items():
        if any(tok.lower() in lowered for tok in profile["match_tokens"]):
            return company
    return "기타"


def _detect_rumor(text: str) -> bool:
    lowered = text.lower()
    return any(tok.lower() in lowered for tok in RUMOR_TOKENS)


# ─────────────────────────────────────────────
# RSS 파싱
# ─────────────────────────────────────────────
def _parse_rss(xml_text: str, keyword: str, max_items: int) -> list[Article]:
    articles: list[Article] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return articles

    channel = root.find("channel")
    if channel is None:
        return articles

    for item in list(channel.findall("item"))[:max_items]:
        link = (item.findtext("link") or "").strip()
        title = _clean_text(item.findtext("title") or "")
        if not link or not title:
            continue

        summary_raw = _clean_text(item.findtext("description") or "")
        published = (item.findtext("pubDate") or "").strip()

        source_tag = item.find("source")
        source = ""
        if source_tag is not None:
            source = (source_tag.text or "").strip()
        if not source and " - " in title:
            source = title.rsplit(" - ", 1)[-1]

        full_text = f"{title} {summary_raw}"
        if not _matches_filter(full_text):
            continue

        company = _detect_company(full_text)
        is_rumor = _detect_rumor(full_text)

        articles.append(
            Article(
                title=title,
                link=link,
                source=source,
                published=published,
                summary_raw=summary_raw,
                matched_keyword=keyword,
                company=company,
                is_rumor=is_rumor,
            )
        )
    return articles


# ─────────────────────────────────────────────
# 수집 함수
# ─────────────────────────────────────────────
def fetch_articles(
    keywords: Iterable[str] | None = None,
    max_per_keyword: int = 8,
) -> list[Article]:
    keywords = list(keywords) if keywords else SEARCH_KEYWORDS
    seen: set[str] = set()
    articles: list[Article] = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    for kw in keywords:
        url = GOOGLE_NEWS_RSS.format(query=urllib.parse.quote(kw))
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
        except Exception:
            continue

        for art in _parse_rss(resp.text, kw, max_per_keyword):
            if art.link not in seen:
                seen.add(art.link)
                articles.append(art)

    articles.sort(key=lambda a: a.published_dt, reverse=True)
    return articles


def fetch_article_body(url: str, timeout: int = 8) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
    except Exception as exc:
        return f"[본문 수집 실패: {exc}]"

    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
        tag.decompose()
    article_tag = soup.find("article") or soup.find(id=re.compile("article|content", re.I))
    target = article_tag if article_tag else soup
    paragraphs = [p.get_text(" ", strip=True) for p in target.find_all("p")]
    paragraphs = [p for p in paragraphs if len(p) > 30]
    body = "\n".join(paragraphs[:40])
    return body or "[본문이 비어 있습니다.]"


# ─────────────────────────────────────────────
# 캐시
# ─────────────────────────────────────────────
_CACHE: dict[str, tuple[float, list[Article]]] = {}
_CACHE_TTL_SEC = 60 * 60  # 1시간


def get_cached_articles(force_refresh: bool = False) -> list[Article]:
    now = time.time()
    cached = _CACHE.get("articles")
    if not force_refresh and cached and (now - cached[0]) < _CACHE_TTL_SEC:
        return cached[1]
    articles = fetch_articles()
    _CACHE["articles"] = (now, articles)
    return articles


def cache_age_seconds() -> float | None:
    cached = _CACHE.get("articles")
    if not cached:
        return None
    return time.time() - cached[0]
