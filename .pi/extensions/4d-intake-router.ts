import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

export const WORKFLOW_VERSION = "system4d-v1.0";
const STATE_ENTRY = "system4d-intake-router-state";

export type RouterPhase =
	| "idle"
	| "intent_captured"
	| "interview_command_proposed"
	| "interview_running"
	| "interview_completed"
	| "kickoff_command_proposed"
	| "recovery_proposed";

export interface RouterState {
	workflowVersion: string;
	sessionFile?: string;
	phase: RouterPhase;
	firstMessageProcessed: boolean;
	runId?: string;
	taskTitle?: string;
	dbPathOrNone?: string;
	interviewCommand?: string;
	kickoffCommand?: string;
	recoveryCommand?: string;
	originalPromptSnippet?: string;
	updatedAt: number;
}

export interface InterviewResponseItem {
	id: string;
	value: string | string[];
	attachments?: string[];
}

export interface InterviewDetails {
	status?: string;
	responses?: InterviewResponseItem[];
	url?: string;
}

export function newState(overrides: Partial<RouterState> = {}): RouterState {
	return {
		workflowVersion: WORKFLOW_VERSION,
		phase: "idle",
		firstMessageProcessed: false,
		dbPathOrNone: "none",
		updatedAt: Date.now(),
		...overrides,
	};
}

export function normalizeInline(value: string, maxLen = 400): string {
	const compact = value.replace(/\s+/g, " ").trim();
	if (compact.length <= maxLen) return compact;
	return compact.slice(0, maxLen - 1) + "…";
}

function quoteArg(value: string): string {
	return JSON.stringify(value);
}

export function formatCommand(name: string, args: string[]): string {
	return `/${name} ${args.map((a) => quoteArg(a)).join(" ")}`;
}

export function yyyymmdd(d: Date): string {
	const y = d.getFullYear();
	const m = String(d.getMonth() + 1).padStart(2, "0");
	const day = String(d.getDate()).padStart(2, "0");
	return `${y}${m}${day}`;
}

export function slugify(input: string): string {
	const slug = input
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, "-")
		.replace(/^-+|-+$/g, "")
		.slice(0, 64);
	return slug.length >= 3 ? slug : "system4d-run";
}

export function pickTaskTitle(text: string): string {
	const labeledMatchers = [
		/main\s+in-?flight\s+theme\s*:\s*(.+)$/im,
		/task\s+title\s*:\s*(.+)$/im,
		/title\s*:\s*(.+)$/im,
	];
	for (const pattern of labeledMatchers) {
		const match = text.match(pattern);
		if (match?.[1]) return normalizeInline(match[1], 140);
	}

	const lines = text
		.split(/\r?\n/)
		.map((l) => l.trim())
		.filter(Boolean);

	const candidate =
		lines.find((line) => !/^[-*#]/.test(line) && !/^branch\s*:/i.test(line) && line.length > 8) ||
		lines[0] ||
		"system4d-workflow";

	return normalizeInline(candidate, 140);
}

export function extractDbPathFromText(text: string): string | undefined {
	const regex = /(?:~|\.{1,2}\/|\/)?[A-Za-z0-9._\/-]+\.(?:db|sqlite|sqlite3)\b/gi;
	const match = text.match(regex);
	if (!match || match.length === 0) return undefined;
	let cleaned = match[0].replace(/[),.;]+$/, "").trim();
	if (cleaned.startsWith("///")) cleaned = cleaned.replace(/^\/{3}/, "");
	if (cleaned.startsWith("//") && !cleaned.startsWith("///")) cleaned = cleaned.replace(/^\/{2}/, "/");
	return cleaned || undefined;
}

function normalizeCandidate(pathLike: string): string {
	let p = pathLike.trim();
	if (!p) return p;
	if (p.startsWith("./")) p = p.slice(2);
	return p;
}

function isIgnoredDbPath(pathLike: string): boolean {
	return /(^|\/)node_modules\//.test(pathLike)
		|| /(^|\/)\.venv\//.test(pathLike)
		|| /(^|\/)\.git\//.test(pathLike)
		|| /(^|\/)dist\//.test(pathLike)
		|| /(^|\/)build\//.test(pathLike)
		|| /(^|\/)\.cache\//.test(pathLike)
		|| /(^|\/)__pycache__\//.test(pathLike);
}

async function discoverDbCandidates(pi: ExtensionAPI): Promise<string[]> {
	const candidates = new Set<string>();

	const fdResult = await pi.exec("fd", ["-HI", "-t", "f", "-e", "db", "-e", "sqlite", "-e", "sqlite3", "."]);
	if (fdResult.code === 0 && fdResult.stdout) {
		for (const line of fdResult.stdout.split(/\r?\n/)) {
			const normalized = normalizeCandidate(line);
			if (normalized) candidates.add(normalized);
		}
	}

	if (candidates.size === 0) {
		const findResult = await pi.exec("bash", [
			"-lc",
			"find . -type f \\( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \\) | head -n 50",
		]);
		if (findResult.code === 0 && findResult.stdout) {
			for (const line of findResult.stdout.split(/\r?\n/)) {
				const normalized = normalizeCandidate(line);
				if (normalized) candidates.add(normalized);
			}
		}
	}

	return [...candidates].filter((p) => p && !isIgnoredDbPath(p));
}

function asList(value: string | string[] | undefined): string[] {
	if (value === undefined) return [];
	if (Array.isArray(value)) return value.map((v) => normalizeInline(v, 120)).filter(Boolean);
	const scalar = normalizeInline(value, 120);
	return scalar ? [scalar] : [];
}

function responseMap(responses: InterviewResponseItem[]): Map<string, string | string[]> {
	const map = new Map<string, string | string[]>();
	for (const item of responses) {
		if (item?.id) map.set(item.id, item.value);
	}
	return map;
}

function scalarFrom(map: Map<string, string | string[]>, id: string): string {
	const value = map.get(id);
	if (value === undefined) return "";
	if (Array.isArray(value)) return normalizeInline(value.join(", "), 260);
	return normalizeInline(value, 260);
}

function listFrom(map: Map<string, string | string[]>, id: string): string[] {
	return asList(map.get(id));
}

function requiredOrFill(label: string, value: string): string {
	const normalized = normalizeInline(value, 260);
	return normalized || `<fill-${label}>`;
}

export function buildKickoffArgs(
	state: RouterState,
	responses: InterviewResponseItem[],
): {
	args: string[];
	missing: string[];
} {
	const map = responseMap(responses);

	const driverRaw = scalarFrom(map, "compass_driver");
	const outcomeRaw = scalarFrom(map, "compass_outcome");
	const constraintsList = listFrom(map, "container_constraints");
	const constraintsRaw = constraintsList.join("; ");
	const boundaryIn = scalarFrom(map, "container_boundary_in");
	const boundaryOut = scalarFrom(map, "container_boundary_out");
	const boundaryRaw = `in: ${boundaryIn || "<unknown>"} | out: ${boundaryOut || "<unknown>"}`;
	const edges = scalarFrom(map, "container_edges");
	const deps = scalarFrom(map, "container_dependencies");
	const edgesDepsRaw = `edges: ${edges || "<unknown>"} | dependencies: ${deps || "<unknown>"}`;
	const successRaw = scalarFrom(map, "success_criteria");

	const extraParts = [
		state.originalPromptSnippet ? `handoff:${state.originalPromptSnippet}` : "",
		scalarFrom(map, "fog_assumptions") ? `assumptions:${scalarFrom(map, "fog_assumptions")}` : "",
		scalarFrom(map, "fog_risks") ? `risks:${scalarFrom(map, "fog_risks")}` : "",
		scalarFrom(map, "fog_debt") ? `debt:${scalarFrom(map, "fog_debt")}` : "",
	].filter(Boolean);
	const extra = normalizeInline(extraParts.join(" || "), 700);

	const runId = state.runId || `${yyyymmdd(new Date())}-system4d-run`;
	const taskTitle = state.taskTitle || "system4d-workflow";
	const dbPathOrNone = state.dbPathOrNone || "none";

	const requiredFields: Array<[string, string]> = [
		["driver", driverRaw],
		["outcome", outcomeRaw],
		["constraints", constraintsRaw],
		["boundary", boundaryRaw],
		["edges_dependencies", edgesDepsRaw],
		["success_criteria", successRaw],
	];
	const missing = requiredFields.filter(([, value]) => !value || value.includes("<unknown>")).map(([k]) => k);

	const args = [
		runId,
		taskTitle,
		requiredOrFill("driver", driverRaw),
		requiredOrFill("outcome", outcomeRaw),
		requiredOrFill("constraints", constraintsRaw),
		requiredOrFill("boundary", boundaryRaw),
		requiredOrFill("edges-dependencies", edgesDepsRaw),
		dbPathOrNone,
		requiredOrFill("success-criteria", successRaw),
		extra,
	];

	return { args, missing };
}

export function buildRecoveryCommand(state: RouterState, status: string): string {
	const runId = state.runId || `${yyyymmdd(new Date())}-system4d-run`;
	const taskTitle = state.taskTitle || "system4d-workflow";
	const dbPathOrNone = state.dbPathOrNone || "none";
	const extra = normalizeInline(
		`session-recovery: interview status=${status}; resume Stage-0 intake and continue from saved answers`,
		300,
	);
	return formatCommand("interview-4d-intake", [runId, taskTitle, dbPathOrNone, extra]);
}

function coerceInterviewDetails(event: unknown): InterviewDetails | undefined {
	if (!event || typeof event !== "object") return undefined;
	const record = event as Record<string, unknown>;
	if (record.toolName !== "interview") return undefined;
	const details = record.details;
	if (!details || typeof details !== "object") return undefined;
	return details as InterviewDetails;
}

export default function system4dIntakeRouter(pi: ExtensionAPI) {
	let state = newState();

	const persist = () => {
		state.updatedAt = Date.now();
		pi.appendEntry(STATE_ENTRY, state);
	};

	const setState = (patch: Partial<RouterState>, save = true) => {
		state = { ...state, ...patch, workflowVersion: WORKFLOW_VERSION };
		if (save) persist();
	};

	const restore = (ctx: any) => {
		const branch = ctx.sessionManager.getBranch();
		let restored: RouterState | undefined;
		for (const entry of branch) {
			if (entry.type === "custom" && entry.customType === STATE_ENTRY && entry.data && typeof entry.data === "object") {
				restored = entry.data as RouterState;
			}
		}
		state = restored ? { ...newState(), ...restored, workflowVersion: WORKFLOW_VERSION } : newState();
		setState({
			sessionFile: ctx.sessionManager.getSessionFile() || undefined,
			firstMessageProcessed: false,
			phase: "idle",
		});
	};

	const prefill = (ctx: any, command: string, notice: string, level: "info" | "warning" = "info") => {
		if (!ctx.hasUI) return;
		ctx.ui.setEditorText(command);
		ctx.ui.notify(notice, level);
	};

	pi.on("session_start", async (_event, ctx) => {
		restore(ctx);
		if (ctx.hasUI) {
			ctx.ui.setStatus("system4d-router", "ready (first-message intake)");
		}
	});

	pi.on("session_switch", async (_event, ctx) => {
		restore(ctx);
	});

	pi.on("tool_call", async (event, ctx) => {
		if (event.toolName === "interview") {
			setState({ phase: "interview_running" });
			if (ctx.hasUI) ctx.ui.setStatus("system4d-router", "interview running");
		}
	});

	pi.on("input", async (event, ctx) => {
		if (event.source === "extension") return { action: "continue" as const };
		if (!ctx.hasUI) return { action: "continue" as const };
		if (state.firstMessageProcessed) return { action: "continue" as const };

		const text = event.text.trim();
		if (!text) return { action: "continue" as const };

		setState({ firstMessageProcessed: true, phase: "intent_captured" });

		if (text.startsWith("/")) {
			// User intentionally sent a command as first message; don't intercept.
			return { action: "continue" as const };
		}

		const taskTitle = pickTaskTitle(text);
		const runId = `${yyyymmdd(new Date())}-${slugify(taskTitle)}`;

		let dbPathOrNone = extractDbPathFromText(text) || "none";
		if (dbPathOrNone === "none") {
			const candidates = await discoverDbCandidates(pi);
			if (candidates.length === 1) {
				dbPathOrNone = candidates[0];
			} else if (candidates.length > 1) {
				ctx.ui.notify(
					`DB auto-discovery found multiple candidates (${candidates.length}); using 'none' (edit command if needed).`,
					"warning",
				);
			}
		}

		const originalPromptSnippet = normalizeInline(text, 700);
		const interviewCommand = formatCommand("interview-4d-intake", [
			runId,
			taskTitle,
			dbPathOrNone,
			originalPromptSnippet,
		]);

		setState({
			runId,
			taskTitle,
			dbPathOrNone,
			originalPromptSnippet,
			interviewCommand,
			phase: "interview_command_proposed",
		});

		prefill(
			ctx,
			interviewCommand,
			"System4D intake command prepared. Review/edit and press Enter to run.",
		);

		return { action: "handled" as const };
	});

	pi.on("tool_result", async (event, ctx) => {
		const details = coerceInterviewDetails(event);
		if (!details?.status) return;

		if (details.status === "queued") {
			if (ctx.hasUI) ctx.ui.setStatus("system4d-router", "interview queued");
			return;
		}

		if (details.status !== "completed") {
			const recoveryCommand = buildRecoveryCommand(state, details.status);
			setState({
				recoveryCommand,
				phase: "recovery_proposed",
			});
			prefill(
				ctx,
				recoveryCommand,
				`Interview ${details.status}. Recovery command prepared (kickoff not proposed).`,
				"warning",
			);
			if (ctx.hasUI) ctx.ui.setStatus("system4d-router", "awaiting interview recovery");
			return;
		}

		const responses = Array.isArray(details.responses) ? details.responses : [];
		const { args, missing } = buildKickoffArgs(state, responses);
		if (missing.length > 0) {
			const recoveryCommand = buildRecoveryCommand(state, "incomplete-required-fields");
			setState({
				recoveryCommand,
				phase: "recovery_proposed",
			});
			prefill(
				ctx,
				recoveryCommand,
				`Interview completed but kickoff gate failed (missing: ${missing.join(", ")}). Recovery command prepared.`,
				"warning",
			);
			if (ctx.hasUI) ctx.ui.setStatus("system4d-router", "gate failed: recovery required");
			return;
		}

		const kickoffCommand = formatCommand("subagent-4d-kickoff", args);
		setState({
			kickoffCommand,
			phase: "kickoff_command_proposed",
		});

		prefill(
			ctx,
			kickoffCommand,
			"Interview completed. Kickoff command prepared. Validate 00-intake/kickoff-gate-checklist.md before sending.",
			"info",
		);
		if (ctx.hasUI) ctx.ui.setStatus("system4d-router", "kickoff command ready");
	});

	pi.registerCommand("s4d-router-status", {
		description: "Show System4D intake router state",
		handler: async (_args, ctx) => {
			const summary = [
				`phase: ${state.phase}`,
				`run_id: ${state.runId ?? "<none>"}`,
				`task_title: ${state.taskTitle ?? "<none>"}`,
				`db_path_or_none: ${state.dbPathOrNone ?? "none"}`,
				`first_message_processed: ${state.firstMessageProcessed ? "yes" : "no"}`,
				`updated_at: ${new Date(state.updatedAt).toISOString()}`,
			];
			if (!ctx.hasUI) return;
			ctx.ui.notify(summary.join(" | "), "info");
		},
	});

	pi.registerCommand("s4d-router-reset", {
		description: "Reset System4D intake router state for the current session",
		handler: async (_args, ctx) => {
			state = newState({ sessionFile: ctx.sessionManager.getSessionFile() || undefined });
			persist();
			if (ctx.hasUI) {
				ctx.ui.setStatus("system4d-router", "ready (reset)");
				ctx.ui.notify("System4D router state reset. Next non-command message will trigger intake proposal.", "info");
			}
		},
	});
}
