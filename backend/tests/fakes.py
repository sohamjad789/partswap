"""Scripted stand-in for `openai.OpenAI` (only `chat.completions.create` is used by the agent loop)."""

import copy
import json
from types import SimpleNamespace
from typing import Any, Optional

import httpx
import openai

_REQUEST = httpx.Request("POST", "http://fake.invalid/v1/chat/completions")


def call(name: str, arguments: Any, id: Optional[str] = None) -> SimpleNamespace:
    """A tool call. `arguments` may be a dict (JSON-encoded here) or a raw string."""
    text = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return SimpleNamespace(id=id or f"call-{name}", type="function",
                           function=SimpleNamespace(name=name, arguments=text))


def reply(*tool_calls: SimpleNamespace, content: Optional[str] = None, reasoning: Optional[str] = None,
          finish_reason: Optional[str] = None) -> SimpleNamespace:
    message = SimpleNamespace(role="assistant", content=content, tool_calls=list(tool_calls) or None,
                              reasoning_content=reasoning)
    finish = finish_reason or ("tool_calls" if tool_calls else "stop")
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish)])


def status_error(code: int) -> openai.APIStatusError:
    return openai.APIStatusError(f"HTTP {code}", response=httpx.Response(code, request=_REQUEST), body=None)


def connection_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=_REQUEST)


class FakeClient:
    """Each `create` call pops the next scripted item: a response from `reply`, or an exception to raise."""

    def __init__(self, script: list[Any]):
        self.script = list(script)
        self.requests: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        self.requests.append(copy.deepcopy(kwargs))
        if not self.script:
            raise AssertionError("FakeClient ran out of scripted responses")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item
