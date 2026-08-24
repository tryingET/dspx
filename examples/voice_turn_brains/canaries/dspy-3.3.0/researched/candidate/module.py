import json

import dspy

from signature import (
    DefinePersona,
    RetrieveVoiceTurnCorpus,
    AnswerResearched,
)


def _retriever_tokens(value: object) -> set[str]:
    text = ''.join(ch.lower() if ch.isalnum() else ' ' for ch in str(value))
    return {part for part in text.split() if part}


def _select_inline_documents(query: object, documents: list[dict[str, str]], k: int) -> list[dict[str, object]]:
    query_tokens = _retriever_tokens(query)
    scored: list[tuple[int, int, dict[str, str]]] = []
    for index, document in enumerate(documents):
        document_tokens = _retriever_tokens(document.get('text', ''))
        score = len(query_tokens & document_tokens)
        scored.append((score, index, document))
    scored.sort(key=lambda item: (-item[0], item[1]))
    selected = []
    for score, _index, document in scored[:k]:
        selected.append({'id': document.get('id', ''), 'text': document.get('text', ''), 'score': score})
    return selected

class DefinePersonaModule(dspy.Module):
    'define_persona'

    def __init__(self, use_cot: bool = False) -> None:
        super().__init__()
        self.predict = dspy.Predict(DefinePersona)

    def forward(self, persona_intent: str) -> dspy.Prediction:
        return self.predict(persona_intent=persona_intent)


class RetrieveVoiceTurnCorpusModule(dspy.Module):
    'retrieve_grounding'

    _DOCUMENTS = [{'id': 'voice-turn-owner-split', 'text': 'The batch voice-turn has three explicit owners. softwareco/infra/workstation owns physical OpenDeck actions, the dictation activation lease, microphone capture, and clipboard transcript delivery. softwareco/owned/local-ai-control-plane owns ai-control voice-turn composition, brain and TTS invocation, and the single sanitized receipt. softwareco/owned/dspx owns the six separate DSPy brain programs and their GEPA optimization evidence.'}, {'id': 'voice-turn-capture-contract', 'text': 'Capture reuses the existing dictate-clip path. The OpenDeck action starts an acknowledged same-user lease on the voice-dictation control socket; a second press releases that lease. When the combined gate becomes inactive, voice-dictation injects finalizing silence and publishes the final transcript to the clipboard. local-ai-control-plane never touches this lease.'}, {'id': 'voice-turn-batch-scope', 'text': 'The v1 hardware-triggered voice-turn is batch and one-time: capture one utterance, run exactly one selected mode brain, synthesize one answer, and persist one receipt. Streaming, a continuing interactive loop, and Pipecat belong to a later real-time phase and are not part of v1.'}, {'id': 'voice-turn-research-boundary', 'text': 'The researched and deep-research brains retrieve only from an operator-declared bounded inline or local corpus snapshot. They do not use live external retrieval, ReAct tool binding, or fabricated sources. If retrieved passages do not support an answer, the brain must say that no supporting sources were found.'}, {'id': 'voice-turn-receipt-boundary', 'text': 'A voice-turn receipt is evidence, not promotion authority. It may contain mode identifiers, model identifiers, timings, statuses, and SHA-256 digests, but it must not contain raw utterance, persona intent, transcript, answer text, or raw artifact paths. Operator-visible stdout may carry in-flight transcript and answer text.'}, {'id': 'voice-turn-modality-boundary', 'text': 'The voice-turn is a composed audio-to-audio route: captured audio becomes text, a text-generation brain transforms it, and TTS produces audio. A composed route is not a native omni model and must never be labeled native-omni.'}, {'id': 'voice-turn-gepa-boundary', 'text': 'GEPA optimization in DSPx consumes explicit behavior examples, writes hash-bound optimizer output, and requires a separate materialize-gepa-candidate step to create an optimized candidate manifest. Optimization and materialization are local empirical evidence; neither selects a winner, approves promotion, activates production, mutates governance, or transfers authority.'}]
    _K = 3

    def __init__(self, use_cot: bool = False) -> None:
        super().__init__()

    def forward(self, transcription: str) -> dspy.Prediction:
        selected = _select_inline_documents(str(transcription), self._DOCUMENTS, self._K)
        return dspy.Prediction(passages=json.dumps(selected, ensure_ascii=False, sort_keys=True))


class AnswerResearchedModule(dspy.Module):
    'cited_corpus_answer'

    def __init__(self, use_cot: bool = False) -> None:
        super().__init__()
        self.predict = dspy.ChainOfThought(AnswerResearched)

    def forward(self, transcription: str, persona: str, passages: str) -> dspy.Prediction:
        return self.predict(transcription=transcription, persona=persona, passages=passages)


def build_modules(*, use_cot: bool = False) -> dict[str, dspy.Module]:
    """Construct the generated topology module instances."""
    return {
        'define_persona': DefinePersonaModule(use_cot=use_cot),
        'retrieve_corpus': RetrieveVoiceTurnCorpusModule(use_cot=use_cot),
        'answer_researched': AnswerResearchedModule(use_cot=use_cot),
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
