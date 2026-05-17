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
import os
import re
import sqlite3
import time
import threading
from typing import Callable, Optional


LANG_NAME = {
    "ko": "한국어",
    "en": "영어",
}

# Groq 8b 모델 — TPM 30000 (70b는 12000). 번역에 충분히 좋음.
PREFERRED_MODEL_GROQ = "llama-3.1-8b-instant"


# ---------------------------------------------------------------------------
# SQLite persistent cache (translation hash → translated text)
# ---------------------------------------------------------------------------
_DB_PATH = os.environ.get("TRANSLATION_CACHE_DB", "/tmp/translations.db")
_DB_LOCK = threading.RLock()
_DB_CONN: Optional[sqlite3.Connection] = None


def _db() -> sqlite3.Connection:
    """Lazy SQLite connection (process-shared)."""
    global _DB_CONN
    if _DB_CONN is None:
        with _DB_LOCK:
            if _DB_CONN is None:
                conn = sqlite3.connect(_DB_PATH, check_same_thread=False, timeout=5.0)
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS translations ("
                    "hash TEXT PRIMARY KEY, lang TEXT, text TEXT, created REAL)"
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_lang ON translations(lang)")
                conn.commit()
                _DB_CONN = conn
    return _DB_CONN


def cache_get(text_hash: str) -> Optional[str]:
    try:
        with _DB_LOCK:
            cur = _db().execute(
                "SELECT text FROM translations WHERE hash = ?", (text_hash,)
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception:
        return None


def cache_put(text_hash: str, lang: str, text: str) -> None:
    try:
        with _DB_LOCK:
            _db().execute(
                "INSERT OR REPLACE INTO translations (hash, lang, text, created) "
                "VALUES (?, ?, ?, ?)",
                (text_hash, lang, text, time.time()),
            )
            _db().commit()
    except Exception:
        pass


def cache_size() -> int:
    try:
        with _DB_LOCK:
            cur = _db().execute("SELECT COUNT(*) FROM translations")
            return cur.fetchone()[0]
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Short-text skip — 30자 미만 또는 한글 50%+ 이상은 번역 skip
# ---------------------------------------------------------------------------
def should_skip(text: str, target_lang: str) -> bool:
    """번역 불필요 판정 — 모델명/숫자/짧은 텍스트 등."""
    if not text or len(text.strip()) < 30:
        return True
    # 이미 target_lang 이면 skip
    if target_lang == "ko":
        # 한글 문자 비율 50% 이상이면 이미 한국어
        hangul = sum(1 for c in text if "가" <= c <= "힣" or "ᄀ" <= c <= "ᇿ")
        if hangul / max(len(text), 1) >= 0.5:
            return True
    elif target_lang == "en":
        # ASCII 비율 80% 이상이면 이미 영어
        ascii_n = sum(1 for c in text if ord(c) < 128)
        if ascii_n / max(len(text), 1) >= 0.8:
            return True
    return False


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
    batch_size: int = 5,
    max_chars_per_item: int = 400,
    sleep_between_batches: float = 0.5,
    max_items: int | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
    use_disk_cache: bool = True,
) -> list[dict]:
    """Batch translate items via chat_fn.

    items: [{"id": "0", "text": "..."}, ...]
    target_lang: "ko" | "en"
    chat_fn(messages) -> response string (OpenAI/Groq 호환).

    Improvements vs v1:
      - batch_size 기본 10 → 5 (Groq TPM 친화적)
      - 배치 간 sleep_between_batches 초 대기 (rate-limit 완화)
      - 429 에러 발생 시 exponential backoff (1, 2, 4, 8초) 후 batch 재시도
      - max_items: 한 호출에서 최대 처리할 항목 수 (lazy translation 용)
      - progress_cb(done, total): 진행률 콜백

    실패한 항목은 원문 그대로 반환.
    """
    if not items or target_lang not in LANG_NAME:
        return items

    # 0) Pre-filter — should_skip (한글 비율 등) + SQLite cache hit
    pending_items: list[dict] = []
    out_by_id: dict[str, str] = {}
    for it in items:
        txt = (it.get("text") or "").strip()
        # short / already-target-lang → 원문 그대로
        if should_skip(txt, target_lang):
            out_by_id[it["id"]] = txt
            continue
        h = text_hash(txt, target_lang)
        if use_disk_cache:
            hit = cache_get(h)
            if hit is not None:
                out_by_id[it["id"]] = hit
                continue
        pending_items.append({"id": it["id"], "text": txt, "_hash": h})

    # 캐시 100% 히트면 LLM 호출 없이 끝
    if not pending_items:
        return [
            {"id": it["id"], "text": out_by_id.get(it["id"], it.get("text", ""))}
            for it in items
        ]

    work_items = pending_items if max_items is None else pending_items[:max_items]
    sys_prompt = _system_prompt(target_lang)
    total = len(work_items)
    done = 0

    for start in range(0, total, batch_size):
        chunk = work_items[start:start + batch_size]
        lines = []
        for it in chunk:
            txt = (it.get("text") or "").strip().replace("\n", " ")
            if len(txt) > max_chars_per_item:
                txt = txt[:max_chars_per_item] + "..."
            lines.append(f"[{it['id']}] {txt}")
        user_msg = "\n".join(lines)
        # Backoff retry for 429
        for attempt, backoff in enumerate([0, 1, 2, 4, 8]):
            if backoff > 0:
                time.sleep(backoff)
            try:
                resp = chat_fn([
                    {"role": "system", "content": sys_prompt},
                    {"role": "user",   "content": user_msg},
                ])
                parsed = _parse_response(resp or "")
                for it in chunk:
                    if it["id"] in parsed:
                        translated = parsed[it["id"]]
                        out_by_id[it["id"]] = translated
                        # persist to SQLite (best effort)
                        if use_disk_cache and "_hash" in it:
                            cache_put(it["_hash"], target_lang, translated)
                break  # 성공 — exit retry loop
            except Exception as e:
                msg = str(e).lower()
                # 429 또는 rate limit 키워드면 backoff 후 재시도
                if ("429" in msg) or ("rate limit" in msg) or ("rate_limit" in msg) or ("tpm" in msg):
                    if attempt < 4:  # 마지막 시도 아니면 retry
                        continue
                # 그 외 에러: 이 배치 포기 (원문 fallback)
                break

        done += len(chunk)
        if progress_cb is not None:
            try:
                progress_cb(done, total)
            except Exception:
                pass
        # 마지막 배치가 아니면 sleep
        if start + batch_size < total and sleep_between_batches > 0:
            time.sleep(sleep_between_batches)

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
