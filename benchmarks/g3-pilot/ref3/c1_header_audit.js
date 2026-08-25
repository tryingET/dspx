/**
summary: "Audits documentation header comments (summary/read_when) across source files."
read_when:
  - "You add or change doc-header conventions or header auditing behavior."
*/

export function auditDocHeaders(sources) {
  const results = [];
  for (const source of sources) {
    const block = extractHeaderBlock(source.text);
    if (block === null) {
      results.push({ file: source.file, hasHeader: false, summary: null, readWhen: null });
      continue;
    }
    const summary = extractQuotedValue(block, "summary:");
    const readWhen = extractQuotedList(block, "read_when:");
    results.push({ file: source.file, hasHeader: true, summary, readWhen });
  }
  return results;
}

export function summarizeHeaderAudit(sources) {
  const entries = auditDocHeaders(sources);
  let withHeader = 0;
  for (const entry of entries) {
    if (entry.hasHeader) {
      withHeader += 1;
    }
  }
  return { total: entries.length, withHeader, missingHeader: entries.length - withHeader };
}

function extractHeaderBlock(text) {
  const start = text.indexOf("/**");
  if (start === -1) {
    return null;
  }
  const end = text.indexOf("*/", start);
  if (end === -1) {
    return null;
  }
  const block = text.slice(start + 3, end);
  return block.includes("summary:") ? block : null;
}

function extractQuotedValue(block, key) {
  const index = block.indexOf(key);
  if (index === -1) {
    return null;
  }
  const tail = block.slice(index + key.length);
  const match = tail.match(/"([^"]*)"/);
  return match === null ? null : match[1];
}

function extractQuotedList(block, key) {
  const index = block.indexOf(key);
  if (index === -1) {
    return [];
  }
  const tail = block.slice(index + key.length);
  const collected = [];
  for (const match of tail.matchAll(/-\s*"([^"]*)"/g)) {
    collected.push(match[1]);
  }
  return collected;
}
