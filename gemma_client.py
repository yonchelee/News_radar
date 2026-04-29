"""로컬 Ollama(Gemma 3) 클라이언트.

http://localhost:11434/api/chat 엔드포인트를 사용한다.
"""
from __future__ import annotations

import json
from typing import Iterator

import requests

OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "gemma3"

SYSTEM_PROMPT = (
    "너는 삼성/LG 등 전자/모빌리티 기업의 '선행기구개발 그룹'에서 일하는 시니어 "
    "기구개발 엔지니어다. 주어진 뉴스 기사를 읽고, 동료 기구 엔지니어들이 즉시 "
    "활용 가능한 형태로 분석해 한국어로 답한다.\n\n"
    "분석 시 반드시 다음 관점을 포함하라:\n"
    "1) 핵심 기술 사양 (치수/두께/공차/강성/내구 사양 등 수치 위주)\n"
    "2) 사용 소재 (합금, 복합재, 폴리머 등 — 등급/규격까지)\n"
    "3) 가공/조립 공법 (다이캐스팅, MIM, 사출, 프레스, 레이저 용접, 본딩 등)\n"
    "4) 경쟁사 동향과 차별 포인트\n"
    "5) 우리 그룹의 선행개발 관점 시사점 (양산 적용 가능성/리스크)\n\n"
    "출력은 마크다운 불릿 형식. 추측은 '추정'이라고 명시하라. "
    "마케팅 문구는 제거하고 엔지니어링 사실만 간결히 전달한다."
)


class OllamaError(RuntimeError):
    pass


def is_available(base_url: str = OLLAMA_BASE_URL, timeout: int = 3) -> bool:
    try:
        r = requests.get(f"{base_url}/api/tags", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def list_models(base_url: str = OLLAMA_BASE_URL, timeout: int = 5) -> list[str]:
    try:
        r = requests.get(f"{base_url}/api/tags", timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def chat(
    messages: list[dict],
    model: str = DEFAULT_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    temperature: float = 0.3,
    timeout: int = 180,
) -> str:
    """단일 응답(non-streaming)을 받아 문자열로 반환."""
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
        raise OllamaError(f"Ollama 요청 실패: {exc}") from exc

    data = r.json()
    return (data.get("message") or {}).get("content", "").strip()


def chat_stream(
    messages: list[dict],
    model: str = DEFAULT_MODEL,
    base_url: str = OLLAMA_BASE_URL,
    temperature: float = 0.3,
    timeout: int = 180,
) -> Iterator[str]:
    """토큰 단위 스트리밍 응답."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature},
    }
    try:
        with requests.post(
            f"{base_url}/api/chat", json=payload, stream=True, timeout=timeout
        ) as r:
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
        raise OllamaError(f"Ollama 스트리밍 실패: {exc}") from exc


def summarize_article(
    title: str,
    body: str,
    model: str = DEFAULT_MODEL,
    extra_instruction: str = "",
) -> str:
    """기사 요약을 위한 헬퍼."""
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
    return chat(messages, model=model)
