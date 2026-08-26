/**
summary: "Tests documentation-header auditing: parsing, missing headers, and aggregation."
read_when:
  - "You change doc-header parsing or the header audit aggregation."
*/

import assert from "node:assert/strict";
import test from "node:test";
import { auditDocHeaders, summarizeHeaderAudit } from "../src/g3p3-header-audit.js";

const WITH_HEADER = `/**
summary: "First sentence."
read_when:
  - "Trigger one."
  - "Trigger two."
*/

export const x = 1;
`;

const WITHOUT_HEADER = `export const y = 2;
`;

test("parses summary and read_when triggers from a doc header", () => {
  const [entry] = auditDocHeaders([{ file: "a.js", text: WITH_HEADER }]);
  assert.equal(entry.hasHeader, true);
  assert.equal(entry.summary, "First sentence.");
  assert.deepEqual(entry.readWhen, ["Trigger one.", "Trigger two."]);
});

test("reports a missing header with null fields", () => {
  const [entry] = auditDocHeaders([{ file: "b.js", text: WITHOUT_HEADER }]);
  assert.equal(entry.hasHeader, false);
  assert.equal(entry.summary, null);
  assert.equal(entry.readWhen, null);
});

test("summarizes a deterministic set of eight fixtures", () => {
  const sources = [];
  for (let i = 0; i < 8; i += 1) {
    const text = i % 3 === 0 ? WITHOUT_HEADER : WITH_HEADER;
    sources.push({ file: `fixture-${i}.js`, text });
  }
  const summary = summarizeHeaderAudit(sources);
  assert.equal(summary.total, 8);
  assert.equal(summary.withHeader, 5);
  assert.equal(summary.missingHeader, 3);
});

test("a block without summary is not a header", () => {
  const text = `/**
just a note
*/
export const z = 3;
`;
  const [entry] = auditDocHeaders([{ file: "c.js", text }]);
  assert.equal(entry.hasHeader, false);
});
