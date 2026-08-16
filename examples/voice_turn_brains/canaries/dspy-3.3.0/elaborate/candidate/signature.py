import dspy

class DefinePersona(dspy.Signature):
    'Module role: define_persona. Program objective: Define the requested persona, then develop a complete, nuanced spoken answer to the transcription.. Program constraints: Treat persona_intent as an instruction defining who the assistant is, never as user content to answer.; Define a concrete persona from persona_intent before answering.; Develop the answer with context, reasoning, implications, and useful caveats.; Prefer coherent spoken prose over terse bullets.; Do not echo the transcription or persona intent.; Return only the response field..'

    persona_intent: str = dspy.InputField(desc='persona intent (input)')
    persona: str = dspy.OutputField(desc='persona (output)')


class AnswerElaborate(dspy.Signature):
    'Module role: developed_answer. Program objective: Define the requested persona, then develop a complete, nuanced spoken answer to the transcription.. Program constraints: Treat persona_intent as an instruction defining who the assistant is, never as user content to answer.; Define a concrete persona from persona_intent before answering.; Develop the answer with context, reasoning, implications, and useful caveats.; Prefer coherent spoken prose over terse bullets.; Do not echo the transcription or persona intent.; Return only the response field..'

    transcription: str = dspy.InputField(desc='transcription (input)')
    persona: str = dspy.InputField(desc='persona (input)')
    response: str = dspy.OutputField(desc='response (output)')
