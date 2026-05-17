"""LLM 클라이언트 — 다중 backend.

지원 backend:
- "ollama"  : 로컬 Ollama (http://localhost:11434, Gemma 3) — 영채님 PC dev용
- "groq"    : Groq API (llama-3.3-70b-versatile, free tier) — Streamlit Cloud primary
- "gemini"  : Google AI Studio (gemini-2.0-flash)

공통 인터페이스:
    is_available(backend, **opts) -> bool
    chat(messages, backend, **opts) -> str
    summarize_article(title, body, backend, **opts) -> str
"""
from __future__ import annotations

import json
import time
from typing import Iterator, Optional

import requests


# ---------------------------------------------------------------------------
# 시스템 프롬프트 (백엔드 무관)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "너는 삼성/LG 등 전자/모빌리티 기업의 '선행기구개발 그룹'에서 일하는 시니어 "
    "기구개발 엔지니어다. 주어진 뉴스 기사를 읽고, 동료 기구 엔지니어들이 즉시 "
    "활용 가능한 형태로 분석해 **반드시 한국어로** 답한다.\n\n"
    "## 언어 처리 규칙\n"
    "- 원문이 영어인 경우: 핵심을 한국어로 의역 요약. 고유명사·모델명·기술용어(예: SoC, AMOLED, USB-C, mmWave)는 원문 표기 유지.\n"
    "- 원문이 중국어(번체/간체)인 경우: 자연스러운 한국어로 번역 요약. 회사/제품 한자명은 한자(한국어 번역) 병기 (예: 小米 17 Max(샤오미 17 맥스)). 측정 단위는 한국어 표기.\n"
    "- 원문이 일본어인 경우: 동일하게 자연스러운 한국어로.\n"
    "- 출력은 무조건 한국어 — 영어/중국어 본문이 그대로 섞이지 않게.\n\n"
    "## 분석 시 반드시 포함\n"
    "1) 핵심 기술 사양 (치수/두께/공차/강성/내구 사양 등 수치 위주)\n"
    "2) 사용 소재 (합금, 복합재, 폴리머 등 — 등급/규격까지)\n"
    "3) 가공/조립 공법 (다이캐스팅, MIM, 사출, 프레스, 레이저 용접, 본딩 등)\n"
    "4) 경쟁사 동향과 차별 포인트\n"
    "5) 우리 그룹의 선행개발 관점 시사점 (양산 적용 가능성/리스크)\n\n"
    "## 출력 규칙\n"
    "- 마크다운 불릿 형식. 추측은 '추정'이라고 명시.\n"
    "- 마케팅 문구 제거, 엔지니어링 사실만 간결히.\n"
    "- 원문에 정보가 없는 항목은 '본문 정보 없음'으로 표기 (지어내지 말 것)."
)


# ---------------------------------------------------------------------------
# 백엔드별 기본값
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_DEFAULT_MODEL = "gemma3"

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
]

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_DEFAULT_MODEL = "gemini-2.0-flash"
GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
]

# 호환용 alias
DEFAULT_MODEL = OLLAMA_DEFAULT_MODEL


class LLMError(RuntimeError):
    pass

# 하위 호환
OllamaError = LLMError


# ---------------------------------------------------------------------------
# 백엔드 가용성 + 모델 목록
# ---------------------------------------------------------------------------
def is_available(
    backend: str = "ollama",
    base_url: str = OLLAMA_BASE_URL,
    api_key: str = "",
    timeout: int = 3,
) -> bool:
    """선택한 백엔드가 호출 가능한 상태인지 확인."""
    if backend == "ollama":
        try:
            r = requests.get(f"{base_url}/api/tags", timeout=timeout)
            return r.status_code == 200
        except Exception:
            return False
    if backend == "groq":
        return bool(api_key)   # 키만 있으면 OK (실제 호출은 chat에서)
    if backend == "gemini":
        return bool(api_key)
    return False


def list_models(
    backend: str = "ollama",
    base_url: str = OLLAMA_BASE_URL,
    api_key: str = "",
    timeout: int = 5,
) -> list[str]:
    if backend == "ollama":
        try:
            r = requests.get(f"{base_url}/api/tags", timeout=timeout)
            r.raise_for_status()
            data = r.json()
            return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            return []
    if backend == "groq":
        return GROQ_MODELS
    if backend == "gemini":
        return GEMINI_MODELS
    return []


# ---------------------------------------------------------------------------
# 통합 chat
# ---------------------------------------------------------------------------
def chat(
    messages: list[dict],
    backend: str = "ollama",
    model: Optional[str] = None,
    base_url: str = OLLAMA_BASE_URL,
    api_key: str = "",
    temperature: float = 0.3,
    timeout: int = 180,
) -> str:
    """선택 백엔드로 chat completion. 응답 string 반환."""
    if backend == "ollama":
        return _chat_ollama(messages, model or OLLAMA_DEFAULT_MODEL, base_url, temperature, timeout)
    if backend == "groq":
        if not api_key:
            raise LLMError("Groq API 키가 설정되지 않았습니다. Streamlit secrets에 GROQ_API_KEY 추가하세요.")
        return _chat_groq(messages, model or GROQ_DEFAULT_MODEL, api_key, temperature, timeout)
    if backend == "gemini":
        if not api_key:
            raise LLMError("Gemini API 키가 설정되지 않았습니다. Streamlit secrets에 GEMINI_API_KEY 추가하세요.")
        return _chat_gemini(messages, model or GEMINI_DEFAULT_MODEL, api_key, temperature, timeout)
    raise LLMError(f"알 수 없는 backend: {backend}")


# ---------------------------------------------------------------------------
# Ollama (로컬)
# ---------------------------------------------------------------------------
def _chat_ollama(messages, model, base_url, temperature, timeout) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    try:
        r = requests.post(f"{base_url}/api/chat", json=payload, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as exc:
        raise LLMError(f"Ollama 요청 실패: {exc}") from exc
    return (r.json().get("message") or {}).get("content", "").strip()


def chat_stream(
    messages: list[dict],
    model: str = OLLAMA_DEFAULT_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    temperature: float = 0.3,
    timeout: int = 180,
) -> Iterator[str]:
    """Ollama 전용 스트리밍 (Groq/Gemini는 non-streaming만)."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature},
    }
    try:
        with requests.post(f"{base_url}/api/chat", json=payload, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                content = (chunk.get("message") or {}).get("content", "")
                if content:
                    yield content
                if chunk.get("done"):
                    break
    except requests.RequestException as exc:
        raise LLMError(f"Ollama 스트리밍 실패: {exc}") from exc


# ---------------------------------------------------------------------------
# Groq (OpenAI 호환)
# ---------------------------------------------------------------------------
# Groq fallback 순서 — 큰 모델부터 작은 모델로
GROQ_FALLBACK_CHAIN = [
    "llama-3.3-70b-versatile",   # 1차 (강력하나 TPM 작음)
    "llama-3.1-8b-instant",      # 2차 (TPM 큼, 빠름)
    "gemma2-9b-it",              # 3차
]


def _post_groq_once(model, messages, api_key, temperature, timeout):
    """Groq 단일 호출 — (status_code, response_or_text, retry_after_sec).

    raises LLMError only on non-recoverable errors (network/auth).
    For 429/5xx, returns the response info so caller can decide.
    """
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.post(GROQ_URL, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        raise LLMError(f"Groq 네트워크 실패: {exc}") from exc
    retry_after = 0.0
    try:
        retry_after = float(r.headers.get("retry-after", "0") or "0")
    except Exception:
        retry_after = 0.0
    if r.status_code == 200:
        return 200, r.json(), 0.0
    return r.status_code, r.text[:400], retry_after


def _chat_groq(messages, model, api_key, temperature, timeout) -> str:
    """Groq chat completion w/ 429 자동 fallback + retry.

    Strategy:
      1) Try requested model
      2) On 429: walk fallback chain (skip already-tried), each smaller model
      3) If entire chain hits 429: sleep min(retry_after, 10s) and retry chain once
      4) If still 429: raise LLMError("Groq rate limit") with clear message
    """
    # Start from requested model, then continue down the chain
    tried: list[str] = []
    queue = [model] if model else []
    for m in GROQ_FALLBACK_CHAIN:
        if m not in queue:
            queue.append(m)

    last_status, last_text, last_retry = None, "", 0.0

    for attempt_round in range(2):  # 2번 round (첫 round, wait 후 second round)
        for m in queue:
            if m in tried:
                continue
            status, body_or_data, retry_after = _post_groq_once(m, messages, api_key, temperature, timeout)
            tried.append(m)
            if status == 200:
                content = ((body_or_data.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
                # 첫 모델이 아니면 fallback 표기 (optional)
                if attempt_round > 0 or m != (model or GROQ_DEFAULT_MODEL):
                    # 응답 앞에 [모델 표기] 주석 (silent — 일부 호출 경로는 raw 응답 필요하니 추가 X)
                    pass
                return content
            if status == 429:
                last_status, last_text, last_retry = 429, body_or_data, retry_after
                continue  # 다음 모델 시도
            # 4xx/5xx other: raise immediately
            raise LLMError(f"Groq 요청 실패 (HTTP {status}): {body_or_data}")

        # 한 round 다 돌았으면 (모두 429): wait
        if attempt_round == 0:
            tried = []  # 다음 round 위해 reset
            wait_s = min(max(last_retry, 0), 15)
            if wait_s <= 0:
                wait_s = 10.0  # default
            time.sleep(wait_s)

    # 두 round 다 실패
    raise LLMError(
        f"Groq rate limit (429): {last_text[:200] if last_text else 'TPM 초과. 잠시 후 다시 시도'}"
    )


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------
def _chat_gemini(messages, model, api_key, temperature, timeout) -> str:
    # OpenAI 형식 → Gemini 형식 변환
    system_text = ""
    contents = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            system_text += content + "\n"
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": content}]})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": content}]})
    body = {
        "contents": contents,
        "generationConfig": {"temperature": temperature},
    }
    if system_text:
        body["systemInstruction"] = {"parts": [{"text": system_text}]}
    url = f"{GEMINI_BASE}/{model}:generateContent?key={api_key.strip()}"
    try:
        r = requests.post(url, json=body, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as exc:
        body_txt = ""
        try:
            body_txt = exc.response.text[:200] if exc.response is not None else ""
        except Exception:
            pass
        raise LLMError(f"Gemini 요청 실패: {exc} {body_txt}") from exc
    data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Gemini 응답 파싱 실패: {data}") from exc


# ---------------------------------------------------------------------------
# 요약 헬퍼
# ---------------------------------------------------------------------------
def summarize_article(
    title: str,
    body: str,
    backend: str = "ollama",
    model: Optional[str] = None,
    base_url: str = OLLAMA_BASE_URL,
    api_key: str = "",
    extra_instruction: str = "",
) -> str:
    user_msg = (
        f"[기사 제목]\n{title}\n\n"
        f"[기사 본문]\n{body[:6000]}\n\n"
        "위 기사를 기구개발 엔지니어 관점으로 요약해줘. "
        "마지막에 '핵심 불릿 5개' 섹션을 별도로 추가해라."
    )
    if extra_instruction.strip():
        user_msg += f"\n\n[추가 지시]\n{extra_instruction.strip()}"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    return chat(messages, backend=backend, model=model, base_url=base_url, api_key=api_key)
