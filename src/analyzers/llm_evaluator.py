"""
LLM-based citation relevance evaluator.
Supports OpenAI, Anthropic, DeepSeek, Gemini, vLLM, and Ollama backends.
"""
import json
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum
import os

import requests


class LLMBackend(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    VLLM = "vllm"
    OLLAMA = "ollama"
    DEEPSEEK = "deepseek"


@dataclass
class EvaluationResult:
    """Result of LLM citation evaluation."""
    entry_key: str
    relevance_score: int  # 1-5
    is_relevant: bool
    explanation: str
    context_used: str
    abstract_used: str
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
    
    PROMPT_TEMPLATE = """You are an expert academic reviewer. Given a citation context from a LaTeX document and the cited paper's abstract, evaluate whether this citation is appropriate and relevant.

## Citation Context (from the manuscript):
{context}

## Cited Paper's Abstract:
{abstract}

## Task:
Evaluate the relevance and appropriateness of this citation. Consider:
1. Does the citation support the claim being made in the context?
2. Is the cited paper's topic related to the discussion?
3. Is this citation necessary, or could it be replaced with a more relevant one?

## Response Format:
Provide your response in the following JSON format:
{{
    "relevance_score": <1-5 integer>,
    "is_relevant": <true/false>,
    "explanation": "<brief explanation in 1-2 sentences>"
}}

Score guide:
- 1: Not relevant at all
- 2: Marginally relevant
- 3: Somewhat relevant
- 4: Relevant and appropriate
- 5: Highly relevant and essential

STRICTLY FOLLOW THE JSON FORMAT. Respond ONLY with the JSON object, no other text."""

    def __init__(
        self,
        backend: LLMBackend = LLMBackend.GEMINI,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        self.backend = backend
        self.api_key = api_key or os.environ.get(f"{backend.name}_API_KEY")
        
        # Set defaults based on backend
        if backend == LLMBackend.OPENAI:
            self.endpoint = endpoint or "https://api.openai.com/v1/chat/completions"
            self.model = model or "gpt-5-mini"
        elif backend == LLMBackend.ANTHROPIC:
            self.endpoint = endpoint or "https://api.anthropic.com/v1/messages"
            self.model = model or "claude-4.5-haiku"
        elif backend == LLMBackend.DEEPSEEK:
            self.endpoint = endpoint or "https://api.deepseek.com/chat/completions"
            self.model = model or "deepseek-chat"
        elif backend == LLMBackend.OLLAMA:
            self.endpoint = endpoint or "http://localhost:11434/api/generate"
            self.model = model or "Qwen/qwen3-4B-Instruct-2507"
        elif backend == LLMBackend.VLLM:
            self.endpoint = endpoint or "http://localhost:8000/v1/chat/completions"
            self.model = model or "Qwen/qwen3-4B-Instruct-2507"
        elif backend == LLMBackend.GEMINI:
            self.endpoint = endpoint or "https://generativelanguage.googleapis.com/v1beta/models"
            self.model = model or "gemini-2.5-flash-lite"
    
    def evaluate(self, entry_key: str, context: str, abstract: str) -> EvaluationResult:
        """Evaluate citation relevance."""
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
        
        # Don't truncate - preserve full context and abstract
        prompt = self.PROMPT_TEMPLATE.format(context=context, abstract=abstract)
        
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
            
            return self._parse_response(entry_key, response, context, abstract)
            
        except Exception as e:
            return EvaluationResult(
                entry_key=entry_key,
                relevance_score=0,
                is_relevant=False,
                explanation="",
                context_used=context,
                abstract_used=abstract,
                error=str(e)
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
    
    def _parse_response(self, entry_key: str, response: str, context: str, abstract: str) -> EvaluationResult:
        """Parse LLM response."""
        # Try to extract JSON from response
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        
        data = {}
        if not json_match:
            # Try to parse the whole response as JSON
            try:
                data = json.loads(response.strip())
            except json.JSONDecodeError:
                pass
        else:
            try:
                data = json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
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
        
        # Extract fields
        relevance_score = data.get("relevance_score", 0)
        if isinstance(relevance_score, str):
            try:
                relevance_score = int(relevance_score)
            except ValueError:
                relevance_score = 0
        
        is_relevant = data.get("is_relevant", False)
        if isinstance(is_relevant, str):
            is_relevant = is_relevant.lower() in ("true", "yes", "1")
        
        explanation = data.get("explanation", "")
        
        return EvaluationResult(
            entry_key=entry_key,
            relevance_score=relevance_score,
            is_relevant=is_relevant,
            explanation=explanation,
            context_used=context,
            abstract_used=abstract
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
        except Exception:
            return False
        return False
