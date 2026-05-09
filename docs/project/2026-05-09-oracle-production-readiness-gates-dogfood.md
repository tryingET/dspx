---
summary: "Dogfood evidence for Oracle backend, backup, and authority gates after shared publication hardening."
read_when:
  - "You need the latest dogfood evidence for DS1621 Oracle publication readiness gates."
  - "You are checking why shared Oracle evidence does not imply generated-program production activation."
---

# 2026-05-09 — Oracle publication readiness gates dogfood

AK task: `AK-2633 Dogfood generated-program authority gate after Oracle backend and backup evidence`.

## Scope

This note records dogfood evidence for the three rollout gates requested by the operator:

1. backend gate;
2. backup/off-NAS gate;
3. authority/activation gate.

It does **not** claim that any generated program was activated in production. Shared Oracle remains empirical memory only.

## Gate 1 — backend

DS1621 infra health passed:

```text
ok: ds1621 oracle contract
ok: ds1621 oracle health
```

DSPx live publication dogfood against the DS1621 shared Oracle backend passed with explicit opt-in and secret custody refs:

```text
dogfood_status=ok
publication_status=published
publication_id=prog-oracle-pub-970db6acb2309a65bd62
shared_oracle_mutated=true
local_index_path=/tmp/dspx-oracle-backend-dogfood-fixed.QA1kw1/candidate/oracle/coordinates.db
local_index_has_database_url=false
oracle_report_status=ok
```

Shared record query proof passed without printing the database password:

```text
publication_record_count=1
publisher_secret_policy_ok=true
```

Dogfood found and fixed one implementation bug before this evidence was accepted: ambient `DSPX_ORACLE_STORE=postgres_pgvector` was leaking into candidate-local program-loop Oracle indexing/reporting. Commit `6be1e7c fix: isolate program oracle local indexes` forces candidate-local program evidence indexing/reporting to SQLite; shared publication remains the explicit shared-write path.

## Gate 2 — backup / off-NAS coverage

Infra repo evidence commit: `57ad1d9 docs: record oracle remote hyper backup success`.

Fresh NAS-side Oracle backup, restore, and dedicated-share export passed:

```text
backup=/volume1/docker/dspx-oracle-coordinate-backend/backups/dspx_oracle-20260508T123255Z.dump
restore=ok
export_path=/volume2/DspxOracleBackups/dspx_oracle-20260508T123255Z.dump
export_bytes=8386
export_sha256=ace24f14be7c4240ac5548b7110241d7070868cd1ab034620ca728d2dead1c7c
```

After the operator ran Hyper Backup, DS1621 coverage verification reported:

```text
selected_share=DspxOracleBackups
selected_share_in_any_hyper_backup_task=true
selected_share_in_remote_hyper_backup_task=true
post_export_any_hyper_backup_success=true
post_export_remote_hyper_backup_success=true
selected_share_tasks=task_1:SynologyDrive:image_local:result=done:last_success=2026-05-09T02:41:51Z;task_3:hypterbackup2Michy:image_remote:result=done:last_success=2026-05-09T02:39:44Z
coverage_status=remote_hyper_backup_success_after_latest_export
```

Monitoring against the latest export contract passed:

```text
monitoring_status=ok
monitoring_failures=0
```

## Gate 3 — authority / activation

The authority gate was dogfooded with a non-production activation target using the generated candidate from the backend dogfood and its shared Oracle publication receipt.

Command shape:

```bash
dspx program-promote activation-packet \
  --manifest /tmp/dspx-oracle-backend-dogfood-fixed.QA1kw1/candidate/manifest.json \
  --owning-domain softwareco/dspx-pilot \
  --activation-target dogfood-only:no-production-route \
  --authority-owner softwareco-generated-program-governance-pilot \
  --oracle-report /tmp/dspx-oracle-backend-dogfood-fixed.QA1kw1/candidate/program_oracle_report.json \
  --oracle-publication-receipt /tmp/dspx-oracle-backend-dogfood-fixed.QA1kw1/candidate/program_oracle_publication_receipt.json \
  --out /tmp/dspx-authority-gate-dogfood-activation-packet.json \
  --json
```

Observed result:

```text
activation_packet_status=blocked
status_kind=advisory_evidence_packet_status_not_authority_state
next_required_action=collect_missing_evidence
missing=jury_results,refined_promotion_review,rollout_owner,rollback_plan
oracle_publication_activation_authority=false
production_activation_applied=false
ak_mutated=false
```

This is the desired authority behavior: even with a live shared Oracle publication receipt, DSPx emits only an advisory activation evidence packet and remains blocked until the governing-domain review evidence, rollout owner, rollback plan, and canonical authority path are explicit.

## Conclusion

- Backend gate: passed for explicit DS1621 shared Oracle publication dogfood.
- Backup/off-NAS gate: passed for the latest Oracle export after remote Hyper Backup success.
- Authority gate: passed as a fail-closed dogfood boundary; no production activation was applied.

Remaining truth: a future concrete generated-program production activation still needs a real owning-domain decision, review evidence, canonical binding, rollout owner, and rollback plan. Oracle/MLflow/DSPx evidence can support that decision but cannot replace it.
