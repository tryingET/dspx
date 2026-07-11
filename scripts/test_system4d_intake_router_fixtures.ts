/**
summary: "Executable fixture checks for the System4D intake router's parsing, synthesis, quoting, and recovery helpers."
read_when:
  - "Changing the 4D intake router or its kickoff and recovery contracts."
*/

import {
	buildDbClarifyCommand,
	buildKickoffArgs,
	buildRecoveryCommand,
	collectRunIdMentions,
	extractDbPathFromText,
	formatCommand,
	newState,
	parseInterviewIntakeArgs,
	pickTaskTitle,
	slugify,
	yyyymmdd,
	type InterviewResponseItem,
} from "../.pi/extensions/4d-intake-router.ts";

function assert(condition: boolean, message: string): void {
	if (!condition) throw new Error(message);
}

function includesAll(haystack: string, needles: string[], label: string): void {
	for (const needle of needles) {
		assert(haystack.includes(needle), `${label}: missing expected token '${needle}'`);
	}
}

function asResponse(id: string, value: string | string[]): InterviewResponseItem {
	return { id, value };
}

function run(): void {
	// Task title extraction
	const handoff = [
		"Branch + cleanliness snapshot:",
		"- Branch: main",
		"Main in-flight theme: MLflow lifecycle hardening + explain enrichment",
	].join("\n");
	const title = pickTaskTitle(handoff);
	includesAll(title.toLowerCase(), ["mlflow", "lifecycle"], "pickTaskTitle(handoff)");

	const fallbackTitle = pickTaskTitle("Investigate replay drift taxonomy regression");
	includesAll(fallbackTitle.toLowerCase(), ["replay", "drift"], "pickTaskTitle(fallback)");

	// Structured intake arg extraction
	const structured = [
		"Run Stage-0 intake interview for:",
		"- `RUN_ID`: `20260208-system4d-intake-workflow-extension-first-smoke-test`",
		"- `TASK_TITLE`: `system4d intake workflow + extension first smoke test`",
		"- `DB_PATH_OR_NONE`: `mlflow.db`",
		"- `EXTRA_CONTEXT`: `Branch + cleanliness snapshot:\n- Branch: main\n- Working tree: dirty (expected)`",
		"",
		"Tasks:",
		"1. Ensure run path exists",
	].join("\n");
	const parsed = parseInterviewIntakeArgs(structured);
	assert(
		parsed.runId === "20260208-system4d-intake-workflow-extension-first-smoke-test",
		"parseInterviewIntakeArgs run_id mismatch",
	);
	assert(
		parsed.taskTitle === "system4d intake workflow + extension first smoke test",
		"parseInterviewIntakeArgs task_title mismatch",
	);
	assert(parsed.dbPathOrNone === "mlflow.db", "parseInterviewIntakeArgs db_path mismatch");
	includesAll(parsed.extraContext || "", ["Branch + cleanliness snapshot", "Working tree: dirty"], "parseInterviewIntakeArgs extra_context");

	// Multiple run-id detection
	const mentions = collectRunIdMentions([
		"RUN_ID one: 20260208-run-a",
		"nested handoff run: 20260208-run-b",
		"repeat run: 20260208-run-a",
	].join("\n"));
	assert(mentions.length === 2, `collectRunIdMentions expected 2 unique ids, got ${mentions.length}`);
	includesAll(mentions.join(","), ["20260208-run-a", "20260208-run-b"], "collectRunIdMentions values");

	// Date + slug stability
	assert(yyyymmdd(new Date("2026-02-08T09:10:11Z")) === "20260208", "yyyymmdd formatting mismatch");
	assert(slugify("MLflow Observability Next!!!") === "mlflow-observability-next", "slugify mismatch");

	// DB path extraction
	assert(
		extractDbPathFromText("tracking uri sqlite:///mlflow.db") === "mlflow.db",
		"extractDbPathFromText sqlite:///... failed",
	);
	assert(
		extractDbPathFromText("db path: ./data/app.sqlite3,") === "./data/app.sqlite3",
		"extractDbPathFromText relative path failed",
	);
	assert(extractDbPathFromText("no db mentioned here") === undefined, "extractDbPathFromText false positive");

	// Command quoting
	const command = formatCommand("interview-4d-intake", [
		"20260208-mlflow-observability",
		"Task \"Name\"",
		"none",
		"line1\nline2",
	]);
	includesAll(command, ["/interview-4d-intake", '"Task \\"Name\\""', '"line1\\nline2"'], "formatCommand");

	// Kickoff arg synthesis (complete)
	const state = newState({
		runId: "20260208-mlflow-observability",
		taskTitle: "mlflow observability",
		dbPathOrNone: "mlflow.db",
		originalPromptSnippet: "handoff from previous session",
	});
	const responsesComplete: InterviewResponseItem[] = [
		asResponse("compass_driver", "Reliability incident"),
		asResponse("compass_outcome", "Deterministic quiet defaults in CI"),
		asResponse("container_constraints", ["Backward compatibility", "No network dependency"]),
		asResponse("container_boundary_in", "DSPx explain and replay"),
		asResponse("container_boundary_out", "Upstream backend rewrites"),
		asResponse("container_edges", "MLflow callback seams"),
		asResponse("container_dependencies", "Upstream MLflow + DSPy maintainer alignment"),
		asResponse("success_criteria", "Kickoff packet review-ready"),
		asResponse("fog_assumptions", "MLflow auth already configured"),
		asResponse("fog_risks", "remote search latency"),
		asResponse("fog_debt", "temporary fallback mappings"),
	];

	const complete = buildKickoffArgs(state, responsesComplete);
	assert(complete.missing.length === 0, `expected no missing fields, got: ${complete.missing.join(", ")}`);
	assert(complete.warnings.length === 0, `expected no warnings, got: ${complete.warnings.join(", ")}`);
	assert(complete.args[0] === "20260208-mlflow-observability", "kickoff arg run_id mismatch");
	assert(complete.args[1] === "mlflow observability", "kickoff arg task_title mismatch");
	includesAll(complete.args[4], ["Backward compatibility", "No network dependency"], "constraints synthesis");
	includesAll(complete.args[5], ["in:", "out:"], "boundary synthesis");
	includesAll(complete.args[6], ["edges:", "dependencies:"], "edges/dependencies synthesis");
	includesAll(complete.args[9], ["handoff:", "assumptions:", "risks:", "debt:"], "extra context synthesis");

	// DB path precedence (explicit state path beats interview mismatch)
	const mismatch = buildKickoffArgs(state, [...responsesComplete, asResponse("db_path_confirmation", "Use ./generated/sixe.db")]);
	assert(mismatch.args[7] === "mlflow.db", "expected explicit state db path to win on mismatch");
	includesAll(mismatch.warnings.join(","), ["db_path_mismatch"], "db mismatch warning");

	// DB path fallback (state=none can resolve from interview response)
	const noneState = newState({
		runId: "20260208-db-fallback",
		taskTitle: "db fallback",
		dbPathOrNone: "none",
	});
	const resolvedFromInterview = buildKickoffArgs(noneState, [
		...responsesComplete,
		asResponse("db_path_confirmation", "Use ./generated/sixe.db"),
	]);
	assert(
		resolvedFromInterview.args[7] === "./generated/sixe.db",
		"expected interview db path to resolve when state db is none",
	);
	includesAll(
		resolvedFromInterview.warnings.join(","),
		["db_path_resolved_from_interview"],
		"db resolved warning",
	);

	// Kickoff arg synthesis (missing)
	const responsesMissing: InterviewResponseItem[] = [asResponse("compass_driver", "Delivery pressure")];
	const missing = buildKickoffArgs(state, responsesMissing);
	includesAll(
		missing.missing.join(","),
		["outcome", "constraints", "boundary", "edges_dependencies", "success_criteria"],
		"missing field detection",
	);

	// Recovery command
	const recovery = buildRecoveryCommand(state, "timeout");
	includesAll(recovery, ["/interview-4d-intake", "timeout"], "recovery command");

	// DB clarification command
	const dbClarify = buildDbClarifyCommand(state, "mlflow.db", "db-path-missing-pre-kickoff");
	includesAll(
		dbClarify,
		["/interview-4d-intake", "\"none\"", "db-path-missing-pre-kickoff", "mlflow.db"],
		"db clarify command",
	);

	console.log(
		JSON.stringify(
			{
				ok: true,
				tests: 14,
				module: "4d-intake-router",
			},
			null,
			2,
		),
	);
}

run();
