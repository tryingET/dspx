from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Tuple

# Internal DTO/provider base (optional)
try:
    from dspx.dtos import LMRequest, LMResponse, Message
    from dspx.lm_base import LMBase as InternalLMBase
    from dspx.capabilities import ProviderCapabilities
except Exception:  # pragma: no cover
    LMRequest = None  # type: ignore
    LMResponse = None  # type: ignore
    Message = None  # type: ignore

    class InternalLMBase:
        pass

    ProviderCapabilities = None  # type: ignore

# DSPy BaseLM (typing-friendly import pattern)
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # only for static typing
    from dspy import BaseLM as DSPyBaseLM
else:  # pragma: no cover
    try:
        from dspy import BaseLM as DSPyBaseLM
    except Exception:
        try:
            from dspy.models import BaseLM as DSPyBaseLM
        except Exception:

            class DSPyBaseLM:
                def __init__(
                    self, model: str = "multi", model_type: str = "text", **kwargs
                ) -> None:
                    self.model = model
                    self.model_type = model_type


@dataclass
class ProviderResult:
    name: str
    model: str | None
    text: str
    raw: Any
    started_at: float
    ended_at: float
    error: Optional[Exception] = None


@dataclass(frozen=True)
class ProviderCwdState:
    has_workspace: bool = False
    workspace: Optional[str] = None
    has_cwd: bool = False
    cwd: Optional[str] = None


@dataclass(frozen=True)
class ProviderPolicyState:
    has_dangerously_bypass: bool = False
    dangerously_bypass: Any = None
    has_auto_mode: bool = False
    auto_mode: Any = None
    has_permission_mode: bool = False
    permission_mode: Any = None
    has_allowed_tools: bool = False
    allowed_tools: Any = None
    has_disallowed_tools: bool = False
    disallowed_tools: Any = None
    has_append_system_prompt: bool = False
    append_system_prompt: Any = None


def _materialize_messages(
    messages: Optional[Iterable[Dict[str, Any]]],
) -> Optional[List[Dict[str, Any]]]:
    if messages is None:
        return None

    materialized: List[Dict[str, Any]] = []
    for message in messages:
        if isinstance(message, dict):
            materialized.append(dict(message))
            continue
        materialized.append(
            {
                "role": getattr(message, "role", None),
                "content": getattr(message, "content", None),
            }
        )
    return materialized


def _build_lm_request_messages(
    messages: Optional[Iterable[Dict[str, Any]]],
) -> Optional[List[Any]]:
    if Message is None or messages is None:
        return None

    typed_messages: List[Any] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError(f"unsupported message role for LMRequest: {role!r}")
        if not isinstance(content, str):
            raise ValueError("LMRequest messages require string content")
        typed_messages.append(Message(role=role, content=content))
    return typed_messages


def _extract_text_from_response(resp: Any) -> str:
    """Best-effort extraction from a DSPy BaseLM-like response object."""
    if resp is None:
        return ""
    try:
        # dict form
        if isinstance(resp, dict):
            ch = (resp.get("choices") or [None])[0]
            if isinstance(ch, dict):
                if "text" in ch:
                    return str(ch["text"]) or ""
                msg = ch.get("message")
                if isinstance(msg, dict) and "content" in msg:
                    return str(msg["content"]) or ""
        # object form
        chs = getattr(resp, "choices", None)
        if isinstance(chs, list) and chs:
            ch0 = chs[0]
            if isinstance(ch0, dict):
                if "text" in ch0:
                    return str(ch0["text"]) or ""
                msg = ch0.get("message")
                if isinstance(msg, dict) and "content" in msg:
                    return str(msg["content"]) or ""
            else:
                # attr-style
                t = getattr(ch0, "text", None)
                if t:
                    return str(t)
                msg = getattr(ch0, "message", None)
                if msg is not None:
                    c = getattr(msg, "content", None)
                    if c:
                        return str(c)
    except Exception:
        pass
    # fallback
    try:
        return str(resp)
    except Exception:
        return ""


def _combine_caps(providers: Sequence[Any]) -> ProviderCapabilities | None:
    """Combine capabilities from multiple providers.

    Aggregation rules:
    - supports_tools: any() — if any provider has tools, the aggregate can use them
    - code_exec: any() — if any provider can execute code, the aggregate can
    - json_mode: all() — ALL providers must support JSON for safe json_mode use
    - multi_turn: any() — if any provider supports history, aggregate can use it
    - structured_output_format: use most restrictive (prefer 'none' over 'json'/'xml')
    - supports_vision: any() — if any provider has vision, aggregate can use it
    - supports_audio: any() — if any provider has audio, aggregate can use it

    This ensures template adapter parse_mode auto-selection is safe when using
    MultiProviderLM with heterogeneous providers.
    """
    try:
        if ProviderCapabilities is None:
            return None

        # Handle empty provider list - return safe defaults
        if not providers:
            return ProviderCapabilities()

        supports_tools = any(
            getattr(getattr(p, "capabilities", None), "supports_tools", False)
            for p in providers
        )
        code_exec = any(
            getattr(getattr(p, "capabilities", None), "code_exec", False)
            for p in providers
        )
        # CRITICAL: Use all() for json_mode to avoid parse failures
        # when one provider doesn't support JSON output
        json_mode = all(
            getattr(getattr(p, "capabilities", None), "json_mode", False)
            for p in providers
        )
        multi_turn = any(
            getattr(getattr(p, "capabilities", None), "multi_turn", False)
            for p in providers
        )
        supports_vision = any(
            getattr(getattr(p, "capabilities", None), "supports_vision", False)
            for p in providers
        )
        supports_audio = any(
            getattr(getattr(p, "capabilities", None), "supports_audio", False)
            for p in providers
        )

        # Use most restrictive structured_output_format
        # Priority: none > xml > json (most restrictive first)
        formats = [
            getattr(
                getattr(p, "capabilities", None), "structured_output_format", "none"
            )
            for p in providers
        ]
        if "none" in formats:
            structured_format: Literal["json", "xml", "none"] = "none"
        elif "xml" in formats:
            structured_format = "xml"
        else:
            structured_format = "json"

        return ProviderCapabilities(
            supports_tools=supports_tools,
            code_exec=code_exec,
            json_mode=json_mode,
            multi_turn=multi_turn,
            structured_output_format=structured_format,
            supports_vision=supports_vision,
            supports_audio=supports_audio,
        )
    except Exception:
        return None


class MultiProviderLM(DSPyBaseLM):
    """Aggregate multiple BaseLM providers under one interface.

    Modes
    - strategy="sequential_first": call providers in order, return first success.
    - strategy="parallel_first": start all, return first finished (others continue running).
    - strategy="collect_concat": run all (sequential), join texts with a separator.
    - strategy="collect_longest": run all (sequential), pick the longest text.

    Notes
    - Parallel-first cannot cancel already-spawned external CLI processes; use with care.
    - If underlying providers may mutate the workspace (e.g., code-editing agents), avoid
      parallel strategies or isolate them via separate working directories.
    """

    def __init__(
        self,
        providers: Sequence[Any],
        *,
        names: Optional[Sequence[str]] = None,
        strategy: str = "sequential_first",
        concat_sep: str = "\n\n---\n\n",
        label: str = "multi",
        # Parallel coordination knobs
        parallel_isolated: bool = False,
        base_cwd: Optional[str] = None,
        isolation_mode: str = "mirror",  # mirror | git-worktree
        worktree_branch_prefix: str = "dspx-multi",
        worktree_commitish: str = "HEAD",
        cleanup_isolated: bool = True,
        validator: Optional[
            Any
        ] = None,  # callable: (text, provider, prompt, messages) -> bool
        abort_others_on_validate: bool = True,
        reducer: Optional[Any] = None,
        reduce_timeout_ms: Optional[int] = None,
        # Policy alignment knobs (best-effort propagation to providers)
        policy_bypass_permissions: Optional[bool] = None,
        policy_allowed_tools: Optional[Any] = None,
        policy_disallowed_tools: Optional[Any] = None,
        policy_append_system_prompt: Optional[str] = None,
    ) -> None:
        DSPyBaseLM.__init__(self, model=f"{label}/{strategy}", model_type="text")
        self.providers: List[Any] = list(providers)
        self.names: List[str] = (
            list(names)
            if names is not None
            else [
                getattr(p, "model", getattr(p, "__class__", type(p)).__name__)
                for p in providers
            ]
        )
        self.strategy = strategy
        self.concat_sep = concat_sep
        # store knobs
        self.parallel_isolated = parallel_isolated
        self.base_cwd = base_cwd
        self.validator = validator
        self.abort_others_on_validate = abort_others_on_validate
        self.reducer = reducer
        self.reduce_timeout_ms = reduce_timeout_ms
        self.policy_bypass_permissions = policy_bypass_permissions
        self.policy_allowed_tools = policy_allowed_tools
        self.policy_disallowed_tools = policy_disallowed_tools
        self.policy_append_system_prompt = policy_append_system_prompt
        self.isolation_mode = isolation_mode
        self.worktree_branch_prefix = worktree_branch_prefix
        self.worktree_commitish = worktree_commitish
        self.cleanup_isolated = cleanup_isolated
        self._async_cleanup_grace_s = 1.0
        self._async_cleanup_poll_s = 0.05
        self._async_cleanup_kill_wait_s = 0.2

        # capabilities
        caps = _combine_caps(self.providers)
        try:
            if hasattr(InternalLMBase, "__init__"):
                InternalLMBase.__init__(self, capabilities=caps)  # type: ignore
        except Exception:
            pass
        self._refresh_capabilities()
        # expose last results snapshot for observability
        self.last_results: List[ProviderResult] = []

    # DSPy entrypoint
    def forward(
        self,
        prompt: Optional[str] = None,
        messages: Optional[Iterable[Dict[str, Any]]] = None,
        **kwargs: Any,
    ):
        results = self._run_all(prompt=prompt, messages=messages)
        self.last_results = list(results)
        text = self._reduce_text(results)
        return _MinimalResponse(
            model=self.model,
            choices=[{"text": text}],
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )

    # Internal DTO entrypoint
    def generate(self, request: "LMRequest", **kwargs):
        if LMRequest is None or LMResponse is None:
            raise RuntimeError("Internal DTOs not available")
        if request is None:
            raise ValueError("LMRequest is required")

        prompt: Optional[str] = None
        messages: Optional[List[Dict[str, Any]]] = None
        if getattr(request, "prompt", None):
            prompt = request.prompt
        else:
            msgs = getattr(request, "messages", None)
            if msgs is not None:
                messages = [{"role": m.role, "content": m.content} for m in msgs]

        results = self._run_all(prompt=prompt, messages=messages)
        self.last_results = list(results)
        text = self._reduce_text(results)
        raw = {
            self.names[i] if i < len(self.names) else str(i): {
                "model": getattr(self.providers[i], "model", None),
                "text": r.text,
                "error": str(r.error) if r.error else None,
                "duration_s": r.ended_at - r.started_at,
            }
            for i, r in enumerate(results)
        }
        return LMResponse(outputs=[text], model=self.model, usage=None, raw=raw)

    # Execution helpers
    def _run_all(
        self, *, prompt: Optional[str], messages: Optional[Iterable[Dict[str, Any]]]
    ) -> List[ProviderResult]:
        materialized_messages = _materialize_messages(messages)
        self._refresh_capabilities()
        policy_states = self._apply_alignment_policies()
        try:
            strat = self.strategy
            if strat == "parallel_first":
                return self._run_parallel_first(
                    prompt=prompt,
                    messages=materialized_messages,
                )
            elif strat in {"collect_concat", "collect_longest"}:
                # sequential collection to avoid simultaneous side-effects
                outs: List[ProviderResult] = []
                for idx, p in enumerate(self.providers):
                    outs.append(
                        self._run_one(
                            idx,
                            p,
                            prompt=prompt,
                            messages=materialized_messages,
                        )
                    )
                return outs
            # default: sequential_first
            outs2: List[ProviderResult] = []
            for idx, p in enumerate(self.providers):
                res = self._run_one(
                    idx,
                    p,
                    prompt=prompt,
                    messages=materialized_messages,
                )
                outs2.append(res)
                if (res.error is None) and res.text.strip():
                    return [res]
            return outs2
        finally:
            self._restore_alignment_policies(policy_states)
            self._refresh_capabilities()

    def _run_one(
        self,
        idx: int,
        provider: Any,
        *,
        prompt: Optional[str],
        messages: Optional[Iterable[Dict[str, Any]]],
    ) -> ProviderResult:
        name = (
            self.names[idx]
            if idx < len(self.names)
            else getattr(provider, "model", f"prov{idx}")
        )
        t0 = time.time()
        try:
            if hasattr(provider, "forward"):
                resp = provider.forward(prompt=prompt, messages=messages)
                text = _extract_text_from_response(resp)
            elif LMRequest is not None and hasattr(provider, "generate"):
                req = LMRequest(
                    prompt=prompt,
                    messages=_build_lm_request_messages(messages),
                )
                r = provider.generate(req)
                text = (
                    (r.outputs or [""])[0] if r and getattr(r, "outputs", None) else ""
                )
            else:
                raise RuntimeError("Provider lacks forward/generate")
            t1 = time.time()
            return ProviderResult(
                name=name,
                model=getattr(provider, "model", None),
                text=text or "",
                raw=(r if "r" in locals() else (resp if "resp" in locals() else None)),
                started_at=t0,
                ended_at=t1,
            )
        except Exception as e:
            t1 = time.time()
            return ProviderResult(
                name=name,
                model=getattr(provider, "model", None),
                text="",
                raw=None,
                started_at=t0,
                ended_at=t1,
                error=e,
            )

    def _run_parallel_first(
        self, *, prompt: Optional[str], messages: Optional[Iterable[Dict[str, Any]]]
    ) -> List[ProviderResult]:
        # Prefer async-capable providers (our wrappers) to allow termination,
        # but still race sync-only providers in background threads so mixed stacks
        # preserve true first-completion semantics.
        async_runs: List[Optional[Any]] = [None] * len(self.providers)
        finished: List[Optional[ProviderResult]] = [None] * len(self.providers)
        completion_order: List[ProviderResult] = []
        sync_results: queue.Queue[tuple[int, ProviderResult]] = queue.Queue()
        sync_threads: List[threading.Thread] = []
        pending_sync: set[int] = set()

        # Prepare per-provider working dirs if isolated
        prev_cwds: List[ProviderCwdState] = [ProviderCwdState()] * len(self.providers)
        prepared_cwds: List[Optional[str]] = [None] * len(self.providers)
        cleanup_info: Optional[Dict[str, Any]] = None
        if self.parallel_isolated and self.base_cwd:
            prepared_cwds, cleanup_info = self._prepare_isolated_cwds(
                len(self.providers)
            )

        def _terminate_pending_async(*, skip: Optional[int] = None) -> None:
            for j, run in enumerate(async_runs):
                if j == skip or run is None:
                    continue
                provj = self.providers[j]
                try:
                    if hasattr(provj, "terminate"):
                        provj.terminate(run)
                except Exception:
                    pass

        def _handle_finished(
            i: int, result: ProviderResult
        ) -> Optional[ProviderResult]:
            finished[i] = result
            completion_order.append(result)
            if self.validator is not None and result.error is None:
                try:
                    ok = bool(
                        self.validator(
                            result.text,
                            provider=self.names[i],
                            prompt=prompt,
                            messages=messages,
                        )
                    )
                except Exception:
                    ok = False
                if ok and self.abort_others_on_validate:
                    _terminate_pending_async(skip=i)
                    return result
            if self.validator is None and self.reducer is None:
                _terminate_pending_async(skip=i)
                return result
            return None

        def _start_sync_worker(i: int, prov: Any) -> None:
            pending_sync.add(i)

            def worker() -> None:
                res = self._run_one(i, prov, prompt=prompt, messages=messages)
                sync_results.put((i, res))

            th = threading.Thread(target=worker, daemon=True)
            sync_threads.append(th)
            th.start()

        # Start all providers under their temporary cwd/workspace settings.
        for i, prov in enumerate(self.providers):
            cwd_override = (
                prepared_cwds[i]
                if (self.parallel_isolated and self.base_cwd)
                else self.base_cwdsafe()
            )
            prev_cwds[i] = self._apply_cwd(prov, cwd_override)
            if hasattr(prov, "start"):
                try:
                    async_runs[i] = prov.start(prompt=prompt, messages=messages)
                    continue
                except Exception:
                    pass
            _start_sync_worker(i, prov)

        remaining_async = set(i for i, run in enumerate(async_runs) if run is not None)

        try:
            while remaining_async or pending_sync:
                made_progress = False

                while True:
                    try:
                        i, res = sync_results.get_nowait()
                    except queue.Empty:
                        break
                    if i not in pending_sync:
                        continue
                    pending_sync.remove(i)
                    made_progress = True
                    selected = _handle_finished(i, res)
                    if selected is not None:
                        return [selected]

                for i in list(remaining_async):
                    run = async_runs[i]
                    if run is None:
                        remaining_async.remove(i)
                        continue
                    popen = getattr(run, "popen", None)
                    if popen is None:
                        remaining_async.remove(i)
                        continue
                    if popen.poll() is None:
                        continue

                    prov = self.providers[i]
                    try:
                        if hasattr(prov, "collect"):
                            cres = prov.collect(run)
                            text = getattr(cres, "text", "")
                            t1 = getattr(cres, "ended_at", time.time())
                            t0 = getattr(cres, "started_at", t1)
                            res = ProviderResult(
                                name=self.names[i],
                                model=getattr(prov, "model", None),
                                text=text,
                                raw=cres,
                                started_at=t0,
                                ended_at=t1,
                            )
                        else:
                            res = ProviderResult(
                                name=self.names[i],
                                model=getattr(prov, "model", None),
                                text="",
                                raw=None,
                                started_at=time.time(),
                                ended_at=time.time(),
                            )
                    except Exception as e:
                        res = ProviderResult(
                            name=self.names[i],
                            model=getattr(prov, "model", None),
                            text="",
                            raw=None,
                            started_at=time.time(),
                            ended_at=time.time(),
                            error=e,
                        )
                    remaining_async.remove(i)
                    made_progress = True
                    selected = _handle_finished(i, res)
                    if selected is not None:
                        return [selected]

                if not made_progress:
                    time.sleep(0.05)
        finally:
            for j, pr in enumerate(self.providers):
                self._restore_cwd(pr, prev_cwds[j])
            if cleanup_info and self.cleanup_isolated:
                self._schedule_isolated_cleanup(
                    cleanup_info,
                    sync_threads=tuple(sync_threads),
                    async_runs=tuple(run for run in async_runs if run is not None),
                )

        candidates = completion_order
        if not candidates:
            return []
        if self.reducer is not None:
            try:
                ctx = {
                    "prompt": prompt,
                    "messages": messages,
                    "strategy": self.strategy,
                }
                picked = self.reducer.pick(candidates, ctx)
                idx = getattr(picked, "winner_index", 0)
                if isinstance(idx, int) and 0 <= idx < len(candidates):
                    return [candidates[idx]]
            except Exception:
                pass
        return [candidates[0]]

    def _refresh_capabilities(self) -> None:
        try:
            setattr(self, "capabilities", _combine_caps(self.providers))
        except Exception:
            pass

    def _capture_policy_state(self, provider: Any) -> ProviderPolicyState:
        return ProviderPolicyState(
            has_dangerously_bypass=hasattr(provider, "dangerously_bypass"),
            dangerously_bypass=getattr(provider, "dangerously_bypass", None),
            has_auto_mode=hasattr(provider, "auto_mode"),
            auto_mode=getattr(provider, "auto_mode", None),
            has_permission_mode=hasattr(provider, "permission_mode"),
            permission_mode=getattr(provider, "permission_mode", None),
            has_allowed_tools=hasattr(provider, "allowed_tools"),
            allowed_tools=getattr(provider, "allowed_tools", None),
            has_disallowed_tools=hasattr(provider, "disallowed_tools"),
            disallowed_tools=getattr(provider, "disallowed_tools", None),
            has_append_system_prompt=hasattr(provider, "append_system_prompt"),
            append_system_prompt=getattr(provider, "append_system_prompt", None),
        )

    def _apply_alignment_policies(self) -> List[ProviderPolicyState]:
        states: List[ProviderPolicyState] = []
        for provider in self.providers:
            states.append(self._capture_policy_state(provider))
            try:
                if self.policy_bypass_permissions is True:
                    if hasattr(provider, "dangerously_bypass"):
                        try:
                            setattr(provider, "dangerously_bypass", True)
                            if hasattr(provider, "auto_mode"):
                                setattr(provider, "auto_mode", False)
                        except Exception:
                            pass
                    if hasattr(provider, "permission_mode"):
                        try:
                            if getattr(provider, "permission_mode", None) in (None, ""):
                                setattr(provider, "permission_mode", "acceptEdits")
                        except Exception:
                            pass
                if self.policy_allowed_tools is not None and hasattr(
                    provider, "allowed_tools"
                ):
                    try:
                        setattr(provider, "allowed_tools", self.policy_allowed_tools)
                    except Exception:
                        pass
                if self.policy_disallowed_tools is not None and hasattr(
                    provider, "disallowed_tools"
                ):
                    try:
                        setattr(
                            provider,
                            "disallowed_tools",
                            self.policy_disallowed_tools,
                        )
                    except Exception:
                        pass
                if self.policy_append_system_prompt is not None and hasattr(
                    provider, "append_system_prompt"
                ):
                    try:
                        setattr(
                            provider,
                            "append_system_prompt",
                            self.policy_append_system_prompt,
                        )
                    except Exception:
                        pass
            except Exception:
                continue
        return states

    def _restore_alignment_policies(
        self, states: Sequence[ProviderPolicyState]
    ) -> None:
        for provider, state in zip(self.providers, states):
            try:
                if state.has_dangerously_bypass:
                    setattr(provider, "dangerously_bypass", state.dangerously_bypass)
            except Exception:
                pass
            try:
                if state.has_auto_mode:
                    setattr(provider, "auto_mode", state.auto_mode)
            except Exception:
                pass
            try:
                if state.has_permission_mode:
                    setattr(provider, "permission_mode", state.permission_mode)
            except Exception:
                pass
            try:
                if state.has_allowed_tools:
                    setattr(provider, "allowed_tools", state.allowed_tools)
            except Exception:
                pass
            try:
                if state.has_disallowed_tools:
                    setattr(provider, "disallowed_tools", state.disallowed_tools)
            except Exception:
                pass
            try:
                if state.has_append_system_prompt:
                    setattr(
                        provider,
                        "append_system_prompt",
                        state.append_system_prompt,
                    )
            except Exception:
                pass

    def _apply_cwd(self, provider: Any, cwd: Optional[str]) -> ProviderCwdState:
        state = ProviderCwdState(
            has_workspace=hasattr(provider, "workspace"),
            workspace=getattr(provider, "workspace", None)
            if hasattr(provider, "workspace")
            else None,
            has_cwd=hasattr(provider, "cwd"),
            cwd=getattr(provider, "cwd", None) if hasattr(provider, "cwd") else None,
        )
        if cwd is None:
            return state
        # Save and override provider-specific cwd/workspace knobs
        if state.has_workspace:
            try:
                setattr(provider, "workspace", cwd)
            except Exception:
                pass
        if state.has_cwd:
            try:
                setattr(provider, "cwd", cwd)
            except Exception:
                pass
        return state

    def _restore_cwd(self, provider: Any, prev: ProviderCwdState) -> None:
        try:
            if prev.has_workspace:
                setattr(provider, "workspace", prev.workspace)
        except Exception:
            pass
        try:
            if prev.has_cwd:
                setattr(provider, "cwd", prev.cwd)
        except Exception:
            pass

    def base_cwdsafe(self) -> Optional[str]:
        return self.base_cwd

    def _repo_has_dirty_worktree(self, repo_root: str) -> bool:
        import subprocess

        try:
            cp = subprocess.run(
                [
                    "git",
                    "-C",
                    repo_root,
                    "status",
                    "--porcelain",
                    "--untracked-files=all",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            return True
        if cp.returncode != 0:
            return True
        return bool(cp.stdout.strip())

    # Isolation helpers
    def _prepare_isolated_cwds(
        self, n: int
    ) -> Tuple[List[Optional[str]], Dict[str, Any]]:
        mode = (self.isolation_mode or "mirror").lower()
        if mode == "git-worktree":
            return self._prepare_worktrees(n)
        # default: mirror copy
        return self._prepare_mirror_isolated_cwds(n)

    def _prepare_mirror_isolated_cwds(
        self, n: int
    ) -> Tuple[List[Optional[str]], Dict[str, Any]]:
        import tempfile
        import shutil
        import os as _os

        prepared: List[Optional[str]] = [None] * n
        roots: List[str] = []
        for i in range(n):
            try:
                tmpdir = tempfile.mkdtemp(prefix=f"dspx_multi_{i}_")

                # Ignore heavy dirs
                def _ig(dir, files):
                    ignore = {
                        ".git",
                        "__pycache__",
                        ".venv",
                        "venv",
                        ".mypy_cache",
                        ".pytest_cache",
                    }
                    return [f for f in files if f in ignore]

                # mypy: base_cwd is Optional; guard at runtime for safety
                assert self.base_cwd is not None
                shutil.copytree(
                    self.base_cwd,
                    _os.path.join(tmpdir, "proj"),
                    dirs_exist_ok=True,
                    ignore=_ig,
                )
                path = _os.path.join(tmpdir, "proj")
                prepared[i] = path
                roots.append(tmpdir)
            except Exception:
                prepared[i] = self.base_cwd
        return prepared, {"mode": "mirror", "roots": roots}

    def _prepare_worktrees(self, n: int) -> Tuple[List[Optional[str]], Dict[str, Any]]:
        import tempfile
        import subprocess
        import os as _os
        import shutil

        # Ensure base_cwd is inside a git repo
        try:
            base_cwd_str: str = self.base_cwd or "."
            cp = subprocess.run(
                ["git", "-C", base_cwd_str, "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=False,
            )
            if cp.returncode != 0:
                # fallback to mirror
                return self._prepare_mirror_isolated_cwds(n)
            repo_root = cp.stdout.strip()
        except Exception:
            return self._prepare_mirror_isolated_cwds(n)

        if self._repo_has_dirty_worktree(repo_root):
            return self._prepare_mirror_isolated_cwds(n)

        worktrees: List[Optional[str]] = [None] * n
        tmp_roots: List[str] = []
        created_paths: List[str] = []
        commitish = self.worktree_commitish or "HEAD"
        for i in range(n):
            tmpdir = tempfile.mkdtemp(prefix=f"dspx_wt_{i}_")
            wt_path = _os.path.join(tmpdir, "wt")
            # Create a detached worktree at commitish to avoid branch conflicts
            cmd = [
                "git",
                "-C",
                repo_root,
                "worktree",
                "add",
                "--detach",
                wt_path,
                commitish,
            ]
            cp = subprocess.run(cmd, capture_output=True, text=True)
            if cp.returncode == 0 and _os.path.isdir(wt_path):
                worktrees[i] = wt_path
                tmp_roots.append(tmpdir)
                created_paths.append(wt_path)
            else:
                # If worktree fails, fallback to mirror for this slot
                try:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception:
                    pass
                # Use mirror fallback for this index only
                mir, info = self._prepare_mirror_isolated_cwds(1)
                worktrees[i] = mir[0]
                if info.get("mode") == "mirror":
                    tmp_roots.extend(info.get("roots", []))
        return worktrees, {
            "mode": "git-worktree",
            "repo_root": repo_root,
            "tmp_roots": tmp_roots,
            "paths": created_paths,
        }

    def _cleanup_isolated(self, info: Dict[str, Any]) -> None:
        mode = (info.get("mode") or "").lower()
        if mode == "mirror":
            for root in info.get("roots", []) or []:
                try:
                    import shutil

                    shutil.rmtree(root, ignore_errors=True)
                except Exception:
                    pass
        elif mode == "git-worktree":
            import subprocess
            import shutil

            repo_root_str: str = str(info.get("repo_root") or ".")
            for p in info.get("paths", []) or []:
                try:
                    subprocess.run(
                        [
                            "git",
                            "-C",
                            repo_root_str,
                            "worktree",
                            "remove",
                            "--force",
                            p,
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                except Exception:
                    pass
            for tmp in info.get("tmp_roots", []) or []:
                try:
                    shutil.rmtree(tmp, ignore_errors=True)
                except Exception:
                    pass

    def _schedule_isolated_cleanup(
        self,
        info: Dict[str, Any],
        *,
        sync_threads: Sequence[threading.Thread],
        async_runs: Sequence[Any],
    ) -> None:
        pending_sync = [th for th in sync_threads if th.is_alive()]
        pending_async = []
        for run in async_runs:
            popen = getattr(run, "popen", None)
            if popen is None:
                continue
            try:
                if popen.poll() is None:
                    pending_async.append(popen)
            except Exception:
                continue

        if not pending_sync and not pending_async:
            self._cleanup_isolated(info)
            return

        def _popen_is_alive(popen: Any) -> bool:
            try:
                return popen.poll() is None
            except Exception:
                return False

        def _force_kill_popen(popen: Any) -> None:
            pid = getattr(popen, "pid", None)
            if pid is not None:
                try:
                    import os
                    import signal

                    os.killpg(pid, signal.SIGKILL)
                except Exception:
                    pass
            for method_name in ("terminate", "kill"):
                try:
                    method = getattr(popen, method_name)
                except Exception:
                    method = None
                if callable(method):
                    try:
                        method()
                    except Exception:
                        pass
            try:
                wait = getattr(popen, "wait")
            except Exception:
                wait = None
            if callable(wait):
                try:
                    wait(timeout=self._async_cleanup_kill_wait_s)
                except Exception:
                    pass

        def _cleanup_when_safe() -> None:
            for th in sync_threads:
                try:
                    th.join()
                except Exception:
                    pass

            if pending_async:
                deadline = time.time() + max(0.0, self._async_cleanup_grace_s)
                alive = [popen for popen in pending_async if _popen_is_alive(popen)]
                while alive and time.time() < deadline:
                    time.sleep(self._async_cleanup_poll_s)
                    alive = [popen for popen in alive if _popen_is_alive(popen)]
                for popen in alive:
                    _force_kill_popen(popen)
                kill_deadline = time.time() + max(
                    self._async_cleanup_kill_wait_s,
                    self._async_cleanup_poll_s,
                )
                while alive and time.time() < kill_deadline:
                    time.sleep(self._async_cleanup_poll_s)
                    alive = [popen for popen in alive if _popen_is_alive(popen)]

            self._cleanup_isolated(info)

        reaper = threading.Thread(target=_cleanup_when_safe, daemon=True)
        reaper.start()

    def _reduce_text(self, results: List[ProviderResult]) -> str:
        if not results:
            return ""
        strat = self.strategy
        # If we got a single result (sequential_first or parallel_first), return it
        if len(results) == 1:
            return results[0].text
        if strat == "collect_concat":
            parts = []
            for r in results:
                label = r.name or (r.model or "provider")
                parts.append(f"[{label}]\n{r.text.strip()}")
            return self.concat_sep.join(parts).strip()
        if strat == "collect_longest":
            best = max(results, key=lambda r: len(r.text or ""))
            return best.text
        # default fallback
        return results[0].text


class _MinimalResponse:
    def __init__(
        self, model: str, choices: List[Dict[str, Any]], usage: Dict[str, Any]
    ):
        self.model = model
        self.choices = choices
        self.usage = usage
