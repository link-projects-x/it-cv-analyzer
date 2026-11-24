"""LLM call for CV parsing. A copy of services/parser/parser/llm.py; services do not import each other.

Claude on Amazon Bedrock through the Anthropic SDK's Mantle client
(endpoint https://bedrock-mantle.<region>.api.aws/anthropic, SigV4 service
"bedrock-mantle"). IAM action: bedrock-mantle:CreateInference on
arn:aws:bedrock-mantle:<region>:<account>:project/*.

Output is constrained with structured outputs (output_config.format). The caller
still validates the result against the contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol


class LlmError(RuntimeError):
    pass


@dataclass(frozen=True)
class LlmResult:
    data: dict
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int


class Llm(Protocol):
    model: str

    def extract(self, system: str, user: str, schema: dict) -> LlmResult: ...


class BedrockClaude:
    def __init__(self, model: str, region: str, effort: str = "low", max_tokens: int = 8000, client=None):
        if client is None:
            from anthropic import AnthropicBedrockMantle

            client = AnthropicBedrockMantle(aws_region=region)
        self._client = client
        self.model = model
        self._effort = effort
        self._max_tokens = max_tokens

    def extract(self, system: str, user: str, schema: dict) -> LlmResult:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self._max_tokens,
            # The system prompt (rules + skill vocabulary) is identical for every CV, so it is cached.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self._effort, "format": {"type": "json_schema", "schema": schema}},
        )

        if response.stop_reason == "refusal":
            # Only the category: stop_details.explanation is free text and this message reaches the logs.
            category = getattr(getattr(response, "stop_details", None), "category", None)
            raise LlmError(f"model refused: category={category}")
        if response.stop_reason == "max_tokens":
            raise LlmError(f"output cut at max_tokens={self._max_tokens}")

        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise LlmError(f"no text block in response, stop_reason={response.stop_reason}")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LlmError(f"response is not JSON: {exc}") from exc

        usage = response.usage
        return LlmResult(
            data=data,
            model=self.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        )
