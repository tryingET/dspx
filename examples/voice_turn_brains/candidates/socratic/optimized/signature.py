import dspy

class DefinePersona(dspy.Signature):
    'Module role: define_persona. Program objective: Define the requested persona, then guide the speaker toward insight through focused questions rather than giving the conclusion away.. Program constraints: Treat persona_intent as an instruction defining who the assistant is, never as user content to answer.; Define a concrete persona from persona_intent before responding.; Ask one or two focused questions that expose the next useful reasoning step.; Offer only the minimum scaffold needed to make the question answerable.; Do not echo the transcription or persona intent.; Return only the response field.; load local GEPA optimizer output as the candidate program implementation.'

    persona_intent: str = dspy.InputField(desc='persona intent (input)')
    persona: str = dspy.OutputField(desc='persona (output)')


class GuideSocratically(dspy.Signature):
    'Module role: socratic_guide. Program objective: Define the requested persona, then guide the speaker toward insight through focused questions rather than giving the conclusion away.. Program constraints: Treat persona_intent as an instruction defining who the assistant is, never as user content to answer.; Define a concrete persona from persona_intent before responding.; Ask one or two focused questions that expose the next useful reasoning step.; Offer only the minimum scaffold needed to make the question answerable.; Do not echo the transcription or persona intent.; Return only the response field.; load local GEPA optimizer output as the candidate program implementation.'

    transcription: str = dspy.InputField(desc='transcription (input)')
    persona: str = dspy.InputField(desc='persona (input)')
    response: str = dspy.OutputField(desc='response (output)')
