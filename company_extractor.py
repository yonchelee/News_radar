"""기사에서 언급된 기업 추출 — 다국어 alias 기반.

word boundary 처리:
- 영어 alias: \\b 경계로 매칭 (AI 같은 짧은 약어 오매칭 방지)
- 한국어/한자: substring 매칭 (CJK는 단어 경계 없음)
- 짧은 영문 약어(2글자 이하)는 대소문자 + 띄어쓰기 엄격
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Company:
    name: str
    aliases: list[str]
    category: str
    category_label: str = ""
    country: str = ""
    industries: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# 회사 사전 — 모바일/EV/반도체/소재 도메인 중심
# ---------------------------------------------------------------------------
COMPANIES: list[Company] = [
    # 한국 테크
    Company("Samsung",     ["Samsung", "삼성", "삼성전자", "三星", "三星电子", "三星電子", "갤럭시", "Galaxy"], "korea_tech", "한국 테크"),
    Company("LG",          ["LG전자", "LG디스플레이", "LG이노텍", " LG ", "엘지", "LG화학", "LG에너지", "LG Energy"], "korea_tech", "한국 테크"),
    Company("SK Hynix",    ["SK Hynix", "SK하이닉스", "하이닉스", "Hynix"], "korea_tech", "한국 테크"),
    Company("SK",          ["SK이노베이션", "SK Innovation", "SK텔레콤", "SK Telecom", "SK온", "SK On"], "korea_tech", "한국 테크"),
    Company("Naver",       ["Naver", "네이버", "NAVER", "Hyper Clova"], "korea_tech", "한국 테크"),
    Company("Kakao",       ["Kakao", "카카오"], "korea_tech", "한국 테크"),
    # 한국 자동차
    Company("Hyundai",     ["Hyundai", "현대자동차", "현대차", "현대 자동차", "Ioniq", "아이오닉"], "korea_auto", "한국 자동차"),
    Company("Kia",         ["Kia", "기아자동차", "기아차", "기아"], "korea_auto", "한국 자동차"),
    # 한국 기타
    Company("POSCO",       ["POSCO", "포스코"], "korea_other", "한국 소재"),
    # 글로벌 테크
    Company("Apple",       ["Apple", "애플", "苹果", "iPhone", "iPad", "MacBook", "macOS", "iOS", "Vision Pro"], "global_tech", "글로벌 테크"),
    Company("Google",      ["Google", "구글", "谷歌", "Pixel", "픽셀", "Android", "Gemini"], "global_tech", "글로벌 테크"),
    Company("Microsoft",   ["Microsoft", "마이크로소프트", "微软", "微軟", "Windows", "Xbox", "Surface", "OpenAI"], "global_tech", "글로벌 테크"),
    Company("Meta",        ["Meta", "메타", "Facebook", "페이스북", "Instagram", "Quest", "Oculus"], "global_tech", "글로벌 테크"),
    Company("Amazon",      ["Amazon", "아마존", "亚马逊", "AWS"], "global_tech", "글로벌 테크"),
    Company("Nvidia",      ["Nvidia", "엔비디아", "英伟达", "NVIDIA"], "global_tech", "글로벌 테크"),
    Company("Qualcomm",    ["Qualcomm", "퀄컴", "高通", "Snapdragon"], "global_tech", "글로벌 테크"),
    Company("Intel",       ["Intel", "인텔", "英特尔"], "global_tech", "글로벌 테크"),
    Company("AMD",         [" AMD ", "에이엠디"], "global_tech", "글로벌 테크"),
    Company("ARM",         [" ARM ", "Arm Ltd"], "global_tech", "글로벌 테크"),
    # 중국 테크/모바일
    Company("Xiaomi",      ["Xiaomi", "샤오미", "小米", "Mi 14", "Mi 15", "Redmi", "레드미"], "china_tech", "중국 테크"),
    Company("Huawei",      ["Huawei", "화웨이", "华为", "Mate ", "Pura "], "china_tech", "중국 테크"),
    Company("OPPO",        ["OPPO", "오포"], "china_tech", "중국 테크"),
    Company("Vivo",        ["Vivo", "비보", "vivo "], "china_tech", "중국 테크"),
    Company("OnePlus",     ["OnePlus", "원플러스", "一加"], "china_tech", "중국 테크"),
    Company("Honor",       ["Honor", "아너", "荣耀"], "china_tech", "중국 테크"),
    # 중국 자동차/배터리
    Company("BYD",         [" BYD ", "比亚迪", "비야디"], "china_auto", "중국 자동차"),
    Company("NIO",         [" NIO ", "蔚来", "니오"], "china_auto", "중국 자동차"),
    Company("Xpeng",       ["Xpeng", "小鹏", "샤오펑"], "china_auto", "중국 자동차"),
    Company("CATL",        ["CATL", "宁德时代", "닝더시대"], "china_auto", "중국 배터리"),
    # 글로벌 자동차
    Company("Tesla",       ["Tesla", "테슬라", "特斯拉", "Cybertruck"], "global_auto", "글로벌 자동차"),
    Company("Ford",        [" Ford ", "포드 자동차"], "global_auto", "글로벌 자동차"),
    Company("GM",          ["General Motors", " GM ", "지엠"], "global_auto", "글로벌 자동차"),
    Company("Rivian",      ["Rivian", "리비안"], "global_auto", "글로벌 자동차"),
    Company("Lucid",       ["Lucid Motors", "루시드"], "global_auto", "글로벌 자동차"),
    Company("BMW",         [" BMW ", "비엠더블유"], "global_auto", "글로벌 자동차"),
    Company("Mercedes",    ["Mercedes", "메르세데스", "Benz", "벤츠"], "global_auto", "글로벌 자동차"),
    Company("Volkswagen",  ["Volkswagen", "폭스바겐"], "global_auto", "글로벌 자동차"),
    # 일본
    Company("Sony",        ["Sony", "소니", "ソニー", "PlayStation", "Xperia"], "japan", "일본"),
    Company("Toyota",      ["Toyota", "도요타", "トヨタ"], "japan", "일본"),
    Company("Panasonic",   ["Panasonic", "파나소닉", "パナソニック"], "japan", "일본"),
    Company("Honda",       ["Honda", "혼다", "ホンダ"], "japan", "일본"),
    # 반도체/공급망
    Company("TSMC",        ["TSMC", "타이완 반도체"], "semi", "반도체"),
    Company("ASML",        ["ASML"], "semi", "반도체"),
    Company("Foxconn",     ["Foxconn", "폭스콘", "富士康", "Hon Hai"], "supply", "공급망"),
    Company("Pegatron",    ["Pegatron", "페가트론"], "supply", "공급망"),
    # 기타 모바일
    Company("Motorola",    ["Motorola", "모토로라", "Moto ", "Razr"], "global_tech", "글로벌 테크"),
    Company("Nokia",       ["Nokia", "노키아"], "global_tech", "글로벌 테크"),
    Company("Asus",        ["Asus", "ASUS", "에이수스", "ROG Phone", "Zenfone"], "global_tech", "글로벌 테크"),
    Company("Lenovo",      ["Lenovo", "레노버", "联想", "ThinkPad"], "china_tech", "중국 테크"),
]

# category → country 매핑
_CATEGORY_TO_COUNTRY = {
    "korea_tech":   "korea",
    "korea_auto":   "korea",
    "korea_other":  "korea",
    "global_tech":  "us",        # global_tech 카테고리에 미국 빅테크 + 기타 다국적 섞여 있음. 회사별 override 아래
    "global_auto":  "us",
    "china_tech":   "china",
    "china_auto":   "china",
    "japan":        "japan",
    "semi":         "taiwan",    # TSMC 기본, ASML override 아래
    "supply":       "taiwan",    # Foxconn 기본, Pegatron 동일
}
# 회사 단위 country override
_COUNTRY_OVERRIDES = {
    "ASML":      "europe",
    "BMW":       "europe",
    "Mercedes":  "europe",
    "Volkswagen":"europe",
    "Nokia":     "europe",
    "ARM":       "europe",
    "Asus":      "taiwan",
    "Lenovo":    "china",
    "Motorola":  "us",
    "Foxconn":   "taiwan",
    "Pegatron":  "taiwan",
    "Sony":      "japan",
    "Toyota":    "japan",
    "Panasonic": "japan",
    "Honda":     "japan",
}
for _c in COMPANIES:
    _c.country = _COUNTRY_OVERRIDES.get(_c.name) or _CATEGORY_TO_COUNTRY.get(_c.category, "")

# 빠른 lookup용
COMPANY_BY_NAME: dict[str, Company] = {c.name: c for c in COMPANIES}
# 회사별 실제 영위 산업 (modal 매핑 — 회사 사업 기준)
# 가능한 산업: mobile, ai, robot, ev, auto, semi, battery, display, wearable,
#              telecom, internet, cloud, materials, appliance, gaming, camera,
#              audio, pc, software, supply, tablet, tv
_INDUSTRIES: dict[str, tuple[str, ...]] = {
    # 한국 테크
    "Samsung":     ("mobile", "semi", "display", "wearable", "appliance"),
    "LG":          ("display", "battery", "appliance"),         # mobile 사업 철수 (2021)
    "SK Hynix":    ("semi",),
    "SK":          ("battery", "telecom"),
    "Naver":       ("ai", "internet"),
    "Kakao":       ("ai", "internet"),
    # 한국 자동차
    "Hyundai":     ("auto", "ev", "robot"),                    # Boston Dynamics
    "Kia":         ("auto", "ev"),
    # 한국 소재
    "POSCO":       ("materials", "battery"),
    # 글로벌 테크
    "Apple":       ("mobile", "ai", "wearable", "pc", "tablet"),
    "Google":      ("ai", "mobile", "internet", "cloud"),
    "Microsoft":   ("ai", "software", "cloud", "gaming"),
    "Meta":        ("ai", "internet", "wearable"),             # Quest VR
    "Amazon":      ("ai", "internet", "cloud"),
    "Nvidia":      ("ai", "semi"),
    "Qualcomm":    ("mobile", "semi", "ai"),
    "Intel":       ("semi", "ai"),
    "AMD":         ("semi", "ai"),
    "ARM":         ("semi",),
    "Motorola":    ("mobile",),
    "Nokia":       ("telecom",),
    "Asus":        ("mobile", "pc"),
    # 중국 테크/모바일
    "Xiaomi":      ("mobile", "ev", "appliance", "wearable"),
    "Huawei":      ("mobile", "telecom", "semi"),
    "OPPO":        ("mobile",),
    "Vivo":        ("mobile",),
    "OnePlus":     ("mobile",),
    "Honor":       ("mobile",),
    "Lenovo":      ("pc", "mobile"),
    # 중국 자동차/배터리
    "BYD":         ("ev", "battery"),
    "NIO":         ("ev",),
    "Xpeng":       ("ev",),
    "CATL":        ("battery",),
    # 글로벌 자동차
    "Tesla":       ("ev", "ai", "robot"),                      # Optimus
    "Ford":        ("auto", "ev"),
    "GM":          ("auto", "ev"),
    "Rivian":      ("ev",),
    "Lucid":       ("ev",),
    "BMW":         ("auto", "ev"),
    "Mercedes":    ("auto", "ev"),
    "Volkswagen":  ("auto", "ev"),
    # 일본
    "Sony":        ("camera", "gaming", "audio"),              # Xperia 매우 미미
    "Toyota":      ("auto", "ev"),
    "Panasonic":   ("battery", "appliance"),
    "Honda":       ("auto", "robot"),                          # ASIMO
    # 반도체/공급망
    "TSMC":        ("semi",),
    "ASML":        ("semi",),
    "Foxconn":     ("supply", "ev"),
    "Pegatron":    ("supply",),
}

# Companies 에 산업 부여
for _c in COMPANIES:
    _c.industries = _INDUSTRIES.get(_c.name, ())

INDUSTRY_LABELS: dict[str, str] = {
    "mobile":    "모바일",
    "ai":        "AI",
    "robot":     "로봇",
    "ev":        "전기차",
    "auto":      "자동차",
    "semi":      "반도체",
    "battery":   "배터리",
    "display":   "디스플레이",
    "wearable":  "웨어러블",
    "telecom":   "통신장비",
    "internet":  "인터넷",
    "cloud":     "클라우드",
    "materials": "소재",
    "appliance": "가전",
    "gaming":    "게이밍",
    "camera":    "카메라",
    "audio":     "오디오",
    "pc":        "PC",
    "software":  "소프트웨어",
    "supply":    "공급망",
    "tablet":    "태블릿",
    "tv":        "TV",
}


def industries_of(name: str) -> tuple[str, ...]:
    c = COMPANY_BY_NAME.get(name)
    return c.industries if c else ()


def industry_labels(name: str) -> list[str]:
    return [INDUSTRY_LABELS.get(i, i) for i in industries_of(name)]



def country_of(name: str) -> str:
    c = COMPANY_BY_NAME.get(name)
    return c.country if c else ""


# ---------------------------------------------------------------------------
# 추출
# ---------------------------------------------------------------------------
_WORD_RE_CACHE: dict[str, re.Pattern] = {}


def _make_pattern(alias: str) -> re.Pattern:
    """영어는 word boundary, CJK/한글은 substring."""
    if alias in _WORD_RE_CACHE:
        return _WORD_RE_CACHE[alias]
    a = alias.strip()
    if re.match(r"^[A-Za-z][A-Za-z0-9 .\-]*$", a):
        # 영어 — \b 경계 (대소문자 무시)
        pat = re.compile(r"\b" + re.escape(a) + r"\b", re.IGNORECASE)
    elif a.startswith(" ") or a.endswith(" "):
        # 짧은 약어용 띄어쓰기 컨벤션 (예: " AMD ", " BYD ") — 그대로
        pat = re.compile(re.escape(a), re.IGNORECASE)
    else:
        # CJK / 한글 — substring (대소문자 무관)
        pat = re.compile(re.escape(a))
    _WORD_RE_CACHE[alias] = pat
    return pat


def extract_companies(title: str, summary: str = "") -> list[str]:
    """제목 + 요약에서 언급된 회사 이름 목록 반환 (Company.name 형식)."""
    text = (title or "") + " " + (summary or "")
    if not text.strip():
        return []
    found: list[str] = []
    for c in COMPANIES:
        for alias in c.aliases:
            if _make_pattern(alias).search(text):
                found.append(c.name)
                break
    return found


def category_label(company_name: str) -> str:
    c = COMPANY_BY_NAME.get(company_name)
    return c.category_label if c else ""


def category_key(company_name: str) -> str:
    c = COMPANY_BY_NAME.get(company_name)
    return c.category if c else ""


# ---------------------------------------------------------------------------
# 카테고리 메타
# ---------------------------------------------------------------------------
COUNTRY_LABELS: dict[str, str] = {
    "korea":  "한국",
    "us":     "미국",
    "china":  "중국",
    "japan":  "일본",
    "europe": "유럽",
    "taiwan": "대만",
}

CATEGORY_LABELS: dict[str, str] = {
    "korea_tech":   "한국 테크",
    "korea_auto":   "한국 자동차",
    "korea_other":  "한국 소재",
    "global_tech":  "글로벌 테크",
    "global_auto":  "글로벌 자동차",
    "china_tech":   "중국 테크",
    "china_auto":   "중국 자동차",
    "japan":        "일본",
    "semi":         "반도체",
    "supply":       "공급망",
}
