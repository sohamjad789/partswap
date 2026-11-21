"""Nemotron tool loop for one BOM line (PLAN.md section 4.10). Any failure falls back to the deterministic decision."""

import itertools
import json
import time
from typing import Any, Callable, Optional

import openai

from app.agent.client import completion_kwargs, make_client
from app.agent.prompts import SYSTEM_PROMPT, USER_PROMPT
from app.agent.tools import TOOL_NAMES, TOOL_SCHEMAS, AgentState, FallbackRequired, execute_tool, summarize
from app.catalog import load_part
from app.decide import decide_deterministic
from app.schemas import AgentStep, BomLine, Decision, DesignContext, Source

Emit = Callable[[str, dict[str, Any]], None]

MAX_TURNS = 10
LINE_TIME_BUDGET_S = 150
MAX_CALLS_PER_TURN = 4
RETRY_WAITS_S = (1, 2, 4)
REASONING_CHARS = 500
REPEAT_LIMITED_ERRORS = {"invalid_arguments", "unknown_tool"}
NO_TOOL_CALL_REMINDER = "Use the tools. Finish by calling record_decision exactly once."


def run_part(line: BomLine, context: DesignContext, model_id: str, emit: Optional[Emit],
             only_candidates: Optional[list[str]] = None, *, client: Any = None) -> Decision:
    counter = itertools.count(1)

    def step(**fields: Any) -> None:
        if emit is not None:
            emit("agent_step", AgentStep(ref=line.ref, step=next(counter), **fields).model_dump(mode="json", exclude_none=True))

    original = load_part(line.mpn)
    if original is None:
        return decide_deterministic(line, context)

    state = AgentState.for_line(line, context, original, model_id=model_id, only_candidates=only_candidates)
    try:
        return _converse(client if client is not None else make_client(), state, step)
    except Exception as exc:  # one line failing never stops the run
        message = f"{type(exc).__name__}: {exc}" if not isinstance(exc, FallbackRequired) else str(exc)

    step(kind="error", text=f"Falling back to the deterministic decision: {message}"[:500])
    if emit is not None:
        emit("part_error", {"ref": line.ref, "message": message, "fallback": True})
    return decide_deterministic(line, context).model_copy(update={"source": Source.deterministic_fallback})


def _first_message(state: AgentState) -> str:
    o = state.original
    return USER_PROMPT.format(
        ref=state.line.ref,
        line_json=state.line.model_dump_json(),
        requirements_json=state.requirements.model_dump_json(exclude_none=True),
        mpn=o.mpn, manufacturer=o.manufacturer, category=o.category.value, package_code=o.package.code,
        goal=state.context.goal.value, preferred_manufacturer=state.context.preferred_manufacturer,
    )


def _converse(client: Any, state: AgentState, step: Callable[..., None]) -> Decision:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _first_message(state)},
    ]
    kwargs = {**completion_kwargs(state.model_id), "tools": TOOL_SCHEMAS, "tool_choice": "auto"}
    recovered = empty_retried = length_retried = False
    last_error: Optional[str] = None
    started = time.monotonic()

    for _ in range(MAX_TURNS):
        if time.monotonic() - started > LINE_TIME_BUDGET_S:
            raise FallbackRequired(f"line exceeded the {LINE_TIME_BUDGET_S}-second time budget")
        response = _complete(client, kwargs, messages)
        choice = response.choices[0]
        message = choice.message
        reasoning = getattr(message, "reasoning_content", None)
        if reasoning:
            step(kind="reasoning", text=str(reasoning)[:REASONING_CHARS])

        content = message.content or ""
        calls = [(c.id, c.function.name, c.function.arguments) for c in (message.tool_calls or [])]
        if choice.finish_reason == "length" and not calls:
            if length_retried:
                raise FallbackRequired("the model hit its length limit twice")
            length_retried = True
            extra_body = kwargs.setdefault("extra_body", {})
            extra_body.setdefault("chat_template_kwargs", {})["enable_thinking"] = False
            continue
        if not calls and not recovered:
            found = _call_from_content(content)
            if found is not None:
                recovered, content = True, ""
                calls = [(f"recovered-{state.line.ref}", *found)]

        if not calls:
            if not content.strip():
                if empty_retried:
                    raise FallbackRequired("the model returned an empty turn twice")
                empty_retried = True
                continue
            messages += [{"role": "assistant", "content": content}, {"role": "user", "content": NO_TOOL_CALL_REMINDER}]
            continue

        messages.append({"role": "assistant", "content": content, "tool_calls": [
            {"id": cid, "type": "function", "function": {"name": name, "arguments": args}} for cid, name, args in calls]})
        ordered = [c for c in calls if c[1] != "record_decision"] + [c for c in calls if c[1] == "record_decision"]
        for index, (cid, name, args) in enumerate(ordered):
            if index >= MAX_CALLS_PER_TURN:
                result: dict[str, Any] = {"error": "too_many_calls"}
            else:
                step(kind="tool_call", tool=name, arguments=_shown_arguments(args))
                result = execute_tool(name, args, state)
                step(kind="tool_result", tool=name, summary=summarize(name, result))
                for note in state.guardrail_notes:
                    step(kind="guardrail", text=note)
                state.guardrail_notes.clear()
                error = result.get("error")
                if error in REPEAT_LIMITED_ERRORS and error == last_error:
                    raise FallbackRequired(f"two consecutive {error} errors")
                last_error = error if error in REPEAT_LIMITED_ERRORS else None
            messages.append({"role": "tool", "tool_call_id": cid, "content": json.dumps(result, ensure_ascii=False)})
            if state.decision is not None:
                return state.decision

    raise FallbackRequired(f"no decision after {MAX_TURNS} model turns")


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, openai.APIConnectionError):
        return True
    return isinstance(exc, openai.APIStatusError) and (exc.status_code == 429 or exc.status_code >= 500)


def _complete(client: Any, kwargs: dict[str, Any], messages: list[dict[str, Any]]) -> Any:
    for attempt in range(len(RETRY_WAITS_S) + 1):
        try:
            return client.chat.completions.create(messages=messages, **kwargs)
        except Exception as exc:
            if attempt == len(RETRY_WAITS_S) or not _retryable(exc):
                raise
            time.sleep(RETRY_WAITS_S[attempt])
    raise AssertionError("unreachable")


def _shown_arguments(arguments: Optional[str]) -> dict[str, Any]:
    try:
        parsed = json.loads(arguments or "{}")
    except (TypeError, ValueError):
        parsed = None
    return parsed if isinstance(parsed, dict) else {"raw": str(arguments)[:200]}


def _call_from_content(content: str) -> Optional[tuple[str, str]]:
    """A tool call the model wrote as JSON text instead of `tool_calls`: `{"name": ..., "arguments": {...}}`."""
    decoder = json.JSONDecoder()
    start = content.find("{")
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(content, start)
        except ValueError:
            start = content.find("{", start + 1)
            continue
        if isinstance(obj, dict) and obj.get("name") in TOOL_NAMES:
            arguments = obj.get("arguments")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except ValueError:
                    return None
            return (obj["name"], json.dumps(arguments)) if isinstance(arguments, dict) else None
        return None
    return None
