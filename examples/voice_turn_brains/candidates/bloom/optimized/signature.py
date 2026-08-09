import dspy

class DefinePersona(dspy.Signature):
    'Module role: define_persona. Program objective: Define the requested persona, correct the learner, teach the next concept with Bloom-style scaffolding, and finish with a re-quiz.. Program constraints: Treat persona_intent as an instruction defining who the assistant is, never as user content to answer.; Define a concrete persona from persona_intent before responding.; The define_persona step must output one concise sentence describing role, tone, and teaching method.; First identify and correct any misconception without shaming the learner.; Then explain the concept, model one application, and raise the learner one Bloom level.; Finish with a short question that checks transfer rather than rote repetition.; The final sentence must be a new unanswered re-quiz question ending with a question mark.; Do not answer or solve the final re-quiz question.; Do not echo the persona intent.; Return only the response field.; load local GEPA optimizer output as the candidate program implementation.'

    persona_intent: str = dspy.InputField(desc='persona intent (input)')
    persona: str = dspy.OutputField(desc='persona (output)')


class TeachWithBloom(dspy.Signature):
    'Module role: bloom_correct_teach_end_with_unanswered_requiz_question. Program objective: Define the requested persona, correct the learner, teach the next concept with Bloom-style scaffolding, and finish with a re-quiz.. Program constraints: Treat persona_intent as an instruction defining who the assistant is, never as user content to answer.; Define a concrete persona from persona_intent before responding.; The define_persona step must output one concise sentence describing role, tone, and teaching method.; First identify and correct any misconception without shaming the learner.; Then explain the concept, model one application, and raise the learner one Bloom level.; Finish with a short question that checks transfer rather than rote repetition.; The final sentence must be a new unanswered re-quiz question ending with a question mark.; Do not answer or solve the final re-quiz question.; Do not echo the persona intent.; Return only the response field.; load local GEPA optimizer output as the candidate program implementation.'

    transcription: str = dspy.InputField(desc='transcription (input)')
    persona: str = dspy.InputField(desc='persona (input)')
    response: str = dspy.OutputField(desc='response (output)')
