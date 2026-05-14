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
def _chat_groq(messages, model, api_key, temperature, timeout) -> str:
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
        r.raise_for_status()
    except requests.RequestException as exc:
        body = ""
        try:
            body = exc.response.text[:200] if exc.response is not None else ""
        except Exception:
            pass
        raise LLMError(f"Groq 요청 실패: {exc} {body}") from exc
    data = r.json()
    return ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()


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
