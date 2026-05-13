"""뉴스 크롤링 모듈.

전문 사이트 + 대형 언론사 RSS 직접 수집 후 한국어 번역.
RSS 2.0 / Atom 두 포맷 지원. API 키 불필요.
"""
from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
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
    company: str       # "삼성" | "애플" | "기타"
    rumor_site: bool
    max_items: int = 15

RSS_SOURCES: list[RssSource] = [
    # ── 애플 전문 ─────────────────────────────
    RssSource("MacRumors",      "https://feeds.macrumors.com/MacRumors-All",                 "애플", True,  20),
    RssSource("9to5Mac",        "https://9to5mac.com/feed/",                                 "애플", False, 15),
    # ── 삼성 전문 ─────────────────────────────
    RssSource("SamMobile",      "https://www.sammobile.com/feed/",                           "삼성", True,  20),
    RssSource("9to5Google",     "https://9to5google.com/feed/",                              "삼성", False, 15),
    # ── 모바일 전반 ───────────────────────────
    RssSource("GSMArena",       "https://www.gsmarena.com/rss-news-reviews.php3",            "기타", False, 20),
    RssSource("The Verge",      "https://www.theverge.com/rss/index.xml",                    "기타", False, 15),
    RssSource("TechCrunch",     "https://techcrunch.com/category/mobile/feed/",              "기타", False, 10),
    # ── 대형 언론사 ───────────────────────────
    RssSource("Bloomberg",      "https://feeds.bloomberg.com/technology/news.rss",           "기타", False, 10),
    RssSource("Reuters",        "https://feeds.reuters.com/reuters/technologyNews",          "기타", False, 10),
    RssSource("BBC Tech",       "https://feeds.bbci.co.uk/news/technology/rss.xml",         "기타", False, 10),
    RssSource("CNBC Tech",      "https://www.cnbc.com/id/19854910/device/rss/rss.html",     "기타", False, 10),
    RssSource("Financial Times","https://www.ft.com/technology?format=rss",                 "기타", False,  8),
]

# 회사 감지 토큰
_COMPANY_TOKENS: dict[str, list[str]] = {
    "삼성": ["samsung", "galaxy", "갤럭시", "삼성", "exynos", "one ui"],
    "애플": ["apple", "iphone", "ipad", "macbook", "ios", "macos", "아이폰", "애플", "tim cook"],
}

# 루머/유출 토큰
RUMOR_TOKENS: list[str] = [
    "rumor", "leak", "leaked", "exclusive", "report", "expected",
    "alleged", "concept", "render", "tipster", "supply chain",
    "coming soon", "spotted", "hints at", "could",
    "루머", "유출", "예상", "전망", "출시 예정", "소문", "소식통", "확인되지",
]

_ATOM_NS = "http://www.w3.org/2005/Atom"


# ─────────────────────────────────────────────
# Article 데이터클래스
# ─────────────────────────────────────────────
@dataclass
class Article:
    title: str
    link: str
    source: str
    published: str
    summary_raw: str = ""
    company: str = "기타"
    is_rumor: bool = False
    title_ko: str = ""       # 한국어 번역 제목
    summary_ko: str = ""     # 한국어 번역 요약
    content: str = field(default="", repr=False)

    @property
    def display_title(self) -> str:
        return self.title_ko or self.title

    @property
    def display_summary(self) -> str:
        return self.summary_ko or self.summary_raw

    @property
    def published_dt(self) -> datetime:
        try:
            return parsedate_to_datetime(self.published).replace(tzinfo=None)
        except Exception:
            pass
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
            try:
                return datetime.strptime(self.published[:len(fmt)], fmt)
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
# 번역
# ─────────────────────────────────────────────
def _is_english(text: str) -> bool:
    if not text:
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return ascii_count / len(text) > 0.75


def translate_articles(articles: list[Article]) -> None:
    """영어 기사 제목·요약을 한국어로 번역 (in-place). 실패해도 원문 유지."""
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        return

    translator = GoogleTranslator(source="auto", target="ko")

    for art in articles:
        # 제목 번역
        if _is_english(art.title) and not art.title_ko:
            try:
                art.title_ko = translator.translate(art.title[:4999]) or art.title
            except Exception:
                pass

        # 요약 번역 (200자 이내로 잘라서 전달)
        if _is_english(art.summary_raw) and not art.summary_ko and art.summary_raw:
            try:
                art.summary_ko = translator.translate(art.summary_raw[:1000]) or art.summary_raw
            except Exception:
                pass


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
    return any(t in text.lower() for t in RUMOR_TOKENS)


def _filter_general(text: str) -> bool:
    low = text.lower()
    all_tokens = _COMPANY_TOKENS["삼성"] + _COMPANY_TOKENS["애플"]
    return any(t in low for t in all_tokens)


# ─────────────────────────────────────────────
# XML 파싱 (RSS 2.0 + Atom)
# ─────────────────────────────────────────────
def _parse_feed(xml_text: str, src: RssSource) -> list[Article]:
    articles: list[Article] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return articles

    # Atom 판별
    if _ATOM_NS in root.tag or root.tag.lower() == "feed":
        for entry in list(root.iter(f"{{{_ATOM_NS}}}entry"))[: src.max_items]:
            title   = _clean(entry.findtext(f"{{{_ATOM_NS}}}title") or "")
            link_el = entry.find(f"{{{_ATOM_NS}}}link")
            link    = (link_el.get("href", "") if link_el is not None else "").strip()
            pub     = (entry.findtext(f"{{{_ATOM_NS}}}published") or
                       entry.findtext(f"{{{_ATOM_NS}}}updated") or "")
            summary = _clean(entry.findtext(f"{{{_ATOM_NS}}}summary") or
                             entry.findtext(f"{{{_ATOM_NS}}}content") or "")
            articles.append(_make(title, link, pub, summary, src))
        return articles

    # RSS 2.0
    channel = root.find("channel") or root
    for item in list(channel.findall("item"))[: src.max_items]:
        title   = _clean(item.findtext("title") or "")
        link    = (item.findtext("link") or "").strip()
        pub     = (item.findtext("pubDate") or "").strip()
        summary = _clean(item.findtext("description") or "")
        articles.append(_make(title, link, pub, summary, src))
    return articles


def _make(title: str, link: str, published: str, summary: str, src: RssSource) -> Article:
    full = f"{title} {summary}"
    company  = src.company if src.company != "기타" else _detect_company(full)
    is_rumor = _detect_rumor(full, src.rumor_site)
    return Article(
        title=title, link=link, source=src.name, published=published,
        summary_raw=summary[:400], company=company, is_rumor=is_rumor,
    )


# ─────────────────────────────────────────────
# 수집
# ─────────────────────────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def fetch_articles() -> list[Article]:
    seen: set[str] = set()
    articles: list[Article] = []

    for src in RSS_SOURCES:
        try:
            r = requests.get(src.url, headers=_HEADERS, timeout=12)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
        except Exception as exc:
            print(f"[WARN] {src.name}: {exc}")
            continue

        for art in _parse_feed(r.text, src):
            if not art.title or not art.link:
                continue
            if src.company == "기타" and not _filter_general(f"{art.title} {art.summary_raw}"):
                continue
            if art.link not in seen:
                seen.add(art.link)
                articles.append(art)

    articles.sort(key=lambda a: a.published_dt, reverse=True)

    if articles:
        translate_articles(articles)

    return articles


def fetch_article_body(url: str, timeout: int = 8) -> str:
    try:
        r = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
    except Exception as exc:
        return f"[본문 수집 실패: {exc}]"
    soup = BeautifulSoup(r.text, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
        tag.decompose()
    target = soup.find("article") or soup.find(id=re.compile("article|content", re.I)) or soup
    paras = [p.get_text(" ", strip=True) for p in target.find_all("p") if len(p.get_text()) > 30]
    return "\n".join(paras[:40]) or "[본문을 추출할 수 없습니다.]"


# ─────────────────────────────────────────────
# 데모 데이터 (RSS 접근 불가 환경용)
# ─────────────────────────────────────────────
def _demo_articles() -> list[Article]:
    raw = [
        # 애플 루머
        ("MacRumors",   "애플", True,
         "Apple's iPhone 17 Pro rumored to feature periscope telephoto across all models",
         "아이폰 17 Pro, 전 모델에 페리스코프 망원 탑재 루머",
         "Supply chain sources suggest Apple plans to bring periscope zoom to the entire iPhone 17 Pro lineup, a first for the series.",
         "공급망 소식통에 따르면 애플은 아이폰 17 Pro 전 라인업에 페리스코프 줌을 탑재할 계획이며, 시리즈 최초 사례가 될 전망입니다."),
        ("9to5Mac",     "애플", False,
         "Apple faces supply chain delays for foldable iPhone hinge components",
         "애플 폴더블 아이폰 힌지 부품 공급망 지연",
         "Reports from Asia indicate Apple's foldable hinge supplier is struggling with yield rates ahead of 2026 launch.",
         "아시아 보도에 따르면 애플의 폴더블 힌지 공급업체가 2026년 출시를 앞두고 수율 문제를 겪고 있습니다."),
        ("MacRumors",   "애플", True,
         "iOS 19 rumored to bring major AI-first redesign",
         "iOS 19, AI 중심의 대규모 디자인 개편 루머",
         "Multiple sources report Apple is working on a ground-up redesign of iOS for the iPhone 17 era.",
         "복수의 소식통에 따르면 애플은 아이폰 17 시대를 위해 iOS를 전면 재설계하고 있습니다."),
        ("9to5Mac",     "애플", False,
         "Apple halts Vision Pro 2 development amid weak first-gen sales",
         "애플, 1세대 판매 부진으로 비전 프로 2 개발 중단",
         "Apple has reportedly put Vision Pro 2 on hold as first-generation sales fall short of internal targets.",
         "애플이 1세대 판매량이 내부 목표에 미치지 못하자 비전 프로 2 개발을 중단한 것으로 알려졌습니다."),
        ("Bloomberg",   "애플", False,
         "Apple's AI push faces regulatory scrutiny in Europe",
         "애플 AI 전략, 유럽 규제 당국 심사 직면",
         "European regulators are examining whether Apple Intelligence features comply with the Digital Markets Act.",
         "유럽 규제 당국이 애플 인텔리전스 기능이 디지털시장법을 준수하는지 조사 중입니다."),
        # 삼성 루머
        ("SamMobile",   "삼성", True,
         "Samsung Galaxy S26 Ultra leak reveals 6000mAh battery and new cooling system",
         "갤럭시 S26 울트라 유출: 6000mAh 배터리·신형 쿨링 시스템",
         "Leaked specs show the Galaxy S26 Ultra will ship with a 6000mAh battery and vapor chamber cooling.",
         "유출된 스펙에 따르면 갤럭시 S26 울트라는 6000mAh 배터리와 베이퍼 챔버 쿨링을 탑재합니다."),
        ("9to5Google",  "삼성", True,
         "Galaxy Z Flip 7 concept renders show slimmer hinge and larger cover display",
         "갤럭시 Z 플립 7 컨셉 렌더링: 얇아진 힌지, 커진 커버 디스플레이",
         "Alleged renders show a redesigned, slimmer hinge and a 4-inch cover display on the Galaxy Z Flip 7.",
         "유출된 렌더링에 따르면 갤럭시 Z 플립 7은 더 얇은 힌지와 4인치 커버 디스플레이를 갖출 예정입니다."),
        ("SamMobile",   "삼성", False,
         "Samsung confirms Galaxy Z Fold 7 hinge durability improved by 30%",
         "삼성, 갤럭시 Z 폴드 7 힌지 내구성 30% 향상 공식 확인",
         "Samsung officially confirmed the Flex Hinge in Z Fold 7 has 30% improved durability over the previous generation.",
         "삼성은 Z 폴드 7의 플렉스 힌지가 전 세대 대비 30% 향상된 내구성을 갖췄다고 공식 확인했습니다."),
        ("Reuters",     "삼성", False,
         "Samsung Electronics reports record Q1 profit on AI chip demand",
         "삼성전자, AI 칩 수요에 힘입어 1분기 사상 최대 영업이익",
         "Samsung Electronics posted record first-quarter operating profit driven by surging demand for HBM memory chips.",
         "삼성전자가 HBM 메모리 칩 수요 급증에 힘입어 사상 최대 1분기 영업이익을 기록했습니다."),
        ("9to5Google",  "삼성", False,
         "Samsung accused of overstating Galaxy AI capabilities in advertisements",
         "삼성, 갤럭시 AI 기능 광고 과장 혐의",
         "Consumer advocacy groups filed complaints alleging Samsung exaggerated Galaxy AI features in marketing materials.",
         "소비자 단체들이 삼성이 마케팅 자료에서 갤럭시 AI 기능을 과장했다며 이의를 제기했습니다."),
        # 기타
        ("GSMArena",    "기타", False,
         "Qualcomm Snapdragon 8 Elite 2 specs leaked ahead of Q4 launch",
         "퀄컴 스냅드래곤 8 엘리트 2 스펙 유출, 4분기 출시 예정",
         "Leaked benchmarks show the Snapdragon 8 Elite 2 delivers 40% CPU improvement over its predecessor.",
         "유출된 벤치마크에 따르면 스냅드래곤 8 엘리트 2는 전 세대 대비 CPU 성능이 40% 향상됐습니다."),
        ("BBC Tech",    "기타", False,
         "Smartphone market grows 8% in Q1 2025 driven by AI features",
         "AI 기능 탑재로 2025년 1분기 스마트폰 시장 8% 성장",
         "Global smartphone shipments rose 8% year-on-year in Q1 2025 as consumers upgrade for AI capabilities.",
         "AI 기능 업그레이드 수요에 힘입어 2025년 1분기 글로벌 스마트폰 출하량이 전년 동기 대비 8% 증가했습니다."),
    ]
    articles = []
    for src_name, company, is_rumor, title, title_ko, summary, summary_ko in raw:
        articles.append(Article(
            title=title, title_ko=title_ko,
            link=f"https://example.com/{len(articles)}",
            source=src_name,
            published="Mon, 12 May 2025 10:00:00 +0000",
            summary_raw=summary, summary_ko=summary_ko,
            company=company, is_rumor=is_rumor,
        ))
    return articles


# ─────────────────────────────────────────────
# 캐시
# ─────────────────────────────────────────────
_CACHE: dict[str, tuple[float, list[Article]]] = {}
_TTL = 3600
is_demo_mode: bool = False


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
