---
summary: "Adopt an explicit concentrated single-owner Core authorization policy with hardware-backed exact-payload authentication."
status: proposed
---

# Proposed ADR — Core single-owner FIDO authorization

## Context

DSPx has one real owner. The historical 2-of-3 policy correctly remains disabled because aliases cannot create independent judgment. Evidence signing/custody is live, but package release authority remains separate.

## Decision

Adopt a new immutable single-owner policy generation binding `tryingET` / GitHub user ID `260287438` to a dedicated FIDO2 OpenSSH public key. Require exact canonical payload SSHSIG verification under namespace `dspx-core-release-authorization-v1`, user presence/verification, a 15-minute maximum lifetime, a single-use nonce, current policy and custody, denylist clearance, and explicit concentrated-risk claims.

Package publication and sdist support remain false. Technical controls are conjunctions, not additional principals.

## Consequences

The model is honest and operational for a solo project, but owner compromise can authorize a release. No consumer may report authority until it independently verifies technical evidence and atomically consumes the nonce; caller-asserted booleans are not proof. Publication remains a later owner transition.

## Current gate

The dedicated FIDO public key is registered, but the first exact-payload signature was not completed because user verification requires the authenticator PIN in a real terminal. A fingerprint identifies the public key; it cannot prove owner intent. The checked-in owner policy therefore keeps `authorization_enabled=false`, and the adapter returns `release_authority=false` even after signature authentication until the trusted technical consumer and atomic nonce ledger exist.
