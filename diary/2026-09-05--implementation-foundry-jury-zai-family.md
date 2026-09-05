---
summary: "Z.ai Coding Plan jury family, owner repin to 6c3473ca, and one live receipt-bound jury on a family recipe."
read_when:
  - "Using or extending the foundry-dspy-lm-auth-zai family."
type: "diary"
---

# Z.ai Coding Plan jury family (AK 5376) and live jury (AK 5377)

- Family `foundry-dspy-lm-auth-zai` mirrors the OpenCode Go family on the owner's new `ZaiBackend` (fork commit 6c3473ca): `pi-api-key`, fixed origin `https://api.z.ai`, catalog `/api/coding/paas/v4/models` (probed live: 200, ten ids), `glm-*` ids, default `glm-5.3`, 180 s.
- Preflight probe accepts `zai` as a bearer provider; CLI help lists the family; owner pin block regenerated with `tests/foundry_jury_owner_repin.py`; `zai_backend.py` added to the required extra owner files.
- Tests: `tests/test_program_foundry_gepa_comparison_jury_zai.py` derived from the OpenCode Go suite (GLM ids, Coding Plan paths); the five-name provider assertions became six. 392 jury-suite tests pass; ruff and ty clean.
- Live: the AK-5365 lineage could not be reused (its consumption receipt is bound one-shot to the local-vLLM jury attempt, "candidate receipt is not reusable"), so a fresh lineage ran end to end on the promoted family recipe Pfannenradieschen: export → import → program-gen/run → quality proposal → foundry (live Oracle) → execute-foundry-gepa → consume → Z.ai preflight → Z.ai jury (182 s, 3 × request_more_evidence: more behavior/runtime examples wanted) → adjudicate (require_review) → Misegraph verify-receipt (insufficient_evidence, live, decision null).
- First adjudicate call passed the consumption receipt by mistake and was refused ("must be canonical comparison-jury-receipt.json"); rerun with the jury receipt succeeded. Recorded in the lineage's commands-run.txt.
- `model_execution` in the quality proposal is still the injected test double (known hollow link, unchanged).
