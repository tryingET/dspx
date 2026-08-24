---
summary: "Implementation-reviewed, execution-unauthorized contract for observing six fresh DSPy 3.3 voice originals before any Soomfon binding decision."
read_when:
  - "Before running a loopback-client evaluation of the fresh DSPy 3.3 voice originals."
  - "Before changing the Soomfon/OpenDeck six-mode DSPx binding."
type: "reference"
---

# DSPy 3.3 Soomfon originals evaluation contract

## Disposition

AK-4808 froze the original six-case design; AK-4809 implemented the externally hash-bound executor, crash-durable attempt ledger, exact environment gate, and provider-effect custody; provider-free readiness task #4965 independently reconciled that implementation against the complete negative matrix. Task #4969 consumed only the predecessor `simple` key and retained terminal `effect_indeterminate`; task #4970 proved the generated source failed the protected snapshot policy before provider dispatch. Task #4971 preserved that predecessor, repaired generation without weakening policy, and regenerated all six originals under DSPy 3.3.1. The successor posture is **implementation reviewed, execution unauthorized**. The contract does not call a model, press a Soomfon key, use microphone/TTS, change `ai-control-brains.json`, or authorize routing. A separate exact AK execution task must carry the independently reviewed current raw digest, exact reviewed source commit or installed payload, and explicit operator authority before any effect.

The machine-readable contract is:

`examples/voice_turn_brains/canaries/dspy-3.3.0/soomfon-evaluation-contract.json`

## Why this gate exists

Read-only workstation reconciliation under AK-4727 established that the installed OpenDeck Autonomy profile and action chain are healthy, but all six live bindings still select historical optimized candidates whose optimizer evidence records DSPy 3.1.3. The workspace now runs DSPy/DSPy-AI 3.3.1, DSPx Core 0.2.1, and GEPA 0.1.4, while the six fresh original canaries remain deliberately unrouted and quality-not-evaluated.

A physical press now would therefore test the historical optimized binding under the new runtime—not the fresh originals whose adoption is being considered. AK-4727 is deferred until DSPx produces a separate compatibility/routing disposition.

## Frozen candidate matrix

| Mode | Fresh candidate | Manifest SHA-256 |
|---|---|---|
| `simple` | `prog-cand-1a93a1982bba` | `ed0fd9db0268aef35fa5cd7314800b26a66864afd384271785fb0a09b5b24cd4` |
| `elaborate` | `prog-cand-090c047d5096` | `7025d592f61b3afe70440ca3f3420736998cd286ed47761596f3e9458538f699` |
| `researched` | `prog-cand-cde70b970af6` | `69696b0d12cb0694b0a63ea3270bb7503df2a70f9112e51a5a152307f104aa5c` |
| `deep-research` | `prog-cand-770d06ac4737` | `8aebeda59ab883211c5318208f53086febc802e195170442cf6c0bc4c62fab5c` |
| `socratic` | `prog-cand-a167f3eb3996` | `ce43ee0674fd1adc1141f929d12cc897f8537bbd8be15475110e62d5d2810f95` |
| `bloom` | `prog-cand-3ddefc610463` | `77dc9cf7bf265f719160e4eea6547801255ad745b92b886a46b8cc0c672f39a0` |

The contract also binds every canary index and verifies that the selected candidates are fresh DSPy 3.3 originals, contain no whole-program pickle surface, differ from the active historical bindings, and retain `quality_approved=false` plus `semantic_equivalence=not_evaluated`.

The predecessor raw contract is preserved byte-for-byte at `examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/07ba8c3559d1e527bd9fe5376a7accac2f48f617e5ba1288329a9cf4362e69eb.json`. Its `simple` disposition remains `effect_indeterminate`; it is not retried or relabeled. The five unattempted predecessor modes do not transfer authority to this successor.

## Reviewed executor and remaining authorization gate

The repository now contains the reviewed hash-bound executor and its provider-free negative matrix. It bypasses the historical LACP `DspxBrain` gap by enforcing the exact endpoint/runtime contract, retaining provider-effect disposition, and using a durable contract-hash/case-keyed attempt ledger. Implementation readiness is not execution authority.

The reviewed executor fails before provider construction unless all of these conditions hold:

- the raw contract bytes match an expected SHA-256 supplied out-of-band by the exact AK execution task and its independent-review evidence; deriving the expected digest from the contract itself is forbidden;
- all six manifest/canary-index hashes match;
- CPython is exactly 3.13.12 and installed DSPx Core 0.2.1, DSPy/DSPy-AI 3.3.1, and GEPA 0.1.4 identities match;
- a sanitized child environment contains exactly the declared provider settings, including `DSPX_OPENAI_COMPAT_API_BASE=http://127.0.0.1:1234/v1`, model `baseline-text`, timeout `30`, and the network policy opt-in;
- the endpoint is neither missing nor spelled as `localhost`/`::1`, and no alternate port/path/model/timeout or `DSPX_OPENAI_COMPAT_API_KEY` is present;
- no microphone, TTS, physical key, GEPA optimization, routing, or candidate mutation is enabled;
- the executor can verify a receipt-bound provider-effect disposition instead of losing it at the LACP abstraction.

The exact loopback URL proves only the client hop. It does not prove which process owns the listener, which model artifact executes, whether the listener proxies elsewhere, or backend no-egress. This contract therefore makes no local-model or backend-locality claim. A future owner may add separately hash-bound service/configuration/model/no-egress evidence; absent that evidence, backend locality remains `not_verified`.

The provider-free execution-readiness review covers every declared mismatch plus contract/hash drift, unknown/missing fields, wrong ledger ownership/mode, containing-directory fsync failure, crashes, timeouts, duplicate attempts, and missing effect disposition. These tests prove implementation behavior only; they do not authorize or simulate a live six-case run.

## Attempt and effect custody

Before each candidate effect, the reviewed executor validates a current-user-owned mode-`0700` non-symlink ledger directory, acquires an exclusive no-follow lock, and creates a no-replace mode-`0600` per-key marker with `O_CREAT|O_EXCL|O_NOFOLLOW`. The marker is keyed by the externally anchored contract SHA-256 and mode. The executor writes the complete bounded `attempted_outcome_unknown` record, fsyncs the file, then fsyncs the containing directory before provider construction. Any existing key or concurrent duplicate refuses execution.

Exactly one candidate invocation may occur per case in fixed order. There is no health probe, DSPx-managed retry, selective rerun, fallback, or resume. Six candidate invocations do not bound DSPy/provider transport-call cardinality. A terminal transition is one exclusive `O_APPEND` bounded record write followed by file and containing-directory fsync. A crash before durable pre-effect directory fsync refuses execution on reconciliation; a crash during or after possible effect, timeout, missing receipt/effect disposition, malformed transition, or other unresolved outcome terminalizes the case as `effect_indeterminate` and stops the suite. A new attempt requires a new contract and exact AK task, not reuse of the consumed key.

## Input and response retention

The exact non-sensitive text inputs and persona intents are committed in the JSON contract. They are predeclared text—not captured microphone transcripts. Captured microphone transcripts remain excluded.

Raw observed responses must never enter Git, general logs, or stdout. The reviewed executor captures them under a private mode-`0700` temporary directory with mode-`0600` files, accessible only to the scorer and independent reviewer. It records the response digest before deletion and deletes raw responses only after scoring and independent review. Crash state is quarantined for owner reconciliation rather than automatically cleaned or rerun. After deletion, the human score is explicitly not reproducible from retained raw text and therefore remains a bounded observation rather than authoritative quality evidence.

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

Create a separate exact execution task carrying raw successor contract SHA-256 `a8afebcd131d59f1bf6794d7a4748906af3fc2a99c7230f7a1256d78bafe2b18`, the provider-free readiness and #4971 review evidence, the exact reviewed source commit or installed payload, the exact runtime/environment membrane, and explicit operator authorization for one loopback-client six-case attempt. Backend locality and no-egress remain unverified. Preserve results and failures without rerun. Only after independent review of the resulting evidence may an owner consider a distinct binding decision; the active `examples/voice_turn_brains/ai-control-brains.json` must remain unchanged until then.
