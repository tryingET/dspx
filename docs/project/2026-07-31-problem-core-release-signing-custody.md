---
summary: "Problem and evidence note for authenticating DSPx Core release evidence and retaining it in CI without conflating custody, publication, or release authority."
read_when:
  - "You are reviewing Core release signing, signer identity, evidence custody, or AK-4125/AK-4126."
  - "You need the trigger and current evidence behind the Core signing-and-custody RFC."
type: "reference"
system4d:
  container:
    boundary: "Decision trigger and evidence for Core signing and CI evidence custody."
    edges:
      - "docs/rfc/RFC-DSPX-CORE-20260731-signing-custody.md"
      - "docs/project/product-posture.md"
      - "docs/project/developer_workflow.md"
  compass:
    driver: "Authenticate exact Core release evidence and retain it long enough for review without creating premature release authority."
    outcome: "An owner-reviewed proposal for signer policy and bounded CI custody."
  engine:
    invariants:
      - "Evidence authenticity, custody, release approval, and publication remain separate transitions."
      - "No long-lived CI signing secret is introduced by default."
      - "The sdist is not a supported release subject unless its separate trigger is accepted."
  fog:
    risks:
      - "A signature may be misread as release approval."
      - "CI retention may be misread as publication or durable archival custody."
---

# Problem and Evidence — Core Release Signing and CI Custody

## Trigger

AK-4124 established a local `dspx-core-release-evidence-v3` envelope and optional mode-0600, no-replace bundle over the exact Core wheel, sdist, installed proof, two verified CycloneDX SBOMs, source state, and a manifest. The bundle remains locally retained and its provenance statement is unauthenticated.

Two owner decisions block the next lawful implementation:

- AK-4125 requires a signature scheme, trusted signer identity, key-custody boundary, signed subject set, revocation policy, and threshold policy.
- AK-4126 requires a CI provider, artifact visibility, retention/deletion policy, access controls, and secret/publication posture.

## Current evidence

`docs/project/developer_workflow.md` documents that:

- Core wheel payload and installed behavior are hash-bound and checked;
- wheel and resolved-environment SBOMs are independently verified against pinned schemas;
- the retained bundle is explicit, no-replace, and local by default;
- signatures remain unverified, CI custody remains absent, and publication/readiness/authority remain false.

`docs/project/product-posture.md` keeps signer verification and CI custody as the immediate release-evidence gates. It also keeps exact-sdist installation behind AK-4137's event trigger.

## Failure modes requiring a decision

1. A long-lived CI key creates a new secret-custody and rotation problem.
2. A generic signature can authenticate an overbroad or ambiguous claim.
3. A valid CI signature can be misrepresented as owner release approval.
4. An uploaded CI bundle can be misrepresented as publication or permanent archive custody.
5. Unbounded retention creates stale-evidence and disclosure risk.
6. Signing the sdist as a supported release subject would trigger an exact-install proof that does not yet exist.

## Decision boundary

The decision must establish:

- how build-evidence authenticity is verified;
- how owner release authorization remains separate;
- what exact artifacts are subjects versus supporting materials;
- where CI evidence may be retained and for how long;
- who can write/read/delete it;
- what remains explicitly unauthorized.

It does not authorize registry publication, package release, production activation, or indefinite archival retention.
