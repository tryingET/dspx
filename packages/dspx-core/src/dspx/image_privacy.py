# summary: "Pre-Predict image privacy and strict source-issued formatting; never marker repair."
# read_when:
#   - "Changing observers, graph/annotation admission or the typed image formatting boundary."

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import importlib
import importlib.metadata
import inspect
import os
from pathlib import Path
import sys
import threading
from types import ModuleType
from typing import Any, Iterator

import dspy
from dspy.adapters.chat_adapter import ChatAdapter
from dspy.core.types import LMImagePart, LMMessage, LMRequest, LMTextPart
from dspy.clients.base_lm import GLOBAL_HISTORY

from .image_admission import ImageContractError, digest, require, sha
from .image_supervision import worker_identity
from .image_worker import require_clean_boundary

_ACTIVE: ContextVar[ImagePrivacy | None] = ContextVar(
    "dspx_image_privacy", default=None
)
_RUN_LOCK = threading.RLock()
_SETTINGS = importlib.import_module("dspy.dsp.utils.settings")
_DEFAULT_TRACE = _SETTINGS.main_thread_config.get("trace")


def _sdk_methods():
    return (
        dspy.Module.__call__,
        dspy.Module.__init__,
        dspy.Module.__getattribute__,
        dspy.Predict.__call__,
        dspy.Predict.__init__,
        dspy.Predict.forward,
        dspy.Predict._forward_preprocess,
        dspy.Predict._forward_postprocess,
        dspy.BaseLM.__call__,
        dspy.BaseLM.__init__,
        dspy.BaseLM._prepare_lm_call,
        dspy.BaseLM._finalize_lm_response,
        dspy.BaseLM.update_history,
        ChatAdapter.__call__,
        ChatAdapter.__init__,
        ChatAdapter.format,
        ChatAdapter.parse,
        ChatAdapter._call_preprocess,
        ChatAdapter._call_postprocess,
        ChatAdapter.format_system_message,
        ChatAdapter.format_user_message_content,
    )


_METHODS = _sdk_methods()
_METHOD_CODE = tuple(
    (fn, fn.__code__, getattr(fn, "__wrapped__", None)) for fn in _METHODS
)


def runtime_identity() -> str:
    require(importlib.metadata.version("dspy") == "3.3.1", "image_privacy")
    owners = [
        "dspy.core.types",
        "dspy.clients.base_lm",
        "dspy.utils.callback",
        "dspy.primitives.module",
        "dspy.predict.predict",
        "dspy.adapters.base",
        "dspy.adapters.chat_adapter",
        "dspy.dsp.utils.settings",
    ]
    members = {}
    for name in owners:
        origin = importlib.import_module(name).__file__
        if type(origin) is not str:
            raise ImageContractError("image_privacy") from None
        members[name] = sha(Path(origin).read_bytes())
    here = Path(__file__).parent
    for name in (
        "image_admission",
        "image_input_contract",
        "image_decoder",
        "image_source_io",
        "image_records",
        "image_supervision",
        "image_custody",
        "image_privacy",
        "image_effects",
        "image_source_profile",
        "image_execution",
        "image_artifacts",
        "image_record_validation",
        "provider_runtime",
        "run_receipts",
        "services/program_runtime_episode",
        "services/program_surfaces",
        "services/run_replay_service",
        "provider_contract",
        "dspy_typed_lm",
        "openai_compatible_provider",
    ):
        members["dspx." + name] = sha((here / (name + ".py")).read_bytes())
    members["python_executable"] = sha(Path(sys.executable).read_bytes())
    return digest("image-runtime-v1", members)


def _empty(value: object) -> bool:
    return (type(value) is list or type(value) is tuple) and len(value) == 0


def _observers(record: dict, *, entry: bool) -> None:
    for key in ("callbacks", "stream_listeners"):
        if key in record:
            require(_empty(record[key]), "image_privacy")
    for key in ("send_stream", "usage_tracker", "caller_predict"):
        require(record.get(key) is None, "image_privacy")
    require(record.get("track_usage", False) is False, "image_privacy")
    trace = record.get("trace")
    require(
        trace is None
        or (entry and trace is _DEFAULT_TRACE and type(trace) is list and not trace),
        "image_privacy",
    )
    callers = record.get("caller_modules")
    if entry:  # a base or outer adapter/LM may carry observers an override would mask
        require(
            (callers is None or _empty(callers))
            and record.get("adapter") is None
            and record.get("lm") is None,
            "image_privacy",
        )
    else:
        active = require_privacy()
        require(
            callers is None
            or (
                type(callers) is list
                and all(id(item) in active.modules for item in callers)
            ),
            "image_privacy",
        )


def _ambient() -> None:
    require(
        os.environ.get("MLFLOW_ENABLE") == "0"
        and sys.gettrace() is None
        and sys.getprofile() is None,
        "image_privacy",
    )
    require(not GLOBAL_HISTORY, "image_privacy")
    for fn, code, wrapped in _METHOD_CODE:
        require(
            fn.__code__ is code and getattr(fn, "__wrapped__", None) is wrapped,
            "image_privacy",
        )
    require(_sdk_methods() == _METHODS, "image_privacy")
    state = _sdk_state()
    require(
        len(state) == len(_SDK_STATE)
        and all(item is held for item, held in zip(state, _SDK_STATE, strict=True)),
        "image_privacy",
    )
    for name, module in tuple(sys.modules.items()):
        if name.startswith("mlflow") and type(module) is ModuleType:
            state = vars(module)
            for key in (
                "AUTOLOGGING_INTEGRATIONS",
                "_AUTOLOGGING_PATCHES",
                "_active_run_stack",
            ):
                if key in state:
                    value = state[key]
                    if type(value) is dict:
                        require(not value, "image_privacy")
                    elif key == "_active_run_stack":
                        require(
                            type(value).__module__.startswith("mlflow.")
                            and value.get() == [],
                            "image_privacy",
                        )
                    else:
                        require(False, "image_privacy")
    tracing = sys.modules.get("dspx.tracing")
    if type(tracing) is ModuleType:
        for key in ("_MLFLOW", "_mlflow", "_TRACING_ENABLED"):
            require(vars(tracing).get(key) in (None, False), "image_privacy")


class ImagePrivacy:
    def __init__(self) -> None:
        self.context: Any = None
        self.session: Any = None
        self.lm: Any = None
        self.modules: set[int] = set()
        self.predictors: dict[int, int] = {}
        self.root: Any = None
        self.root_types: tuple[type, ...] = ()
        self.profile: object | None = None
        self.formatter: Any = None

    def check(self) -> None:
        worker_identity()
        _ambient()
        _observers(_SETTINGS.main_thread_config, entry=True)
        _observers(dict(_SETTINGS.thread_local_overrides.get()), entry=False)
        require(
            type(self.formatter) is BoundedImageChatAdapter
            and not set(vars(self.formatter)) & set(_FORMATTER_BASELINE)
            and all(
                getattr(type(self.formatter), name) is fn and fn.__code__ is code
                for name, (fn, code) in _FORMATTER_BASELINE.items()
            )
            and self.formatter.use_json_adapter_fallback is False
            and self.formatter.use_native_function_calling is False
            and self.formatter.native_response_types == []
            and _empty(self.formatter.callbacks),
            "image_privacy",
        )
        require(
            dspy.settings.adapter is self.formatter
            and dspy.settings.disable_history is True
            and dspy.settings.max_history_size == 0
            and dspy.settings.max_trace_size == 0
            and dspy.settings.warn_on_type_mismatch is False
            and dspy.settings.provide_traceback is False,
            "image_privacy",
        )
        if self.lm is not None:
            require(
                self.lm.cache is False
                and _empty(self.lm.callbacks)
                and _empty(self.lm.history),
                "image_privacy",
            )
        if self.root is not None:
            self.bind_graph(self.root, profile=self.profile)

    def bind_graph(
        self,
        root: object,
        *,
        root_types: tuple[type, ...] = (),
        profile: object | None = None,
    ) -> None:
        from .image_source_profile import ImageSourceProfile

        if type(profile) is ImageSourceProfile:
            require(profile.owns(root), "image_privacy")
            root_types = (type(root),)
        else:
            require(
                not root_types and type(root) in (dspy.Predict, dspy.ChainOfThought),
                "image_privacy",
            )
        self.profile = profile
        require(
            type(root) in (dspy.Predict, dspy.ChainOfThought, *root_types),
            "image_privacy",
        )
        pending = [(root, 0)]
        visited = set()
        predictors = []
        modules = set()
        while pending:
            obj, depth = pending.pop()
            if id(obj) in visited:
                continue
            visited.add(id(obj))
            require(depth <= 16 and len(visited) <= 4096, "image_budget")
            if type(obj) in {
                str,
                int,
                float,
                bool,
                bytes,
                type(None),
            } or inspect.isclass(obj):
                continue
            if type(obj) is dict:
                pending.extend((item, depth + 1) for item in obj.values())
                continue
            if type(obj) is list or type(obj) is tuple:
                pending.extend((item, depth + 1) for item in obj)
                continue
            require(
                type(obj) in (dspy.Predict, dspy.ChainOfThought, *root_types),
                "image_privacy",
            )
            attrs = vars(obj)
            require(
                _empty(attrs.get("callbacks"))
                and _empty(attrs.get("history"))
                and attrs.get("_compiled", False) is False,
                "image_privacy",
            )
            modules.add(id(obj))
            if type(obj) is dspy.Predict:
                require(
                    all(_empty(attrs.get(key)) for key in ("demos", "train", "traces"))
                    and attrs.get("lm") is None
                    and attrs.get("config") == {},
                    "image_privacy",
                )
                predictors.append(obj)
                self.signature(obj.signature, None)
            pending.extend(
                (item, depth + 1)
                for key, item in attrs.items()
                if key not in {"signature", "stage"}
            )
        require(bool(predictors), "image_privacy")
        self.modules = modules
        self.predictors = {
            id(item.signature): index for index, item in enumerate(predictors)
        }
        self.root, self.root_types = root, root_types

    def signature(self, signature, inputs: dict | None) -> None:
        from .image_source_profile import check_signature

        check_signature(self.context, signature, inputs)


def require_privacy() -> ImagePrivacy:
    require_clean_boundary()
    value = _ACTIVE.get()
    if type(value) is not ImagePrivacy:
        raise ImageContractError("image_privacy") from None
    return value


@contextmanager
def image_privacy() -> Iterator[ImagePrivacy]:
    require_clean_boundary()
    worker_identity()
    require(_ACTIVE.get() is None, "image_privacy")
    _ambient()
    _observers(_SETTINGS.main_thread_config, entry=True)
    _observers(dict(_SETTINGS.thread_local_overrides.get()), entry=True)
    require(dspy.settings.adapter is None, "image_privacy")
    value = ImagePrivacy()
    with _RUN_LOCK:
        token = _ACTIVE.set(value)
        try:
            value.formatter = BoundedImageChatAdapter()
            with dspy.context(
                callbacks=[],
                disable_history=True,
                max_history_size=0,
                trace=None,
                max_trace_size=0,
                warn_on_type_mismatch=False,
                provide_traceback=False,
                send_stream=None,
                stream_listeners=[],
                track_usage=False,
                usage_tracker=None,
                adapter=value.formatter,
            ):
                value.check()
                yield value
                value.check()
        except BaseException as error:
            failed = True
            failure_code = (
                error.code if type(error) is ImageContractError else "image_privacy"
            )
        else:
            failed = False
        finally:
            value.context = value.session = value.lm = value.root = None
            _ACTIVE.reset(token)
    if failed:
        raise ImageContractError(failure_code) from None


class BoundedImageChatAdapter(ChatAdapter):
    def __init__(self) -> None:
        super().__init__(
            callbacks=[],
            use_native_function_calling=False,
            native_response_types=[],
            use_json_adapter_fallback=False,
        )
        self.native_response_types = []  # constructor [] actually selects upstream defaults
        require(self.native_response_types == [], "image_privacy")

    def __call__(self, lm, lm_kwargs, signature, demos, inputs):
        active = require_privacy()
        active.check()
        require(
            not demos
            and not lm_kwargs
            and id(signature) in active.predictors
            and lm is active.lm,
            "image_privacy",
        )
        active.signature(signature, inputs)
        require(active.session is not None, "image_custody")
        rows = active.session._scan()
        plan = active.session.record["request_plan"]
        require(
            len(rows) < len(plan)
            and plan[len(rows)]["predictor_slot"] == active.predictors[id(signature)],
            "image_admission_invalid",
        )
        try:
            return super().__call__(lm, lm_kwargs, signature, demos, inputs)
        except Exception as error:
            failure_code = (
                error.code
                if type(error) is ImageContractError
                else "image_finalization"
            )
        raise ImageContractError(failure_code) from None

    def format(self, signature, demos, inputs):
        active = require_privacy()
        active.check()
        require(not demos and active.context is not None, "image_privacy")
        active.signature(signature, inputs)
        system = self.format_system_message(signature)
        messages = [LMMessage(role="system", parts=[LMTextPart(text=system)])]
        # Per-field scan binds slots before concatenating the ordinary ChatAdapter layout.
        content = self.format_user_message_content(signature, inputs, main_request=True)
        parts = []
        for item in active.context.split(content):
            if type(item) is str:
                parts.append(LMTextPart(text=item))
            else:
                import base64

                parts.append(
                    LMImagePart(
                        media_type=item.media_type,
                        data=base64.b64encode(item.data).decode("ascii"),
                    )
                )
        messages.append(LMMessage(role="user", parts=parts))
        return messages

    def _render_request(self, lm, lm_kwargs, messages):
        require_privacy().check()
        require(
            not lm_kwargs and all(type(item) is LMMessage for item in messages),
            "image_privacy",
        )
        return LMRequest(model=lm.model, messages=messages)

    def _call_lm(self, lm, request):
        require_privacy().check()
        return lm(request=request)

    def parse(self, signature, completion):
        from .image_source_profile import parse_image_completion

        return parse_image_completion(signature, completion)

    async def acall(self, *args, **kwargs):
        raise ImageContractError("image_parallel_unsupported") from None


_FORMATTER_BASELINE = {
    name: (fn, fn.__code__)
    for name, fn in vars(BoundedImageChatAdapter).items()
    if callable(fn) and hasattr(fn, "__code__")
}
_PATH = (dspy.Predict, dspy.ChainOfThought, BoundedImageChatAdapter, dspy.BaseLM)
_SDK_CLASSES = tuple(dict.fromkeys(cls for root in _PATH for cls in root.__mro__))


def _sdk_state() -> list[object]:
    """Every class on the call path by identity: a later class-level wrap, override,
    attribute hook or code swap (e.g. ChainOfThought.__call__) differs from import."""
    return [
        part
        for owner in _SDK_CLASSES
        for name, value in vars(owner).items()
        for part in (
            name,
            value,
            getattr(value, "__code__", None),
            getattr(value, "__wrapped__", None),
        )
    ]


_SDK_STATE = _sdk_state()
