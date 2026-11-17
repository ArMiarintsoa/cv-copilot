"""Accès au LLM (Claude via API ou modèle open source via Ollama) avec sortie JSON validée."""
from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.config import settings

T = TypeVar("T", bound=BaseModel)


def get_llm():
    if settings.llm_provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url, temperature=0)
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(model=settings.anthropic_model, temperature=0, max_tokens=4096)


def ask(system: str, user: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    msg = get_llm().invoke([SystemMessage(content=system), HumanMessage(content=user)])
    content = msg.content
    if isinstance(content, list):  # blocs de contenu
        content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return content


def extract_json(text: str) -> str:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Aucun objet JSON dans la réponse du LLM")
    return text[start : end + 1]


def ask_json(system: str, user: str, model_cls: type[T], retries: int = 1) -> T:
    prompt = user
    last_err: Exception | None = None
    for _ in range(retries + 1):
        raw = ask(system, prompt)
        try:
            return model_cls.model_validate_json(extract_json(raw))
        except (ValueError, ValidationError, json.JSONDecodeError) as e:
            last_err = e
            prompt = (
                f"{user}\n\nTa réponse précédente était invalide ({str(e)[:300]}). "
                "Réponds UNIQUEMENT par un objet JSON valide conforme au schéma."
            )
    raise RuntimeError(f"Sortie LLM invalide après {retries + 1} essais : {last_err}")
