"""뉴스 크롤링 모듈.

모바일 / 로보틱스 / AI 3개 섹터, 24개 회사별 RSS 수집.
회사 로고: Clearbit Logo API (logo.clearbit.com).
번역: deep-translator Google 백엔드.
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
# 섹터 / 회사 정의
# ─────────────────────────────────────────────
SECTORS: dict[str, dict] = {
    "모바일": {
        "emoji": "📱",
        "companies": {
            "삼성":   {"domain": "samsung.com",   "tokens": ["samsung", "galaxy", "갤럭시", "삼성", "exynos", "one ui"]},
            "애플":   {"domain": "apple.com",     "tokens": ["apple", "iphone", "ipad", "ios", "macos", "아이폰", "애플", "vision pro", "tim cook"]},
            "화웨이": {"domain": "huawei.com",    "tokens": ["huawei", "화웨이", "honor", "harmonyos", "kirin"]},
            "OPPO":   {"domain": "oppo.com",      "tokens": ["oppo", "oneplus", "realme", "find x", "reno"]},
            "샤오미": {"domain": "xiaomi.com",    "tokens": ["xiaomi", "샤오미", "redmi", "poco", "miui", "hyperos"]},
            "Google": {"domain": "google.com",    "tokens": ["google pixel", "pixel phone", "pixel fold", "pixel watch", "tensor chip", "pixel tablet"]},
            "Sony":   {"domain": "sony.com",      "tokens": ["sony xperia", "xperia"]},
        },
    },
    "로보틱스": {
        "emoji": "🤖",
        "companies": {
            "Boston Dynamics": {"domain": "bostondynamics.com", "tokens": ["boston dynamics", "atlas robot", "spot robot", "stretch robot"]},
            "Figure AI":       {"domain": "figure.ai",          "tokens": ["figure ai", "figure robot", "figure 02", "helix ai", "figure humanoid"]},
            "Agility Robotics":{"domain": "agilityrobotics.com","tokens": ["agility robotics", "digit robot", "agility robot"]},
            "Unitree":         {"domain": "unitree.com",        "tokens": ["unitree", "unitree h1", "unitree g1", "go2 robot"]},
            "1X Technologies": {"domain": "1x.tech",            "tokens": ["1x technologies", "1x tech", "neo robot", "eve robot"]},
            "Apptronik":       {"domain": "apptronik.com",      "tokens": ["apptronik", "apollo robot"]},
            "현대":            {"domain": "hyundai.com",        "tokens": ["hyundai robotics", "현대 로봇", "현대로보틱스", "hyundai robot"]},
            "Tesla":           {"domain": "tesla.com",          "tokens": ["tesla optimus", "optimus robot", "tesla bot", "tesla humanoid"]},
        },
    },
    "AI": {
        "emoji": "🧠",
        "companies": {
            "OpenAI":    {"domain": "openai.com",    "tokens": ["openai", "chatgpt", "gpt-4", "gpt-5", "o1 model", "o3 model", "sora", "dall-e"]},
            "Anthropic": {"domain": "anthropic.com", "tokens": ["anthropic", "claude ai", "claude 3", "claude 4", "claude sonnet", "claude opus"]},
            "Google":    {"domain": "google.com",    "tokens": ["google gemini", "gemini ai", "deepmind", "google ai", "gemma model", "bard"]},
            "Meta":      {"domain": "meta.com",      "tokens": ["meta ai", "llama", "meta llm", "meta artificial intelligence"]},
            "Microsoft": {"domain": "microsoft.com", "tokens": ["microsoft copilot", "azure openai", "bing ai", "microsoft ai", "phi model", "microsoft 365 ai"]},
            "xAI":       {"domain": "x.ai",          "tokens": ["xai", "grok", "x.ai", "grok-2", "grok-3", "elon musk ai"]},
            "Nvidia":    {"domain": "nvidia.com",    "tokens": ["nvidia ai", "h100", "blackwell gpu", "cuda ai", "jensen huang", "nvidia nim", "gb200"]},
            "Mistral AI":{"domain": "mistral.ai",   "tokens": ["mistral", "mixtral", "mistral ai", "le chat"]},
            "Tesla":     {"domain": "tesla.com",     "tokens": ["tesla ai", "tesla fsd", "dojo supercomputer", "full self-driving", "tesla autopilot"]},
        },
    },
}

# 회사 → 섹터 역색인 (빠른 조회용)
_COMPANY_TO_SECTOR: dict[str, str] = {
    company: sector
    for sector, info in SECTORS.items()
    for company in info["companies"]
}

# 루머 토큰
RUMOR_TOKENS: list[str] = [
    "rumor", "leak", "leaked", "exclusive", "report", "expected",
    "alleged", "concept", "render", "tipster", "supply chain",
    "coming soon", "spotted", "hints at", "could launch",
    "루머", "유출", "예상", "전망", "출시 예정", "소문", "소식통",
]

_ATOM_NS = "http://www.w3.org/2005/Atom"


# ─────────────────────────────────────────────
# RSS 소스 정의
# ─────────────────────────────────────────────
class RssSource(NamedTuple):
    name: str
    url: str
    sector: str       # "모바일" | "로보틱스" | "AI" | "기타"
    rumor_site: bool
    max_items: int = 15

RSS_SOURCES: list[RssSource] = [
    # ── 모바일 ──────────────────────────────────────────
    RssSource("MacRumors",    "https://feeds.macrumors.com/MacRumors-All",            "모바일", True,  20),
    RssSource("9to5Mac",      "https://9to5mac.com/feed/",                            "모바일", False, 15),
    RssSource("SamMobile",    "https://www.sammobile.com/feed/",                      "모바일", True,  20),
    RssSource("9to5Google",   "https://9to5google.com/feed/",                         "모바일", False, 15),
    RssSource("GSMArena",     "https://www.gsmarena.com/rss-news-reviews.php3",       "모바일", False, 20),
    # ── 로보틱스 ─────────────────────────────────────────
    RssSource("IEEE Spectrum","https://spectrum.ieee.org/feeds/topic/robotics.rss",   "로보틱스", False, 15),
    RssSource("Robot Report", "https://www.therobotreport.com/feed/",                 "로보틱스", False, 15),
    RssSource("TC Robotics",  "https://techcrunch.com/category/robotics/feed/",       "로보틱스", False, 10),
    # ── AI ───────────────────────────────────────────────
    RssSource("VentureBeat",  "https://venturebeat.com/category/ai/feed/",            "AI", False, 15),
    RssSource("The Decoder",  "https://the-decoder.com/feed/",                        "AI", False, 15),
    RssSource("Ars Technica", "https://arstechnica.com/ai/feed/",                     "AI", False, 10),
    # ── 대형 언론 (전 섹터 커버) ─────────────────────────
    RssSource("The Verge",    "https://www.theverge.com/rss/index.xml",               "기타", False, 15),
    RssSource("TechCrunch",   "https://techcrunch.com/category/mobile/feed/",         "기타", False, 10),
    RssSource("Bloomberg",    "https://feeds.bloomberg.com/technology/news.rss",      "기타", False, 10),
    RssSource("Reuters",      "https://feeds.reuters.com/reuters/technologyNews",     "기타", False, 10),
    RssSource("BBC Tech",     "https://feeds.bbci.co.uk/news/technology/rss.xml",    "기타", False, 10),
]


# ─────────────────────────────────────────────
# Article
# ─────────────────────────────────────────────
@dataclass
class Article:
    title: str
    link: str
    source: str
    published: str
    summary_raw: str = ""
    sector: str = "기타"
    company: str = "기타"
    is_rumor: bool = False
    title_ko: str = ""
    summary_ko: str = ""
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

    @property
    def logo_url(self) -> str:
        sector_info = SECTORS.get(self.sector, {})
        company_info = sector_info.get("companies", {}).get(self.company, {})
        domain = company_info.get("domain", "")
        if domain:
            return f"https://logo.clearbit.com/{domain}"
        return ""

    @property
    def favicon_url(self) -> str:
        sector_info = SECTORS.get(self.sector, {})
        company_info = sector_info.get("companies", {}).get(self.company, {})
        domain = company_info.get("domain", "")
        if domain:
            return f"https://www.google.com/s2/favicons?domain={domain}&sz=32"
        return ""


# ─────────────────────────────────────────────
# 번역
# ─────────────────────────────────────────────
def _is_english(text: str) -> bool:
    if not text:
        return False
    return sum(1 for c in text if ord(c) < 128) / len(text) > 0.75


def translate_articles(articles: list[Article]) -> None:
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        return
    tr = GoogleTranslator(source="auto", target="ko")
    for art in articles:
        if _is_english(art.title) and not art.title_ko:
            try:
                art.title_ko = tr.translate(art.title[:4999]) or ""
            except Exception:
                pass
        if _is_english(art.summary_raw) and not art.summary_ko and art.summary_raw:
            try:
                art.summary_ko = tr.translate(art.summary_raw[:1000]) or ""
            except Exception:
                pass


# ─────────────────────────────────────────────
# 감지 로직
# ─────────────────────────────────────────────
def _detect_company_in_sector(text: str, sector_name: str) -> str:
    low = text.lower()
    companies = SECTORS.get(sector_name, {}).get("companies", {})
    for company, info in companies.items():
        if any(t in low for t in info["tokens"]):
            return company
    return "기타"


def _detect_sector_and_company(text: str, source_sector: str) -> tuple[str, str]:
    low = text.lower()

    # 지정 섹터가 있으면 해당 섹터 내에서만 회사 탐색
    if source_sector in SECTORS:
        company = _detect_company_in_sector(low, source_sector)
        return source_sector, company

    # 일반 소스 → 전 섹터에서 가장 많이 매칭되는 회사 선택
    best = ("기타", "기타", 0)
    for sector_name, sector_info in SECTORS.items():
        for company, info in sector_info["companies"].items():
            score = sum(1 for t in info["tokens"] if t in low)
            if score > best[2]:
                best = (sector_name, company, score)
    return best[0], best[1]


def _detect_rumor(text: str, rumor_site: bool) -> bool:
    if rumor_site:
        return True
    return any(t in text.lower() for t in RUMOR_TOKENS)


def _filter_relevant(text: str) -> bool:
    """기타 소스에서 무관 기사 제거."""
    low = text.lower()
    for sector_info in SECTORS.values():
        for info in sector_info["companies"].values():
            if any(t in low for t in info["tokens"]):
                return True
    return False


# ─────────────────────────────────────────────
# XML 파싱
# ─────────────────────────────────────────────
def _clean(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_feed(xml_text: str, src: RssSource) -> list[Article]:
    articles: list[Article] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return articles

    # Atom
    if _ATOM_NS in root.tag or root.tag.lower() == "feed":
        for entry in list(root.iter(f"{{{_ATOM_NS}}}entry"))[: src.max_items]:
            title   = _clean(entry.findtext(f"{{{_ATOM_NS}}}title") or "")
            lel     = entry.find(f"{{{_ATOM_NS}}}link")
            link    = (lel.get("href", "") if lel is not None else "").strip()
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
    sector, company = _detect_sector_and_company(full, src.sector)
    return Article(
        title=title, link=link, source=src.name, published=published,
        summary_raw=summary[:400], sector=sector, company=company,
        is_rumor=_detect_rumor(full, src.rumor_site),
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
            if src.sector == "기타" and not _filter_relevant(f"{art.title} {art.summary_raw}"):
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
# 데모 데이터
# ─────────────────────────────────────────────
def _demo_articles() -> list[Article]:
    rows = [
        # sector, company, rumor, source, title_en, title_ko, summary_en, summary_ko
        ("모바일","애플",   True, "MacRumors",
         "iPhone 17 Pro rumored to feature periscope telephoto across all models",
         "아이폰 17 Pro, 전 모델 페리스코프 망원 탑재 루머",
         "Supply chain sources suggest Apple plans periscope zoom for all iPhone 17 Pro models.",
         "공급망 소식통에 따르면 애플은 아이폰 17 Pro 전 라인업에 페리스코프 줌을 탑재할 계획입니다."),
        ("모바일","삼성",   True, "SamMobile",
         "Galaxy S26 Ultra leak reveals 6000mAh battery and vapor chamber cooling",
         "갤럭시 S26 울트라 유출: 6000mAh 배터리·베이퍼 챔버",
         "Leaked specs show the Galaxy S26 Ultra ships with a 6000mAh battery.",
         "유출된 스펙에 따르면 갤럭시 S26 울트라는 6000mAh 배터리를 탑재합니다."),
        ("모바일","화웨이", False,"The Verge",
         "Huawei Mate 70 Pro outperforms expectations despite chip restrictions",
         "화웨이 Mate 70 Pro, 칩 제재에도 기대 이상 성능 발휘",
         "Huawei's latest flagship shows surprising performance despite US chip export restrictions.",
         "화웨이 최신 플래그십이 미국 반도체 수출 규제에도 놀라운 성능을 보여줬습니다."),
        ("모바일","샤오미", True, "GSMArena",
         "Xiaomi 15 Ultra concept renders reveal 200MP periscope camera",
         "샤오미 15 울트라 컨셉 렌더링: 200MP 페리스코프 카메라",
         "Alleged renders show Xiaomi 15 Ultra with a 200MP periscope telephoto lens.",
         "유출된 렌더링에 따르면 샤오미 15 울트라는 200MP 페리스코프 망원 렌즈를 탑재합니다."),
        ("모바일","OPPO",  False,"GSMArena",
         "OPPO Find X8 Pro launches globally with Hasselblad camera system",
         "OPPO 파인드 X8 Pro, 하셀블라드 카메라 탑재 글로벌 출시",
         "OPPO officially launched the Find X8 Pro globally with co-engineered Hasselblad cameras.",
         "OPPO가 하셀블라드와 공동 개발한 카메라를 탑재한 파인드 X8 Pro를 글로벌 출시했습니다."),
        ("모바일","Google",True, "9to5Google",
         "Google Pixel 10 Pro rumored to feature in-house Tensor G5 with 3nm process",
         "구글 픽셀 10 Pro, 자체 텐서 G5(3nm) 탑재 루머",
         "Tipsters claim the Pixel 10 Pro will debut Google's Tensor G5 chip built on 3nm.",
         "제보자들에 따르면 픽셀 10 Pro는 3nm 공정 기반 텐서 G5 칩을 탑재할 예정입니다."),
        ("모바일","Sony",  False,"GSMArena",
         "Sony Xperia 1 VII gaming performance review highlights thermal management",
         "소니 엑스페리아 1 VII 게이밍 성능: 발열 관리가 핵심",
         "Sony's Xperia 1 VII impresses with dedicated gaming mode and advanced cooling.",
         "소니 엑스페리아 1 VII는 전용 게이밍 모드와 고급 쿨링 시스템으로 주목받고 있습니다."),
        # 로보틱스
        ("로보틱스","Boston Dynamics",True, "IEEE Spectrum",
         "Boston Dynamics Atlas humanoid robot begins automotive factory trials",
         "보스턴다이나믹스 아틀라스, 자동차 공장 시범 운영 시작",
         "Atlas is now being tested in real automotive manufacturing environments alongside human workers.",
         "아틀라스 로봇이 자동차 제조 현장에서 인간 작업자와 함께 실제 시범 운영을 시작했습니다."),
        ("로보틱스","Figure AI",  True, "Robot Report",
         "Figure AI's Helix model enables robots to learn tasks in hours not weeks",
         "Figure AI 헬릭스 모델, 로봇 학습 시간 수주→수시간으로 단축",
         "Figure's new Helix AI model allows robots to master new manipulation tasks within hours.",
         "Figure의 새로운 헬릭스 AI 모델로 로봇이 새로운 작업을 수 시간 내에 습득할 수 있게 됐습니다."),
        ("로보틱스","Tesla",      True, "TC Robotics",
         "Tesla Optimus Gen 3 walks 40% faster, claims internal memo leak",
         "테슬라 옵티머스 3세대, 40% 빠른 보행속도 달성 — 내부 문서 유출",
         "A leaked internal Tesla memo claims Optimus Gen 3 achieves human-level walking speed.",
         "유출된 테슬라 내부 문서에 따르면 옵티머스 3세대가 인간 수준의 보행 속도를 달성했습니다."),
        ("로보틱스","Unitree",    True, "IEEE Spectrum",
         "Unitree G1 humanoid priced at $16k disrupts industrial robotics market",
         "유니트리 G1, 1600만원 인간형 로봇으로 산업용 로봇 시장 파격 진입",
         "Unitree's G1 humanoid at $16,000 is forcing competitors to rethink pricing strategies.",
         "1만6000달러(약 2100만원)짜리 유니트리 G1이 경쟁사들의 가격 전략을 재고하게 만들고 있습니다."),
        ("로보틱스","Agility Robotics",False,"Robot Report",
         "Agility Robotics Digit completes 1 million warehouse picks at Amazon",
         "어질리티 로보틱스 디짓, 아마존 물류센터 100만 번 피킹 달성",
         "Digit has surpassed 1 million item picks in Amazon warehouses, a major milestone.",
         "디짓 로봇이 아마존 물류센터에서 100만 번 물품 피킹이라는 이정표를 달성했습니다."),
        # AI
        ("AI","OpenAI",   True, "The Decoder",
         "OpenAI GPT-5 rumored to debut multimodal reasoning with 10x capacity",
         "OpenAI GPT-5, 멀티모달 추론 및 10배 용량 루머",
         "Sources claim GPT-5 will feature native multimodal reasoning far beyond GPT-4.",
         "소식통에 따르면 GPT-5는 GPT-4를 크게 뛰어넘는 네이티브 멀티모달 추론 기능을 갖출 예정입니다."),
        ("AI","Anthropic", False,"VentureBeat",
         "Anthropic Claude 4 Opus sets new benchmark on coding and reasoning tasks",
         "Anthropic 클로드 4 오퍼스, 코딩·추론 벤치마크 신기록",
         "Claude 4 Opus outperforms competitors on SWE-bench coding and MMLU reasoning tasks.",
         "클로드 4 오퍼스가 SWE-벤치 코딩과 MMLU 추론 과제에서 경쟁사를 앞섰습니다."),
        ("AI","Google",   True, "Ars Technica",
         "Google Gemini Ultra 2 reportedly achieves human-level performance on GPQA",
         "구글 제미나이 울트라 2, GPQA 인간 수준 성능 달성 루머",
         "Leaked evals suggest Gemini Ultra 2 achieves human expert-level on graduate-level science.",
         "유출된 평가 결과에 따르면 제미나이 울트라 2가 대학원 수준 과학 문제에서 인간 전문가 수준에 도달했습니다."),
        ("AI","Nvidia",   False,"VentureBeat",
         "Nvidia Blackwell B200 GPU demand exceeds supply by 10x heading into 2026",
         "엔비디아 블랙웰 B200 GPU, 2026년 앞두고 수요가 공급의 10배",
         "Nvidia's Blackwell B200 supply chain is severely constrained as AI demand surges.",
         "AI 수요 급증으로 엔비디아 블랙웰 B200 공급망이 심각하게 부족한 상황입니다."),
        ("AI","xAI",      True, "The Decoder",
         "xAI Grok 3 rumored to feature real-time web browsing and image generation",
         "xAI 그록 3, 실시간 웹 탐색·이미지 생성 기능 루머",
         "Sources say Grok 3 will integrate real-time web access and native image generation.",
         "소식통에 따르면 그록 3는 실시간 웹 검색과 네이티브 이미지 생성 기능을 통합할 예정입니다."),
        ("AI","Microsoft", False,"Ars Technica",
         "Microsoft Copilot integration reaches 1 billion monthly active users",
         "마이크로소프트 코파일럿, 월간 활성 사용자 10억 명 돌파",
         "Microsoft announced Copilot has exceeded 1 billion monthly active users across its products.",
         "마이크로소프트가 코파일럿의 월간 활성 사용자가 10억 명을 넘어섰다고 발표했습니다."),
        ("AI","Meta",     True, "VentureBeat",
         "Meta Llama 4 Scout achieves GPT-4o parity at fraction of cost, leak suggests",
         "메타 라마 4 스카우트, GPT-4o 수준 성능을 훨씬 낮은 비용에 달성 — 유출",
         "Leaked benchmark results show Meta's Llama 4 Scout matching GPT-4o on key tasks.",
         "유출된 벤치마크 결과에 따르면 메타의 라마 4 스카우트가 주요 과제에서 GPT-4o와 동등한 성능을 보입니다."),
        ("AI","Mistral AI",False,"The Decoder",
         "Mistral AI raises $1B Series C at $6B valuation amid enterprise demand surge",
         "미스트랄 AI, 기업 수요 급증 속 6조원 기업가치로 1조원 시리즈 C 유치",
         "Mistral AI secured a $1 billion Series C round valuing the company at $6 billion.",
         "미스트랄 AI가 기업가치 6조원으로 1조원 규모의 시리즈 C 투자를 유치했습니다."),
    ]

    articles = []
    for sector, company, is_rumor, source, title, title_ko, summary, summary_ko in rows:
        articles.append(Article(
            title=title, title_ko=title_ko,
            link=f"https://example.com/{len(articles)}",
            source=source, published="Mon, 12 May 2025 10:00:00 +0000",
            summary_raw=summary, summary_ko=summary_ko,
            sector=sector, company=company, is_rumor=is_rumor,
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
    is_demo_mode = not arts
    if is_demo_mode:
        arts = _demo_articles()
    _CACHE["v"] = (now, arts)
    return arts


def cache_age_seconds() -> float | None:
    c = _CACHE.get("v")
    return (time.time() - c[0]) if c else None
