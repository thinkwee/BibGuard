"""
LLM-based citation relevance evaluator.
Supports OpenAI, Anthropic, DeepSeek, Gemini, vLLM, and Ollama backends.
"""
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Tuple
from enum import Enum
import os

import requests

logger = logging.getLogger(__name__)


class LLMBackend(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    VLLM = "vllm"
    OLLAMA = "ollama"
    DEEPSEEK = "deepseek"


# Map backend → environment variable name for the API key.
_BACKEND_ENV = {
    LLMBackend.OPENAI: "OPENAI_API_KEY",
    LLMBackend.ANTHROPIC: "ANTHROPIC_API_KEY",
    LLMBackend.GEMINI: "GEMINI_API_KEY",
    LLMBackend.DEEPSEEK: "DEEPSEEK_API_KEY",
    LLMBackend.VLLM: "VLLM_API_KEY",
    LLMBackend.OLLAMA: "",  # local, no key
}

# Order in which we auto-detect a usable backend when the user hasn't picked
# one explicitly. Cheapest/fastest first.
_AUTODETECT_ORDER = [
    LLMBackend.GEMINI,
    LLMBackend.OPENAI,
    LLMBackend.DEEPSEEK,
    LLMBackend.ANTHROPIC,
    LLMBackend.OLLAMA,
]


def autodetect_backend() -> Optional[Tuple[LLMBackend, str]]:
    """
    Find the first backend that has credentials in the environment.

    Returns (backend, api_key) or None. For Ollama we attempt a localhost
    probe so users with `ollama serve` running get auto-selected with no
    config.
    """
    for backend in _AUTODETECT_ORDER:
        env = _BACKEND_ENV.get(backend, "")
        if env:
            key = os.environ.get(env, "").strip()
            if key:
                return backend, key
        elif backend == LLMBackend.OLLAMA:
            # Local probe — small timeout so absence isn't painful.
            try:
                r = requests.get("http://localhost:11434/api/tags", timeout=1.0)
                if r.status_code == 200:
                    return backend, ""
            except requests.RequestException:
                continue
    return None


@dataclass
class EvaluationResult:
    """Result of LLM citation evaluation."""
    entry_key: str
    relevance_score: int  # 1-5
    is_relevant: bool
    explanation: str
    context_used: str
    abstract_used: str
    citation_role: str = ""  # baseline | method | dataset | counterexample | survey | motivation | other
    line_number: Optional[int] = None
    file_path: Optional[str] = None
    error: Optional[str] = None

    @property
    def score_label(self) -> str:
        labels = {
            1: "Not Relevant",
            2: "Marginally Relevant",
            3: "Somewhat Relevant",
            4: "Relevant",
            5: "Highly Relevant"
        }
        return labels.get(self.relevance_score, "Unknown")


class LLMEvaluator:
    """Evaluates citation relevance using LLM."""
    
    PROMPT_TEMPLATE = """You are an expert academic reviewer. Given a citation context from a LaTeX document and the cited paper's abstract, evaluate whether this citation is appropriate and relevant, and identify the citation's role in the manuscript.

## Citation Context (from the manuscript):
{context}

## Cited Paper's Abstract:
{abstract}

## Task:
Evaluate the relevance and appropriateness of this citation. Consider:
1. Does the citation support the claim being made in the context?
2. Is the cited paper's topic related to the discussion?
3. Is this citation necessary, or could it be replaced with a more relevant one?
4. What is the *role* of this citation in the manuscript?

## Citation roles (pick exactly one):
- "baseline": cited paper is used/compared as a baseline or prior method.
- "method": cited paper introduces a method that the manuscript builds on or uses directly.
- "dataset": cited paper provides a dataset/benchmark the manuscript uses.
- "counterexample": cited to show a contrary finding or argue against.
- "survey": cited as a survey/overview reference.
- "motivation": cited to motivate the problem (background, application, statistics).
- "other": none of the above clearly applies.

## Response Format:
Respond with ONE JSON object, no other text:
{{
    "relevance_score": <integer 1-5>,
    "is_relevant": <true|false>,
    "citation_role": "<one of: baseline|method|dataset|counterexample|survey|motivation|other>",
    "explanation": "<1-2 sentences>"
}}

Score guide: 1=Not relevant, 2=Marginally, 3=Somewhat, 4=Relevant, 5=Highly relevant.
STRICTLY FOLLOW THE JSON FORMAT."""

    def __init__(
        self,
        backend: LLMBackend = LLMBackend.GEMINI,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        self.backend = backend
        self.api_key = api_key or os.environ.get(f"{backend.name}_API_KEY")
        
        # Set defaults based on backend (cheap, fast models that exist)
        if backend == LLMBackend.OPENAI:
            self.endpoint = endpoint or "https://api.openai.com/v1/chat/completions"
            self.model = model or "gpt-4o-mini"
        elif backend == LLMBackend.ANTHROPIC:
            self.endpoint = endpoint or "https://api.anthropic.com/v1/messages"
            self.model = model or "claude-haiku-4-5-20251001"
        elif backend == LLMBackend.DEEPSEEK:
            self.endpoint = endpoint or "https://api.deepseek.com/chat/completions"
            self.model = model or "deepseek-chat"
        elif backend == LLMBackend.OLLAMA:
            self.endpoint = endpoint or "http://localhost:11434/api/generate"
            self.model = model or "qwen2.5:3b-instruct"
        elif backend == LLMBackend.VLLM:
            self.endpoint = endpoint or "http://localhost:8000/v1/chat/completions"
            self.model = model or "Qwen/Qwen2.5-3B-Instruct"
        elif backend == LLMBackend.GEMINI:
            self.endpoint = endpoint or "https://generativelanguage.googleapis.com/v1beta/models"
            self.model = model or "gemini-2.5-flash"
    
    # Retry config for transient LLM failures (rate limits, server errors, JSON issues).
    MAX_ATTEMPTS = 3
    RETRY_BASE_DELAY = 1.5  # seconds, exponential

    def evaluate(self, entry_key: str, context: str, abstract: str) -> EvaluationResult:
        """Evaluate citation relevance with retries on transient errors."""
        if not context or not abstract:
            return EvaluationResult(
                entry_key=entry_key,
                relevance_score=0,
                is_relevant=False,
                explanation="Missing context or abstract",
                context_used=context,
                abstract_used=abstract,
                error="Missing context or abstract for evaluation"
            )

        prompt = self.PROMPT_TEMPLATE.format(context=context, abstract=abstract)

        last_err: Optional[str] = None
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                if self.backend in (LLMBackend.OPENAI, LLMBackend.DEEPSEEK, LLMBackend.VLLM):
                    response = self._call_openai_compatible(prompt)
                elif self.backend == LLMBackend.ANTHROPIC:
                    response = self._call_anthropic(prompt)
                elif self.backend == LLMBackend.OLLAMA:
                    response = self._call_ollama(prompt)
                elif self.backend == LLMBackend.GEMINI:
                    response = self._call_gemini(prompt)
                else:
                    raise ValueError(f"Unknown backend: {self.backend}")

                parsed = self._parse_response(entry_key, response, context, abstract)
                # Successful structured parse → return.
                if parsed.error is None:
                    return parsed
                # JSON parse failed — retry with the same prompt; LLM jitter
                # often resolves on a second pass.
                last_err = parsed.error
            except requests.exceptions.RequestException as e:
                last_err = f"network: {e}"
                # Transient: retry with backoff.
            except Exception as e:
                last_err = str(e)

            if attempt < self.MAX_ATTEMPTS:
                delay = self.RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.debug("LLM attempt %d/%d failed (%s); retrying in %.1fs",
                             attempt, self.MAX_ATTEMPTS, last_err, delay)
                time.sleep(delay)

        return EvaluationResult(
            entry_key=entry_key,
            relevance_score=0,
            is_relevant=False,
            explanation="",
            context_used=context,
            abstract_used=abstract,
            error=last_err or "Unknown error after retries"
        )
    
    def _call_openai_compatible(self, prompt: str) -> str:
        """Call OpenAI-compatible API (OpenAI, DeepSeek, vLLM)."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 2000,
            "response_format": {"type": "json_object"} if self.backend == LLMBackend.OPENAI else None
        }
        
        response = requests.post(
            self.endpoint,
            json=payload,
            headers=headers,
            timeout=60
        )
        response.raise_for_status()
        
        data = response.json()
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return ""

    def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic API."""
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "max_tokens": 2000,
            "temperature": 0.1,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        
        response = requests.post(
            self.endpoint,
            json=payload,
            headers=headers,
            timeout=60
        )
        response.raise_for_status()
        
        data = response.json()
        content = data.get("content", [])
        if content and content[0].get("type") == "text":
            return content[0].get("text", "")
        return ""

    def _call_ollama(self, prompt: str) -> str:
        """Call Ollama API."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 2000
            },
            "format": "json"
        }
        
        response = requests.post(
            self.endpoint,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        
        return response.json().get("response", "")
    
    def _call_gemini(self, prompt: str) -> str:
        """Call Gemini API."""
        # Build URL with model
        url = f"{self.endpoint}/{self.model}:generateContent"
        if self.api_key:
            url += f"?key={self.api_key}"
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 2000,
                "responseMimeType": "application/json"
            }
        }
        
        response = requests.post(
            url,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        
        candidates = response.json().get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if parts:
                return parts[0].get("text", "")
        return ""
    
    @staticmethod
    def _extract_json_object(text: str) -> Optional[dict]:
        """
        Robust JSON extraction. Handles:
          - bare JSON
          - fenced ```json ... ``` blocks
          - JSON embedded in surrounding prose
          - nested objects (the simple `\\{[^{}]*\\}` regex misses these)
        """
        if not text:
            return None
        s = text.strip()

        # Direct parse
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

        # Strip Markdown code fences (```json ... ``` or ``` ... ```)
        fence_match = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL | re.IGNORECASE)
        if fence_match:
            inner = fence_match.group(1).strip()
            try:
                obj = json.loads(inner)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
            s = inner  # fall through to brace-balance scan on inner

        # Brace-balanced scan: find the first complete top-level {...}.
        start = s.find("{")
        while start != -1:
            depth = 0
            in_str = False
            esc = False
            for i in range(start, len(s)):
                ch = s[i]
                if esc:
                    esc = False
                    continue
                if ch == "\\":
                    esc = True
                    continue
                if ch == '"':
                    in_str = not in_str
                    continue
                if in_str:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        chunk = s[start:i + 1]
                        try:
                            obj = json.loads(chunk)
                            if isinstance(obj, dict):
                                return obj
                        except json.JSONDecodeError:
                            break
            start = s.find("{", start + 1)
        return None

    def _parse_response(self, entry_key: str, response: str, context: str, abstract: str) -> EvaluationResult:
        """Parse LLM response with robust JSON extraction."""
        data = self._extract_json_object(response) or {}

        if not data:
             return EvaluationResult(
                entry_key=entry_key,
                relevance_score=0,
                is_relevant=False,
                explanation=response,
                context_used=context,
                abstract_used=abstract,
                error="Failed to parse LLM response as JSON"
            )
        
        # Extract & validate fields
        raw_score = data.get("relevance_score", data.get("score", 0))
        try:
            relevance_score = int(float(raw_score))
        except (TypeError, ValueError):
            relevance_score = 0
        relevance_score = max(0, min(5, relevance_score))

        is_relevant = data.get("is_relevant", relevance_score >= 4)
        if isinstance(is_relevant, str):
            is_relevant = is_relevant.strip().lower() in ("true", "yes", "1", "y")

        explanation = str(data.get("explanation", data.get("reason", ""))).strip()
        citation_role = str(data.get("citation_role", data.get("role", ""))).strip().lower() or "other"
        if citation_role not in {"baseline", "method", "dataset", "counterexample", "survey", "motivation", "other"}:
            citation_role = "other"

        # Sanity: a score of 0 means the LLM didn't actually return one — flag it.
        if relevance_score == 0:
            return EvaluationResult(
                entry_key=entry_key,
                relevance_score=0,
                is_relevant=False,
                explanation=explanation or response,
                context_used=context,
                abstract_used=abstract,
                citation_role=citation_role,
                error="LLM did not return a usable relevance_score",
            )

        return EvaluationResult(
            entry_key=entry_key,
            relevance_score=relevance_score,
            is_relevant=is_relevant,
            explanation=explanation,
            context_used=context,
            abstract_used=abstract,
            citation_role=citation_role,
        )
    
    def test_connection(self) -> bool:
        """Test if LLM backend is accessible."""
        try:
            if self.backend == LLMBackend.OLLAMA:
                response = requests.get(
                    self.endpoint.replace("/api/generate", "/api/tags"),
                    timeout=5
                )
                return response.status_code == 200
            elif self.backend in (LLMBackend.OPENAI, LLMBackend.DEEPSEEK, LLMBackend.VLLM):
                # Test with a simple model list or empty completion
                headers = {"Authorization": f"Bearer {self.api_key}"}
                # Try listing models if possible, otherwise simple completion
                if "chat/completions" in self.endpoint:
                    # Try a minimal completion
                    payload = {
                        "model": self.model,
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 1
                    }
                    response = requests.post(self.endpoint, json=payload, headers=headers, timeout=10)
                    return response.status_code == 200
                else:
                    return False
            elif self.backend == LLMBackend.ANTHROPIC:
                headers = {
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                payload = {
                    "model": self.model,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}]
                }
                response = requests.post(self.endpoint, json=payload, headers=headers, timeout=10)
                return response.status_code == 200
            elif self.backend == LLMBackend.GEMINI:
                if not self.api_key:
                    return False
                url = f"{self.endpoint}/{self.model}:generateContent?key={self.api_key}"
                payload = {
                    "contents": [{"parts": [{"text": "test"}]}],
                    "generationConfig": {"maxOutputTokens": 10}
                }
                response = requests.post(url, json=payload, timeout=10)
                return response.status_code == 200
        except Exception as e:
            logger.debug("LLM test_connection failed for %s: %s", self.backend.value, e)
            return False
        return False
