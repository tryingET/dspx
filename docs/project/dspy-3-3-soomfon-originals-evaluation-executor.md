---
summary: "Hash-bound, crash-durable executor for the frozen six-case DSPy 3.3 Soomfon originals evaluation contract."
read_when:
  - "Before implementing, reviewing, or invoking the Soomfon originals executor."
  - "When reconciling a consumed or indeterminate Soomfon evaluation attempt."
type: "reference"
---

# Soomfon DSPy 3.3 originals evaluation executor

## Status

AK-4809 implements the execution membrane required by the frozen AK-4808 design. It does not execute the six cases. A separate exact AK task must carry the independently reviewed contract digest and authorize one loopback-client attempt.

Frozen contract:

`examples/voice_turn_brains/canaries/dspy-3.3.0/soomfon-evaluation-contract.json`

Reviewed out-of-band SHA-256:

`b720939ac2b299dab51ededabde9659166647a9e0e2e4d33c37cfd04a17bb625`

The executor does not derive or default this digest. The operator must supply it explicitly:

```bash
DSPX_PROVIDER=openai-compatible \
DSPX_OPENAI_COMPAT_MODEL=baseline-text \
DSPX_OPENAI_COMPAT_API_BASE=http://127.0.0.1:1234/v1 \
DSPX_OPENAI_COMPAT_TIMEOUT=30 \
DSPX_POLICY_ALLOW_NETWORK_MUTATE=1 \
just dspx soomfon evaluate-originals \
  --expected-contract-sha256 b720939ac2b299dab51ededabde9659166647a9e0e2e4d33c37cfd04a17bb625
```

Do not run that command without the separate exact execution task. The URL proves only the client hop; backend process, model artifact, no-egress, and locality remain unverified.

## Pre-effect membrane

Before creating an attempt marker or provider:

1. read bounded raw contract bytes with no-follow semantics;
2. require the reviewed out-of-band SHA-256 above and compare it to the raw bytes before JSON parsing;
3. validate both an exact canonical-content fingerprint and the closed contract schema/fixed six-case order;
4. verify exact CPython 3.13.12 and installed DSPx/DSPy/GEPA distribution versions;
5. require the exact provider, model, endpoint, timeout, and network-policy environment;
6. reject the credential environment variable;
7. build an allowlisted child environment rather than forwarding ambient provider state;
8. recursively reject unknown nested contract fields and stable-read/hash-bind every fresh manifest, receipt, and canary index.

The exact candidate surfaces are copied from their hash-bound inventory into a private staged tree before provider construction. In the child, manifest, receipt, input, and declared surface bytes are stable-read and hash-checked again before the one-shot child claim. Generated Python modules then load only from that captured in-memory source snapshot, so runtime execution does not reopen mutable candidate/input paths. The child uses isolated Python `-I -P` from a private empty working directory. `program-run` centrally refuses all six protected manifest hashes without an inherited executor custody context, and custody cannot authorize an unprotected hash.

The CLI exposes no contract path, mode selector, endpoint/model/timeout override, state root, retry, resume, fallback, or raw-response option.

## Attempt custody

State lives below the effective user's fixed private DSPx state root:

`~/.local/state/dspx/soomfon-evaluation/<contract-sha256>/`

Each case uses a contract-digest/mode-keyed no-replace JSONL marker. The executor:

- walks every state path component with dirfd-relative no-follow operations, validates ownership/mode, and fsyncs each containing directory when creating a child;
- acquires a nonblocking exclusive suite lock;
- creates each mode-`0600` marker with `O_CREAT|O_EXCL|O_APPEND|O_NOFOLLOW`;
- writes `attempted_outcome_unknown`, fsyncs the file, then fsyncs the containing directory before provider construction;
- appends one bounded terminal record, then repeats file and directory fsync;
- binds inherited marker, ledger, lock, and raw-root FDs to the fixed effective-user state path, then revalidates exact input, manifest, receipt, runtime, and provider identities in the child;
- refuses an existing key or concurrent suite;
- reconciles a lone, malformed, identity-corrupt, partial, or durability-unconfirmed terminal marker to a separate durable `effect_indeterminate` sidecar without rerun; only a strictly keyed, state-evidence-complete terminal marker with no observed persistence failure remains unchanged;
- never removes a consumed marker.

A crash after marker durability, timeout, dispatched failure, malformed/truncated/missing provider evidence, receipt failure, or terminal persistence failure remains `effect_indeterminate`. Only an explicit `preflight_rejected` sequence with zero dispatch can become `failed_no_effect_proved`. `completed_failure` after dispatch remains conservatively indeterminate.

## Runtime and response custody

Each case runs in a fresh process group under umask `077`. The child arms a Linux parent-death `SIGKILL` before custody and provider construction. `SIGINT` is masked across spawn until the child handle is under cleanup custody; timeout or any supervision interruption then kills the process group and waits for the child leader. A normal leader exit is rejected if the process group still exists. Generated-source policy admits only declared local functions/classes, closed safe builtins, reviewed module attributes, and reviewed sibling exports; it rejects callable rebinding, dynamic dispatch/introspection, process control, provider replacement, network helpers, and filesystem access. The verified working directory must also be empty. The executor still does not claim containment of an independently escaped external process outside this policy. The child calls `run_program_runtime_episode()` with Oracle, replay-fixture capture, publication, and semantic analysis disabled. Parent stdout and stderr are suppressed.

The child creates and retains the `runtime/` directory by descriptor with no-replace dirfd operations only after validating the inherited raw-root FD and an exact pre-effect directory inventory. Runtime inputs, observed response files, evidence JSON, and the runtime receipt publish with exclusive descriptor-relative no-follow writes. Final recursive custody rejects symlinks, non-private modes/owners, special files, and multi-link regular files. The parent captures a canonical complete-tree digest before semantic validation, requires the descriptor-walked post-validation digest to match, and persists that digest with the validated runtime-episode, runtime-receipt, and behavior hashes.

The parent validates the complete runtime episode through `load_validated_program_runtime_episode_bundle()`, including receipt-bound provider evidence. Success requires:

- exact endpoint/model/effective-timeout metadata;
- complete, untruncated `dspx-provider-effect-evidence-v1`;
- runtime `execution_status: executed` rather than degraded/failed output;
- candidate `io_spec()` inputs/outputs exactly equal the hash-bound manifest declaration before invocation;
- exactly one dispatched `completed_success` attempt;
- a non-empty response;
- a valid current runtime receipt plus the complete manifest/input/behavior/trace/Oracle/declared-output inventory;
- an unchanged canonical private-tree digest with mode/ownership/symlink closure.

Before durable success, the executor recursively fsyncs every retained raw file and directory. Any catchable post-marker failure is converted to a terminal indeterminate append; a failed terminal append leaves the initial unknown marker for reconciliation.

The command output and suite result contain only bounded identities, dispositions, hashes, lengths, latency, and private evidence paths. They never contain transcription, persona intent, or response text. Raw responses remain private pending scoring and independent review; deletion is a later explicit custody step.

## Nonclaims

Executor implementation does not prove:

- that any case ran;
- live-provider or model compatibility;
- backend locality or no-egress;
- answer quality or semantic equivalence;
- GEPA improvement;
- physical Soomfon behavior;
- routing, promotion, activation, release, or publication.
