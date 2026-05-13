"""카테고리 분류 테스트 — python3 test_classify.py 로 실행"""
from news_crawler import _detect_mech_category, _detect_top_category

# (기사 텍스트, 기대 mech_cat, 기대 top_cat)
TESTS = [
    # ── 소재·재질 정탐 ──────────────────────────────────────
    ("Samsung Galaxy S26 titanium alloy frame revealed",          "소재·재질",    "기술·개발"),
    ("Apple using magnesium alloy for new MacBook chassis",       "소재·재질",    "기술·개발"),
    # ── 소재 오탐 방지 (Material Design) ───────────────────
    ("Google updates Material Design language for Android",       "기타",        "마케팅·출시"),
    # ── 구동·관절 정탐 ──────────────────────────────────────
    ("Galaxy Z Fold hinge mechanism durability test",             "구동·관절",    "기술·개발"),
    ("Boston Dynamics Atlas actuator joint upgrade",              "구동·관절",    "기술·개발"),
    # ── 구동 오탐 방지 (Motorola) ──────────────────────────
    ("Motorola launches new Edge 50 smartphone",                  "기타",        "마케팅·출시"),
    # ── 마케팅·출시 ─────────────────────────────────────────
    ("Samsung announces Galaxy S26 launch date and price",        "기타",        "마케팅·출시"),
    ("Apple unveils iPhone 17 Pro at WWDC keynote event",         "기타",        "마케팅·출시"),
    # ── AI/SW → 기술 분류 억제 ─────────────────────────────
    ("Google announces Gemini Intelligence feature for Android",  "기타",        "마케팅·출시"),
    ("OpenAI releases new GPT-5 model with improved reasoning",   "기타",        "마케팅·출시"),
    # ── 열관리 정탐 ─────────────────────────────────────────
    ("Galaxy S26 vapor chamber thermal management cooling system","열관리·냉각",  "기술·개발"),
    # ── 열관리 오탐 방지 (fan 커뮤니티) ────────────────────
    ("Fans excited about Samsung Galaxy launch event",            "기타",        "마케팅·출시"),
    # ── 사양·치수 정탐 ──────────────────────────────────────
    ("Galaxy S26 Ultra specs: 6.8 inch display 5000mah battery", "사양·치수",    "기술·개발"),
    # ── 사양 오탐 방지 (Instagram) ─────────────────────────
    ("Samsung Instagram collaboration campaign announced",        "기타",        "마케팅·출시"),
    # ── 제조·공정 정탐 ──────────────────────────────────────
    ("TSMC 2nm semiconductor process mass production yield",      "제조·공정",    "기술·개발"),
    # ── 사업·전략 정탐 ──────────────────────────────────────
    ("Samsung reports record revenue Q1 earnings profit",         "기타",        "사업·전략"),
    # ── 사양 정탐 (치수) ────────────────────────────────────
    ("iPhone 17 weight dimensions specification leak",            "사양·치수",    "기술·개발"),
]


def run():
    pass_cnt = 0
    fail_cases = []

    for text, exp_mech, exp_top in TESTS:
        mech = _detect_mech_category(text)
        top  = _detect_top_category(text, mech)
        ok   = (mech == exp_mech) and (top == exp_top)
        if ok:
            pass_cnt += 1
            print(f"✅  {text[:55]}")
        else:
            fail_cases.append((text, exp_mech, exp_top, mech, top))
            print(f"❌  {text[:55]}")
            print(f"    기대: mech={exp_mech}, top={exp_top}")
            print(f"    실제: mech={mech}, top={top}")

    total = len(TESTS)
    print(f"\n{'='*60}")
    print(f"결과: {pass_cnt}/{total} 통과  ({round(pass_cnt/total*100)}%)")
    if fail_cases:
        print(f"실패 {len(fail_cases)}건 — 위 ❌ 항목 확인")
    else:
        print("모두 통과!")


if __name__ == "__main__":
    run()
