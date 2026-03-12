from pydantic import BaseModel, Field
import pytest

from app.config import get_settings
from app.core.usage_tracker import get_usage_tracker
from app.core import usage_tracker as usage_tracker_module
from app.core.structured_json import (
    StructuredJsonError,
    extract_json_object,
    parse_structured_json_text,
    request_native_structured_json,
    request_native_structured_json_async,
    request_structured_json,
    request_structured_json_async,
)


class _SimplePayload(BaseModel):
    foo: str


class _NestedPayload(BaseModel):
    title: str
    meta: _SimplePayload


class _BoundedListPayload(BaseModel):
    items: list[str] = Field(default_factory=list, max_length=1)


class _BoundedIntPayload(BaseModel):
    score: int = Field(ge=0, le=100)


class _SanitizedTopicPayload(BaseModel):
    suggested_topic: str = Field(max_length=12)


class _FakeTextBlock:
    def __init__(self, text: str):
        self.text = text


class _FakeUsage:
    def __init__(self, input_tokens: int = 12, output_tokens: int = 8):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeResponse:
    def __init__(self, text: str, *, stop_reason: str = "end_turn"):
        self.content = [_FakeTextBlock(text)]
        self.usage = _FakeUsage()
        self.stop_reason = stop_reason


def _normalize_response_spec(item):
    if isinstance(item, dict):
        return item.get("text", ""), item.get("stop_reason", "end_turn")
    return item, "end_turn"


class _FakeMessages:
    def __init__(self, responses: list[str]):
        self._responses = iter(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text, stop_reason = _normalize_response_spec(next(self._responses))
        return _FakeResponse(text, stop_reason=stop_reason)


class _FakeClient:
    def __init__(self, responses: list[str]):
        self.messages = _FakeMessages(responses)


class _AsyncFakeMessages:
    def __init__(self, responses: list[str]):
        self._responses = iter(responses)

    async def create(self, **_kwargs):
        text, stop_reason = _normalize_response_spec(next(self._responses))
        return _FakeResponse(text, stop_reason=stop_reason)


class _AsyncFakeClient:
    def __init__(self, responses: list[str]):
        self.messages = _AsyncFakeMessages(responses)


@pytest.fixture(autouse=True)
def _structured_json_test_env(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key-for-smoke")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    get_settings.cache_clear()
    usage_tracker_module._tracker = None
    yield
    get_settings.cache_clear()
    usage_tracker_module._tracker = None


def test_extract_json_object_accepts_code_fence_and_prefix():
    raw = 'Sure, here is the payload:\n```json\n{"foo":"bar"}\n```'
    assert extract_json_object(raw) == {"foo": "bar"}


def test_parse_structured_json_text_exposes_preview():
    result = parse_structured_json_text(
        raw_text='Sure, here is the payload:\n```json\n{"foo":"bar"}\n```',
        response_model=_SimplePayload,
        request_name="unit_parse_text",
        response_block_types=["text"],
    )

    assert result.value.foo == "bar"
    assert result.telemetry.raw_preview is not None
    assert "payload" in result.telemetry.raw_preview
    assert result.telemetry.response_block_types == ["text"]


def test_parse_structured_json_text_logs_validation_failure():
    with pytest.raises(StructuredJsonError) as exc_info:
        parse_structured_json_text(
            raw_text='{"foo": 123}',
            response_model=_SimplePayload,
            request_name="unit_parse_validation_failure",
            response_block_types=["text"],
        )

    assert exc_info.value.telemetry.validation_failed is True
    assert exc_info.value.telemetry.validation_error is not None
    flow = get_usage_tracker().summary()["structured_outputs"]["by_flow"]["unit_parse_validation_failure"]
    assert flow["failures"] == 1
    assert flow["failures_by_kind"]["validation"] == 1
    assert flow["last_failure"]["error_kind"] == "validation"
    assert flow["last_failure"]["validation_failed"] is True


def test_request_structured_json_repairs_invalid_payload():
    client = _FakeClient(
        responses=[
            '{"foo": "bar"',
            '{"foo": "bar"}',
        ]
    )

    result = request_structured_json(
        client=client,
        model="claude-test",
        prompt="Return JSON",
        response_model=_SimplePayload,
        schema_hint='{"foo":"string"}',
        max_tokens=200,
        repair_max_tokens=200,
        request_name="unit_test",
    )

    assert result.value.foo == "bar"
    assert result.telemetry.parse_failed is True
    assert result.telemetry.repair_attempted is True
    assert result.telemetry.repair_succeeded is True
    assert result.telemetry.stop_reason == "end_turn"
    flow = get_usage_tracker().summary()["structured_outputs"]["by_flow"]["unit_test"]
    assert flow["channels"]["text_json_repair"] == 1
    assert flow["successes"] == 1


def test_request_structured_json_raises_when_repair_also_fails():
    client = _FakeClient(
        responses=[
            '{"foo": "bar"',
            "still not json",
        ]
    )

    with pytest.raises(StructuredJsonError) as exc_info:
        request_structured_json(
            client=client,
            model="claude-test",
            prompt="Return JSON",
            response_model=_SimplePayload,
            schema_hint='{"foo":"string"}',
            max_tokens=200,
            repair_max_tokens=200,
            request_name="unit_test_failure",
        )

    assert exc_info.value.telemetry.parse_failed is True
    assert exc_info.value.telemetry.repair_attempted is True
    assert exc_info.value.telemetry.repair_succeeded is False
    assert exc_info.value.telemetry.repair_error is not None


def test_request_structured_json_retries_after_empty_response():
    client = _FakeClient(
        responses=[
            "",
            '{"foo": "bar"}',
        ]
    )

    result = request_structured_json(
        client=client,
        model="claude-test",
        prompt="Return JSON",
        response_model=_SimplePayload,
        schema_hint='{"foo":"string"}',
        max_tokens=200,
        repair_max_tokens=200,
        request_name="unit_test_empty_retry",
    )

    assert result.value.foo == "bar"
    assert result.telemetry.parse_failed is True
    assert result.telemetry.empty_response is False
    assert result.telemetry.retry_attempted is True
    assert result.telemetry.retry_succeeded is True


def test_request_structured_json_raises_empty_response_after_retry():
    client = _FakeClient(
        responses=[
            "",
            "",
        ]
    )

    with pytest.raises(StructuredJsonError) as exc_info:
        request_structured_json(
            client=client,
            model="claude-test",
            prompt="Return JSON",
            response_model=_SimplePayload,
            schema_hint='{"foo":"string"}',
            max_tokens=200,
            repair_max_tokens=200,
            request_name="unit_test_empty_retry_failure",
        )

    assert exc_info.value.telemetry.retry_attempted is True
    assert exc_info.value.telemetry.retry_succeeded is False
    assert exc_info.value.telemetry.repair_attempted is False
    assert exc_info.value.telemetry.repair_error == "Empty model response"
    flow = get_usage_tracker().summary()["structured_outputs"]["by_flow"]["unit_test_empty_retry_failure"]
    assert flow["failures_by_kind"]["empty_response"] == 1


def test_request_native_structured_json_validates_payload():
    client = _FakeClient(responses=['{"foo": "bar"}'])

    result = request_native_structured_json(
        client=client,
        model="claude-test",
        prompt="Return JSON",
        response_model=_SimplePayload,
        max_tokens=200,
        request_name="unit_test_native",
    )

    assert result.value.foo == "bar"
    assert result.telemetry.generation_channel == "native_json_schema"
    assert result.telemetry.parse_failed is False
    assert result.telemetry.validation_failed is False
    assert result.telemetry.repair_attempted is False
    assert result.telemetry.stop_reason == "end_turn"
    flow = get_usage_tracker().summary()["structured_outputs"]["by_flow"]["unit_test_native"]
    assert flow["channels"]["native_json_schema"] == 1
    assert flow["successes"] == 1


def test_request_native_structured_json_raises_on_invalid_payload():
    client = _FakeClient(responses=['{"foo": 123}'])

    with pytest.raises(StructuredJsonError) as exc_info:
        request_native_structured_json(
            client=client,
            model="claude-test",
            prompt="Return JSON",
            response_model=_SimplePayload,
            max_tokens=200,
            request_name="unit_test_native_failure",
        )

    assert exc_info.value.telemetry.generation_channel == "native_json_schema"
    assert exc_info.value.telemetry.parse_failed is False
    assert exc_info.value.telemetry.validation_failed is True
    assert exc_info.value.telemetry.validation_error is not None
    assert exc_info.value.telemetry.repair_attempted is False
    flow = get_usage_tracker().summary()["structured_outputs"]["by_flow"]["unit_test_native_failure"]
    assert flow["channels"]["native_json_schema"] == 1
    assert flow["failures"] == 1
    assert flow["failures_by_kind"]["validation"] == 1
    assert flow["last_failure"]["error_kind"] == "validation"
    assert flow["last_failure"]["stop_reason"] == "end_turn"


def test_request_native_structured_json_normalizes_object_schema_for_anthropic():
    client = _FakeClient(responses=['{"title": "ok", "meta": {"foo": "bar"}}'])

    result = request_native_structured_json(
        client=client,
        model="claude-test",
        prompt="Return JSON",
        response_model=_NestedPayload,
        max_tokens=200,
        request_name="unit_test_native_schema_normalized",
    )

    assert result.value.title == "ok"
    schema = client.messages.calls[0]["output_config"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["_SimplePayload"]["additionalProperties"] is False


def test_request_native_structured_json_removes_unsupported_max_items_from_schema():
    client = _FakeClient(responses=['{"items": ["one"]}'])

    result = request_native_structured_json(
        client=client,
        model="claude-test",
        prompt="Return JSON",
        response_model=_BoundedListPayload,
        max_tokens=200,
        request_name="unit_test_native_schema_without_max_items",
    )

    assert result.value.items == ["one"]
    schema = client.messages.calls[0]["output_config"]["format"]["schema"]
    assert "maxItems" not in schema["properties"]["items"]


def test_request_native_structured_json_keeps_local_validation_for_bounded_lists():
    client = _FakeClient(responses=['{"items": ["one", "two"]}'])

    with pytest.raises(StructuredJsonError) as exc_info:
        request_native_structured_json(
            client=client,
            model="claude-test",
            prompt="Return JSON",
            response_model=_BoundedListPayload,
            max_tokens=200,
            request_name="unit_test_native_bounded_list_validation",
        )

    assert exc_info.value.telemetry.validation_failed is True
    flow = get_usage_tracker().summary()["structured_outputs"]["by_flow"]["unit_test_native_bounded_list_validation"]
    assert flow["failures_by_kind"]["validation"] == 1


def test_request_native_structured_json_removes_unsupported_numeric_bounds_from_schema():
    client = _FakeClient(responses=['{"score": 42}'])

    result = request_native_structured_json(
        client=client,
        model="claude-test",
        prompt="Return JSON",
        response_model=_BoundedIntPayload,
        max_tokens=200,
        request_name="unit_test_native_schema_without_numeric_bounds",
    )

    assert result.value.score == 42
    schema = client.messages.calls[0]["output_config"]["format"]["schema"]
    assert "minimum" not in schema["properties"]["score"]
    assert "maximum" not in schema["properties"]["score"]


def test_request_native_structured_json_keeps_local_validation_for_bounded_ints():
    client = _FakeClient(responses=['{"score": 101}'])

    with pytest.raises(StructuredJsonError) as exc_info:
        request_native_structured_json(
            client=client,
            model="claude-test",
            prompt="Return JSON",
            response_model=_BoundedIntPayload,
            max_tokens=200,
            request_name="unit_test_native_bounded_int_validation",
        )

    assert exc_info.value.telemetry.validation_failed is True
    flow = get_usage_tracker().summary()["structured_outputs"]["by_flow"]["unit_test_native_bounded_int_validation"]
    assert flow["failures_by_kind"]["validation"] == 1


def test_request_native_structured_json_applies_payload_sanitizer_before_validation():
    client = _FakeClient(responses=['{"suggested_topic":"this topic is definitely too long"}'])

    def _sanitize(payload):
        return {
            **payload,
            "suggested_topic": "short topic",
        }, True

    result = request_native_structured_json(
        client=client,
        model="claude-test",
        prompt="Return JSON",
        response_model=_SanitizedTopicPayload,
        max_tokens=200,
        request_name="unit_test_native_payload_sanitizer",
        payload_sanitizer=_sanitize,
    )

    assert result.value.suggested_topic == "short topic"
    assert result.telemetry.payload_sanitize_attempted is True
    assert result.telemetry.payload_sanitized is True


def test_request_native_structured_json_salvages_truncated_json_on_max_tokens():
    client = _FakeClient(
        responses=[
            {
                "text": '{"foo": "bar',
                "stop_reason": "max_tokens",
            }
        ]
    )

    result = request_native_structured_json(
        client=client,
        model="claude-test",
        prompt="Return JSON",
        response_model=_SimplePayload,
        max_tokens=200,
        request_name="unit_test_native_truncated_salvage",
    )

    assert result.value.foo == "bar"
    assert result.telemetry.generation_channel == "native_json_schema_salvage"
    assert result.telemetry.stop_reason == "max_tokens"
    assert result.telemetry.repair_attempted is True
    assert result.telemetry.repair_succeeded is True
    assert result.telemetry.parse_failed is False
    flow = get_usage_tracker().summary()["structured_outputs"]["by_flow"]["unit_test_native_truncated_salvage"]
    assert flow["channels"]["native_json_schema_salvage"] == 1
    assert flow["successes"] == 1


@pytest.mark.asyncio
async def test_request_structured_json_async_repairs_invalid_payload():
    client = _AsyncFakeClient(
        responses=[
            '{"foo": "bar"',
            '{"foo": "bar"}',
        ]
    )

    result = await request_structured_json_async(
        client=client,
        model="claude-test",
        prompt="Return JSON",
        response_model=_SimplePayload,
        schema_hint='{"foo":"string"}',
        max_tokens=200,
        repair_max_tokens=200,
        request_name="unit_test_async",
    )

    assert result.value.foo == "bar"
    assert result.telemetry.parse_failed is True
    assert result.telemetry.repair_attempted is True
    assert result.telemetry.repair_succeeded is True


@pytest.mark.asyncio
async def test_request_native_structured_json_async_validates_payload():
    client = _AsyncFakeClient(responses=['{"foo": "bar"}'])

    result = await request_native_structured_json_async(
        client=client,
        model="claude-test",
        prompt="Return JSON",
        response_model=_SimplePayload,
        max_tokens=200,
        request_name="unit_test_native_async",
    )

    assert result.value.foo == "bar"
    assert result.telemetry.generation_channel == "native_json_schema"
    assert result.telemetry.parse_failed is False
