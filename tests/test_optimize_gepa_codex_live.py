# summary: "Live-gated Codex GEPA optimization smoke test with a loadable DSPy artifact."
# read_when:
#   - "Changing live Codex-backed GEPA optimization."

from __future__ import annotations

import csv
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import dspy

from dspx.services.optimize_service import run_gepa_optimize


pytestmark = [pytest.mark.live, pytest.mark.model]


def _codex_ready() -> bool:
    if shutil.which("codex") is None:
        return False

    checks = (
        ["codex", "login", "status"],
        ["codex", "auth", "whoami"],
    )
    for cmd in checks:
        p = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if p.returncode == 0:
            return True
    return False


@pytest.mark.skipif(
    os.getenv("DSPX_RUN_LIVE_TESTS", "0").lower() not in {"1", "true", "yes"},
    reason="set DSPX_RUN_LIVE_TESTS=1 to run live Codex GEPA test",
)
@pytest.mark.skipif(
    not _codex_ready(),
    reason="codex CLI not available or not authenticated (codex login status)",
)
def test_gepa_codex_live_smoke(tmp_path: Path) -> None:
    os.environ["DSPX_PROVIDER"] = "codex-exec"

    program = tmp_path / "prog.py"
    program.write_text(
        "\n".join(
            [
                "import dspy",
                "",
                "class Student(dspy.Module):",
                "    def __init__(self):",
                "        super().__init__()",
                "        self.predict = dspy.Predict('question -> answer')",
                "",
                "    def forward(self, question: str) -> dspy.Prediction:",
                "        return self.predict(question=question)",
                "",
                "def build_student() -> dspy.Module:",
                "    return Student()",
                "",
            ]
        ),
        encoding="utf-8",
    )

    train = tmp_path / "train.csv"
    with train.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["question", "answer"])
        w.writeheader()
        # Keep it permissive: metric=contains and answer="hello".
        for _ in range(3):
            w.writerow(
                {"question": "Reply with the single word: hello", "answer": "hello"}
            )

    out_dir = tmp_path / "optimized"
    res = run_gepa_optimize(
        program_path=program,
        train_path=train,
        out_dir=out_dir,
        input_keys=["question"],
        output_keys=["answer"],
        student_provider="codex-exec",
        reflection_provider="codex-exec",
        auto=None,
        max_metric_calls=2,
        metric="contains",
        seed=0,
        nrows=3,
    )
    assert (res.out_dir / "manifest.json").exists()

    loaded = dspy.load(str(res.out_dir), allow_pickle=True)
    pred = loaded(question="Reply with the single word: hello")
    assert isinstance(pred, dspy.Prediction)
