"""기사 자동 번역 — LLM 백엔드 활용 배치 처리.

사용:
    from translator import translate_batch
    items = [{"id": "0", "text": "iPhone 17 launches"}, ...]
    out = translate_batch(items, target_lang="ko", chat_fn=my_llm)
    # → [{"id": "0", "text": "iPhone 17 출시"}, ...]

캐시는 외부에서 관리 (예: st.session_state.translation_cache).
이 모듈은 캐시 의존성 없이 stateless.
"""
from __future__ import annotations

import hashlib
import re
from typing import Callable


LANG_NAME = {
    "ko": "한국어",
    "en": "영어",
}


def _system_prompt(target_lang: str) -> str:
    if target_lang == "ko":
        return (
            "당신은 뉴스 헤드라인 번역가입니다. 주어진 텍스트를 자연스러운 한국어로 번역합니다.\n\n"
            "규칙:\n"
            "1. 모델명/회사명/기술용어(iPhone, Samsung, OpenAI, GPT, LLM, AI, EV, USB-C, AMOLED, "
            "Snapdragon, Pixel, Tesla, Galaxy 등) 는 영문 그대로 유지.\n"
            "2. 이미 한국어인 텍스트는 그대로 반환 (재번역 X).\n"
            "3. 중국어/일본어/영어 → 자연스러운 한국어 표현. 직역 X.\n"
            "4. 출력 형식 정확히 준수 — 각 항목 [id] 번역텍스트 형식, 한 줄씩, 추가 설명/메타 일체 금지.\n"
            "5. 마크다운/이모지/접두사 사용 금지. 번역 텍스트만."
        )
    return (
        "You are a news headline translator. Translate the given text to natural English.\n\n"
        "Rules:\n"
        "1. Keep brand/model names/technical terms (Samsung, Galaxy, iPhone, OpenAI, GPT, "
        "Snapdragon, Tesla, AMOLED, USB-C, LLM, AI, EV, etc) unchanged.\n"
        "2. Text already in English: return as is (no re-translation).\n"
        "3. Korean/Chinese/Japanese → idiomatic English, not literal.\n"
        "4. Output exactly: `[id] translated_text` one per line, no extra commentary.\n"
        "5. No markdown, no emoji, no prefix labels — translation text only."
    )


_LINE_RE = re.compile(r"^\s*\[(\d+)\]\s*(.+?)\s*$")


def _parse_response(resp: str) -> dict[str, str]:
    """LLM 응답을 {id: translated} 로 파싱."""
    out: dict[str, str] = {}
    for line in resp.splitlines():
        m = _LINE_RE.match(line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def text_hash(text: str, target_lang: str) -> str:
    """캐시 키용 짧은 해시."""
    h = hashlib.sha1(f"{target_lang}:{text}".encode("utf-8")).hexdigest()
    return h[:16]


def translate_batch(
    items: list[dict],
    target_lang: str,
    chat_fn: Callable[[list[dict]], str],
    batch_size: int = 10,
    max_chars_per_item: int = 400,
) -> list[dict]:
    """items: [{"id": "0", "text": "..."}, ...]
    target_lang: "ko" | "en"
    chat_fn(messages) -> response string (OpenAI/Groq 호환).

    실패한 항목은 원문 그대로 반환.
    """
    if not items or target_lang not in LANG_NAME:
        return items

    out_by_id: dict[str, str] = {}
    sys_prompt = _system_prompt(target_lang)

    for start in range(0, len(items), batch_size):
        chunk = items[start:start + batch_size]
        lines = []
        for it in chunk:
            txt = (it.get("text") or "").strip().replace("\n", " ")
            if len(txt) > max_chars_per_item:
                txt = txt[:max_chars_per_item] + "..."
            lines.append(f"[{it['id']}] {txt}")
        user_msg = "\n".join(lines)
        try:
            resp = chat_fn([
                {"role": "system", "content": sys_prompt},
                {"role": "user",   "content": user_msg},
            ])
            parsed = _parse_response(resp or "")
            for it in chunk:
                if it["id"] in parsed:
                    out_by_id[it["id"]] = parsed[it["id"]]
        except Exception:
            continue   # 실패 항목 silent skip

    # 결과 매핑: 번역 있으면 사용, 없으면 원문 그대로
    return [
        {"id": it["id"], "text": out_by_id.get(it["id"], it.get("text", ""))}
        for it in items
    ]


def detect_lang(text: str) -> str:
    """매우 간단한 언어 감지 (한/중/일/그 외 영문). 정확도 낮지만 빠름."""
    if not text:
        return "en"
    # 한글 (가-힣)
    if re.search(r"[가-힯]", text):
        return "ko"
    # 한자 (CJK Unified)
    if re.search(r"[一-鿿]", text):
        # 일본어 가나 검사
        if re.search(r"[぀-ゟ゠-ヿ]", text):
            return "ja"
        return "zh"
    # 일본어 단독 (가나)
    if re.search(r"[぀-ゟ゠-ヿ]", text):
        return "ja"
    return "en"
