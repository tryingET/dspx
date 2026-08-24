---
summary: "Design-only, no-routing contract for observing all six fresh DSPy 3.3 voice originals before any Soomfon binding decision."
read_when:
  - "Before running a loopback-client evaluation of the fresh DSPy 3.3 voice originals."
  - "Before changing the Soomfon/OpenDeck six-mode DSPx binding."
type: "proposal"
---

# DSPy 3.3 Soomfon originals evaluation contract

## Disposition

AK-4808 freezes a **design-only, execution-blocked contract** for one predeclared observed turn through each fresh DSPy 3.3 voice original. It does not call a model, press a Soomfon key, use microphone/TTS, change `ai-control-brains.json`, or authorize routing. Execution remains blocked until a separately scoped task implements and negatively tests the externally anchored hash-bound executor, crash-durable attempt ledger, exact environment gate, and provider-effect custody defined below.

The machine-readable contract is:

`examples/voice_turn_brains/canaries/dspy-3.3.0/soomfon-evaluation-contract.json`

## Why this gate exists

Read-only workstation reconciliation under AK-4727 established that the installed OpenDeck Autonomy profile and action chain are healthy, but all six live bindings still select historical optimized candidates whose optimizer evidence records DSPy 3.1.3. The workspace now runs DSPy/DSPy-AI 3.3.0 and GEPA 0.1.4, while the six fresh original canaries remain deliberately unrouted and quality-not-evaluated.

A physical press now would therefore test the historical optimized binding under the new runtime—not the fresh originals whose adoption is being considered. AK-4727 is deferred until DSPx produces a separate compatibility/routing disposition.

## Frozen candidate matrix

| Mode | Fresh candidate | Manifest SHA-256 |
|---|---|---|
| `simple` | `prog-cand-d4f50d25a3fa` | `aa0b473e7f0cd056246149eacfcb25c5ed023ab61a1b9410103443e68c30fac1` |
| `elaborate` | `prog-cand-324b55917e00` | `1304cc07864c241ab9b66e19589394e729640204996b317c0286c628d8e727cd` |
| `researched` | `prog-cand-f233bfe89cd1` | `bc3fbd7dc5d4993d93ee1af9737be7d12720d67a4df7793509e171e094cfe051` |
| `deep-research` | `prog-cand-3b0ba61de49a` | `03e4d23e6d0eede3cd474d5d84d8fc1091e3c52c3b5c318f4b9be686e71c09fa` |
| `socratic` | `prog-cand-3f26182ab33f` | `01b28caa003943e616ad07815870f1abb0f200d0990e52f487271c79ed855fac` |
| `bloom` | `prog-cand-1a4f0633acc8` | `087994808d60ee46b7283c4d8f0b7c269323c016c392d1e9bdee075abe8a53ba` |

The contract also binds every canary index and verifies that the selected candidates are fresh DSPy 3.3 originals, contain no whole-program pickle surface, differ from the active historical bindings, and retain `quality_approved=false` plus `semantic_equivalence=not_evaluated`.

## Required executor before any run

The current LACP `DspxBrain` validates a family of loopback endpoints rather than this contract's exact endpoint, and it discards the DSPx runtime ID without returning the provider-effect disposition. No durable contract-hash/case-keyed attempt ledger exists. Therefore this design is not executable as written.

A separately scoped implementation must add a hash-bound executor that fails before provider construction unless all of these conditions hold:

- the raw contract bytes match an expected SHA-256 supplied out-of-band by the exact AK execution task and its independent-review evidence; deriving the expected digest from the contract itself is forbidden;
- all six manifest/canary-index hashes match;
- CPython is exactly 3.13.12 and installed DSPx Core 0.1.0, DSPy/DSPy-AI 3.3.0, and GEPA 0.1.4 identities match;
- a sanitized child environment contains exactly the declared provider settings, including `DSPX_OPENAI_COMPAT_API_BASE=http://127.0.0.1:1234/v1`, model `baseline-text`, timeout `30`, and the network policy opt-in;
- the endpoint is neither missing nor spelled as `localhost`/`::1`, and no alternate port/path/model/timeout or `DSPX_OPENAI_COMPAT_API_KEY` is present;
- no microphone, TTS, physical key, GEPA optimization, routing, or candidate mutation is enabled;
- the executor can verify a receipt-bound provider-effect disposition instead of losing it at the LACP abstraction.

The exact loopback URL proves only the client hop. It does not prove which process owns the listener, which model artifact executes, whether the listener proxies elsewhere, or backend no-egress. This contract therefore makes no local-model or backend-locality claim. A future owner may add separately hash-bound service/configuration/model/no-egress evidence; absent that evidence, backend locality remains `not_verified`.

The execution path requires negative tests for every mismatch plus contract/hash drift, unknown/missing fields, crashes, timeouts, duplicate attempts, and missing effect disposition. Passing design-regression tests in AK-4808 does not satisfy those executor tests.

## Attempt and effect custody

Before each candidate effect, the future executor must validate a current-user-owned mode-`0700` non-symlink ledger directory, acquire an exclusive no-follow lock, and create a mode-`0600` per-key marker with `O_CREAT|O_EXCL|O_NOFOLLOW`. The marker is keyed by the externally anchored contract SHA-256 and mode. The executor writes the complete bounded `attempted_outcome_unknown` record, fsyncs the file, then fsyncs the containing directory before provider construction. Any existing key or concurrent duplicate refuses execution.

Exactly one candidate invocation may occur per case in fixed order. There is no health probe, DSPx-managed retry, selective rerun, fallback, or resume. Six candidate invocations do not bound DSPy/provider transport-call cardinality. A terminal transition is one exclusive `O_APPEND` bounded record write followed by file and containing-directory fsync. A crash before durable pre-effect directory fsync refuses execution on reconciliation; a crash during or after possible effect, timeout, missing receipt/effect disposition, malformed transition, or other unresolved outcome terminalizes the case as `effect_indeterminate` and stops the suite. A new attempt requires a new contract and exact AK task, not reuse of the consumed key.

## Input and response retention

The exact non-sensitive text inputs and persona intents are committed in the JSON contract. They are predeclared text—not captured microphone transcripts. Captured microphone transcripts remain excluded.

Raw observed responses must never enter Git, general logs, or stdout. The future executor must capture them under a private mode-`0700` temporary directory with mode-`0600` files, accessible only to the scorer and independent reviewer. It records the response digest before deletion and deletes raw responses only after scoring and independent review. Crash state is quarantined for owner reconciliation rather than automatically cleaned or rerun. After deletion, the human score is explicitly not reproducible from retained raw text and therefore remains a bounded observation rather than authoritative quality evidence.

## Bounded review semantics

The JSON contract defines exact 0/1/2 anchors for relevance, mode adherence, clarity, capability truthfulness, and—for research modes—evidence grounding. Every scored dimension requires a rationale; missing or unknown scores fail. Any unsupported capability claim or fabricated/missing required research citation is a mandatory failure. Meeting the frozen arithmetic threshold means only `bounded_observed_turn_acceptable` for that exact input and environment.

It does not establish:

- general answer quality;
- semantic equivalence to the historical candidates;
- GEPA improvement or DSPy-version causality;
- cross-device or future-model behavior;
- routing, promotion, activation, release, or publication authority.

## Deep-research label truth

The fresh `deep-research` original is a bounded retrieve-then-answer program over an inline local corpus. It is not iterative ReActV2 research and does not use external retrieval. The proposed observed turn must retain that label explicitly.

Decision 115 remains the separate architecture gate for one fixed hash-bound declared-corpus ReActV2 tool. Neither this contract nor a passing observed turn resolves that decision.

## Next lawful move

First create a separate exact implementation task for the executor, negative matrix, no-replace attempt ledger, and provider-effect custody gap. Independent review must accept that implementation before a different exact task may consume this frozen six-case contract through the exact loopback client hop; backend locality remains unverified. Preserve results and failures without rerun. Only after independent review of the resulting evidence may an owner consider a distinct binding decision; the active `examples/voice_turn_brains/ai-control-brains.json` must remain unchanged until then.
