from __future__ import annotations

import argparse
import os
import sys
import time
from typing import List

import dspy

from dspx.provider_registry import ensure_default_providers, create
from dspx.multi_provider_lm import MultiProviderLM
from dspx.validators import non_empty, json_parsable, regex, contains_all, all_of, any_of
from dspx.tracing import enable_mlflow_from_env, ensure_run_from_env


def _build_validator(spec: str):
    if not spec or spec == "none":
        return non_empty()
    if spec == "json":
        return json_parsable()
    if spec.startswith("regex:"):
        return regex(spec.split(":", 1)[1])
    if spec.startswith("contains:"):
        words = [s for s in spec.split(":", 1)[1].split(",") if s]
        return contains_all(words)
    # default fallback
    return non_empty()


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compare multi-provider LM strategies with optional MLflow logging.")
    ap.add_argument("prompt", help="Prompt text to run. Use @file:path to read from file.")
    ap.add_argument("--providers", default="codex-exec,claude-cli,gemini-cli", help="Comma-separated provider order.")
    ap.add_argument("--strategy", default="sequential_first", choices=["sequential_first","parallel_first","collect_concat","collect_longest"])
    ap.add_argument("--parallel-isolated", action="store_true", help="Run providers in isolated workdirs")
    ap.add_argument("--isolation-mode", default="mirror", choices=["mirror","git-worktree"], help="Isolation strategy when parallel_isolated")
    ap.add_argument("--base-cwd", default=None, help="Base repository path to mirror or use for worktrees")
    ap.add_argument("--worktree-commitish", default="HEAD", help="Commit-ish for git worktrees")
    ap.add_argument("--validator", default="none", help="Validator: none|json|regex:<pat>|contains:a,b,c")
    ap.add_argument("--bypass", action="store_true", help="Align bypass/policy across providers")
    ap.add_argument("--mlflow", action="store_true", help="Enable MLflow via env if available")

    args = ap.parse_args(argv)

    if args.prompt.startswith("@file:"):
        path = args.prompt.split(":",1)[1]
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            prompt = f.read()
    else:
        prompt = args.prompt

    ensure_default_providers()
    names = [s.strip() for s in args.providers.split(",") if s.strip()]
    provs = [create(n) for n in names]

    validator = _build_validator(args.validator)

    lm = MultiProviderLM(
        providers=provs,
        names=names,
        strategy=args.strategy,
        parallel_isolated=args.parallel_isolated,
        isolation_mode=args.isolation_mode,
        base_cwd=args.base_cwd,
        worktree_commitish=args.worktree_commitish,
        policy_bypass_permissions=True if args.bypass else None,
        validator=validator,
    )
    dspy.configure(lm=lm)

    if args.mlflow:
        os.environ.setdefault("MLFLOW_ENABLE", "1")
        enable_mlflow_from_env()
        ensure_run_from_env(run_name=os.getenv("MLFLOW_RUN_NAME", f"multi-demo-{int(time.time())}"), tags={
            "strategy": args.strategy,
            "parallel_isolated": str(args.parallel_isolated),
            "isolation_mode": args.isolation_mode,
            "providers": args.providers,
        })

    t0 = time.time()
    p = dspy.Predict("question -> answer")
    out = p(question=prompt)
    t1 = time.time()

    text = getattr(out, "answer", None)
    if text is None:
        # Predict("question -> answer") returns attribute .answer under DSPy
        # but some versions may use .output; fallback
        text = getattr(out, "output", "")

    print("=== RESULT ===")
    print((text or "").strip())
    print()
    print(f"Total duration: {t1 - t0:.2f}s")

    # MLflow: log outputs and timings if enabled
    if args.mlflow:
        try:
            import mlflow
            mlflow.log_metric("duration_total_s", t1 - t0)  # type: ignore[attr-defined]
            mlflow.log_text((text or ""), artifact_file="output/final.txt")  # type: ignore[attr-defined]
            # Log per-provider timings from the multi-lm last_results
            lr = getattr(lm, "last_results", [])
            winner = None
            best_end = None
            for r in lr:
                prov = r.name or (r.model or "provider")
                mlflow.log_metric(f"provider.{prov}.duration_s", (r.ended_at - r.started_at))  # type: ignore[attr-defined]
                mlflow.log_text(r.text or "", artifact_file=f"output/{prov}.txt")  # type: ignore[attr-defined]
                if best_end is None or r.ended_at < best_end:
                    best_end = r.ended_at
                    winner = prov
            if winner:
                mlflow.set_tag("winner", winner)  # type: ignore[attr-defined]
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
