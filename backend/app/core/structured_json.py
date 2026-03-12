import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar

from anthropic import Anthropic, AsyncAnthropic
from pydantic import BaseModel, ValidationError

from app.core.usage_tracker import get_usage_tracker

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_REPAIR_PROMPT = """You repair malformed JSON produced by another model.

Return ONLY valid JSON.

Rules:
- Preserve the original intent and values as much as possible.
- Do not add commentary, markdown, or code fences.
- Do not invent extra top-level fields beyond the schema hint.
- If a value is clearly missing and cannot be recovered, use null, empty string, or empty array depending on the field intent.

Schema hint:
{schema_hint}

Malformed JSON:
{raw_json}
"""


@dataclass
class StructuredJsonTelemetry:
    request_name: str
    generation_channel: str = "text_json"
    parse_failed: bool = False
    parse_error: str | None = None
    validation_failed: bool = False
    validation_error: str | None = None
    repair_attempted: bool = False
    repair_succeeded: bool = False
    repair_error: str | None = None
    fallback_used: bool = False
    provider_error: str | None = None
    raw_text_length: int = 0
    response_block_types: list[str] = field(default_factory=list)
    empty_response: bool = False
    retry_attempted: bool = False
    retry_succeeded: bool = False
    raw_preview: str | None = None
    stop_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    prompt_length: int = 0
    schema_length: int = 0
    payload_sanitize_attempted: bool = False
    payload_sanitized: bool = False


@dataclass
class StructuredJsonResult(Generic[ModelT]):
    value: ModelT
    raw_text: str
    telemetry: StructuredJsonTelemetry


class StructuredJsonError(RuntimeError):
    def __init__(self, message: str, telemetry: StructuredJsonTelemetry, raw_text: str):
        super().__init__(message)
        self.telemetry = telemetry
        self.raw_text = raw_text


def _extract_text_from_response(response) -> tuple[str, list[str]]:
    parts: list[str] = []
    block_types: list[str] = []
    for block in getattr(response, "content", []) or []:
        block_type = getattr(block, "type", None) or block.__class__.__name__
        block_types.append(str(block_type))
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts).strip(), block_types


def _compact_preview(raw_text: str, limit: int = 240) -> str | None:
    text = re.sub(r"\s+", " ", (raw_text or "")).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _capture_raw_observability(telemetry: StructuredJsonTelemetry, raw_text: str) -> None:
    telemetry.raw_text_length = len(raw_text)
    telemetry.empty_response = not bool(raw_text.strip())
    telemetry.raw_preview = _compact_preview(raw_text)


def _capture_completion_observability(
    telemetry: StructuredJsonTelemetry,
    response,
    *,
    prompt: str,
    schema: str | dict | None = None,
) -> None:
    telemetry.prompt_length = len(prompt or "")
    telemetry.stop_reason = str(getattr(response, "stop_reason", None) or "").strip() or None
    usage = getattr(response, "usage", None)
    telemetry.input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    telemetry.output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    if schema is None:
        telemetry.schema_length = 0
        return
    if isinstance(schema, dict):
        telemetry.schema_length = len(json.dumps(schema, ensure_ascii=False, sort_keys=True))
        return
    telemetry.schema_length = len(str(schema))


def _normalize_native_json_schema(schema: dict) -> dict:
    unsupported_keywords = {
        "maxItems",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
    }

    def _walk(node):
        if isinstance(node, dict):
            normalized = {
                key: _walk(value)
                for key, value in node.items()
                if key not in unsupported_keywords
            }
            node_type = normalized.get("type")
            is_object_type = node_type == "object" or (
                isinstance(node_type, list) and "object" in node_type
            )
            if (is_object_type or "properties" in normalized) and "additionalProperties" not in normalized:
                normalized["additionalProperties"] = False
            return normalized
        if isinstance(node, list):
            return [_walk(item) for item in node]
        return node

    return _walk(schema)


def _extract_balanced_json(raw: str) -> str | None:
    start_index = -1
    opening = ""

    for index, char in enumerate(raw):
        if char in "{[":
            start_index = index
            opening = char
            break

    if start_index == -1:
        return None

    closing = "}" if opening == "{" else "]"
    depth = 0
    in_string = False
    escaping = False

    for index in range(start_index, len(raw)):
        char = raw[index]

        if in_string:
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == "\"":
                in_string = False
            continue

        if char == "\"":
            in_string = True
            continue

        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return raw[start_index : index + 1]

    return None


def _candidate_json_texts(raw_text: str) -> list[str]:
    stripped = raw_text.strip()
    candidates: list[str] = []

    if stripped:
        candidates.append(stripped)

    for match in _JSON_BLOCK_RE.finditer(raw_text):
        block = match.group(1).strip()
        if block:
            candidates.append(block)

    balanced = _extract_balanced_json(raw_text)
    if balanced:
        candidates.append(balanced.strip())

    unique_candidates: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique_candidates.append(candidate)
    return unique_candidates


def _close_truncated_json(raw_text: str) -> str | None:
    candidate = raw_text.strip()
    if not candidate or candidate[0] not in "{[":
        return None
    if _extract_balanced_json(candidate):
        return None

    closed: list[str] = []
    expected_closings: list[str] = []
    in_string = False
    escaping = False

    for char in candidate:
        closed.append(char)
        if in_string:
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == "\"":
                in_string = False
            continue

        if char == "\"":
            in_string = True
            continue
        if char == "{":
            expected_closings.append("}")
            continue
        if char == "[":
            expected_closings.append("]")
            continue
        if char in "}]":
            if not expected_closings or expected_closings[-1] != char:
                return None
            expected_closings.pop()

    repaired = "".join(closed).rstrip()
    if re.search(r'[:]\s*$', repaired):
        return None
    repaired = re.sub(r",\s*$", "", repaired)
    if in_string:
        repaired += "\""
    repaired += "".join(reversed(expected_closings))
    return repaired if repaired != candidate else None


def extract_json_object(raw_text: str) -> dict:
    last_error: Exception | None = None

    for candidate in _candidate_json_texts(raw_text):
        try:
            parsed = json.loads(candidate)
        except Exception as exc:
            last_error = exc
            continue

        if isinstance(parsed, dict):
            return parsed

        last_error = ValueError("Structured JSON response must be a JSON object")

    if last_error is not None:
        raise ValueError(str(last_error))

    raise ValueError("No JSON object found in model response")


def parse_structured_json_text(
    *,
    raw_text: str,
    response_model: type[ModelT],
    request_name: str,
    response_block_types: list[str] | None = None,
) -> StructuredJsonResult[ModelT]:
    telemetry = StructuredJsonTelemetry(request_name=request_name)
    telemetry.response_block_types = response_block_types or []
    _capture_raw_observability(telemetry, raw_text)

    try:
        payload = extract_json_object(raw_text)
    except Exception as exc:
        telemetry.parse_failed = True
        telemetry.parse_error = str(exc)
        _log_structured_output_event(telemetry, success=False)
        logger.warning(
            "%s parse_failed: %s (text_len=%s, block_types=%s, preview=%r)",
            request_name,
            exc,
            telemetry.raw_text_length,
            telemetry.response_block_types,
            telemetry.raw_preview,
        )
        raise StructuredJsonError(
            f"{request_name} structured JSON parse failed: {exc}",
            telemetry=telemetry,
            raw_text=raw_text,
        ) from exc

    try:
        value = response_model.model_validate(payload)
        _log_structured_output_event(telemetry, success=True)
        return StructuredJsonResult(
            value=value,
            raw_text=raw_text,
            telemetry=telemetry,
        )
    except ValidationError as exc:
        telemetry.validation_failed = True
        telemetry.validation_error = str(exc)
        _log_structured_output_event(telemetry, success=False)
        logger.warning(
            "%s validation_failed: %s (text_len=%s, block_types=%s, preview=%r)",
            request_name,
            exc,
            telemetry.raw_text_length,
            telemetry.response_block_types,
            telemetry.raw_preview,
        )
        raise StructuredJsonError(
            f"{request_name} structured JSON validation failed: {exc}",
            telemetry=telemetry,
            raw_text=raw_text,
        ) from exc


def _call_model_for_text(
    *,
    client: Anthropic,
    model: str,
    prompt: str,
    max_tokens: int,
) -> tuple[str, object, list[str]]:
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    get_usage_tracker().log(
        model,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )
    extracted_text, block_types = _extract_text_from_response(response)
    return extracted_text, response, block_types


def _call_model_for_native_json(
    *,
    client: Anthropic,
    model: str,
    prompt: str,
    max_tokens: int,
    json_schema: dict,
    system: str | None = None,
) -> tuple[str, object, list[str]]:
    request_kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {
            "format": {
                "type": "json_schema",
                "schema": json_schema,
            }
        },
    }
    if system:
        request_kwargs["system"] = system
    response = client.messages.create(**request_kwargs)
    get_usage_tracker().log(
        model,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )
    extracted_text, block_types = _extract_text_from_response(response)
    return extracted_text, response, block_types


async def _call_model_for_text_async(
    *,
    client: AsyncAnthropic,
    model: str,
    prompt: str,
    max_tokens: int,
    system: str | None = None,
) -> tuple[str, object, list[str]]:
    request_kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        request_kwargs["system"] = system
    response = await client.messages.create(**request_kwargs)
    get_usage_tracker().log(
        model,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )
    extracted_text, block_types = _extract_text_from_response(response)
    return extracted_text, response, block_types


async def _call_model_for_native_json_async(
    *,
    client: AsyncAnthropic,
    model: str,
    prompt: str,
    max_tokens: int,
    json_schema: dict,
    system: str | None = None,
) -> tuple[str, object, list[str]]:
    request_kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {
            "format": {
                "type": "json_schema",
                "schema": json_schema,
            }
        },
    }
    if system:
        request_kwargs["system"] = system
    response = await client.messages.create(**request_kwargs)
    get_usage_tracker().log(
        model,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )
    extracted_text, block_types = _extract_text_from_response(response)
    return extracted_text, response, block_types


def _repair_json_text(
    *,
    client: Anthropic,
    model: str,
    raw_text: str,
    schema_hint: str,
    max_tokens: int,
) -> str:
    prompt = _REPAIR_PROMPT.format(
        schema_hint=schema_hint.strip(),
        raw_json=raw_text.strip()[:12000],
    )
    repaired_text, _, _ = _call_model_for_text(
        client=client,
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
    )
    return repaired_text


async def _repair_json_text_async(
    *,
    client: AsyncAnthropic,
    model: str,
    raw_text: str,
    schema_hint: str,
    max_tokens: int,
) -> str:
    prompt = _REPAIR_PROMPT.format(
        schema_hint=schema_hint.strip(),
        raw_json=raw_text.strip()[:12000],
    )
    repaired_text, _, _ = await _call_model_for_text_async(
        client=client,
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
    )
    return repaired_text


def _merge_block_types(*block_type_groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in block_type_groups:
        for block_type in group:
            if block_type in seen:
                continue
            seen.add(block_type)
            merged.append(block_type)
    return merged


def classify_structured_failure(telemetry: StructuredJsonTelemetry) -> str:
    if telemetry.provider_error:
        return "provider"
    if telemetry.empty_response:
        return "empty_response"
    if telemetry.validation_failed:
        return "validation"
    if telemetry.parse_failed:
        return "parse"
    if telemetry.repair_error:
        return "repair"
    return "unknown"


def summarize_structured_failure(telemetry: StructuredJsonTelemetry) -> str | None:
    message = (
        telemetry.provider_error
        or telemetry.validation_error
        or telemetry.parse_error
        or telemetry.repair_error
    )
    if not message:
        return None
    text = re.sub(r"\s+", " ", str(message)).strip()
    if len(text) <= 240:
        return text
    return text[:239].rstrip() + "…"


def _log_structured_output_event(telemetry: StructuredJsonTelemetry, *, success: bool) -> None:
    get_usage_tracker().log_structured_output(
        request_name=telemetry.request_name,
        generation_channel=telemetry.generation_channel,
        success=success,
        failure_kind=None if success else classify_structured_failure(telemetry),
        stop_reason=telemetry.stop_reason,
        validation_failed=telemetry.validation_failed,
        failure_message=None if success else summarize_structured_failure(telemetry),
    )


def _apply_payload_sanitizer(
    telemetry: StructuredJsonTelemetry,
    payload: dict,
    payload_sanitizer: Callable[[object], tuple[object, bool]] | None,
    *,
    request_name: str,
) -> dict:
    if payload_sanitizer is None:
        return payload

    telemetry.payload_sanitize_attempted = True
    sanitized_payload, payload_sanitized = payload_sanitizer(payload)
    if not isinstance(sanitized_payload, dict):
        raise ValueError("Payload sanitizer must return a JSON object payload")
    telemetry.payload_sanitized = bool(payload_sanitized)
    if telemetry.payload_sanitized:
        logger.info("%s native_payload_sanitized", request_name)
    return sanitized_payload


def request_structured_json(
    *,
    client: Anthropic,
    model: str,
    prompt: str,
    response_model: type[ModelT],
    schema_hint: str,
    max_tokens: int,
    repair_max_tokens: int,
    request_name: str,
) -> StructuredJsonResult[ModelT]:
    telemetry = StructuredJsonTelemetry(request_name=request_name)
    raw_text, response, block_types = _call_model_for_text(
        client=client,
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
    )
    _capture_completion_observability(telemetry, response, prompt=prompt, schema=schema_hint)
    telemetry.response_block_types = block_types
    _capture_raw_observability(telemetry, raw_text)

    try:
        payload = extract_json_object(raw_text)
        value = response_model.model_validate(payload)
        _log_structured_output_event(telemetry, success=True)
        return StructuredJsonResult(
            value=value,
            raw_text=raw_text,
            telemetry=telemetry,
        )
    except ValidationError as exc:
        telemetry.validation_failed = True
        telemetry.validation_error = str(exc)
        logger.warning(
            "%s validation_failed: %s (text_len=%s, block_types=%s, stop_reason=%s, prompt_len=%s, schema_len=%s, preview=%r)",
            request_name,
            exc,
            telemetry.raw_text_length,
            telemetry.response_block_types,
            telemetry.stop_reason,
            telemetry.prompt_length,
            telemetry.schema_length,
            telemetry.raw_preview,
        )
    except Exception as exc:
        telemetry.parse_failed = True
        telemetry.parse_error = str(exc)
        logger.warning(
            "%s parse_failed: %s (text_len=%s, block_types=%s, stop_reason=%s, prompt_len=%s, schema_len=%s, preview=%r)",
            request_name,
            exc,
            telemetry.raw_text_length,
            telemetry.response_block_types,
            telemetry.stop_reason,
            telemetry.prompt_length,
            telemetry.schema_length,
            telemetry.raw_preview,
        )

    if telemetry.empty_response:
        telemetry.retry_attempted = True
        retry_text, retry_response, retry_block_types = _call_model_for_text(
            client=client,
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
        )
        _capture_completion_observability(telemetry, retry_response, prompt=prompt, schema=schema_hint)
        telemetry.response_block_types = _merge_block_types(telemetry.response_block_types, retry_block_types)
        raw_text = retry_text
        _capture_raw_observability(telemetry, raw_text)

        try:
            payload = extract_json_object(raw_text)
            value = response_model.model_validate(payload)
            telemetry.retry_succeeded = True
            _log_structured_output_event(telemetry, success=True)
            return StructuredJsonResult(
                value=value,
                raw_text=raw_text,
                telemetry=telemetry,
            )
        except ValidationError as exc:
            telemetry.validation_failed = True
            telemetry.validation_error = str(exc)
            logger.warning(
                "%s retry_validation_failed: %s (text_len=%s, block_types=%s, stop_reason=%s, prompt_len=%s, schema_len=%s, preview=%r)",
                request_name,
                exc,
                telemetry.raw_text_length,
                telemetry.response_block_types,
                telemetry.stop_reason,
                telemetry.prompt_length,
                telemetry.schema_length,
                telemetry.raw_preview,
            )
        except Exception as exc:
            telemetry.parse_error = str(exc)
            logger.warning(
                "%s retry_parse_failed: %s (text_len=%s, block_types=%s, stop_reason=%s, prompt_len=%s, schema_len=%s, preview=%r)",
                request_name,
                exc,
                telemetry.raw_text_length,
                telemetry.response_block_types,
                telemetry.stop_reason,
                telemetry.prompt_length,
                telemetry.schema_length,
                telemetry.raw_preview,
            )

    if not raw_text.strip():
        telemetry.repair_error = "Empty model response"
        _log_structured_output_event(telemetry, success=False)
        logger.error(
            "%s empty_response_after_retry text_len=%s block_types=%s retry_attempted=%s retry_succeeded=%s preview=%r",
            request_name,
            telemetry.raw_text_length,
            telemetry.response_block_types,
            telemetry.retry_attempted,
            telemetry.retry_succeeded,
            telemetry.raw_preview,
        )
        raise StructuredJsonError(
            f"{request_name} structured JSON failed after empty model response",
            telemetry=telemetry,
            raw_text=raw_text,
        )

    telemetry.repair_attempted = True
    try:
        repaired_text = _repair_json_text(
            client=client,
            model=model,
            raw_text=raw_text,
            schema_hint=schema_hint,
            max_tokens=repair_max_tokens,
        )
        payload = extract_json_object(repaired_text)
        value = response_model.model_validate(payload)
        telemetry.generation_channel = "text_json_repair"
        telemetry.repair_succeeded = True
        logger.info("%s repair_succeeded", request_name)
        _log_structured_output_event(telemetry, success=True)
        return StructuredJsonResult(
            value=value,
            raw_text=repaired_text,
            telemetry=telemetry,
        )
    except ValidationError as exc:
        telemetry.validation_failed = True
        telemetry.validation_error = str(exc)
        telemetry.repair_error = str(exc)
        logger.warning("%s repair_validation_failed: %s", request_name, exc)
        _log_structured_output_event(telemetry, success=False)
        logger.error(
            "%s structured_json_error parse_failed=%s validation_failed=%s repair_attempted=%s repair_succeeded=%s parse_error=%s validation_error=%s repair_error=%s text_len=%s block_types=%s stop_reason=%s prompt_len=%s schema_len=%s retry_attempted=%s retry_succeeded=%s empty_response=%s preview=%r",
            request_name,
            telemetry.parse_failed,
            telemetry.validation_failed,
            telemetry.repair_attempted,
            telemetry.repair_succeeded,
            telemetry.parse_error,
            telemetry.validation_error,
            telemetry.repair_error,
            telemetry.raw_text_length,
            telemetry.response_block_types,
            telemetry.stop_reason,
            telemetry.prompt_length,
            telemetry.schema_length,
            telemetry.retry_attempted,
            telemetry.retry_succeeded,
            telemetry.empty_response,
            telemetry.raw_preview,
        )
        raise StructuredJsonError(
            f"{request_name} structured JSON failed after repair validation: {exc}",
            telemetry=telemetry,
            raw_text=raw_text,
        ) from exc
    except Exception as exc:
        telemetry.repair_error = str(exc)
        logger.warning("%s repair_failed: %s", request_name, exc)
        _log_structured_output_event(telemetry, success=False)
        logger.error(
            "%s structured_json_error parse_failed=%s validation_failed=%s repair_attempted=%s repair_succeeded=%s parse_error=%s validation_error=%s repair_error=%s text_len=%s block_types=%s stop_reason=%s prompt_len=%s schema_len=%s retry_attempted=%s retry_succeeded=%s empty_response=%s preview=%r",
            request_name,
            telemetry.parse_failed,
            telemetry.validation_failed,
            telemetry.repair_attempted,
            telemetry.repair_succeeded,
            telemetry.parse_error,
            telemetry.validation_error,
            telemetry.repair_error,
            telemetry.raw_text_length,
            telemetry.response_block_types,
            telemetry.stop_reason,
            telemetry.prompt_length,
            telemetry.schema_length,
            telemetry.retry_attempted,
            telemetry.retry_succeeded,
            telemetry.empty_response,
            telemetry.raw_preview,
        )
        raise StructuredJsonError(
            f"{request_name} structured JSON failed after repair: {exc}",
            telemetry=telemetry,
            raw_text=raw_text,
        ) from exc


def request_native_structured_json(
    *,
    client: Anthropic,
    model: str,
    prompt: str,
    response_model: type[ModelT],
    max_tokens: int,
    request_name: str,
    system: str | None = None,
    json_schema: dict | None = None,
    payload_sanitizer: Callable[[object], tuple[object, bool]] | None = None,
) -> StructuredJsonResult[ModelT]:
    telemetry = StructuredJsonTelemetry(
        request_name=request_name,
        generation_channel="native_json_schema",
    )
    schema = _normalize_native_json_schema(json_schema or response_model.model_json_schema())
    telemetry.prompt_length = len(prompt)
    telemetry.schema_length = len(json.dumps(schema, ensure_ascii=False, sort_keys=True))

    try:
        raw_text, response, block_types = _call_model_for_native_json(
            client=client,
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            json_schema=schema,
            system=system,
        )
    except Exception as exc:
        telemetry.provider_error = str(exc)
        _log_structured_output_event(telemetry, success=False)
        logger.error("%s native_provider_error: %s", request_name, exc)
        raise StructuredJsonError(
            f"{request_name} native structured request failed: {exc}",
            telemetry=telemetry,
            raw_text="",
        ) from exc

    _capture_completion_observability(telemetry, response, prompt=prompt, schema=schema)
    telemetry.response_block_types = block_types
    _capture_raw_observability(telemetry, raw_text)
    if not raw_text.strip():
        telemetry.parse_failed = True
        telemetry.parse_error = "Empty model response"
        _log_structured_output_event(telemetry, success=False)
        logger.error(
            "%s native_empty_response block_types=%s",
            request_name,
            telemetry.response_block_types,
        )
        raise StructuredJsonError(
            f"{request_name} native structured JSON returned an empty response",
            telemetry=telemetry,
            raw_text=raw_text,
        )

    try:
        payload = extract_json_object(raw_text)
        payload = _apply_payload_sanitizer(
            telemetry,
            payload,
            payload_sanitizer,
            request_name=request_name,
        )
        value = response_model.model_validate(payload)
        _log_structured_output_event(telemetry, success=True)
        return StructuredJsonResult(
            value=value,
            raw_text=raw_text,
            telemetry=telemetry,
        )
    except ValidationError as exc:
        telemetry.validation_failed = True
        telemetry.validation_error = str(exc)
        _log_structured_output_event(telemetry, success=False)
        logger.error(
            "%s native_validation_failed: %s (text_len=%s, block_types=%s, stop_reason=%s, prompt_len=%s, schema_len=%s, payload_sanitize_attempted=%s, payload_sanitized=%s, preview=%r)",
            request_name,
            exc,
            telemetry.raw_text_length,
            telemetry.response_block_types,
            telemetry.stop_reason,
            telemetry.prompt_length,
            telemetry.schema_length,
            telemetry.payload_sanitize_attempted,
            telemetry.payload_sanitized,
            telemetry.raw_preview,
        )
        raise StructuredJsonError(
            f"{request_name} native structured JSON validation failed: {exc}",
            telemetry=telemetry,
            raw_text=raw_text,
        ) from exc
    except Exception as exc:
        telemetry.parse_failed = True
        telemetry.parse_error = str(exc)
        salvage_text: str | None = None
        if telemetry.stop_reason == "max_tokens":
            telemetry.repair_attempted = True
            salvage_text = _close_truncated_json(raw_text)
        if salvage_text:
            try:
                payload = extract_json_object(salvage_text)
                payload = _apply_payload_sanitizer(
                    telemetry,
                    payload,
                    payload_sanitizer,
                    request_name=request_name,
                )
                value = response_model.model_validate(payload)
                telemetry.generation_channel = "native_json_schema_salvage"
                telemetry.repair_succeeded = True
                telemetry.parse_error = None
                telemetry.parse_failed = False
                _capture_raw_observability(telemetry, salvage_text)
                logger.info("%s native_salvage_succeeded", request_name)
                _log_structured_output_event(telemetry, success=True)
                return StructuredJsonResult(
                    value=value,
                    raw_text=salvage_text,
                    telemetry=telemetry,
                )
            except ValidationError as salvage_exc:
                telemetry.validation_failed = True
                telemetry.validation_error = str(salvage_exc)
                telemetry.repair_error = str(salvage_exc)
            except Exception as salvage_exc:
                telemetry.repair_error = str(salvage_exc)
        _log_structured_output_event(telemetry, success=False)
        logger.error(
            "%s native_parse_failed: %s (text_len=%s, block_types=%s, stop_reason=%s, prompt_len=%s, schema_len=%s, repair_attempted=%s, repair_succeeded=%s, repair_error=%s, payload_sanitize_attempted=%s, payload_sanitized=%s, preview=%r)",
            request_name,
            exc,
            telemetry.raw_text_length,
            telemetry.response_block_types,
            telemetry.stop_reason,
            telemetry.prompt_length,
            telemetry.schema_length,
            telemetry.repair_attempted,
            telemetry.repair_succeeded,
            telemetry.repair_error,
            telemetry.payload_sanitize_attempted,
            telemetry.payload_sanitized,
            telemetry.raw_preview,
        )
        raise StructuredJsonError(
            f"{request_name} native structured JSON failed: {exc}",
            telemetry=telemetry,
            raw_text=raw_text,
        ) from exc


async def request_structured_json_async(
    *,
    client: AsyncAnthropic,
    model: str,
    prompt: str,
    response_model: type[ModelT],
    schema_hint: str,
    max_tokens: int,
    repair_max_tokens: int,
    request_name: str,
    system: str | None = None,
) -> StructuredJsonResult[ModelT]:
    telemetry = StructuredJsonTelemetry(request_name=request_name)
    telemetry.prompt_length = len(prompt)
    telemetry.schema_length = len(schema_hint)
    raw_text, response, block_types = await _call_model_for_text_async(
        client=client,
        model=model,
        prompt=prompt,
        max_tokens=max_tokens,
        system=system,
    )
    _capture_completion_observability(telemetry, response, prompt=prompt, schema=schema_hint)
    telemetry.response_block_types = block_types
    _capture_raw_observability(telemetry, raw_text)

    try:
        payload = extract_json_object(raw_text)
        value = response_model.model_validate(payload)
        _log_structured_output_event(telemetry, success=True)
        return StructuredJsonResult(
            value=value,
            raw_text=raw_text,
            telemetry=telemetry,
        )
    except ValidationError as exc:
        telemetry.validation_failed = True
        telemetry.validation_error = str(exc)
        logger.warning(
            "%s validation_failed: %s (text_len=%s, block_types=%s, stop_reason=%s, prompt_len=%s, schema_len=%s, preview=%r)",
            request_name,
            exc,
            telemetry.raw_text_length,
            telemetry.response_block_types,
            telemetry.stop_reason,
            telemetry.prompt_length,
            telemetry.schema_length,
            telemetry.raw_preview,
        )
    except Exception as exc:
        telemetry.parse_failed = True
        telemetry.parse_error = str(exc)
        logger.warning(
            "%s parse_failed: %s (text_len=%s, block_types=%s, stop_reason=%s, prompt_len=%s, schema_len=%s, preview=%r)",
            request_name,
            exc,
            telemetry.raw_text_length,
            telemetry.response_block_types,
            telemetry.stop_reason,
            telemetry.prompt_length,
            telemetry.schema_length,
            telemetry.raw_preview,
        )

    if telemetry.empty_response:
        telemetry.retry_attempted = True
        retry_text, retry_response, retry_block_types = await _call_model_for_text_async(
            client=client,
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            system=system,
        )
        _capture_completion_observability(telemetry, retry_response, prompt=prompt, schema=schema_hint)
        telemetry.response_block_types = _merge_block_types(telemetry.response_block_types, retry_block_types)
        raw_text = retry_text
        _capture_raw_observability(telemetry, raw_text)

        try:
            payload = extract_json_object(raw_text)
            value = response_model.model_validate(payload)
            telemetry.retry_succeeded = True
            _log_structured_output_event(telemetry, success=True)
            return StructuredJsonResult(
                value=value,
                raw_text=raw_text,
                telemetry=telemetry,
            )
        except ValidationError as exc:
            telemetry.validation_failed = True
            telemetry.validation_error = str(exc)
            logger.warning(
                "%s retry_validation_failed: %s (text_len=%s, block_types=%s, stop_reason=%s, prompt_len=%s, schema_len=%s, preview=%r)",
                request_name,
                exc,
                telemetry.raw_text_length,
                telemetry.response_block_types,
                telemetry.stop_reason,
                telemetry.prompt_length,
                telemetry.schema_length,
                telemetry.raw_preview,
            )
        except Exception as exc:
            telemetry.parse_error = str(exc)
            logger.warning(
                "%s retry_parse_failed: %s (text_len=%s, block_types=%s, stop_reason=%s, prompt_len=%s, schema_len=%s, preview=%r)",
                request_name,
                exc,
                telemetry.raw_text_length,
                telemetry.response_block_types,
                telemetry.stop_reason,
                telemetry.prompt_length,
                telemetry.schema_length,
                telemetry.raw_preview,
            )

    if not raw_text.strip():
        telemetry.repair_error = "Empty model response"
        _log_structured_output_event(telemetry, success=False)
        logger.error(
            "%s empty_response_after_retry text_len=%s block_types=%s retry_attempted=%s retry_succeeded=%s preview=%r",
            request_name,
            telemetry.raw_text_length,
            telemetry.response_block_types,
            telemetry.retry_attempted,
            telemetry.retry_succeeded,
            telemetry.raw_preview,
        )
        raise StructuredJsonError(
            f"{request_name} structured JSON failed after empty model response",
            telemetry=telemetry,
            raw_text=raw_text,
        )

    telemetry.repair_attempted = True
    try:
        repaired_text = await _repair_json_text_async(
            client=client,
            model=model,
            raw_text=raw_text,
            schema_hint=schema_hint,
            max_tokens=repair_max_tokens,
        )
        payload = extract_json_object(repaired_text)
        value = response_model.model_validate(payload)
        telemetry.generation_channel = "text_json_repair"
        telemetry.repair_succeeded = True
        logger.info("%s repair_succeeded", request_name)
        _log_structured_output_event(telemetry, success=True)
        return StructuredJsonResult(
            value=value,
            raw_text=repaired_text,
            telemetry=telemetry,
        )
    except ValidationError as exc:
        telemetry.validation_failed = True
        telemetry.validation_error = str(exc)
        telemetry.repair_error = str(exc)
        logger.warning("%s repair_validation_failed: %s", request_name, exc)
        _log_structured_output_event(telemetry, success=False)
        logger.error(
            "%s structured_json_error parse_failed=%s validation_failed=%s repair_attempted=%s repair_succeeded=%s parse_error=%s validation_error=%s repair_error=%s text_len=%s block_types=%s stop_reason=%s prompt_len=%s schema_len=%s retry_attempted=%s retry_succeeded=%s empty_response=%s preview=%r",
            request_name,
            telemetry.parse_failed,
            telemetry.validation_failed,
            telemetry.repair_attempted,
            telemetry.repair_succeeded,
            telemetry.parse_error,
            telemetry.validation_error,
            telemetry.repair_error,
            telemetry.raw_text_length,
            telemetry.response_block_types,
            telemetry.stop_reason,
            telemetry.prompt_length,
            telemetry.schema_length,
            telemetry.retry_attempted,
            telemetry.retry_succeeded,
            telemetry.empty_response,
            telemetry.raw_preview,
        )
        raise StructuredJsonError(
            f"{request_name} structured JSON failed after repair validation: {exc}",
            telemetry=telemetry,
            raw_text=raw_text,
        ) from exc
    except Exception as exc:
        telemetry.repair_error = str(exc)
        logger.warning("%s repair_failed: %s", request_name, exc)
        _log_structured_output_event(telemetry, success=False)
        logger.error(
            "%s structured_json_error parse_failed=%s validation_failed=%s repair_attempted=%s repair_succeeded=%s parse_error=%s validation_error=%s repair_error=%s text_len=%s block_types=%s stop_reason=%s prompt_len=%s schema_len=%s retry_attempted=%s retry_succeeded=%s empty_response=%s preview=%r",
            request_name,
            telemetry.parse_failed,
            telemetry.validation_failed,
            telemetry.repair_attempted,
            telemetry.repair_succeeded,
            telemetry.parse_error,
            telemetry.validation_error,
            telemetry.repair_error,
            telemetry.raw_text_length,
            telemetry.response_block_types,
            telemetry.stop_reason,
            telemetry.prompt_length,
            telemetry.schema_length,
            telemetry.retry_attempted,
            telemetry.retry_succeeded,
            telemetry.empty_response,
            telemetry.raw_preview,
        )
        raise StructuredJsonError(
            f"{request_name} structured JSON failed after repair: {exc}",
            telemetry=telemetry,
            raw_text=raw_text,
        ) from exc


async def request_native_structured_json_async(
    *,
    client: AsyncAnthropic,
    model: str,
    prompt: str,
    response_model: type[ModelT],
    max_tokens: int,
    request_name: str,
    system: str | None = None,
    json_schema: dict | None = None,
    payload_sanitizer: Callable[[object], tuple[object, bool]] | None = None,
) -> StructuredJsonResult[ModelT]:
    telemetry = StructuredJsonTelemetry(
        request_name=request_name,
        generation_channel="native_json_schema",
    )
    schema = _normalize_native_json_schema(json_schema or response_model.model_json_schema())
    telemetry.prompt_length = len(prompt)
    telemetry.schema_length = len(json.dumps(schema, ensure_ascii=False, sort_keys=True))

    try:
        raw_text, response, block_types = await _call_model_for_native_json_async(
            client=client,
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            json_schema=schema,
            system=system,
        )
    except Exception as exc:
        telemetry.provider_error = str(exc)
        _log_structured_output_event(telemetry, success=False)
        logger.error("%s native_provider_error: %s", request_name, exc)
        raise StructuredJsonError(
            f"{request_name} native structured request failed: {exc}",
            telemetry=telemetry,
            raw_text="",
        ) from exc

    _capture_completion_observability(telemetry, response, prompt=prompt, schema=schema)
    telemetry.response_block_types = block_types
    _capture_raw_observability(telemetry, raw_text)
    if not raw_text.strip():
        telemetry.parse_failed = True
        telemetry.parse_error = "Empty model response"
        _log_structured_output_event(telemetry, success=False)
        logger.error(
            "%s native_empty_response block_types=%s",
            request_name,
            telemetry.response_block_types,
        )
        raise StructuredJsonError(
            f"{request_name} native structured JSON returned an empty response",
            telemetry=telemetry,
            raw_text=raw_text,
        )

    try:
        payload = extract_json_object(raw_text)
        payload = _apply_payload_sanitizer(
            telemetry,
            payload,
            payload_sanitizer,
            request_name=request_name,
        )
        value = response_model.model_validate(payload)
        _log_structured_output_event(telemetry, success=True)
        return StructuredJsonResult(
            value=value,
            raw_text=raw_text,
            telemetry=telemetry,
        )
    except ValidationError as exc:
        telemetry.validation_failed = True
        telemetry.validation_error = str(exc)
        _log_structured_output_event(telemetry, success=False)
        logger.error(
            "%s native_validation_failed: %s (text_len=%s, block_types=%s, stop_reason=%s, prompt_len=%s, schema_len=%s, payload_sanitize_attempted=%s, payload_sanitized=%s, preview=%r)",
            request_name,
            exc,
            telemetry.raw_text_length,
            telemetry.response_block_types,
            telemetry.stop_reason,
            telemetry.prompt_length,
            telemetry.schema_length,
            telemetry.payload_sanitize_attempted,
            telemetry.payload_sanitized,
            telemetry.raw_preview,
        )
        raise StructuredJsonError(
            f"{request_name} native structured JSON validation failed: {exc}",
            telemetry=telemetry,
            raw_text=raw_text,
        ) from exc
    except Exception as exc:
        telemetry.parse_failed = True
        telemetry.parse_error = str(exc)
        salvage_text: str | None = None
        if telemetry.stop_reason == "max_tokens":
            telemetry.repair_attempted = True
            salvage_text = _close_truncated_json(raw_text)
        if salvage_text:
            try:
                payload = extract_json_object(salvage_text)
                payload = _apply_payload_sanitizer(
                    telemetry,
                    payload,
                    payload_sanitizer,
                    request_name=request_name,
                )
                value = response_model.model_validate(payload)
                telemetry.generation_channel = "native_json_schema_salvage"
                telemetry.repair_succeeded = True
                telemetry.parse_error = None
                telemetry.parse_failed = False
                _capture_raw_observability(telemetry, salvage_text)
                logger.info("%s native_salvage_succeeded", request_name)
                _log_structured_output_event(telemetry, success=True)
                return StructuredJsonResult(
                    value=value,
                    raw_text=salvage_text,
                    telemetry=telemetry,
                )
            except ValidationError as salvage_exc:
                telemetry.validation_failed = True
                telemetry.validation_error = str(salvage_exc)
                telemetry.repair_error = str(salvage_exc)
            except Exception as salvage_exc:
                telemetry.repair_error = str(salvage_exc)
        _log_structured_output_event(telemetry, success=False)
        logger.error(
            "%s native_parse_failed: %s (text_len=%s, block_types=%s, stop_reason=%s, prompt_len=%s, schema_len=%s, repair_attempted=%s, repair_succeeded=%s, repair_error=%s, payload_sanitize_attempted=%s, payload_sanitized=%s, preview=%r)",
            request_name,
            exc,
            telemetry.raw_text_length,
            telemetry.response_block_types,
            telemetry.stop_reason,
            telemetry.prompt_length,
            telemetry.schema_length,
            telemetry.repair_attempted,
            telemetry.repair_succeeded,
            telemetry.repair_error,
            telemetry.payload_sanitize_attempted,
            telemetry.payload_sanitized,
            telemetry.raw_preview,
        )
        raise StructuredJsonError(
            f"{request_name} native structured JSON failed: {exc}",
            telemetry=telemetry,
            raw_text=raw_text,
        ) from exc
