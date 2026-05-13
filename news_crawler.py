"""뉴스 크롤링 모듈.

삼성/애플 전문 사이트 RSS를 직접 수집한다.
Google News RSS 불필요 — API 키 없이 동작.
RSS 2.0 / Atom 두 포맷 모두 지원.
"""
from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import NamedTuple

import requests
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# RSS 소스 정의
# ─────────────────────────────────────────────
class RssSource(NamedTuple):
    name: str
    url: str
    company: str        # "삼성" | "애플" | "기타" — None 이면 내용으로 자동 판별
    rumor_site: bool    # 사이트 자체가 루머/유출 전문이면 True
    max_items: int = 15

RSS_SOURCES: list[RssSource] = [
    # ── 애플 전문 ──────────────────────────────
    RssSource("MacRumors",   "https://feeds.macrumors.com/MacRumors-All",         "애플", True,  20),
    RssSource("9to5Mac",     "https://9to5mac.com/feed/",                          "애플", False, 15),
    # ── 삼성 전문 ──────────────────────────────
    RssSource("SamMobile",   "https://www.sammobile.com/feed/",                   "삼성", True,  20),
    RssSource("9to5Google",  "https://9to5google.com/feed/",                      "삼성", False, 15),
    # ── 모바일 전반 ────────────────────────────
    RssSource("GSMArena",    "https://www.gsmarena.com/rss-news-reviews.php3",    "기타", False, 20),
    RssSource("The Verge",   "https://www.theverge.com/rss/index.xml",            "기타", False, 15),
    RssSource("TechCrunch",  "https://techcrunch.com/category/mobile/feed/",      "기타", False, 10),
]

# 회사 감지 토큰 (기타 소스에서 사용)
_COMPANY_TOKENS: dict[str, list[str]] = {
    "삼성": ["samsung", "galaxy", "갤럭시", "삼성"],
    "애플": ["apple", "iphone", "ipad", "macbook", "ios", "아이폰", "애플"],
}

# 루머/유출 감지 토큰
RUMOR_TOKENS: list[str] = [
    "rumor", "leak", "leaked", "exclusive", "report", "expected",
    "alleged", "concept", "render", "tipster", "supply chain",
    "루머", "유출", "예상", "전망", "출시 예정", "소문", "소식통", "확인되지",
]

# Atom 네임스페이스
_ATOM_NS = "http://www.w3.org/2005/Atom"


# ─────────────────────────────────────────────
# Article 데이터클래스
# ─────────────────────────────────────────────
@dataclass
class Article:
    title: str
    link: str
    source: str          # 사이트 이름 (MacRumors, SamMobile …)
    published: str       # 원본 날짜 문자열
    summary_raw: str = ""
    company: str = "기타"
    is_rumor: bool = False
    content: str = field(default="", repr=False)

    @property
    def published_dt(self) -> datetime:
        # RFC 2822 (RSS)
        try:
            return parsedate_to_datetime(self.published).replace(tzinfo=None)
        except Exception:
            pass
        # ISO 8601 (Atom)
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(self.published[:19], fmt[:len(self.published[:19])])
                return dt.replace(tzinfo=None)
            except Exception:
                pass
        return datetime.now()

    @property
    def published_ago(self) -> str:
        try:
            diff = datetime.now() - self.published_dt
            h = int(diff.total_seconds() // 3600)
            if h < 1:
                m = int(diff.total_seconds() // 60)
                return f"{m}분 전" if m > 0 else "방금"
            if h < 24:
                return f"{h}시간 전"
            return f"{h // 24}일 전"
        except Exception:
            return self.published[:10] if self.published else ""


# ─────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────
def _clean(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _detect_company(text: str) -> str:
    low = text.lower()
    for company, tokens in _COMPANY_TOKENS.items():
        if any(t in low for t in tokens):
            return company
    return "기타"


def _detect_rumor(text: str, rumor_site: bool) -> bool:
    if rumor_site:
        return True
    low = text.lower()
    return any(t in low for t in RUMOR_TOKENS)


def _filter_general(text: str) -> bool:
    """기타 소스에서 삼성/애플 무관 기사 제거."""
    low = text.lower()
    all_tokens = _COMPANY_TOKENS["삼성"] + _COMPANY_TOKENS["애플"]
    return any(t in low for t in all_tokens)


# ─────────────────────────────────────────────
# XML 파싱 (RSS 2.0 + Atom)
# ─────────────────────────────────────────────
def _parse_feed(xml_text: str, source: RssSource) -> list[Article]:
    articles: list[Article] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return articles

    tag = root.tag.lower()

    # ── Atom ──
    if "atom" in tag or f"{{{_ATOM_NS}}}" in root.tag:
        ns = {"a": _ATOM_NS}
        entries = root.findall("a:entry", ns) or root.findall(f"{{{_ATOM_NS}}}entry")
        for entry in entries[: source.max_items]:
            title = _clean(
                (entry.findtext(f"{{{_ATOM_NS}}}title") or
                 entry.findtext("a:title", namespaces=ns) or "")
            )
            link_el = entry.find(f"{{{_ATOM_NS}}}link") or entry.find("a:link", ns)
            link = ""
            if link_el is not None:
                link = link_el.get("href", "") or (link_el.text or "")
            published = (
                entry.findtext(f"{{{_ATOM_NS}}}published") or
                entry.findtext(f"{{{_ATOM_NS}}}updated") or ""
            )
            summary = _clean(
                entry.findtext(f"{{{_ATOM_NS}}}summary") or
                entry.findtext(f"{{{_ATOM_NS}}}content") or ""
            )
            articles.append(_make_article(title, link, published, summary, source))
        return articles

    # ── RSS 2.0 ──
    channel = root.find("channel")
    if channel is None:
        channel = root  # 일부 피드는 <rss> 바로 아래 <item>
    for item in list(channel.findall("item"))[: source.max_items]:
        title = _clean(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        published = (item.findtext("pubDate") or "").strip()
        summary = _clean(item.findtext("description") or "")
        articles.append(_make_article(title, link, published, summary, source))

    return articles


def _make_article(
    title: str, link: str, published: str, summary: str, source: RssSource
) -> Article:
    full_text = f"{title} {summary}"
    company = source.company if source.company != "기타" else _detect_company(full_text)
    is_rumor = _detect_rumor(full_text, source.rumor_site)
    return Article(
        title=title,
        link=link,
        source=source.name,
        published=published,
        summary_raw=summary[:300],
        company=company,
        is_rumor=is_rumor,
    )


# ─────────────────────────────────────────────
# 수집 함수
# ─────────────────────────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def fetch_articles() -> list[Article]:
    seen: set[str] = set()
    articles: list[Article] = []

    for src in RSS_SOURCES:
        try:
            resp = requests.get(src.url, headers=_HEADERS, timeout=12)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
        except Exception as exc:
            print(f"[WARN] {src.name}: {exc}")
            continue

        for art in _parse_feed(resp.text, src):
            if not art.title or not art.link:
                continue
            # 기타 소스는 삼성/애플 관련 기사만 통과
            if src.company == "기타" and not _filter_general(f"{art.title} {art.summary_raw}"):
                continue
            if art.link not in seen:
                seen.add(art.link)
                articles.append(art)

    articles.sort(key=lambda a: a.published_dt, reverse=True)
    return articles


def fetch_article_body(url: str, timeout: int = 8) -> str:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
    except Exception as exc:
        return f"[본문 수집 실패: {exc}]"
    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
        tag.decompose()
    article_tag = soup.find("article") or soup.find(id=re.compile("article|content", re.I))
    target = article_tag if article_tag else soup
    paragraphs = [p.get_text(" ", strip=True) for p in target.find_all("p") if len(p.get_text()) > 30]
    return "\n".join(paragraphs[:40]) or "[본문을 추출할 수 없습니다.]"


# ─────────────────────────────────────────────
# 캐시 (1시간)
# ─────────────────────────────────────────────
_CACHE: dict[str, tuple[float, list[Article]]] = {}
_TTL = 3600


def _demo_articles() -> list[Article]:
    """RSS 접근 불가 환경에서 UI 확인용 샘플 데이터."""
    return [
        Article("Apple's iPhone 17 Pro rumored to feature periscope telephoto across all models",
                "https://www.macrumors.com/", "MacRumors", "Mon, 12 May 2025 10:00:00 +0000",
                "Supply chain sources suggest Apple plans to bring periscope zoom to the entire iPhone 17 Pro lineup.",
                "애플", True),
        Article("Samsung Galaxy S26 Ultra leak reveals massive battery upgrade",
                "https://www.sammobile.com/", "SamMobile", "Mon, 12 May 2025 08:00:00 +0000",
                "Leaked specs indicate a 6000mAh battery in the Galaxy S26 Ultra, up from 5000mAh.",
                "삼성", True),
        Article("Apple faces supply chain delays for foldable iPhone components",
                "https://9to5mac.com/", "9to5Mac", "Mon, 12 May 2025 07:30:00 +0000",
                "Reports from Asia suggest Apple's foldable hinge supplier is struggling with yield rates.",
                "애플", False),
        Article("Samsung confirms Galaxy Z Fold 7 hinge durability improvements",
                "https://www.sammobile.com/", "SamMobile", "Sun, 11 May 2025 15:00:00 +0000",
                "Samsung officially stated the new Flex Hinge in Z Fold 7 lasts 30% longer than the previous generation.",
                "삼성", False),
        Article("iOS 19 rumored to bring major redesign with AI-first interface",
                "https://www.macrumors.com/", "MacRumors", "Sun, 11 May 2025 12:00:00 +0000",
                "Multiple sources report Apple is working on a ground-up redesign of iOS for the upcoming iPhone 17 era.",
                "애플", True),
        Article("Galaxy S26 display panel to use new low-power LTPO4 technology",
                "https://9to5google.com/", "9to5Google", "Sun, 11 May 2025 10:00:00 +0000",
                "Samsung Display is reportedly mass-producing LTPO4 panels with 20% improved power efficiency.",
                "삼성", True),
        Article("Apple halts Vision Pro 2 development amid weak sales",
                "https://9to5mac.com/", "9to5Mac", "Sat, 10 May 2025 09:00:00 +0000",
                "Apple has reportedly put Vision Pro 2 on hold as first-generation sales fall short of targets.",
                "애플", False),
        Article("Samsung Galaxy Z Flip 7 concept renders leak online",
                "https://www.gsmarena.com/", "GSMArena", "Sat, 10 May 2025 08:00:00 +0000",
                "Alleged renders show a slimmer hinge design and larger cover display for the Galaxy Z Flip 7.",
                "삼성", True),
        Article("iPhone 17 Air battery life concerns surface in latest report",
                "https://www.macrumors.com/", "MacRumors", "Fri, 09 May 2025 15:00:00 +0000",
                "The ultra-thin iPhone 17 Air may ship with a smaller battery, raising battery life concerns.",
                "애플", False),
        Article("Samsung accused of exaggerating Galaxy AI features in ads",
                "https://9to5google.com/", "9to5Google", "Fri, 09 May 2025 11:00:00 +0000",
                "Consumer advocacy groups filed complaints over Samsung's Galaxy AI marketing claims.",
                "삼성", False),
        Article("Apple Watch Ultra 3 titanium chassis leak suggests larger sensor array",
                "https://www.macrumors.com/", "MacRumors", "Thu, 08 May 2025 09:00:00 +0000",
                "CAD renders show a redesigned back panel with additional health sensors.",
                "애플", True),
        Article("Samsung to use Snapdragon 8 Elite 2 exclusively in Galaxy S26 series",
                "https://www.sammobile.com/", "SamMobile", "Thu, 08 May 2025 08:00:00 +0000",
                "Qualcomm will supply all Galaxy S26 chipsets, ending the Exynos split for major markets.",
                "삼성", True),
    ]


is_demo_mode: bool = False  # fetch 후 실제 데이터 없으면 True로 설정


def get_cached_articles(force_refresh: bool = False) -> list[Article]:
    global is_demo_mode
    now = time.time()
    cached = _CACHE.get("v")
    if not force_refresh and cached and (now - cached[0]) < _TTL:
        return cached[1]
    arts = fetch_articles()
    if arts:
        is_demo_mode = False
    else:
        is_demo_mode = True
        arts = _demo_articles()
    _CACHE["v"] = (now, arts)
    return arts


def cache_age_seconds() -> float | None:
    c = _CACHE.get("v")
    return (time.time() - c[0]) if c else None
