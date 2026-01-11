from __future__ import annotations

import csv
import os
from pathlib import Path

import dspy

from dspx.services.optimize_service import run_gepa_optimize


def test_gepa_optimize_saves_loadable_program(tmp_path: Path) -> None:
    os.environ["DSPX_PROVIDER"] = "stub"

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
        w.writerow({"question": "What is 2+2?", "answer": "4"})
        w.writerow({"question": "What is 3+3?", "answer": "6"})

    out_dir = tmp_path / "optimized"
    res = run_gepa_optimize(
        program_path=program,
        train_path=train,
        out_dir=out_dir,
        auto="light",
        max_metric_calls=2,
        seed=0,
    )

    assert res.out_dir.exists() and res.out_dir.is_dir()

    loaded = dspy.load(str(res.out_dir))
    pred = loaded(question="hello")
    assert isinstance(pred, dspy.Prediction)
