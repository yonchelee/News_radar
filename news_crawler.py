"""뉴스 크롤링 모듈.

Google News RSS를 사용하여 한국어 기술 뉴스를 수집하고,
선행기구개발 그룹 관심 키워드로 필터링한다.
feedparser 대신 requests + xml.etree.ElementTree 사용 (Python 3.11 호환).
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

# 선행기구개발 그룹 관심 키워드 (검색 + 필터)
SEARCH_KEYWORDS: list[str] = [
    "모바일 힌지",
    "폴더블 힌지",
    "EV 배터리 케이스",
    "전기차 배터리 팩",
    "전기차 부품",
    "신소재 부품",
    "마그네슘 합금 부품",
    "탄소복합소재 부품",
    "갤럭시 폴드 힌지",
    "스마트폰 방열",
]

# 필터링 시 본문/제목에 포함되어야 하는 단어 (느슨한 OR 매칭)
FILTER_TOKENS: list[str] = [
    "모바일", "스마트폰", "폴더블", "힌지",
    "전기차", "EV", "배터리", "배터리팩", "셀", "팩",
    "부품", "소재", "신소재", "합금", "복합소재", "방열",
    "케이스", "기구", "사출", "다이캐스팅", "프레스",
]

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"


@dataclass
class Article:
    title: str
    link: str
    source: str
    published: str
    summary_raw: str = ""
    matched_keyword: str = ""
    content: str = field(default="", repr=False)

    @property
    def published_dt(self) -> datetime:
        try:
            return datetime.strptime(self.published, "%a, %d %b %Y %H:%M:%S %Z")
        except Exception:
            return datetime.now(tz=timezone.utc)


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


def _parse_rss(xml_text: str, keyword: str, max_items: int) -> list[Article]:
    """RSS XML 텍스트를 파싱하여 Article 리스트 반환."""
    articles: list[Article] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return articles

    ns = {"media": "http://search.yahoo.com/mrss/"}
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

        # 출처: <source> 태그 또는 제목 마지막 " - 출처명"
        source_tag = item.find("source")
        source = ""
        if source_tag is not None:
            source = (source_tag.text or "").strip()
        if not source and " - " in title:
            source = title.rsplit(" - ", 1)[-1]

        full_text = f"{title} {summary_raw}"
        if not _matches_filter(full_text):
            continue

        articles.append(
            Article(
                title=title,
                link=link,
                source=source,
                published=published,
                summary_raw=summary_raw,
                matched_keyword=keyword,
            )
        )
    return articles


def fetch_articles(
    keywords: Iterable[str] | None = None,
    max_per_keyword: int = 8,
) -> list[Article]:
    """키워드별로 Google News RSS를 조회하여 Article 리스트를 반환."""
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
    """기사 원문 페이지에서 본문 텍스트를 추출 (best-effort).

    Google News는 redirect를 사용하므로 requests가 final URL을 따라간다.
    완벽한 본문 추출은 어려우므로 <p> 태그 결합 방식으로 근사한다.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
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
    return body or "[본문이 비어 있습니다. 사이트 구조 차이로 추출에 실패했을 수 있습니다.]"


# 캐시: (timestamp, articles)
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
