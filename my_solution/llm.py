"""Thin OpenAI Responses client for the answer step. Needs OPENAI_API_KEY; OPENAI_MODEL overrides the model."""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

from prompt import ANSWER_SCHEMA, DEVELOPER_MESSAGE

DEFAULT_MODEL = "gpt-6-luna"   # feature-skill tier map: RAG/Q&A over provided context -> Luna
# Reasoning effort of the answer call. "none" is the only effort that accepts temperature 0 (repeatable) and is
# fastest; "low"/"medium" make the model think first (slower, costlier). Experiment switch: MY_SOLUTION_ANSWER_EFFORT.
ANSWER_EFFORT = os.getenv("MY_SOLUTION_ANSWER_EFFORT", "none")
REASONING_TIMEOUT_S = 45
TIMEOUT_S = 6   # with max_retries=1 a stuck call costs at most ~12 s, not ~40 s



class AnswerLLM:
    def __init__(self, model: Optional[str] = None):
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
        self.usage = {"calls": 0, "input": 0, "cached": 0, "output": 0}
        self._client = None

    def available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))

    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(timeout=TIMEOUT_S, max_retries=1)
        return self._client

    def warm_up(self) -> None:
        """Open the HTTPS connection during (untimed) ingest so the first answer is not slow."""
        try:
            self.client().models.retrieve(self.model)
        except Exception as e:
            if not getattr(self, "_warned", False):   # one clear line, once: otherwise every answer silently becomes "I don't know"
                self._warned = True
                print(f"[my_solution] WARNING: the OpenAI model '{self.model}' could not be reached ({type(e).__name__}: {e}). "
                      "Until this is fixed, answers will be \"I don't know\". Check OPENAI_API_KEY and access to the model.",
                      file=sys.stderr, flush=True)

    def ask(self, user_message: str, instructions: Optional[str] = None, effort: Optional[str] = None) -> dict:
        """The answer step. `instructions` overrides the system message (intent switch); `effort` overrides the reasoning
        effort for this call (used for hours questions only, MY_SOLUTION_HOURS_EFFORT)."""
        instructions = instructions or DEVELOPER_MESSAGE
        effort = effort or ANSWER_EFFORT
        if effort == "none":
            return self.ask_json(instructions, user_message, ANSWER_SCHEMA, "member_answer",
                                 "dupaco-answer-v1", max_tokens=600)
        # reasoning tokens count as output, so allow more; no temperature above effort none
        return self.ask_json(instructions, user_message, ANSWER_SCHEMA, "member_answer",
                             "dupaco-answer-v1", max_tokens=6000, timeout=REASONING_TIMEOUT_S, effort=effort)

    def ask_json(self, instructions: str, user_message: str, schema: dict, name: str,
                 cache_key: str, max_tokens: int = 600, timeout: Optional[float] = None,
                 effort: str = "none") -> dict:
        """One structured call: effort none + temperature 0 + strict JSON schema. `timeout` overrides the
        answer-time limit (used by loading-time extraction, which is not timed)."""
        client = self.client() if timeout is None else self.client().with_options(timeout=timeout)
        extra = {}
        if timeout is None: extra["service_tier"] = "priority"
        params = dict(
            model=self.model,
            instructions=instructions,
            input=user_message,
            reasoning={"effort": effort},
            **({"temperature": 0} if effort == "none" else {}),   # temperature is accepted only at effort none
            text={"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
            max_output_tokens=max_tokens,
            prompt_cache_key=cache_key,
        )
        try:
            r = client.responses.create(**extra, **params)
        except Exception as e:
            if not extra or getattr(e, "status_code", None) not in (400, 403, 404, 422):
                raise
            r = client.responses.create(**params)   # the option was refused: retry once with the default options
        u = r.usage
        self.usage["calls"] += 1
        self.usage["input"] += u.input_tokens
        self.usage["output"] += u.output_tokens
        details = getattr(u, "input_tokens_details", None)
        self.usage["cached"] += getattr(details, "cached_tokens", 0) or 0
        return parse_first_json(r.output_text)


def parse_first_json(text: str) -> dict:
    """The first JSON object in the output. Observed once on gpt-6-luna under a strict schema:
    output_text held the object followed by extra data, which json.loads rejects."""
    text = text.strip()
    obj, _ = json.JSONDecoder().raw_decode(text[text.index("{"):])
    return obj
