from __future__ import annotations

from program import build_program, intent_summary, io_spec


def main() -> None:
    program = build_program()
    assert program is not None
    assert io_spec()['inputs'] == ['transcription', 'persona_intent']
    assert io_spec()['outputs'] == ['response']
    assert intent_summary()['objective']
    print('program smoke ok: VoiceTurnSimpleBrain')


if __name__ == '__main__':
    main()

SAMPLE_INPUTS = {'transcription': 'sample_transcription', 'persona_intent': 'sample_persona_intent'}