"""LLM call for vacancy parsing.

Claude on Amazon Bedrock through the Anthropic SDK's Mantle client
(endpoint https://bedrock-mantle.<region>.api.aws/anthropic, SigV4 service
"bedrock-mantle"). IAM action: bedrock-mantle:CreateInference on
arn:aws:bedrock-mantle:<region>:<account>:project/*.

Output is constrained with structured outputs (output_config.format). The caller
still validates the result against the contract.

ClaudeCli runs the same extraction through `claude -p` (Claude Code CLI) under the
logged-in Claude subscription. Local runs only: the CLI and its login are not in the
Lambda package.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Callable, Protocol


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
            # The system prompt (rules + skill vocabulary) is identical for every vacancy, so it is cached.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self._effort, "format": {"type": "json_schema", "schema": schema}},
        )

        if response.stop_reason == "refusal":
            raise LlmError(f"model refused: {getattr(response, 'stop_details', None)}")
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


Runner = Callable[[list[str], str, int, dict], subprocess.CompletedProcess]


def _run(cmd: list[str], stdin: str, timeout: int, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=timeout, env=env)


class ClaudeCli:
    def __init__(self, model: str = "haiku", timeout: int = 180, thinking: bool = False, runner: Runner = _run):
        self.model = model
        self._timeout = timeout
        self._thinking = thinking
        self._runner = runner

    def extract(self, system: str, user: str, schema: dict) -> LlmResult:
        cmd = [
            "claude", "-p",
            "--output-format", "json",
            "--model", self.model,
            "--tools", "",
            "--system-prompt", system,
            "--json-schema", json.dumps(schema),
            "--setting-sources", "",
            "--strict-mcp-config",
            "--no-session-persistence",
        ]
        # An empty ANTHROPIC_API_KEY would make the CLI try the key instead of the subscription login.
        env = {k: v for k, v in os.environ.items() if not (k == "ANTHROPIC_API_KEY" and not v)}
        if not self._thinking:
            # claude -p thinks by default. On 5 labelled vacancies: thinking F1 0.94, 57,058 output tokens;
            # without F1 0.84, 6,776 tokens. Off by default for the full run.
            env["MAX_THINKING_TOKENS"] = "0"
        try:
            proc = self._runner(cmd, user, self._timeout, env)
        except subprocess.TimeoutExpired as exc:
            raise LlmError(f"claude -p timed out after {self._timeout}s") from exc
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise LlmError(f"claude -p exited {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:300]}") from exc
        if proc.returncode != 0 or out.get("is_error"):
            raise LlmError(f"claude -p failed: {str(out.get('result') or proc.stderr).strip()[:300]}")
        data = out.get("structured_output")
        if not isinstance(data, dict):
            raise LlmError(f"no structured_output in claude -p response, subtype={out.get('subtype')}")

        usage = out.get("usage") or {}
        models = list((out.get("modelUsage") or {}).keys())
        return LlmResult(
            data=data,
            model=models[0] if models else self.model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
        )
