// Reference solution TS-05 (calibration only)
const encoder = new TextEncoder();
const compareUtf8 = (left, right) => {
  const a = encoder.encode(left);
  const b = encoder.encode(right);
  const length = Math.min(a.length, b.length);
  for (let index = 0; index < length; index += 1) {
    if (a[index] !== b[index]) return a[index] - b[index];
  }
  return a.length - b.length;
};

const EVIDENCE_KIND_ORDER = [
  "definition",
  "reference",
  "match",
  "graph_node",
  "graph_edge",
];

const STOP_WORDS = new Set([
  "and",
  "the",
  "for",
  "its",
  "with",
  "change",
  "focused",
  "test",
  "tests",
  "behavior",
]);

const words = (text) =>
  new Set(
    String(text)
      .toLowerCase()
      .match(/[a-z0-9]+/g) ?? [],
  );

const queryTokens = (question) =>
  [...words(question)]
    .filter((token) => token.length >= 3 && !STOP_WORDS.has(token))
    .sort(compareUtf8);

const matchingTokenCount = (text, tokens) => {
  const available = words(text);
  return tokens.reduce((count, token) => count + Number(available.has(token)), 0);
};

const buildRankingRows = (caseDefinition, repository, structuralEvidence) => {
  const tokens = queryTokens(caseDefinition.question);
  return repository.records.map((record) => {
    const structural = structuralEvidence.stats.get(record.path);
    return {
      path: record.path,
      pathScore: matchingTokenCount(record.path, tokens) * 2,
      metadataScore:
        record.metadataStatus === "present"
          ? matchingTokenCount([record.summary ?? "", ...record.readWhen].join(" "), tokens)
          : 0,
      directEvidenceCount: structural.directCount,
      relatedEvidenceCount: structural.relatedCount,
      structuralKindCounts: structural.kindCounts,
    };
  });
};

const structuralOrder = (left, right) => {
  const totalOrder =
    right.directEvidenceCount - left.directEvidenceCount ||
    right.relatedEvidenceCount - left.relatedEvidenceCount;
  if (totalOrder !== 0) return totalOrder;
  for (const kind of EVIDENCE_KIND_ORDER) {
    const kindOrder = right.structuralKindCounts[kind] - left.structuralKindCounts[kind];
    if (kindOrder !== 0) return kindOrder;
  }
  return 0;
};

const selectArm = (rows, arm, maxItems) => {
  const ordered = [...rows];
  ordered.sort((left, right) => {
    if (arm === "structural" || arm === "fusion") {
      const structural = structuralOrder(left, right);
      if (structural !== 0) return structural;
    }
    if (arm === "source_list" || arm === "fusion") {
      const total = right.pathScore + right.metadataScore - (left.pathScore + left.metadataScore);
      if (total !== 0) return total;
      const metadata = right.metadataScore - left.metadataScore;
      if (metadata !== 0) return metadata;
    }
    if (arm !== "structural") {
      const path = right.pathScore - left.pathScore;
      if (path !== 0) return path;
    }
    return compareUtf8(left.path, right.path);
  });
  return ordered.slice(0, maxItems).map(({ path }) => path);
};

export function rankAndSelect(caseDefinition, repository, structuralEvidence, arm, maxItems) {
  const rows = buildRankingRows(caseDefinition, repository, structuralEvidence);
  return selectArm(rows, arm, maxItems);
}
