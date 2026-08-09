import json

import dspy

from signature import (
    DefinePersona,
    TeachWithBloom,
)

class DefinePersonaModule(dspy.Module):
    'define_persona'

    def __init__(self, use_cot: bool = False) -> None:
        super().__init__()
        self.predict = dspy.Predict(DefinePersona)

    def forward(self, persona_intent: str) -> dspy.Prediction:
        return self.predict(persona_intent=persona_intent)


class TeachWithBloomModule(dspy.Module):
    'bloom_correct_teach_end_with_unanswered_requiz_question'

    def __init__(self, use_cot: bool = False) -> None:
        super().__init__()
        self.predict = dspy.Predict(TeachWithBloom)

    def forward(self, transcription: str, persona: str) -> dspy.Prediction:
        return self.predict(transcription=transcription, persona=persona)


def build_modules(*, use_cot: bool = False) -> dict[str, dspy.Module]:
    """Construct the generated topology module instances."""
    return {
        'define_persona': DefinePersonaModule(use_cot=use_cot),
        'teach_with_bloom': TeachWithBloomModule(use_cot=use_cot),
    }


def io_spec() -> dict[str, list[str]]:
    """Return the declared program IO contract."""
    return {'inputs': ['transcription', 'persona_intent'], 'outputs': ['response']}


def output_weights() -> dict[str, float]:
    """Provide deterministic output weighting for evaluation."""
    return {
        'response': 1.0,
    }


def normalize_output(
    key: str,
    gold: str,
    pred: str,
    pred_name: str | None = None,
    pred_trace: object | None = None,
) -> tuple[str, str]:
    """Normalize gold/pred pairs for deterministic checks."""
    if _json_container_text(gold) and _json_container_text(pred):
        return _normalize_json_text(gold), _normalize_json_text(pred)
    return gold, pred


def _json_container_text(value: str) -> bool:
    text = value.strip()
    return (text.startswith('{') and text.endswith('}')) or (text.startswith('[') and text.endswith(']'))


def _normalize_json_text(value: str) -> str:
    parsed = json.loads(value.strip())
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
