#!/usr/bin/env python3
"""
Benchmark: mono-agent Claude Opus vs multi-agent orchestrator.

Usage:
    python backend/scripts/benchmark.py "Analyse the competitive landscape for AI code assistants"
    python backend/scripts/benchmark.py --task "My task description" --base-url http://localhost:8000

Requires: ANTHROPIC_API_KEY env var and a running backend for multi-agent mode.
"""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from anthropic import AsyncAnthropic


API_BASE = "http://localhost:8000/api"
MONO_MODEL = "claude-opus-4-5"
JUDGE_MODEL = "claude-sonnet-4-5-20250514"
POLL_INTERVAL = 5  # seconds

TEST_TASKS = {
    "yc_eval": {
        "title": "YC Application Evaluation",
        "description": (
            "Evaluate the viability of a startup idea: an AI-powered platform that automates "
            "due diligence for venture capital firms. Cover market size (TAM/SAM/SOM), competitive "
            "landscape, technical feasibility, go-to-market strategy, and potential risks. "
            "Provide a structured analysis with concrete data points and a final recommendation."
        ),
    },
    "market_analysis": {
        "title": "AI Code Assistants Market Analysis",
        "description": (
            "Produce a comprehensive competitive analysis of the AI code assistant market in 2026. "
            "Include market share estimates, pricing comparison, feature matrices, developer satisfaction "
            "data, and emerging trends. Cover GitHub Copilot, Cursor, Claude Code, Windsurf, and "
            "any significant new entrants. Cite sources where possible."
        ),
    },
    "technical_report": {
        "title": "RAG Architecture Technical Report",
        "description": (
            "Write a technical report on state-of-the-art Retrieval-Augmented Generation (RAG) "
            "architectures. Compare naive RAG, advanced RAG (with reranking, query decomposition, "
            "hybrid search), and agentic RAG approaches. Include benchmarks, trade-offs (latency vs "
            "accuracy), cost analysis, and recommendations for production deployment. "
            "The report should be suitable for a senior engineering audience."
        ),
    },
}

JUDGE_PROMPT = """\
You are an expert evaluator comparing two outputs for the same task.

## Task
{task_description}

## Output A (Multi-agent system)
{multi_result}

## Output B (Single Claude Opus call)
{mono_result}

## Instructions
Score each output on 4 dimensions (1-10 scale):
1. **Completeness**: Does it cover all aspects of the task?
2. **Source quality**: Are claims backed by specific data, sources, or evidence?
3. **Accuracy**: Are the facts and reasoning correct?
4. **Structure**: Is the output well-organized and easy to follow?

Return ONLY a JSON object with this exact structure:
{{
  "multi_agent": {{"completeness": N, "source_quality": N, "accuracy": N, "structure": N}},
  "mono_agent": {{"completeness": N, "source_quality": N, "accuracy": N, "structure": N}},
  "reasoning": "Brief explanation of key differences"
}}
"""


async def run_mono_agent(task_description: str, api_key: str) -> dict:
    """Single Claude Opus call with the raw task description."""
    client = AsyncAnthropic(api_key=api_key)
    t0 = time.monotonic()
    resp = await client.messages.create(
        model=MONO_MODEL,
        max_tokens=8192,
        messages=[{"role": "user", "content": task_description}],
    )
    elapsed = time.monotonic() - t0
    result_text = resp.content[0].text if resp.content else ""
    return {
        "mode": "mono-agent",
        "model": MONO_MODEL,
        "duration_s": round(elapsed, 2),
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "result_length": len(result_text),
        "result_preview": result_text[:500],
        "result_full": result_text,
    }


async def run_multi_agent(task_description: str, base_url: str) -> dict:
    """Create and execute a task via the orchestrator API, then poll until done."""
    async with httpx.AsyncClient(base_url=base_url, timeout=300) as http:
        # Create task
        create_resp = await http.post(
            "/api/tasks",
            json={
                "title": task_description[:80],
                "description": task_description,
                "priority": "medium",
                "execution_mode": "auto",
            },
        )
        create_resp.raise_for_status()
        task = create_resp.json()
        task_id = task["id"]
        print(f"  [multi] Task created: {task_id}")

        # Execute
        exec_resp = await http.post(f"/api/tasks/{task_id}/execute")
        exec_resp.raise_for_status()
        print("  [multi] Execution started, polling…")

        # Poll
        t0 = time.monotonic()
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            status_resp = await http.get(f"/api/tasks/{task_id}")
            status_resp.raise_for_status()
            task_data = status_resp.json()
            status = task_data["status"]
            elapsed = time.monotonic() - t0
            print(f"  [multi] {elapsed:.0f}s — status={status}")
            if status in ("completed", "failed"):
                break
            if elapsed > 600:
                print("  [multi] Timeout after 10 minutes")
                break

        elapsed = time.monotonic() - t0
        plan = task_data.get("execution_plan", {})
        nodes = plan.get("nodes", [])
        result_text = task_data.get("result") or ""

        # Aggregate node-level metadata
        all_sources = []
        all_assumptions = []
        all_warnings = []
        quality_scores = []
        for n in nodes:
            all_sources.extend(n.get("sources", []))
            all_assumptions.extend(n.get("assumptions", []))
            all_warnings.extend(n.get("warnings", []))
            qs = n.get("quality_score")
            if qs is not None:
                quality_scores.append(qs)

        avg_quality = round(sum(quality_scores) / len(quality_scores)) if quality_scores else None

        return {
            "mode": "multi-agent",
            "status": status,
            "duration_s": round(elapsed, 2),
            "node_count": len(nodes),
            "result_length": len(result_text),
            "result_preview": result_text[:500],
            "sources": all_sources,
            "assumptions": all_assumptions,
            "warnings": all_warnings,
            "quality_scores": quality_scores,
            "avg_quality_score": avg_quality,
        }


def generate_report(task_description: str, mono: dict, multi: dict) -> str:
    """Generate a markdown benchmark report."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Benchmark Report — {ts}",
        "",
        "## Task",
        f"> {task_description}",
        "",
        "## Comparison",
        "",
        "| Metric | Mono-agent (Opus) | Multi-agent (Orchestrator) |",
        "|--------|-------------------|----------------------------|",
        f"| Duration | {mono['duration_s']}s | {multi['duration_s']}s |",
        f"| Tokens (input) | {mono['input_tokens']} | — |",
        f"| Tokens (output) | {mono['output_tokens']} | — |",
        f"| Nodes | 1 | {multi['node_count']} |",
        f"| Result length | {mono['result_length']} chars | {multi['result_length']} chars |",
        f"| Sources | — | {len(multi['sources'])} |",
        f"| Assumptions | — | {len(multi['assumptions'])} |",
        f"| Warnings | — | {len(multi['warnings'])} |",
        f"| Avg quality score | — | {multi['avg_quality_score'] or 'N/A'}/100 |",
        "",
        "## Quality scores per node",
        "",
    ]

    if multi["quality_scores"]:
        for i, qs in enumerate(multi["quality_scores"], 1):
            lines.append(f"- Node {i}: **{qs}/100**")
    else:
        lines.append("_No quality scores available._")

    lines.extend([
        "",
        "## Mono-agent result (first 500 chars)",
        "",
        "```",
        mono["result_preview"],
        "```",
        "",
        "## Multi-agent result (first 500 chars)",
        "",
        "```",
        multi["result_preview"],
        "```",
        "",
    ])

    return "\n".join(lines)


async def judge_outputs(
    task_description: str,
    mono_result: str,
    multi_result: str,
    api_key: str,
) -> dict:
    """Use Claude Sonnet as an LLM judge to compare outputs on 4 axes."""
    client = AsyncAnthropic(api_key=api_key)
    prompt = JUDGE_PROMPT.format(
        task_description=task_description,
        multi_result=multi_result[:6000],
        mono_result=mono_result[:6000],
    )
    resp = await client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text if resp.content else "{}"
    # Extract JSON from response
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(text[start:end])
    return {"error": "Failed to parse judge response", "raw": text}


def generate_suite_report(results: list[dict]) -> str:
    """Generate an aggregate markdown report from multiple benchmark runs."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Benchmark Suite Report — {ts}", ""]

    dims = ["completeness", "source_quality", "accuracy", "structure"]
    multi_totals = {d: 0.0 for d in dims}
    mono_totals = {d: 0.0 for d in dims}
    count = 0

    for r in results:
        lines.extend([
            f"## {r['title']}",
            f"> {r['description'][:120]}…" if len(r['description']) > 120 else f"> {r['description']}",
            "",
            "| Dimension | Multi-agent | Mono-agent | Winner |",
            "|-----------|-------------|------------|--------|",
        ])
        judge = r.get("judge", {})
        ma = judge.get("multi_agent", {})
        sa = judge.get("mono_agent", {})
        for d in dims:
            ms = ma.get(d, "?")
            ss = sa.get(d, "?")
            winner = "Multi" if isinstance(ms, (int, float)) and isinstance(ss, (int, float)) and ms > ss else "Mono" if isinstance(ms, (int, float)) and isinstance(ss, (int, float)) and ss > ms else "Tie"
            lines.append(f"| {d.replace('_', ' ').title()} | {ms}/10 | {ss}/10 | {winner} |")
            if isinstance(ms, (int, float)) and isinstance(ss, (int, float)):
                multi_totals[d] += ms
                mono_totals[d] += ss
        count += 1
        reasoning = judge.get("reasoning", "")
        if reasoning:
            lines.extend(["", f"**Judge reasoning:** {reasoning}", ""])
        lines.extend([
            f"| Duration | {r.get('multi_duration', '?')}s | {r.get('mono_duration', '?')}s | |",
            f"| Result length | {r.get('multi_length', '?')} | {r.get('mono_length', '?')} | |",
            "",
        ])

    if count > 0:
        lines.extend(["## Aggregate", "", "| Dimension | Multi-agent avg | Mono-agent avg | Winner |", "|-----------|-----------------|----------------|--------|"])
        multi_wins = 0
        mono_wins = 0
        for d in dims:
            ma_avg = round(multi_totals[d] / count, 1)
            sa_avg = round(mono_totals[d] / count, 1)
            winner = "Multi" if ma_avg > sa_avg else "Mono" if sa_avg > ma_avg else "Tie"
            if ma_avg > sa_avg:
                multi_wins += 1
            elif sa_avg > ma_avg:
                mono_wins += 1
            lines.append(f"| {d.replace('_', ' ').title()} | {ma_avg}/10 | {sa_avg}/10 | {winner} |")
        lines.extend([
            "",
            "## Verdict",
            "",
            f"Multi-agent wins on **{multi_wins}/{len(dims)}** dimensions, "
            f"mono-agent on **{mono_wins}/{len(dims)}**.",
            "",
        ])

    return "\n".join(lines)


async def run_suite(api_key: str, base_url: str) -> str:
    """Run all TEST_TASKS, judge results, and return a suite report."""
    results = []
    for key, task_info in TEST_TASKS.items():
        desc = task_info["description"]
        print(f"\n{'='*60}")
        print(f"Task: {task_info['title']}")
        print(f"{'='*60}")

        print("▶ Running mono-agent…")
        mono = await run_mono_agent(desc, api_key)
        print(f"  Done in {mono['duration_s']}s")

        print("▶ Running multi-agent…")
        try:
            multi = await run_multi_agent(desc, base_url)
            print(f"  Done in {multi['duration_s']}s — {multi['node_count']} nodes")
        except httpx.ConnectError:
            print("  Error: cannot connect to backend")
            continue

        if multi.get("status") == "failed":
            print("  Multi-agent task failed, skipping judge")
            continue

        print("▶ Judging outputs…")
        judge = await judge_outputs(desc, mono["result_full"], multi.get("result_preview", "")[:6000], api_key)
        print(f"  Judge: {json.dumps(judge, indent=2)}")

        results.append({
            "key": key,
            "title": task_info["title"],
            "description": desc,
            "judge": judge,
            "multi_duration": multi["duration_s"],
            "mono_duration": mono["duration_s"],
            "multi_length": multi["result_length"],
            "mono_length": mono["result_length"],
        })

    return generate_suite_report(results)


async def main():
    parser = argparse.ArgumentParser(description="Benchmark mono-agent vs multi-agent")
    parser.add_argument("task", nargs="?", help="Task description")
    parser.add_argument("--task", dest="task_flag", help="Task description (alternative)")
    parser.add_argument("--base-url", default=API_BASE, help="Backend base URL")
    parser.add_argument("--mono-only", action="store_true", help="Run only mono-agent")
    parser.add_argument("--multi-only", action="store_true", help="Run only multi-agent")
    parser.add_argument("--suite", action="store_true", help="Run all predefined test tasks with LLM judge")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if args.suite:
        if not api_key:
            print("Error: ANTHROPIC_API_KEY required for suite mode")
            sys.exit(1)
        report = await run_suite(api_key, args.base_url)
        out_dir = Path(__file__).resolve().parent.parent / "data" / "benchmarks"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"suite_{ts}.md"
        out_path.write_text(report, encoding="utf-8")
        print(f"\n✅ Suite report saved to {out_path}")
        print(report)
        return

    task_description = args.task or args.task_flag
    if not task_description:
        print("Error: provide a task description as argument or via --task (or use --suite)")
        sys.exit(1)

    if not api_key and not args.multi_only:
        print("Error: ANTHROPIC_API_KEY env var required for mono-agent mode")
        sys.exit(1)

    mono_result = None
    multi_result = None

    if not args.multi_only:
        print("▶ Running mono-agent (Claude Opus)…")
        mono_result = await run_mono_agent(task_description, api_key)
        print(f"  Done in {mono_result['duration_s']}s — {mono_result['result_length']} chars")

    if not args.mono_only:
        print("▶ Running multi-agent (orchestrator)…")
        try:
            multi_result = await run_multi_agent(task_description, args.base_url)
            print(f"  Done in {multi_result['duration_s']}s — {multi_result['result_length']} chars — {multi_result['node_count']} nodes")
        except httpx.ConnectError:
            print("  Error: cannot connect to backend. Is it running?")
            if not mono_result:
                sys.exit(1)

    if mono_result and multi_result:
        report = generate_report(task_description, mono_result, multi_result)
        out_dir = Path(__file__).resolve().parent.parent / "data" / "benchmarks"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"{ts}.md"
        out_path.write_text(report, encoding="utf-8")
        print(f"\n✅ Report saved to {out_path}")
        print(report)
    elif mono_result:
        print(f"\nMono-agent result ({mono_result['result_length']} chars):")
        print(mono_result["result_preview"])
    elif multi_result:
        print(f"\nMulti-agent result ({multi_result['result_length']} chars, quality avg: {multi_result['avg_quality_score']}):")
        print(multi_result["result_preview"])


if __name__ == "__main__":
    asyncio.run(main())
