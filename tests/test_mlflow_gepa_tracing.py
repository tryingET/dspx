# summary: "Tests GEPA optimization tracing without noisy MLflow span failures."
# read_when:
#   - "Changing GEPA optimization or MLflow DSPy tracing integration."

from __future__ import annotations

import csv
import logging
from pathlib import Path

from dspx.services.optimize_service import run_gepa_optimize
from dspx.tracing import enable_mlflow_from_env


def test_gepa_tracing_enabled_has_no_noisy_span_start_failures(
    monkeypatch, tmp_path: Path, caplog
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")
    monkeypatch.setenv("MLFLOW_EXPERIMENT", "DSPxGEPAWarnings")

    assert enable_mlflow_from_env() is True

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
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    train = tmp_path / "train.csv"
    with train.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["question", "answer"])
        w.writeheader()
        w.writerow({"question": "What is 2+2?", "answer": "4"})
        w.writerow({"question": "What is 3+3?", "answer": "6"})

    caplog.set_level(logging.WARNING, logger="mlflow.tracing.fluent")

    run_gepa_optimize(
        program_path=program,
        train_path=train,
        out_dir=tmp_path / "optimized",
        auto=None,
        max_metric_calls=1,
        seed=0,
    )

    fluent_warnings = "\n".join(
        rec.getMessage()
        for rec in caplog.records
        if rec.name == "mlflow.tracing.fluent"
    )
    assert "Failed to start span" not in fluent_warnings
