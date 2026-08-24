# summary: "Provides a minimal credential-free typed-stub DSPy prediction example."
# read_when:
#   - "Changing the supported provider example or typed DSPy call boundary."

import dspy

from dspx.provider_registry import create


def main() -> int:
    lm = create("stub")
    dspy.configure(lm=lm)
    qa = dspy.Predict("question -> answer")
    result = qa(question="Say hello")
    print(result.answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
