---
summary: "Tactical goals for this project."
read_when:
  - "When planning sprints/weeks"
---

# Tactical Goals

- Goal: Operationalize Oracle Phase C (Time Travel) on top of receipt v2 lineage and branch metadata.
  - Definition of done: Users can inspect behavioral branches/history through a documented, tested CLI slice.
- Goal: Keep replay/explain trustworthy as dependencies and providers change.
  - Definition of done: Receipt-first validation remains green and provenance/drift checks stay explicit in CI.
- Goal: Preserve a strict core-first architecture while apps remain optional consumers.
  - Definition of done: `apps/* -> core` stays one-way and boundary checks remain part of the standard quality gate.
