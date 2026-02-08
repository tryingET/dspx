import {
	buildKickoffArgs,
	buildRecoveryCommand,
	extractDbPathFromText,
	formatCommand,
	newState,
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
	assert(complete.args[0] === "20260208-mlflow-observability", "kickoff arg run_id mismatch");
	assert(complete.args[1] === "mlflow observability", "kickoff arg task_title mismatch");
	includesAll(complete.args[4], ["Backward compatibility", "No network dependency"], "constraints synthesis");
	includesAll(complete.args[5], ["in:", "out:"], "boundary synthesis");
	includesAll(complete.args[6], ["edges:", "dependencies:"], "edges/dependencies synthesis");
	includesAll(complete.args[9], ["handoff:", "assumptions:", "risks:", "debt:"], "extra context synthesis");

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

	console.log(
		JSON.stringify(
			{
				ok: true,
				tests: 9,
				module: "4d-intake-router",
			},
			null,
			2,
		),
	);
}

run();
