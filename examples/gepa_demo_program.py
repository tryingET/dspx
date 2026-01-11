from __future__ import annotations

import dspy


class Student(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.predict = dspy.Predict("question -> answer")

    def forward(self, question: str) -> dspy.Prediction:
        return self.predict(question=question)


def build_student() -> dspy.Module:
    return Student()


def io_spec():
    return (["question"], ["answer"])
