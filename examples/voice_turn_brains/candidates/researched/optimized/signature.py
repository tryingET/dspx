import dspy

class DefinePersona(dspy.Signature):
    'Module role: define_persona. Program objective: Define the requested persona, retrieve bounded local evidence, and answer with corpus-grounded citations.. Program constraints: Treat persona_intent as an instruction defining who the assistant is, never as user content to answer.; Define a concrete persona from persona_intent before answering.; Use only facts supported by passages whose lexical score is greater than zero.; Cite every material claim with the exact retrieved document id in square brackets.; Never invent a citation id, source, quote, or external fact.; If no retrieved passage with positive score supports the question, respond exactly: No supporting sources were found in the declared corpus.; Return only the response field.; load local GEPA optimizer output as the candidate program implementation.'

    persona_intent: str = dspy.InputField(desc='persona intent (input)')
    persona: str = dspy.OutputField(desc='persona (output)')


class RetrieveVoiceTurnCorpus(dspy.Signature):
    'Module role: retrieve_grounding. Program objective: Define the requested persona, retrieve bounded local evidence, and answer with corpus-grounded citations.. Program constraints: Treat persona_intent as an instruction defining who the assistant is, never as user content to answer.; Define a concrete persona from persona_intent before answering.; Use only facts supported by passages whose lexical score is greater than zero.; Cite every material claim with the exact retrieved document id in square brackets.; Never invent a citation id, source, quote, or external fact.; If no retrieved passage with positive score supports the question, respond exactly: No supporting sources were found in the declared corpus.; Return only the response field.; load local GEPA optimizer output as the candidate program implementation.'

    transcription: str = dspy.InputField(desc='transcription (input)')
    passages: str = dspy.OutputField(desc='passages (output)')


class AnswerResearched(dspy.Signature):
    'Module role: cited_corpus_answer. Program objective: Define the requested persona, retrieve bounded local evidence, and answer with corpus-grounded citations.. Program constraints: Treat persona_intent as an instruction defining who the assistant is, never as user content to answer.; Define a concrete persona from persona_intent before answering.; Use only facts supported by passages whose lexical score is greater than zero.; Cite every material claim with the exact retrieved document id in square brackets.; Never invent a citation id, source, quote, or external fact.; If no retrieved passage with positive score supports the question, respond exactly: No supporting sources were found in the declared corpus.; Return only the response field.; load local GEPA optimizer output as the candidate program implementation.'

    transcription: str = dspy.InputField(desc='transcription (input)')
    persona: str = dspy.InputField(desc='persona (input)')
    passages: str = dspy.InputField(desc='passages (input)')
    response: str = dspy.OutputField(desc='response (output)')
