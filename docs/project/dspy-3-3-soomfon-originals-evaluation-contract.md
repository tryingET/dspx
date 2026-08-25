---
summary: "AK-5038 provider-free Luna runtime-receipt repair; pending review and execution unauthorized."
read_when:
  - "Before considering any model-backed evaluation of the six fresh DSPy 3.3 voice originals."
  - "Before changing Soomfon evaluation custody, authorization, provider receipts, or routing."
type: "reference"
---

# DSPy 3.3 Soomfon originals evaluation contract

## Disposition

Task AK-5038 repairs generic runtime-receipt validation to consume the same centralized exact
`codex/gpt-5.6-luna` reasoning `xhigh` identity as the Soomfon owner path, without invoking a
provider, and issues a fresh schema-v3 contract for the same six regenerated DSPy 3.3.1
originals. Its posture is **pending independent review, execution unauthorized**.
No task 5038 artifact authorizes a provider/model call, OAuth
flow, credential inspection, physical key, microphone, TTS, routing, promotion, activation,
release, or publication.

The active machine contract is:

`examples/voice_turn_brains/canaries/dspy-3.3.0/soomfon-evaluation-contract.json`

Its current raw SHA-256 is
`56b2f269bd6b494a2d4d08c716787449cde5dd5a63bbbfc5d4666feb32306e3a`.
The digest must be supplied out-of-band; deriving the trust anchor from contract bytes is
forbidden.

## Predecessors and immutable history

The consumed Luna xhigh contract is archived byte-for-byte at:

`examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/cea459c1926e7cd765372e926a23fbcefab1cfa061024f720de76ba35d002e0d.json`

Its raw SHA-256 remains
`cea459c1926e7cd765372e926a23fbcefab1cfa061024f720de76ba35d002e0d`.
Execution task #5035 attempted only `simple`. Two attributable provider receipt chains completed;
only response SHA-256 `da0ef16db1293c5de87f8af9abc6940291eb894bcca68d688d2cb601b3bd954a`
and length `306` are retained publicly. The generic runtime validator still contained obsolete
Sol/max literals outside AK-5033 scope, so the immutable terminal disposition is
`effect_indeterminate` with reason `runtime_receipt_invalid`. The attempt cannot be retried,
resumed, relabeled, or transferred, and the raw response must not be read or exposed.

The earlier unused AK-5028 contract is archived byte-for-byte at:

`examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/0f602482f29037d1a8f0c71731872390614198998d1fda94079172052cc29207.json`

Its raw SHA-256 remains
`0f602482f29037d1a8f0c71731872390614198998d1fda94079172052cc29207`.
Task #5032 was deferred before claim, credential access, model transport, or any attempted mode
because the operator selected the Luna xhigh route. The archive remains execution unauthorized
and remains an immutable predecessor of the active contract.

The earlier consumed contract remains archived byte-for-byte at:

`examples/voice_turn_brains/canaries/dspy-3.3.0/predecessor-contracts/9d9d1b6ea87d3fd16e3db3e1fc97c5bbc68cc241bf67d52cf6c8b2593a1bf24b.json`

Its raw SHA-256 remains
`9d9d1b6ea87d3fd16e3db3e1fc97c5bbc68cc241bf67d52cf6c8b2593a1bf24b`.
Execution task #5027 consumed only `simple`. The dspy-lm-auth attempt completed exactly two
attributable receipt chains and retained only response SHA-256
`1ad1fd227ca1d37421d54f608ac1cc2fab5f041a53a009b117855bb548c833a3` and length
`431` as response evidence. The child returned successfully, but parent `_evaluate_case` passed
the reduced classifier projection to `verify_retained_soomfon_journals`, which requires the full
`soomfon-provider-outcome-evidence-v1` envelope. The immutable terminal disposition therefore
remains `effect_indeterminate` with reason `provider_receipt_journal_invalid`. Provider-free
re-verification establishes journal integrity only; it does not relabel, retry, score, or resume
the consumed attempt.

The five unattempted modes receive no execution-authority transfer. The predecessor namespace
may not be reused, retried, or relabeled. The existing archives
`a8afebcd131d59f1bf6794d7a4748906af3fc2a99c7230f7a1256d78bafe2b18` and
`07ba8c3559d1e527bd9fe5376a7accac2f48f617e5ba1288329a9cf4362e69eb` remain untouched; the
latter remains terminal `effect_indeterminate`.

## Frozen six-case matrix

The candidate order, case text, persona intent, posture, candidate IDs, manifest hashes, canary
index hashes, and research corpus hashes are byte-semantically unchanged from the a8af
predecessor.

| Mode | Fresh candidate | Manifest SHA-256 |
|---|---|---|
| `simple` | `prog-cand-1a93a1982bba` | `ed0fd9db0268aef35fa5cd7314800b26a66864afd384271785fb0a09b5b24cd4` |
| `elaborate` | `prog-cand-090c047d5096` | `7025d592f61b3afe70440ca3f3420736998cd286ed47761596f3e9458538f699` |
| `researched` | `prog-cand-cde70b970af6` | `69696b0d12cb0694b0a63ea3270bb7503df2a70f9112e51a5a152307f104aa5c` |
| `deep-research` | `prog-cand-770d06ac4737` | `8aebeda59ab883211c5318208f53086febc802e195170442cf6c0bc4c62fab5c` |
| `socratic` | `prog-cand-a167f3eb3996` | `ce43ee0674fd1adc1141f929d12cc897f8537bbd8be15475110e62d5d2810f95` |
| `bloom` | `prog-cand-3ddefc610463` | `77dc9cf7bf265f719160e4eea6547801255ad745b92b886a46b8cc0c672f39a0` |

The active `examples/voice_turn_brains/ai-control-brains.json` and all six AK-4971 candidate
artifacts must remain unchanged.

## Exact provider-owner candidate

The contract binds provider-owner task #4991 result:

- commit `7c51dda703f6a5d0a95aba13734294a82ea4314f`;
- tree `c303dd657146da90404618adead417e82e2dc2c0`;
- version `tryinget-dspy-lm-auth==0.1.6.dev0`;
- wheel SHA-256 `e1b8acaa354df4640422512a779b9486d5c4caceeb9c9ab05c4a07f1b1eb3512`;
- installed payload SHA-256 `8c8a2aa569df171fab35e25b02cb313ee20725901c7bec7ede0edc2364dccaf2`;
- lock SHA-256 `0b18a1759b2507967ed8f2f4918c436e2679e406aafb061620a11954b1550c7c`;
- exact owner module hashes and exact DSPy/LiteLLM/httpx/httpcore wheel, payload, count,
  version, and RECORD identities listed in the JSON contract.

The accepted v11 owner-source shape remains unchanged. The corrected exact identity uses the
independently observed LiteLLM 1.82.1 and httpx 0.28.1 installed `RECORD` hashes, additionally
verifies the #4991 `auth.py` hash, and does not weaken or relabel the owner boundary.

## Exact runtime and route

A later authorized runtime must match CPython 3.13.12, DSPx Core 0.2.1, DSPy/DSPy-AI 3.3.1,
GEPA 0.1.4, LiteLLM 1.82.1, httpx 0.28.1, and httpcore 1.0.9 with the contract-bound payloads.
The task-local provider configuration is exactly:

- requested route `dspy-lm-auth:codex:gpt-5.6-luna:xhigh`;
- resolved route `openai:gpt-5.6-luna:responses`;
- external owner `dspy_lm_auth.LM`, requested model `codex/gpt-5.6-luna`;
- `auth_provider="codex"` and `credential_mode="no-refresh"`;
- `reasoning_effort="xhigh"`, `num_retries=0`, `cache=False`, timeout 60 seconds;
- DSPy 3.3.1 defaults `temperature=None` and `max_tokens=None`, with no other LM kwargs;
- synchronous execution only, with no fallback, health probe, resume, or selective rerun;
- parent `sys.dont_write_bytecode is True`, child `-B` plus
  `PYTHONDONTWRITEBYTECODE=1`, and no `__pycache__`, `.pyc`, or existing loaded-module
  `__cached__` artifact anywhere under the security-critical DSPx or owner package roots.

This does not restore `dspy-lm-auth` in the generic provider registry. Generic environment
selection still fails. The path becomes selectable only after an exact
`SoomfonRuntimeCustody` for the current contract has validated; DSPx adds no second DSPy LM
subclass.

## Exactly two calls and maximum twelve effects

Every successful case performs **exactly two** ordered logical LM calls. The mode-specific JSON
adapter accepts `DefinePersona` first and the mode's answer/synthesis signature second. Local
research retrieval is not an LM call. Duplicate, out-of-order, third, asynchronous, fallback,
or widened-configuration calls reject before transport.

The six-case suite therefore has a **maximum twelve** logical LM calls and a maximum twelve
provider transports. Every call has zero configured retries. The suite stops on the first
non-success, and no resume or selective rerun is available.

## Provider receipt and ledger custody

The outer attempt marker remains contract-hash/mode keyed, no-replace, mode `0600`, under a
current-user mode-`0700` tree. File and containing-directory fsync complete before the candidate
effect boundary. A new contract uses a new namespace; predecessor namespaces stay immutable.

Each logical LM call receives one unique owner `ProviderOutcomeReceipt` through DSPx's existing
`ReceiptReservation`, `ReceiptJournal`, `verify_receipt_chain`, and `reduce_verified_chain`
primitives. Journals are private, no-replace, ordered by contract, mode, and call ordinal, and every
reservation rebinds the exact current pre-terminal marker SHA-256. The marker itself binds the
later task ID, local-projection hash, and canonical-AK reconciliation hash. The exact owner source, loaded receipt types, LM type, and dependency payloads are checked before
a call and revalidated before progression. Immediately before each of the two logical calls,
canonical AK authority must still be unchanged, claimed, and leased for at least 90 seconds—the
60-second provider timeout plus a 30-second margin. Failure occurs before receipt creation,
credential access, or transport, so an expiry/revocation between calls cannot permit call two.

Only exact attributable `provider_response_completed` receipt chains permit progression.
Missing, open, malformed, poisoned, inflight, rejected, or indeterminate chains are terminal.
Closed provider evidence contains only hashes, identities, and receipt projections—never prompt,
response, token, header, credential path/content, exception text, traceback, or raw diagnostic.

## Execution authorization preflight

A later execution task must supply all three out-of-band inputs:

1. the current contract digest;
2. a private, separately hashed DSPx-local `soomfon-execution-authorization-v3` projection;
3. the exact clean, no-bytecode provider-owner source root.

The JSON is an integrity/binding projection only. It is neither produced nor authenticated by
AK and cannot authorize itself. Before state-root creation the parent requires at least 1800
seconds on the claim lease; immediately before every marker it repeats that minimum and the
exact read-only canonical AK queries for the later task, live completion contract and guardrails,
attached evidence, each named evidence record, and done dependency #5038. The child reconciles
again before task-local provider import or any possible credential access. Each logical call
reconciles once more with a 90-second minimum and requires the task, contract, evidence,
projection, and authorization state to remain unchanged.

The two review records must carry distinct format-valid review dispatch references and exact
`ACCEPT` / `PASS` verdicts for the separately recorded security-review and provider-free-test
runs. The operator record must bind a distinct format-valid explicit one-suite request. All
three canonical records must be attached pass results for the exact task/repo and must bind the
current contract, executing DSPx source or payload, #4991 owner, `codex/gpt-5.6-luna`, reasoning
xhigh, and exact effect budget.

AK is canonical storage and attachment authority under workspace policy. Current AK evidence
uses fields such as `checked_by=cli`; this contract does **not** reinterpret them as
cryptographic distinct-principal authentication. Review dispatch references record separate
runs and verdicts, while the operator request records explicit one-suite authority. The trusted
effective OS user and canonical AK DB are the local threat boundary; compromise by that same UID
or mutation of canonical AK storage is outside this contract, consistently with private-state
owner custody.

The only accepted AK executable is
`/home/tryinget/.local/libexec/agent-kernel/c6297eccf67a3762ef01269f67e87eaa8828f127/ak-bin`,
SHA-256 `61f6290115262e0319c3b178f053d74a486a3eba881aaa13739c1db45f0f6b91`,
regular current-user-owned mode `0555`. It is opened with `O_NOFOLLOW`, hashed through that fd,
executed as `/proc/self/fd/<n>` with `pass_fds` and no shell, and re-fstatted afterward. Output
and time remain bounded. PATH, symlink, and parent lookup do not select AK.

The live completion kind remains exactly `soomfon_one_suite_execution_authorization`; required
check types are `review:independent-security`, `test:independent-provider-free`, and
`authorization:operator-one-suite`. Reviewed-source mode compares loaded origins and current
bytes to exact Git blobs at the authorized clean commit/tree. Installed mode compares origins
and complete payload to the exact distribution/RECORD. Any package shadow, `__pycache__`,
`.pyc`, or existing security-module `__cached__` artifact rejects. No AK mutation occurs.
Task #5038 cannot satisfy this execution authorization gate; a future execution task must have an ID greater than 5038 and depend exactly on `[5038]`.

## Private response behavior

Raw responses are confined to the protected private runtime tree used by the scorer/reviewer.
They are never printed to stdout or general logs and never enter provider evidence. The retained
#5027 raw response must not be read, deleted, or rewritten during this provider-free repair. Suite
and CLI output may expose only response SHA-256, length, closed receipt disposition, runtime
hashes, and non-authority fields.

## Nonclaims and next lawful move

This implementation proves no live model compatibility, answer quality, semantic equivalence,
GEPA improvement, backend locality, physical Soomfon execution, routing, promotion, activation,
release, or publication.

The next lawful move is independent review of this provider-free Luna runtime-receipt repair,
followed only then by a separate exact claimed AK task greater than 5038, depending exactly on
`[5038]`, with
canonical attached review/operator evidence and a local integrity projection for one suite.
Only independently reviewed resulting evidence could inform a later, distinct owner binding
decision. The active routing file must remain unchanged until that separate decision exists.
