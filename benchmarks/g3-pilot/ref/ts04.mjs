// Reference solution TS-04 (calibration only): byte-identical render parity
const isControlCode = (code) => code < 32 || code === 127 || (code >= 128 && code <= 159);
const replaceControlCharacters = (value) =>
  Array.from(value)
    .map((character) => {
      const code = character.charCodeAt(0);
      return isControlCode(code) ? " " : character;
    })
    .join("");

const markdownInlineLabel = (value, fallback = "unnamed", maxLength = 240) => {
  const text = replaceControlCharacters(String(value ?? ""))
    .replace(/</gu, "‹")
    .replace(/>/gu, "›")
    .replace(/\s+/gu, " ")
    .trim();
  if (!text) return fallback;
  return text.length > maxLength ? `${text.slice(0, Math.max(0, maxLength - 1))}…` : text;
};

const longestBacktickRun = (text) => {
  const runs = String(text).match(/`+/gu) ?? [];
  return runs.reduce((max, run) => Math.max(max, run.length), 0);
};

const markdownFence = (label, content) => {
  const safeLabel = markdownInlineLabel(label);
  const fenceLength = Math.max(
    3,
    longestBacktickRun(content) + 1,
    longestBacktickRun(safeLabel) + 1,
  );
  const fence = "`".repeat(fenceLength);
  return [fence, `# ${safeLabel}`, content, fence].join("\n");
};

const DOGFOOD_USER_OMISSION_FOLLOWUP_CLASSES = Object.freeze([
  "useful_omission",
  "residual_probe",
  "validation_activity",
  "legacy_missingness",
  "provenance_source_owner_followup",
  "true_missing_capability",
  "other",
]);
const DOGFOOD_OMISSION_FOLLOWUP_CLASS_GUIDANCE = `optionally use objects with provider, reason, and classification (${DOGFOOD_USER_OMISSION_FOLLOWUP_CLASSES.join(", ")})`;

const formatPacketItem = (item) => {
  const displayId = markdownInlineLabel(item.id, "packet item");
  const heading = `### ${displayId}`;
  const meta = [
    `- kind: ${markdownInlineLabel(item.kind, "unknown")}`,
    `- mode: ${markdownInlineLabel(item.contentMode, "unknown")}`,
    item.provenance?.path
      ? `- path: ${markdownInlineLabel(item.provenance.path, "unknown")}`
      : undefined,
    item.provenance?.command
      ? `- command: ${markdownInlineLabel(item.provenance.command, "unknown")}`
      : undefined,
    `- rationale: ${markdownInlineLabel(item.rationale, "none")}`,
  ].filter(Boolean);
  return [heading, ...meta, "", markdownFence(item.id, item.content)].join("\n");
};

const formatContextPlan = (plan) => {
  if (!plan.ok) return `Context plan failed: ${(plan.errors ?? []).join("; ")}`;
  throw new Error("not needed for reference");
};

export const renderPacket = (result) => {
  if (!result.ok) return formatContextPlan(result.plan);
  const { packet } = result;
  const sectionSummaries = packet.sections.map(
    (section) =>
      `- ${section.provider}: ${section.items.length} item(s), ${section.estimatedTokens} tokens`,
  );
  const bodySections = packet.sections.map((section) =>
    [
      `## ${section.title}`,
      `Provider: ${section.provider}`,
      `Authority: ${section.authority}`,
      "",
      ...section.items.map(formatPacketItem),
    ].join("\n"),
  );
  const omissions = packet.omissions.map(
    (omission) =>
      `- ${markdownInlineLabel(omission.provider, "provider")}/${markdownInlineLabel(omission.reason, "reason")}: ${markdownInlineLabel(omission.detail, "detail omitted")}`,
  );
  const ownerRouting = (packet.ownerSurfaceRecommendations ?? []).map(
    (recommendation) =>
      `- ${markdownInlineLabel(recommendation.surface, "surface")}: ${markdownInlineLabel(recommendation.nextAction, "next action")} (${markdownInlineLabel(recommendation.nonAuthorization, "non-authorization")})`,
  );
  const utility = packet.measurementReceipt.packetUtilityRecommendation;
  const dogfoodFollowup = packet.measurementReceipt.dogfoodFollowupReceipt;
  const dogfoodObservationTemplate = packet.dogfoodObservationTemplate
    ? markdownFence(
        "dogfood-observation-template.json",
        JSON.stringify(packet.dogfoodObservationTemplate, null, 2),
      )
    : undefined;
  return [
    `# Context packet: ${markdownInlineLabel(packet.objective, "objective")}`,
    "",
    `Selected provider content: ${packet.totals.candidatesSelected} item(s), ${packet.totals.estimatedTokens} estimated tokens, ${packet.totals.bytes} bytes`,
    "Budget accounting: packet totals count selected provider content only; rendered scaffolding is reported separately in tool details.",
    `Estimated tool calls avoided: ${packet.measurementReceipt.estimatedToolCallsAvoided}`,
    "",
    "## Packet utility",
    utility
      ? [
          `- status: ${utility.status}`,
          `- reason: ${utility.reason}`,
          `- next: ${utility.nextAction}`,
          `- non-authorization: ${utility.nonAuthorization}`,
        ].join("\n")
      : "- none",
    "",
    "## Dogfood follow-up",
    dogfoodFollowup
      ? [
          `- status: ${dogfoodFollowup.status}`,
          `- expected low-level calls avoided: ${dogfoodFollowup.expectedLowLevelCallsAvoided}`,
          "- activity type: optionally fill activityType as implementation, review, validation, planning, or other",
          "- runtime context: optionally fill runtimeContext as source_local, installed_artifact, live_pi_reloaded, or unknown",
          "- actual low-level read/search/status calls: fill externally after work if useful",
          "- validation commands run: fill validationCommandsRun separately from context probes if recording dogfood",
          `- omission follow-ups: ${DOGFOOD_OMISSION_FOLLOWUP_CLASS_GUIDANCE}`,
          `- non-authorization: ${dogfoodFollowup.nonAuthorization}`,
        ].join("\n")
      : "- none",
    "",
    "## Section summary",
    sectionSummaries.length ? sectionSummaries.join("\n") : "- none",
    "",
    ...bodySections,
    "",
    "## Omissions",
    omissions.length ? omissions.join("\n") : "- none",
    "",
    "## Owner-surface routing",
    ownerRouting.length ? ownerRouting.join("\n") : "- none",
    "",
    "## Dogfood observation template",
    dogfoodObservationTemplate ?? "- none",
    "",
    "## Non-authorizations",
    ...packet.nonAuthorizations.map((item) => `- ${item}`),
  ].join("\n");
};
