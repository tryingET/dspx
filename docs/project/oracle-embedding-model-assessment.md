---
summary: "Evidence-ranked MiniLM/mDenseOn/mLateOn assessment, preserved AK-4510 failure, and accepted AK-4517 mDenseOn adoption."
read_when:
  - "When selecting or changing the Oracle embedding model."
  - "When interpreting the preserved AK-4510 failure or AK-4517 recovery."
type: "reference"
---

# Oracle dense embedding model assessment

## Decision boundary

This assessment selects a **dense single-vector candidate** for DSPx Oracle. It does not select a semantic-analysis LM, authorize a shared coordinate store, establish broad semantic quality, or grant release, publication, promotion, or activation authority.

The checked-in MiniLM evaluation remains immutable historical evidence. A newer model may supersede the runtime default only after its own frozen Oracle-specific quality, identity, and bounded CPU gates pass; failed history is not rewritten.

## Why MiniLM was used first

`sentence-transformers/all-MiniLM-L6-v2` was a conservative first production-semantic probe because it is small, CPU-friendly, uses one 384-dimensional vector and cosine similarity, fits the existing SQLite/pgvector schema, and could be artifact-, tokenizer-, runtime-, and normalization-bound without introducing a second retrieval architecture. That made it useful for proving the evaluation membrane.

It was not selected because it was state of the art. Its 256-token window, English-centric training, symmetric encoding, and roughly 2019–2021-era architecture are material limitations for multilingual, long-context Oracle evidence.

## LightOn assessment

The LightOn collection published in July 2026 contains two relevant trained models and two unsupervised pretraining checkpoints.

### `lightonai/mDenseOn`

- 307M-parameter ModernBERT/mmBERT dense retriever;
- one normalized 768-dimensional vector per text;
- explicit `query: ` and `document: ` role prefixes;
- CLS pooling and cosine similarity;
- up to 8,192 tokens;
- Apache-2.0;
- author-reported BEIR 56.70, MIRACL target-language 59.61, MLDR target-language 64.98, and MTEB Code 71.53 nDCG@10.

It is architecturally compatible with Oracle's dense vector stores. The published scores are strong selection evidence, but they are author-reported broad benchmarks rather than DSPx Oracle proof. The model is about 1.23 GB and roughly 13.5 times the retained MiniLM weight artifact, so CPU load, memory, and latency must be observed locally.

### `lightonai/mLateOn`

- 307M-parameter late-interaction/ColBERT retriever;
- one 128-dimensional vector per token rather than one vector per record;
- `[Q]`/`[D]` roles and MaxSim scoring;
- PyLate/PLAID storage and retrieval semantics;
- Apache-2.0;
- stronger author-reported multilingual and long-document results than mDenseOn.

mLateOn is **not** a drop-in embedding replacement. Adopting it would require a separate multi-vector representation, MaxSim scorer, persistence/index contract, dependency review, and migration decision. It remains a future reranking or late-interaction backend candidate, not the current dense default.

The unsupervised checkpoints are training-stage artifacts and were not considered as runtime defaults.

## Selection

`lightonai/mDenseOn` is the selected **dense default** because it materially improves the capabilities MiniLM lacks while preserving the one-vector/cosine storage architecture. mLateOn is excluded from this bounded selection because it changes the retrieval architecture.

The frozen AK-4510 contract precommitted 15 model-blind queries over 10 Oracle concepts, including six cross-lingual queries and one label located after MiniLM's 256-token window. It required exact model/runtime/tokenizer/prompt identity, candidate-local SQLite, no semantic-analysis LM or shared-store call, no selective rerun, and one task-fixed attempt ledger.

## Preserved AK-4510 outcome

The one AK-4510 acquisition/comparative sequence is terminally preserved at:

`/home/tryinget/.local/state/pi-quests/tmp/dspx-oracle-embedding-selection-ak4510-20260802T061504Z-737025`

Observed facts:

- exact mDenseOn commit `a5fdb000f7a21da96c3bddde3a782ef777316df3` and all eight allowlisted artifacts were acquired;
- `model.safetensors` matched SHA-256 `a336c49f…45c`;
- the retained MiniLM baseline was re-executed into candidate-local SQLite;
- mDenseOn loaded under the exact frozen CPU runtime;
- its first document forward call failed before producing a vector because the tokenizer emitted `token_type_ids`, while `ModernBertModel.forward()` does not accept that keyword;
- the task-fixed ledger is consumed and forbids another AK-4510 root;
- no semantic-analysis LM, shared-store, publication, release, or activation effect occurred.

The failure remains adapter-compatibility history, not an observed semantic miss. It is not rewritten by the later recovery.

## AK-4517 forward recovery and default adoption

AK-4517 used a separate precommitted ledger and the exact retained AK-4510 snapshot entirely offline. The adapter removed only `token_type_ids`, then encoded every frozen document and query as complete ordered batches with explicit `document: ` and `query: ` roles. No artifact reacquisition, selective query rerun, DSPx retry, semantic-analysis LM call, shared-store connection, publication, release, or activation effect occurred.

The terminal recovery is retained at:

`/home/tryinget/.local/state/pi-quests/tmp/dspx-oracle-embedding-recovery-ak4517-20260802T064448Z-979337`

Observed bounded results:

- mDenseOn Recall@1, MRR, and nDCG@5 were each `1.0` over all 15 frozen labels;
- MiniLM Recall@1 was `0.8`, MRR was `0.842857…`, and nDCG@5 was `0.833333…`;
- cross-lingual Recall@1 improved by `0.333333…`, and the post-256-token long-context case improved by `1.0`;
- model load was `2.1398` seconds, total encode time was `4.3162` seconds, retained model bytes were `1,262,138,563`, and peak RSS was `1,907,945,472` bytes on the frozen CPU runtime;
- complete identity, absolute Oracle-specific quality, comparative capability, and bounded CPU resource gates all passed;
- independent verification re-ranked both SQLite databases, re-derived metrics and selection, reproduced the complete batches, checked resources and preserved lineage, and returned `accepted`;
- result SHA-256 is `b20249ef…03e20`; independent-verification SHA-256 is `3bd5db06…06548`.

DSPx therefore uses embedding version `2` for newly produced mDenseOn coordinates, encodes indexed records as documents and text searches as queries, and keeps explicit `sentence-transformers` selection as the legacy MiniLM path. Existing version-1 rows are not rewritten: an in-place cross-version upsert fails closed, so adoption requires a new/rebuilt version-2 index rather than silent historical replacement. Backend identity remains production-claim-false unless the exact runtime identity is separately bound.

## Claims that remain false

- statistically representative or broad production-semantic Oracle quality;
- independent semantic-analysis-LM quality;
- shared Postgres/pgvector readiness;
- mLateOn readiness;
- release authority, package publication, promotion, or activation.

## Sources

- <https://huggingface.co/collections/lightonai/mdenseon-and-mlateon>
- <https://huggingface.co/lightonai/mDenseOn>
- <https://huggingface.co/lightonai/mLateOn>
- <https://arxiv.org/abs/2607.27178>
- `benchmarks/semantic/oracle-embedding-selection-v2.json`
