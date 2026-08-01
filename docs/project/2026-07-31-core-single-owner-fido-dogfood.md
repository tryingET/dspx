---
summary: "Fail-closed registration dogfood for the proposed single-owner Core FIDO authorization policy."
type: evidence
---

# Core single-owner FIDO registration dogfood

## Observed

- A Yubico FIDO authenticator was detected as a security token.
- The operator explicitly approved a unique new key path: `~/.ssh/dspx-core-release-owner-sk`.
- OpenSSH generated a dedicated `sk-ssh-ed25519@openssh.com` key with user verification required.
- Public fingerprint: `SHA256:OYAnSnMFl+jvWmFJ6TFcHdikBdL7N2MG3k+FIlSqVis`.
- Only the public key is recorded in the proposed owner policy. No private key handle or PIN is committed.
- An exact canonical approval payload was built against successful 90-day evidence run `30660312181`.

## Fail-closed result

The agent subprocess could not present the FIDO PIN prompt because no SSH askpass program was available. The operator asked whether the fingerprint alone could suffice. It cannot: a fingerprint identifies a public key but does not prove possession, user presence, user verification, or approval of the exact payload.

No signature was produced, no nonce was consumed, and no release authority was granted. The proposed owner policy remains disabled. Package publication and sdist support remain false.

## Next legal experiment

From a normal interactive terminal, sign the already canonicalized payload with:

```bash
ssh-keygen -Y sign \
  -f ~/.ssh/dspx-core-release-owner-sk \
  -n dspx-core-release-authorization-v1 \
  <canonical-approval-payload>
```

Enter the authenticator PIN and touch the YubiKey. Then verify the detached SSHSIG against the pinned public key. This proves owner intent only; release authority must still wait for in-process current-policy, denylist, evidence-authenticity, current paired-custody verification, and atomic nonce consumption.
