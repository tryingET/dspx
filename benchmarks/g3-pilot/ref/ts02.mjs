// Reference solution TS-02 (calibration only)
import { closeSync, lstatSync, openSync, readSync, statSync } from "node:fs";
import path from "node:path";

const FILE_BUDGET_POLICY = {
  budgets: {
    code: { lines: 500, bytes: 50 * 1024 },
    test: { lines: 1000, bytes: 80 * 1024 },
    markdown: { lines: 800, bytes: 60 * 1024 },
  },
  codeExtensions: [".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"],
  markdownExtensions: [".md", ".mdx"],
  excludedDirs: [
    ".git", ".hg", ".svn", "node_modules", "dist", "build", "coverage",
    ".next", ".turbo", ".cache", ".tmp", "tmp", "vendor",
  ],
  excludedFileSuffixes: [
    ".d.ts", ".min.js", ".bundle.js", ".map", ".tgz",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".lock",
  ],
};
const FILE_BUDGETS = FILE_BUDGET_POLICY.budgets;
const CODE_EXTENSIONS = new Set(FILE_BUDGET_POLICY.codeExtensions);
const MARKDOWN_EXTENSIONS = new Set(FILE_BUDGET_POLICY.markdownExtensions);
const EXCLUDED_DIRS = new Set(FILE_BUDGET_POLICY.excludedDirs);
const EXCLUDED_SUFFIXES = FILE_BUDGET_POLICY.excludedFileSuffixes;

const toPosix = (value) => value.split(path.sep).join("/");

function pathIsInside(root, candidate) {
  const rel = path.relative(path.resolve(root), path.resolve(candidate));
  return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
}

function fileBudgetKindForPath(relativePath) {
  const normalized = toPosix(relativePath).toLowerCase();
  if (normalized.split("/").some((segment) => EXCLUDED_DIRS.has(segment))) return null;
  if (EXCLUDED_SUFFIXES.some((suffix) => normalized.endsWith(suffix))) return null;
  const ext = path.extname(normalized).toLowerCase();
  if (MARKDOWN_EXTENSIONS.has(ext)) return "markdown";
  if (!CODE_EXTENSIONS.has(ext)) return null;
  const base = path.basename(normalized);
  if (
    normalized.startsWith("tests/") ||
    normalized.includes("/tests/") ||
    /\.(?:test|spec)\.[cm]?[jt]sx?$/u.test(base) ||
    /\.(?:test|spec)\.m?js$/u.test(base)
  ) {
    return "test";
  }
  return "code";
}

function lineCountFile(filePath) {
  const fd = openSync(filePath, "r");
  const buffer = Buffer.allocUnsafe(64 * 1024);
  let bytesReadTotal = 0;
  let lines = 0;
  let lastByte;

  try {
    while (true) {
      const bytesRead = readSync(fd, buffer, 0, buffer.length, null);
      if (bytesRead === 0) break;
      bytesReadTotal = bytesReadTotal + bytesRead;
      lastByte = buffer[bytesRead - 1];
      for (let index = 0; index < bytesRead; index += 1) {
        if (buffer[index] === 10) lines += 1;
      }
    }
  } finally {
    closeSync(fd);
  }

  if (bytesReadTotal === 0) return 0;
  return lastByte === 10 ? lines : lines + 1;
}

function analyzeFileBudgetForPath({ displayPath, absolutePath }) {
  const kind = fileBudgetKindForPath(displayPath);
  if (!kind) return null;
  const budget = FILE_BUDGETS[kind];

  try {
    if (lstatSync(absolutePath).isSymbolicLink()) return null;
    const stats = statSync(absolutePath);
    if (!stats.isFile()) return null;
    const bytes = stats.size;
    const lines = lineCountFile(absolutePath);
    if (lines <= budget.lines && bytes <= budget.bytes) return null;
    return {
      path: toPosix(displayPath),
      kind,
      lines,
      bytes,
      maxLines: budget.lines,
      maxBytes: budget.bytes,
    };
  } catch {
    return null;
  }
}

// --- intake safety (context-intake-safety.js conventions)
const GENERATED_OR_VENDOR_PARTS = new Set(["node_modules", "dist", "build", "coverage"]);
const HIDDEN_OR_INTERNAL_PARTS = new Set(["__pycache__"]);
const isControlCode = (code) => code < 32 || code === 127 || (code >= 128 && code <= 159);
const hasControlCharacter = (value) =>
  Array.from(value).some((character) => isControlCode(character.charCodeAt(0)));
const hasSchemeOrDrivePrefix = (value) => /^[A-Za-z][A-Za-z0-9+.-]*:/u.test(value);
const repoRelativePathSafetyIssue = (value, label = "path seed") => {
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

export function budgetRisks(seeds, root) {
  const risks = [];
  const seen = new Set();
  for (const seed of seeds) {
    if (seed?.kind !== "path" || typeof seed.value !== "string") continue;
    const absolutePath = path.resolve(root, seed.value);
    if (!pathIsInside(root, absolutePath)) continue;
    const key = toPosix(seed.value);
    if (seen.has(key)) continue;
    seen.add(key);
    const analysis = analyzeFileBudgetForPath({ displayPath: key, absolutePath });
    if (analysis) risks.push(analysis);
  }
  const unsafeSeeds = [];
  for (const seed of seeds) {
    if (seed?.kind !== "path" || typeof seed.value !== "string") continue;
    const issue = repoRelativePathSafetyIssue(seed.value);
    if (issue !== undefined) unsafeSeeds.push({ value: seed.value, issue });
  }
  return { risks, unsafeSeeds };
}
