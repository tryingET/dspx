# rocs-cli

Minimal ROCS CLI for ai-society.

Commands:
- `rocs version`
- `rocs resolve --repo . [--profile <name>] [--resolve-refs]`
- `rocs summary --repo .`
- `rocs validate --repo . [--profile <name>] [--resolve-refs] [--strict-placeholders]`
- `rocs validate --repo . [--validate-deps]` (optional: enforce strict schema on ref layers too)
- `rocs validate --repo . --only path|ref --layer <name>`
- `rocs diff --repo . --baseline <gitlab:...@ref> [--profile <name>]`
- `rocs lint --repo . [--fail-on-warn]`
- `rocs check-inverses --repo . [--fix]`
- `rocs graph --repo . [--relation is_a] [--format excalidraw|json|dot] [--out <path>]`
- `rocs cache dir|ls|prune|clear`
- `rocs normalize --repo . [--apply]`
- `rocs pack <ont_id> --repo . [--profile <name>] [--resolve-refs]`
- `rocs build --repo . [--profile <name>] [--resolve-refs] [--clean]`

Scope (MVP):
- Validate ROCS repo structure + ontology front matter schema.
- Build local artifacts into `ontology/dist/` (offline-first; remote layers only when `--resolve-refs` is set).

Layer refs (optional):
- `--resolve-refs` enables fetching `<gitlab:<project_path>@<ref>>` layers into a local cache.
- If your env vars live in a dotenv file, pass `--env-file <path>` (no need to export).
- Cache location: `ROCS_CACHE_DIR` or `$XDG_CACHE_HOME/rocs` or `~/.cache/rocs`.
- GitLab config: `ROCS_GITLAB_BASE_URL` (or `GITLAB_BASE_URL`) and `ROCS_GITLAB_TOKEN` (or `PAT_GITLAB`).
- In GitLab CI: base url falls back to `CI_SERVER_URL`; auth can use `CI_JOB_TOKEN`.

Graph export:
- `rocs graph` writes an `.excalidraw.json` file by default (open it in Excalidraw).
- For `excalidraw-cli` (external): use `--format excalidraw-cli-json`, then run `excalidraw-cli create <file> -o graph.excalidraw`.

Tests:
- `uv run python -m unittest discover -s tests -p 'test_*.py' -q`

VHS recordings (documentation by recorded behavior):
- Install `vhs` (and its deps: `ttyd`, `ffmpeg`), then run: `core/rocs-cli/scripts/vhs-run.sh`
- Outputs land in `core/rocs-cli/artifacts/vhs/` (gitignored); share the `.gif` when reporting behavior regressions.
