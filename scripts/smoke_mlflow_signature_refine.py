from __future__ import annotations

import os
from typing import Iterable


def _iter_artifact_paths(client, run_id: str) -> Iterable[str]:
    stack = list(client.list_artifacts(run_id))
    while stack:
        a = stack.pop()
        yield a.path
        if a.is_dir:
            stack.extend(client.list_artifacts(run_id, a.path))


def main() -> None:
    from mlflow.tracking import MlflowClient

    uri = os.environ["MLFLOW_TRACKING_URI"]
    exp_name = os.environ["MLFLOW_EXPERIMENT"]
    expected_outfile = os.environ.get("DSPX_EXPECT_OUTFILE", "refined_sig.py")
    expected_template_version = os.environ.get("DSPX_EXPECT_TEMPLATE_VERSION", "v1")

    client = MlflowClient(tracking_uri=uri)
    exp = client.get_experiment_by_name(exp_name)
    assert exp is not None, f"missing experiment: {exp_name}"

    runs = client.search_runs(
        [exp.experiment_id],
        order_by=["attributes.start_time DESC"],
        max_results=5,
    )
    assert runs, "no runs found"
    r = runs[0]

    assert (r.info.run_name or "") == "signature-refine", r.info.run_name
    assert r.data.tags.get("service") == "signature", r.data.tags.get("service")
    assert r.data.tags.get("template_version") == expected_template_version, (
        expected_template_version,
        r.data.tags.get("template_version"),
    )
    assert r.data.tags.get("signature.mode") == "refine", r.data.tags.get(
        "signature.mode"
    )

    paths = set(_iter_artifact_paths(client, r.info.run_id))
    assert any(p.endswith(".py") for p in paths), sorted(paths)
    assert expected_outfile in paths, (expected_outfile, sorted(paths))
    assert f"{expected_outfile}.meta.json" in paths, (
        f"{expected_outfile}.meta.json",
        sorted(paths),
    )

    print("ok")


if __name__ == "__main__":
    main()
