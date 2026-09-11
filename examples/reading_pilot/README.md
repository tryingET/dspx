---
summary: "Provider-free reading-pilot implementation and synthetic native-runtime proof boundaries."
read_when:
  - "Reviewing the separate passage A/B empirical pilot, before any execution admission."
---

# Reading pilot (AK5681)

This is a separate **reading-pilot**, not AK5456's synthetic receipt or AK5457's
inspection consumer. It does not prove the eight-family Obsidian consumer,
whole-book reading, semantic quality, canonical acceptance, or real model use.
The original broader AK5458 acceptance remains deferred. A timed-out budget
interview is **not live consent**. This implementation grants no live permission.

## Supported boundary

Exactly one immutable A→B batch, at most two HTTP dispatches, one generated DSPy
`Predict` per case. No automatic three-batch/six-call lifecycle is implemented.
After any start, the API refuses restart/reuse, including failed and interrupted
campaigns. Owner reconciliation must retain that history; do not delete markers,
copy a campaign, or create a fresh campaign to reset a consumed allowance.
Semantic-failed revision batches require new explicit owner supervision, a frozen
rubric, the previous result, a reviewed revised candidate and a fresh budget.
They are not an operation supported or admitted by this API.

## Public interfaces

- `reading_pilot_verification.PilotContract`: closed explicit source review,
  reviewed byte locators, distinct A/B purposes, source hash, public schema/rubric
  hash, template hash, runtime fingerprint, loopback route, reviewed server-side
  bound, operator/runtime/budget review references, and the exact two-call budget.
- `reading_pilot.prepare_pilot(parent=..., contract_payload=..., source=bytes,
  template_bytes=..., expected_contract_sha256=...)`: provider-free native
  `materialize_program_from_intent`, under isolated stub configuration. It returns
  a content-free `PilotStatus` with the candidate inventory hash for independent
  review, not permission to execute. The parent must already be an explicitly
  selected owner-private 0700 directory outside any checkout. It creates only a
  fresh `pilot-*` child. Supplied source bytes are never opened through model paths.
- `reading_pilot.run_pilot(parent=..., campaign_id=...,
  expected_contract_sha256=..., expected_candidate_sha256=...,
  candidate_review_ref=..., operator_admission_ref=...)`: native
  `run_program_runtime_episode` through the generic loopback HTTP typed provider,
  then native validated readback. Independent expected hashes/references must come
  from caller custody, not the submitted bundle. They are **not cryptographic
  identities, proof of consent, or a new governance engine**.
- `reading_pilot_verification.verify_pilot(..., expected_result_sha256=...)`:
  provider-free completed-batch readback using independently retained hashes.
  Its content-free status separates formatting/reference checks from
  `semantic_review=needed`. Failure verification retains the local terminal
  packet; the completed-batch verifier never promotes it to completion.

The exact output JSON Schema and rubric are defined independently in
`reading_pilot_verification.public_spec()`. Their canonical bytes/hash are frozen
in the contract and saved as `public.json`. The complete schema/rubric is appended
to the provider-facing output descriptor before generation. Source/candidate/
input/output/episode/receipt metadata is computed by code, never by the model.

L1 paraphrases; L2 explicates with generated example/analogy; L3 reconstructs the
source argument; L4 applies nine intellectual standards; L5 explicitly simulates
the author's perspective with evidence and uncertainty. **Added L6**, not attributed
to Paul/Elder, proposes use, limits, counterexample and an observable test.
All claims require exact reviewed-locator quotations. Quote containment proves
reference integrity only: a quote can be genuine while the interpretation is bad.
If the source cannot support a required claim, record failure/insufficiency in the
human review rather than invent support or claim a completed reading level.

## Local custody and limits

Layout: `<private-parent>/pilot-*/{source/,candidate/,A/,B/,home/,tmp/,cache/}`,
plus frozen contract/public/template/purposes, candidate inventory, exclusive start,
per-case intent/worker-claim/terminal records, private child logs and `result.json`.
All directories/files are 0700/0600. Byte-identical source is passed to both cases.
Model output is inert data. No Oracle indexing, semantic calls, MLflow, tools,
retrieval, repairs, retries, cache reuse, JSON-adapter fallback, or remote fallback.
There is no deletion, repair, resume, service startup, or canonical-write API.

The route must already be canonical IP-literal loopback HTTP with an explicit
port. Padded ports, scoped/expanded IPv6, credentials, query/fragment delimiters
(including empty ones), trailing-port/path variants and noncanonical spellings
reject before preparation or dispatch. That is **not OS network isolation**
and does not prove the server lacks remote forwarding. A separately reviewed
local-only deployment and server-side output bound are required. The typed LM
rejects `max_tokens` and similar generation kwargs: none are passed. The declared
server bound is checked for presence/binding, not remotely enforced or attested.
Post-response byte checks and a worker deadline do not prove a generation cap.
The runtime fingerprint covers selected code/interpreter bytes (including the
custody helper's actual bytes) and DSPy version,
not a complete installed dependency closure, secure import sandbox, or hostile
same-UID actor. Cooperative private custody is assumed; no atomic protection
against a hostile process rewriting files is claimed.

HTTP uncertainty or worker interruption permanently latches the campaign. A
reserved allowance is not proof of an actual dispatch. Each returned native runtime
produces an exclusive `A.provider.json` / `B.provider.json` with schema
`reading-pilot-provider-observation-v1`, binding the worker's native provider return
to the pre-dispatch contract/candidate/input identities. Before exiting, the worker
sends exactly 65 bytes (lowercase SHA-256 plus newline) through a dedicated inherited
pipe: the digest of the exact observation serialized from its in-memory native
return. The descriptor is an explicit private launcher argument, never selected by
environment; stdout/stderr remain private logs. Generation has no observation pipe.
The parent retains the digest in memory, requires exact framing and EOF plus a
successful worker exit, and checks private observation bytes against it **before**
asserting any effect/count. The pipe is drained concurrently with execution with a
66-byte ceiling and a deadline; oversized payloads cannot deadlock the worker.
Errors/deadlines kill the owned process group and reap the worker. This is
cooperative local process custody, not independent server authentication, hostile
same-UID protection, or an importable bundle's self-certification. Preexisting
observations are rejected. No additional editable hash file is a trust anchor.

A later **unrelated** output/episode integrity failure reports
`state=failed_integrity` and `integrity=failed`, retains the observed
`provider_effect` and dispatch count, and stops B. Missing/malformed/truncated IPC,
worker error, or observation bytes disagreeing with the independently held pipe
digest cannot support known facts. The digest is checked again during readback and
before terminalization; this also rejects coordinated observation+behavior-provider
forgeries. Such failures produce `effect_indeterminate`, unknown count, null
`provider_effect` and failed integrity; B remains stopped. Native bundle readback
still checks its provider projection against the authenticated observation, but a
broken editable native projection cannot replace the worker's facts or yield global
completion. No contradictory artifact is rewritten to make it agree. Later
`verify_pilot` readback uses the observation digest bound into the independently
retained expected result hash, never an artifact's own declared hash as proof.
A completed provider failure likewise stays `completed_failure`, not
`effect_indeterminate`. Even an observed indeterminate HTTP effect can have a known
one-dispatch count; only missing/untrustworthy observations leave that count unknown.
A worker killed before returning an observation still has an unknown count. Native
artifacts and provider observations are never rewritten by these reductions. A
failure to persist the aggregate retains known facts in the source-free return but
provides no result hash. Completed historical campaigns are not repaired or rerun
by this change. Fully observed provider failure, malformed JSON or bad references
also stops before B. These statuses are not semantic or empirical acceptance.

## Independent local review and empirical acceptance

A human reviewer separately retains source/public-rubric/candidate/output/result
hashes and reviews the real source alongside blinded A/B outputs; reveal the
purpose mapping afterwards. Score each L1–L6, source qualifiers, author/reader
separation, contrary evidence, source fidelity and substantive A/B changes.
Hash-bound output shape, input differences and synthetic server responses cannot
supply these judgments. Human review remains outside the model output schema and
outside the execution API; retain it in a separately controlled local review
location, for example
`<reviewer-private-root>/<campaign-id>/human-review.json`, binding the externally
held source, public rubric, candidate, both outputs and result hashes plus the
reviewer's per-level judgments and A/B assessment. No semantic pass or human
review packet is manufactured here.

Real empirical acceptance additionally requires independently collected server-side
request metadata matched to each episode: actual cardinality, requested/observed
model and deployment identity. Native attempt evidence alone is not provider
output authentication or model-weight proof. Synthetic tests compare a real local
HTTP server's independent request counter with native receipts, but establish only
fixture-backed behavior. Source text, prompts, outputs, errors and human review
must never enter remote assistant/tool output; export only independently checked
content-free statuses/hashes. There is no blanket `safe=true` flag.

## Focused validation

Only the two new test files belong to this slice. Run them using offline `uv run
--no-sync` inside bwrap with unshared network, a read-only host tree, fresh HOME/
caches and private writable scratch. The test HTTP server lives inside that
network namespace and uses exclusively invented text. Set
`READING_PILOT_ISOLATED_TESTS=1` only inside that namespace; absent that explicit
harness admission, these socket-backed tests skip rather than use host networking.
The environment flag is a harness selector, not proof of OS isolation; retain the
actual bwrap command and results. No host provider, real book, Obsidian read,
install, full suite or AK5511 validation is part of this proof.
