"""Baseline evaluation harness.

Runs the shipped example exchanges (see the `evaluations/` folder) against a
critic model and reports how well the critic's verdicts match the expected
severity/quality, plus how fast it is. Each case is run several times (default
5) so both compliance *and* consistency/latency are visible.

These cases are deliberately simple and "obvious" — a baseline capability check
for a critic model, not a frontier stress test.

Run it with:

    agent-critic-eval --config config/config.yaml
    # or: python -m agent_critic.evaluate --config config/config.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import yaml

from .config import Config, RouteRubric, load_config
from .critic import critique
from .models import CritiqueRequest


@dataclass
class Case:
    id: str
    route: str
    system_prompt: str
    user_prompt: str
    assistant_response: str
    expected_severity: list[str]
    expected_quality: list[str]


@dataclass
class CaseResult:
    case: Case
    severities: list[str] = field(default_factory=list)
    qualities: list[str] = field(default_factory=list)
    complied: list[bool] = field(default_factory=list)
    latencies_ms: list[float] = field(default_factory=list)
    fallbacks: int = 0

    @property
    def pass_count(self) -> int:
        return sum(self.complied)

    @property
    def rate(self) -> float:
        return self.pass_count / len(self.complied) if self.complied else 0.0


def _as_list(value) -> list[str]:
    return [value] if isinstance(value, str) else list(value)


def load_rubrics(evaldir: Path) -> dict[str, str]:
    data = yaml.safe_load((evaldir / "rubrics.yaml").read_text(encoding="utf-8"))
    return {r["name"]: r["quality_rubric"] for r in data["routes"]}


def load_cases(evaldir: Path) -> list[Case]:
    cases: list[Case] = []
    for path in sorted((evaldir / "cases").glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        expected = raw["expected"]
        cases.append(
            Case(
                id=raw.get("id", path.stem),
                route=raw["route"],
                system_prompt=raw["system_prompt"],
                user_prompt=raw["user_prompt"],
                assistant_response=raw["assistant_response"],
                expected_severity=_as_list(expected["severity"]),
                expected_quality=_as_list(expected["quality"]),
            )
        )
    return cases


def complies(env, case: Case) -> bool:
    """True when the verdict matches the case's expected values. A fallback
    envelope (the critic failed to produce a usable verdict) never complies."""
    if env.meta.get("fallback"):
        return False
    return env.severity in case.expected_severity and env.quality in case.expected_quality


def build_config(config_path: str, rubrics: dict[str, str]) -> Config:
    """Load the deployment config but inject the evaluation rubrics, so the
    rubric used to judge each case travels with the evaluation set rather than
    depending on whatever routes the local config.yaml happens to define."""
    cfg = load_config(config_path)
    cfg.routes = [RouteRubric(name=name, quality_rubric=text) for name, text in rubrics.items()]
    return cfg


async def run_case(
    client: httpx.AsyncClient, cfg: Config, case: Case, repeats: int, critic_key: str | None
) -> CaseResult:
    result = CaseResult(case=case)
    for _ in range(repeats):
        request = CritiqueRequest(
            route=case.route,
            system_prompt=case.system_prompt,
            user_prompt=case.user_prompt,
            assistant_response=case.assistant_response,
            critic_model=critic_key,
        )
        env = await critique(client, cfg, request)
        result.severities.append(env.severity)
        result.qualities.append(env.quality)
        result.complied.append(complies(env, case))
        result.latencies_ms.append(env.meta.get("latency_ms", 0))
        if env.meta.get("fallback"):
            result.fallbacks += 1
    return result


async def run_all(cfg: Config, cases: list[Case], repeats: int, critic_key: str | None) -> list[CaseResult]:
    async with httpx.AsyncClient() as client:
        results = []
        for case in cases:
            results.append(await run_case(client, cfg, case, repeats, critic_key))
        return results


def _observed(result: CaseResult) -> str:
    sev = Counter(result.severities).most_common(1)[0][0]
    qual = Counter(result.qualities).most_common(1)[0][0]
    return f"{sev} / {qual}"


def report(results: list[CaseResult], threshold: float, max_latency_ms: float | None) -> bool:
    print("\nAgent Critic — baseline evaluations")
    line = f"pass threshold: {threshold:.0%}"
    if max_latency_ms:
        line += f"   max mean latency: {max_latency_ms:.0f} ms"
    print(line + "\n")

    header = (
        f"{'CASE':<34} {'ROUTE':<8} {'STATUS':<6} {'COMPLY':<7} "
        f"{'OBSERVED sev/qual':<24} {'LATENCY ms min/mean/max'}"
    )
    print(header)
    print("-" * len(header))

    cases_passed = 0
    total_runs = total_complied = total_fallbacks = 0
    all_latencies: list[float] = []

    for r in results:
        mean_lat = statistics.mean(r.latencies_ms) if r.latencies_ms else 0
        slow = bool(max_latency_ms) and mean_lat > max_latency_ms
        passed = r.rate >= threshold and not slow
        cases_passed += passed
        total_runs += len(r.complied)
        total_complied += r.pass_count
        total_fallbacks += r.fallbacks
        all_latencies.extend(r.latencies_ms)

        latency = f"{min(r.latencies_ms):.0f} / {mean_lat:.0f} / {max(r.latencies_ms):.0f}"
        flags = " ⚠ slow" if slow else ""
        print(
            f"{r.case.id:<34} {r.case.route:<8} {'PASS' if passed else 'FAIL':<6} "
            f"{f'{r.pass_count}/{len(r.complied)}':<7} {_observed(r):<24} {latency}{flags}"
        )

    print("-" * len(header))
    overall = statistics.mean(all_latencies) if all_latencies else 0
    print(
        f"\nSummary: {cases_passed}/{len(results)} cases passed · "
        f"{total_complied}/{total_runs} runs complied · "
        f"{total_fallbacks} fallback envelope(s) · "
        f"overall latency mean {overall:.0f} ms"
    )
    return cases_passed == len(results)


def main() -> None:
    parser = argparse.ArgumentParser(prog="agent-critic-eval", description=__doc__)
    parser.add_argument("--config", default="config/config.yaml", help="Deployment config (model endpoints).")
    parser.add_argument("--evaldir", default="evaluations", help="Folder holding rubrics.yaml and cases/.")
    parser.add_argument("--repeats", type=int, default=5, help="Runs per case (default 5).")
    parser.add_argument("--critic", default=None, help="Pool key to pin as the critic (else selection default).")
    parser.add_argument("--threshold", type=float, default=0.6, help="Min compliance rate for a case to pass.")
    parser.add_argument(
        "--max-latency-ms", type=float, default=None, help="Flag cases whose mean latency exceeds this."
    )
    args = parser.parse_args()

    evaldir = Path(args.evaldir)
    rubrics = load_rubrics(evaldir)
    cases = load_cases(evaldir)
    if not cases:
        raise SystemExit(f"No evaluation cases found under {evaldir / 'cases'}.")

    cfg = build_config(args.config, rubrics)
    results = asyncio.run(run_all(cfg, cases, args.repeats, args.critic))
    ok = report(results, args.threshold, args.max_latency_ms)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
