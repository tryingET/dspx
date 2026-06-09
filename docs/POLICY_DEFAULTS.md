---
summary: "Default policy posture matrix for capabilities and mutating operations."
read_when:
  - "You are changing policy gates, confirmations, or safety defaults."
  - "You need to know which env vars/flags are required for risky operations."
---

Policy Defaults Matrix
======================

Scope: default CLI/server posture for high-risk capabilities and Forge mutations.

| Capability / operation | Default posture | Required env / flags to proceed | Audit / log expectation |
| --- | --- | --- | --- |
| `network.read` | Allow (bounded) | Host allowlist for URL-based tools (`--allow-host` / configured allowed hosts). Optional capability narrowing via `DSPX_POLICY_ALLOWED_CAPS`. | Redacted request target in previews/logs; operation visible in tool output and tracing when enabled. |
| `network.mutate` | Confirm for CLI; fail-closed for direct OpenAPI calls | Interactive confirmation by default; non-interactive CLI override via `--yes`. Direct/programmatic OpenAPI mutation requires `DSPX_POLICY_ALLOW_NETWORK_MUTATE=1` or explicit policy bypass. To pre-authorize mutation class: `--allow-network-mutate` or `DSPX_POLICY_ALLOW_NETWORK_MUTATE=1`. | Redacted mutation preview (method + URL) before execution; mutation intent captured in CLI output/traces. |
| `code.exec` | Confirm | Interactive confirmation by default; `--yes` for non-interactive flows. Capability allow/deny via `DSPX_POLICY_ALLOWED_CAPS` / `DSPX_POLICY_DISALLOWED_CAPS` (or bypass via `DSPX_POLICY_BYPASS=1`, unsafe). | Tool name + capability path visible; failures/successes recorded in command output and optional traces. |
| `filesystem.read` | Allow, confined | Built-in read tools are confined to `DSPX_FILESYSTEM_ROOT` when set, otherwise the current working directory. Capability allow/deny via `DSPX_POLICY_ALLOWED_CAPS` / `DSPX_POLICY_DISALLOWED_CAPS`. | Returned paths reflect confined resolved targets; symlink escapes are skipped or rejected. |
| `filesystem.write` | Confirm | Interactive confirmation by default; `--yes` for non-interactive flows. Capability allow/deny via `DSPX_POLICY_ALLOWED_CAPS` / `DSPX_POLICY_DISALLOWED_CAPS`. | Mutating tool invocation recorded; prefer dry-run previews where available. |
| `forge issues apply` | Deny by default (dry-run) | `--apply` **and** `--allow-network-mutate` (or `DSPX_POLICY_ALLOW_NETWORK_MUTATE=1`), plus GitLab env config (`DSPX_GITLAB_TOKEN`, project map/base URL/allowlists). | Always emits manifest + per-issue result JSON; redact tokens/secret material in logs. |
| `forge issues close-duplicates` | Deny by default (dry-run + separate close gate) | `--apply` **and** `--allow-network-mutate` (or `DSPX_POLICY_ALLOW_NETWORK_MUTATE=1`) **and** `--allow-issue-close`. | Emits close-duplicates manifest/results; closure actions auditable from generated output artifacts. |

Notes
-----
- Global unsafe bypass: `DSPX_POLICY_BYPASS=1` disables checks; use only in controlled environments.
- Capability allowlists are strongest when combined with host/project allowlists.
- For Forge operations, keep dry-run as the default in automation unless a promotion step explicitly flips `--apply`.
