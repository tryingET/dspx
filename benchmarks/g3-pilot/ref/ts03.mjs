// Reference solution TS-03 (calibration only)
const finiteNumberForKeys = (value, keys) => {
  if (!value || typeof value !== "object") return undefined;
  for (const key of keys) {
    const candidate = value[key];
    if (typeof candidate === "number" && Number.isFinite(candidate)) return candidate;
  }
  return undefined;
};

const compactSessionContextUsage = (usage) => {
  const tokens = finiteNumberForKeys(usage, ["tokens", "totalTokens", "usedTokens", "inputTokens"]);
  const windowTokens = finiteNumberForKeys(usage, [
    "windowTokens",
    "contextWindow",
    "maxTokens",
    "limitTokens",
  ]);
  const contextPressureRatio = tokens && windowTokens ? tokens / windowTokens : undefined;
  return {
    tokens: tokens ?? null,
    windowTokens: windowTokens ?? null,
    contextPressureRatio: contextPressureRatio ?? null,
    rawUsageOmitted: Boolean(usage),
  };
};

const hasHighSessionContextPressure = (usage) => {
  const { tokens, contextPressureRatio } = compactSessionContextUsage(usage);
  return Boolean(
    (contextPressureRatio !== null && contextPressureRatio >= 0.8) ||
      (tokens !== null && tokens >= 120_000),
  );
};

const PROVIDER_CAPABILITIES = {
  agents: { adapterStatus: "wired", executionStatus: "executable_now" },
  git: { adapterStatus: "wired", executionStatus: "executable_now" },
  docs: { adapterStatus: "wired", executionStatus: "executable_now" },
  session: {
    adapterStatus: "guarded",
    executionStatus: "runtime_eligibility_required",
    executionCondition: "caller_required_or_high_context_pressure",
  },
  sci: { adapterStatus: "guarded", executionStatus: "runtime_preflight_required" },
  prompt_vault: { adapterStatus: "planned_unwired", executionStatus: "owner_routed" },
  ak: { adapterStatus: "planned_unwired", executionStatus: "owner_routed" },
  fcos: { adapterStatus: "planned_unwired", executionStatus: "owner_routed" },
};

const contextPackProviderCapability = (provider, env = {}, planContext = {}) => {
  const capability = PROVIDER_CAPABILITIES[provider];
  if (!capability) return { adapterStatus: "unknown", executionStatus: "owner_routed" };
  if (provider === "sci" && env.sciReadOnlySafe !== true) {
    return { adapterStatus: "guarded", executionStatus: "blocked_by_safety_gate" };
  }
  if (
    provider === "session" &&
    (planContext.reason === "provider required by caller" ||
      hasHighSessionContextPressure(env.contextUsage))
  ) {
    return { adapterStatus: "guarded", executionStatus: "executable_now" };
  }
  return { ...capability };
};

export function providerMatrix(providers, env, planContext) {
  return providers.map((provider) => {
    const capability = contextPackProviderCapability(provider, env, planContext);
    return {
      provider,
      adapterStatus: capability.adapterStatus,
      executionStatus: capability.executionStatus,
    };
  });
}
