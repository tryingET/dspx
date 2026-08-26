// Reference solution TS-01 (calibration only)
const GENERATED_OR_VENDOR_PARTS = new Set(["node_modules", "dist", "build", "coverage"]);
const HIDDEN_OR_INTERNAL_PARTS = new Set(["__pycache__"]);

const isControlCode = (code) => code < 32 || code === 127 || (code >= 128 && code <= 159);

export const hasControlCharacter = (value) =>
  Array.from(value).some((character) => isControlCode(character.charCodeAt(0)));

export const hasSchemeOrDrivePrefix = (value) => /^[A-Za-z][A-Za-z0-9+.-]*:/u.test(value);

export const repoRelativePathSafetyIssue = (value, label = "path seed") => {
  if (typeof value !== "string" || !value.trim()) return `${label} is empty`;
  if (hasControlCharacter(value)) return `${label} contains control characters`;
  if (hasSchemeOrDrivePrefix(value)) return "URI or drive-letter path seed omitted";
  if (value.startsWith("/") || value.startsWith("~"))
    return "absolute/home-relative path seed omitted";
  if (value.includes("\\")) return "path seed must use repo-relative POSIX separators";

  const parts = value.split("/").filter(Boolean);
  if (!parts.length || parts.some((part) => part === "." || part === "..")) {
    return "current-directory or parent-traversing path seed omitted";
  }
  if (parts.some((part) => part.startsWith(".") || HIDDEN_OR_INTERNAL_PARTS.has(part))) {
    return "hidden/internal path seed omitted";
  }
  if (parts.some((part) => GENERATED_OR_VENDOR_PARTS.has(part))) {
    return "generated/vendor path seed omitted";
  }
  return undefined;
};

export const symbolSeedSafetyIssue = (value, label = "symbol seed") => {
  if (typeof value !== "string" || !value.trim()) return `${label} is empty`;
  if (hasControlCharacter(value)) return `${label} contains control characters`;
  if (value.length > 240) return `${label} exceeds 240 characters`;
  return undefined;
};

const CONTEXT_PLAN_SEED_KINDS = Object.freeze([
  "path",
  "symbol",
  "task",
  "fcos",
  "ak",
  "prompt",
  "free_text",
]);
const CONTEXT_PLAN_SEED_KIND_SET = new Set(CONTEXT_PLAN_SEED_KINDS);
const coerceString = (value, fallback = "") => {
  if (typeof value === "string") return value;
  return fallback;
};

export const normalizeContextPlanSeedKind = (kind) => {
  const value = coerceString(kind, "free_text");
  return CONTEXT_PLAN_SEED_KIND_SET.has(value) ? value : "free_text";
};

export function auditSeeds(seeds) {
  return seeds.map((seed) => {
    const kind = normalizeContextPlanSeedKind(seed?.kind);
    let issue = null;
    if (kind === "path") issue = repoRelativePathSafetyIssue(seed?.value) ?? null;
    if (kind === "symbol") issue = symbolSeedSafetyIssue(seed?.value) ?? null;
    return { normalizedKind: kind, issue };
  });
}
