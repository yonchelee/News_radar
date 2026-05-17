"""뉴스 크롤링 — 다중 RSS 소스 통합.

Source registry 기반. 카테고리별 그룹 + 병렬 fetch + 실패 silent skip.

소스 추가 방법:
    SOURCES["my_source"] = Source(
        name="My Source", url="https://...", category="mobile", language="ko"
    )
"""
from __future__ import annotations

import concurrent.futures
import html
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

import feedparser
import requests
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# 키워드 (Google News 키워드 검색용 + 필터링용)
# ---------------------------------------------------------------------------
SEARCH_KEYWORDS: list[str] = [
    "모바일 힌지", "폴더블 힌지", "EV 배터리 케이스", "전기차 배터리 팩",
    "전기차 부품", "신소재 부품", "마그네슘 합금 부품", "탄소복합소재 부품",
    "갤럭시 폴드 힌지", "스마트폰 방열",
]
FILTER_TOKENS: list[str] = [
    "모바일", "스마트폰", "폴더블", "힌지",
    "전기차", "EV", "배터리", "배터리팩", "셀", "팩",
    "부품", "소재", "신소재", "합금", "복합소재", "방열",
    "케이스", "기구", "사출", "다이캐스팅", "프레스",
    # 영문 토큰 (영문 소스 필터링용)
    "mobile", "smartphone", "foldable", "hinge", "iphone", "galaxy", "pixel",
    "ev", "battery", "tesla", "byd", "lithium", "solid-state",
    "material", "alloy", "magnesium", "composite", "carbon fiber",
    "thermal", "cooling", "die-casting", "injection",
]


# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------
@dataclass
class Source:
    key: str
    name: str
    url: str
    category: str      # "global" | "mobile" | "ev" | "community" | "kr-it" | "kr-component" | "kw"
    language: str      # "en" | "ko"
    apply_filter: bool = False   # FILTER_TOKENS 적용 여부 (잡음 많은 일반 소스만 True)


SOURCES: dict[str, Source] = {
    # --- 키워드 기반 검색 (Google News) ---
    "google":      Source("google", "Google News (키워드)", "", "kw", "ko"),

    # --- Geeknews (특수: 큐레이션) ---
    "geeknews":    Source("geeknews", "Geeknews", "https://feeds.feedburner.com/geeknews-feed", "kr-it", "ko"),

    # --- 글로벌 테크 일반 ---
    "hackernews":  Source("hackernews", "Hacker News", "https://news.ycombinator.com/rss", "global", "en", True),
    "theverge":    Source("theverge", "The Verge", "https://www.theverge.com/rss/index.xml", "global", "en", True),
    "engadget":    Source("engadget", "Engadget", "https://www.engadget.com/rss.xml", "global", "en", True),
    "techcrunch":  Source("techcrunch", "TechCrunch", "https://techcrunch.com/feed/", "global", "en", True),
    "arstechnica": Source("arstechnica", "Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "global", "en", True),
    "macrumors":   Source("macrumors", "MacRumors", "https://feeds.macrumors.com/MacRumors-All", "global", "en", True),

    # --- 모바일 / 스마트폰 ---
    "gsmarena":    Source("gsmarena", "GSMArena", "https://www.gsmarena.com/rss-news-reviews.php3", "mobile", "en"),
    "9to5google":  Source("9to5google", "9to5Google", "https://9to5google.com/feed/", "mobile", "en"),
    "9to5mac":     Source("9to5mac", "9to5Mac", "https://9to5mac.com/feed/", "mobile", "en"),
    "androidauth": Source("androidauth", "Android Authority", "https://www.androidauthority.com/feed/", "mobile", "en"),
    "xda":         Source("xda", "XDA Developers", "https://www.xda-developers.com/feed/", "mobile", "en"),

    # --- EV / 배터리 ---
    "electrek":    Source("electrek", "Electrek", "https://electrek.co/feed/", "ev", "en"),
    "insideevs":   Source("insideevs", "InsideEVs", "https://insideevs.com/rss/articles/all/", "ev", "en"),
    "cleantech":   Source("cleantech", "CleanTechnica", "https://cleantechnica.com/feed/", "ev", "en", True),
    "evannex":     Source("evannex", "EVannex", "https://evannex.com/blogs/news.atom", "ev", "en"),

    # --- 커뮤니티 ---
    "r_android":   Source("r_android", "r/Android", "https://www.reddit.com/r/Android/.rss", "community", "en"),
    "r_ev":        Source("r_ev", "r/electric_vehicles", "https://www.reddit.com/r/electric_vehicles/.rss", "community", "en"),
    "r_gadgets":   Source("r_gadgets", "r/gadgets", "https://www.reddit.com/r/gadgets/.rss", "community", "en", True),

    # --- 국내 IT ---
    "zdnetkr":     Source("zdnetkr", "ZDNet Korea", "https://feeds.feedburner.com/zdkorea", "kr-it", "ko", True),
    "ddaily":      Source("ddaily", "디지털데일리", "https://feeds.feedburner.com/ddaily", "kr-it", "ko", True),
    "venturesquare": Source("venturesquare", "벤처스퀘어", "https://www.venturesquare.net/feed", "kr-it", "ko", True),

    # --- 국내 부품/소재/산업 ---
    "thelec":      Source("thelec", "The Elec (전자부품)", "https://www.thelec.kr/rss/allArticle.xml", "kr-component", "ko"),
    "irobotnews":  Source("irobotnews", "로봇신문", "https://www.irobotnews.com/rss/allArticle.xml", "kr-component", "ko", True),
    "epnc":        Source("epnc", "전자부품뉴스", "https://www.epnc.co.kr/rss/allArticle.xml", "kr-component", "ko"),

    # --- 중화권 IT (한자, Gemma가 한국어로 번역 요약) ---
    "ithome_cn":   Source("ithome_cn", "IT之家", "https://www.ithome.com/rss/", "cn", "zh"),
    "cnbeta":      Source("cnbeta", "CnBeta", "https://www.cnbeta.com.tw/backend.php", "cn", "zh"),
    "36kr":        Source("36kr", "36Kr", "https://www.36kr.com/feed", "cn", "zh"),
    "sspai":       Source("sspai", "少数派 (sspai)", "https://sspai.com/feed", "cn", "zh"),
    "geekpark":    Source("geekpark", "GeekPark", "https://www.geekpark.net/rss", "cn", "zh"),

    # --- US 메이저 미디어 (비즈니스/테크 핵심, apply_filter=False) ---
    "bloomberg_tech":     Source("bloomberg_tech", "Bloomberg Technology", "https://feeds.bloomberg.com/technology/news.rss", "us-major", "en"),
    "bloomberg_business": Source("bloomberg_business", "Bloomberg Business", "https://feeds.bloomberg.com/business/news.rss", "us-major", "en"),
    "bloomberg_markets":  Source("bloomberg_markets", "Bloomberg Markets", "https://feeds.bloomberg.com/markets/news.rss", "us-major", "en"),
    "wsj_tech":           Source("wsj_tech", "WSJ Tech", "https://feeds.a.dj.com/rss/RSSWSJD.xml", "us-major", "en"),
    "wsj_world":          Source("wsj_world", "WSJ World", "https://feeds.a.dj.com/rss/RSSWorldNews.xml", "us-major", "en"),
    "bbc_business":       Source("bbc_business", "BBC Business", "http://feeds.bbci.co.uk/news/business/rss.xml", "us-major", "en"),
    "bbc_tech":           Source("bbc_tech", "BBC Technology", "http://feeds.bbci.co.uk/news/technology/rss.xml", "us-major", "en"),
    "cnn_business":       Source("cnn_business", "CNN Business", "http://rss.cnn.com/rss/money_news_international.rss", "us-major", "en"),
    "cnbc_tech":          Source("cnbc_tech", "CNBC Tech", "https://www.cnbc.com/id/19854910/device/rss/rss.html", "us-major", "en"),
    "cnbc_business":      Source("cnbc_business", "CNBC Business", "https://www.cnbc.com/id/10001147/device/rss/rss.html", "us-major", "en"),
    "nyt_tech":           Source("nyt_tech", "NYT Technology", "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "us-major", "en"),
    "nyt_business":       Source("nyt_business", "NYT Business", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "us-major", "en"),
    "ft_tech":            Source("ft_tech", "Financial Times Tech", "https://www.ft.com/technology?format=rss", "us-major", "en"),
    "forbes_innov":       Source("forbes_innov", "Forbes Innovation", "https://www.forbes.com/innovation/feed/", "us-major", "en", True),
    "mit_tech":           Source("mit_tech", "MIT Technology Review", "https://www.technologyreview.com/feed/", "us-major", "en"),
    "wired":              Source("wired", "Wired", "https://www.wired.com/feed/rss", "us-major", "en", True),
    "wapo_tech":          Source("wapo_tech", "Washington Post Tech", "https://feeds.washingtonpost.com/rss/business/technology", "us-major", "en"),
}

CATEGORY_LABELS = {
    "kw":           "키워드 검색",
    "global":       "글로벌 테크",
    "mobile":       "모바일",
    "ev":           "EV·배터리",
    "community":    "커뮤니티",
    "kr-it":        "국내 IT",
    "kr-component": "부품·소재",
    "cn":           "중화권 IT",
    "us-major":     "메이저 미디어",
}

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
DEFAULT_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


# ---------------------------------------------------------------------------
# Article
# ---------------------------------------------------------------------------
@dataclass
class Article:
    title: str
    link: str
    source: str
    published: str
    summary_raw: str = ""
    matched_keyword: str = ""
    content: str = field(default="", repr=False)
    source_category: str = ""

    @property
    def published_dt(self) -> datetime:
        """파싱된 datetime을 항상 timezone-aware UTC로 반환 (정렬 호환)."""
        for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z",
                    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                dt = datetime.strptime(self.published, fmt)
                # naive → UTC aware로 보정
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                continue
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


# ---------------------------------------------------------------------------
# Source fetchers
# ---------------------------------------------------------------------------
# Per-source hard timeout (slow source가 전체 fetch를 막지 않도록)
FETCH_TIMEOUT_SEC = 8


def _fetch_rss_generic(src: Source, max_entries: int = 30) -> list[Article]:
    """일반 RSS 소스 fetcher — 8초 hard timeout."""
    try:
        # feedparser.parse는 직접 timeout 미지원 → requests로 본문 받고 파싱
        resp = requests.get(
            src.url, timeout=FETCH_TIMEOUT_SEC,
            headers={"User-Agent": DEFAULT_AGENT},
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return []
        feed = feedparser.parse(resp.content)
    except Exception:
        return []
    out: list[Article] = []
    seen: set[str] = set()
    for entry in feed.entries[:max_entries]:
        link = getattr(entry, "link", "")
        title = _clean_text(getattr(entry, "title", ""))
        if not link or not title or link in seen:
            continue
        summary_raw = _clean_text(getattr(entry, "summary", ""))
        full_text = f"{title} {summary_raw}"
        if src.apply_filter and not _matches_filter(full_text):
            continue
        # 매칭 키워드 추정
        matched = src.name
        for tok in FILTER_TOKENS:
            if tok.lower() in full_text.lower():
                matched = tok
                break
        seen.add(link)
        out.append(Article(
            title=title, link=link,
            source=src.name,
            published=getattr(entry, "published", "") or getattr(entry, "updated", ""),
            summary_raw=summary_raw,
            matched_keyword=matched,
            source_category=src.category,
        ))
    return out


def _fetch_google_news(max_per_keyword: int = 5) -> list[Article]:
    """Google News RSS — 키워드 검색."""
    seen: set[str] = set()
    out: list[Article] = []
    for kw in SEARCH_KEYWORDS:
        url = GOOGLE_NEWS_RSS.format(query=urllib.parse.quote(kw))
        try:
            resp = requests.get(
                url, timeout=FETCH_TIMEOUT_SEC,
                headers={"User-Agent": DEFAULT_AGENT},
            )
            if resp.status_code != 200:
                continue
            feed = feedparser.parse(resp.content)
        except Exception:
            continue
        for entry in feed.entries[:max_per_keyword]:
            link = getattr(entry, "link", "")
            title = _clean_text(getattr(entry, "title", ""))
            if not link or not title or link in seen:
                continue
            summary_raw = _clean_text(getattr(entry, "summary", ""))
            source = ""
            if getattr(entry, "source", None):
                source = getattr(entry.source, "title", "") or ""
            if not source and " - " in title:
                source = title.rsplit(" - ", 1)[-1]
            if not _matches_filter(f"{title} {summary_raw}"):
                continue
            seen.add(link)
            out.append(Article(
                title=title, link=link,
                source=f"Google News · {source}" if source else "Google News",
                published=getattr(entry, "published", ""),
                summary_raw=summary_raw, matched_keyword=kw,
                source_category="kw",
            ))
    return out


def fetch_source(source_key: str) -> list[Article]:
    """소스 키 하나에 대해 fetch."""
    if source_key == "google":
        return _fetch_google_news()
    src = SOURCES.get(source_key)
    if not src or not src.url:
        return []
    return _fetch_rss_generic(src)


# ---------------------------------------------------------------------------
# Aggregator + 캐시
# ---------------------------------------------------------------------------
_CACHE: dict[str, tuple[float, list[Article]]] = {}
_CACHE_TTL_SEC = 60 * 60  # 1시간


def get_cached_articles(
    force_refresh: bool = False,
    sources: list[str] | None = None,
    max_parallel: int = 16,
) -> list[Article]:
    """다중 소스 병렬 fetch + 통합 캐시."""
    sources = sources or list(SOURCES.keys())
    cache_key = ",".join(sorted(sources))
    now = time.time()
    cached = _CACHE.get(cache_key)
    if not force_refresh and cached and (now - cached[0]) < _CACHE_TTL_SEC:
        return cached[1]

    combined: list[Article] = []
    seen_links: set[str] = set()

    # 병렬 fetch (실패 silent skip)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel) as ex:
        future_to_key = {ex.submit(fetch_source, k): k for k in sources}
        for fut in concurrent.futures.as_completed(future_to_key, timeout=60):
            try:
                arts = fut.result()
            except Exception:
                continue
            for a in arts:
                if a.link in seen_links:
                    continue
                seen_links.add(a.link)
                combined.append(a)

    combined.sort(key=lambda a: a.published_dt, reverse=True)
    _CACHE[cache_key] = (now, combined)
    return combined


def cache_age_seconds(sources: list[str] | None = None) -> float | None:
    sources = sources or list(SOURCES.keys())
    cache_key = ",".join(sorted(sources))
    cached = _CACHE.get(cache_key)
    return time.time() - cached[0] if cached else None


# ---------------------------------------------------------------------------
# 기사 본문 추출 (변경 없음)
# ---------------------------------------------------------------------------
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


# 하위 호환
def fetch_articles(*args, **kwargs):
    """이전 시그니처 호환 wrapper."""
    return _fetch_google_news()


def fetch_geeknews(*args, **kwargs):
    return _fetch_rss_generic(SOURCES["geeknews"])
