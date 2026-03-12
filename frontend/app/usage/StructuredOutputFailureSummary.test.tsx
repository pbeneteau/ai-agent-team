import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { StructuredOutputFailureSummary } from "./StructuredOutputFailureSummary";

describe("StructuredOutputFailureSummary", () => {
  it("renders a compact last-failure summary", () => {
    const html = renderToStaticMarkup(
      <StructuredOutputFailureSummary
        flow="knowledge_readiness"
        failure={{
          at: "2026-03-10T10:00:00+00:00",
          request_name: "knowledge_audit:agent-1",
          channel: "native_json_schema",
          error_kind: "validation",
          stop_reason: "max_tokens",
          validation_failed: true,
          message: "Field required: recommendations.0.summary",
        }}
      />,
    );

    expect(html).toContain("Latest failure");
    expect(html).toContain("Schema mismatch");
    expect(html).toContain("Validation failed");
    expect(html).toContain("max_tokens");
    expect(html).toContain("Native schema");
    expect(html).toContain("Field required");
    expect(html).toContain("Next action");
  });

  it("renders nothing without failure data", () => {
    const html = renderToStaticMarkup(
      <StructuredOutputFailureSummary flow="knowledge_readiness" failure={null} />,
    );

    expect(html).toBe("");
  });
});
