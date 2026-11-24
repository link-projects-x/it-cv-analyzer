import json
import subprocess

import pytest

from parser.llm import ClaudeCli, LlmError


def _proc(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _ok_body(**extra) -> str:
    body = {
        "subtype": "success",
        "is_error": False,
        "result": "done",
        "structured_output": {"seniority": "middle"},
        "usage": {"input_tokens": 1200, "output_tokens": 80, "cache_read_input_tokens": 900},
        "modelUsage": {"claude-haiku-4-5-20251001": {"inputTokens": 1200}},
    }
    body.update(extra)
    return json.dumps(body)


class Recorder:
    def __init__(self, proc):
        self.proc = proc
        self.calls = []

    def __call__(self, cmd, stdin, timeout, env):
        self.calls.append((cmd, stdin, timeout, env))
        if isinstance(self.proc, Exception):
            raise self.proc
        return self.proc


def test_returns_structured_output_and_usage():
    run = Recorder(_proc(_ok_body()))
    result = ClaudeCli(runner=run).extract("SYS", "USER", {"type": "object"})

    assert result.data == {"seniority": "middle"}
    assert result.model == "claude-haiku-4-5-20251001"
    assert (result.input_tokens, result.output_tokens, result.cache_read_tokens) == (1200, 80, 900)


def test_passes_prompt_schema_and_no_tools():
    run = Recorder(_proc(_ok_body()))
    ClaudeCli(model="sonnet", runner=run).extract("SYS", "USER", {"type": "object", "required": ["a"]})

    cmd, stdin, _, _ = run.calls[0]
    assert stdin == "USER"
    assert cmd[cmd.index("--system-prompt") + 1] == "SYS"
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == {"type": "object", "required": ["a"]}
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert cmd[cmd.index("--tools") + 1] == ""


def test_drops_empty_api_key_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    run = Recorder(_proc(_ok_body()))
    ClaudeCli(runner=run).extract("S", "U", {})

    assert "ANTHROPIC_API_KEY" not in run.calls[0][3]


@pytest.mark.parametrize(
    "proc",
    [
        _proc("not json", returncode=1, stderr="not logged in"),
        _proc(_ok_body(is_error=True, result="usage limit reached")),
        _proc(_ok_body(), returncode=2),
        _proc(_ok_body(structured_output=None, subtype="error_max_structured_output_retries")),
    ],
)
def test_failures_raise_llm_error(proc):
    with pytest.raises(LlmError):
        ClaudeCli(runner=Recorder(proc)).extract("S", "U", {})


def test_timeout_raises_llm_error():
    run = Recorder(subprocess.TimeoutExpired(cmd="claude", timeout=1))
    with pytest.raises(LlmError, match="timed out"):
        ClaudeCli(timeout=1, runner=run).extract("S", "U", {})


def test_default_sets_max_thinking_tokens_zero(monkeypatch):
    monkeypatch.delenv("MAX_THINKING_TOKENS", raising=False)
    run = Recorder(_proc(_ok_body()))
    ClaudeCli(runner=run).extract("S", "U", {})
    assert run.calls[0][3]["MAX_THINKING_TOKENS"] == "0"


def test_thinking_leaves_env_alone(monkeypatch):
    monkeypatch.delenv("MAX_THINKING_TOKENS", raising=False)
    run = Recorder(_proc(_ok_body()))
    ClaudeCli(thinking=True, runner=run).extract("S", "U", {})
    assert "MAX_THINKING_TOKENS" not in run.calls[0][3]
