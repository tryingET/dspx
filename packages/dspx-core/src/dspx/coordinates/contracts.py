"""Behavioral contracts for Oracle.

Contracts define invariants that should hold true across executions.
They enable verification of behavioral properties like:
- No PII in outputs
- Deterministic responses for same inputs
- Output format compliance
- Response quality thresholds
"""

from __future__ import annotations

import ast
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .embeddings import ExecutionEmbedding
    from .storage import CoordinateIndex

logger = logging.getLogger(__name__)


class ContractSeverity(Enum):
    """Severity level for contract violations."""

    INFO = "info"  # Informational, no action needed
    WARNING = "warning"  # Should investigate
    ERROR = "error"  # Must fix
    CRITICAL = "critical"  # System-breaking


class ContractStatus(Enum):
    """Status of a contract check."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"  # Contract not applicable
    ERROR = "error"  # Error during evaluation


@dataclass
class ContractViolation:
    """A single contract violation."""

    contract_name: str
    run_id: str
    severity: ContractSeverity
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_name": self.contract_name,
            "run_id": self.run_id,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


@dataclass
class ContractResult:
    """Result of evaluating a contract against an execution."""

    contract_name: str
    run_id: str
    status: ContractStatus
    message: str
    violations: list[ContractViolation] = field(default_factory=list)
    evaluation_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_name": self.contract_name,
            "run_id": self.run_id,
            "status": self.status.value,
            "message": self.message,
            "violations": [v.to_dict() for v in self.violations],
            "evaluation_time_ms": round(self.evaluation_time_ms, 2),
        }


@dataclass
class Contract:
    """A behavioral contract definition.

    Contracts are rules that should hold true for all executions.
    They can be simple (regex patterns) or complex (custom validators).
    """

    name: str
    description: str
    invariant: str  # Human-readable invariant description
    severity: ContractSeverity = ContractSeverity.ERROR
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    # Validator configuration
    validator_type: str = "custom"  # "regex", "json_schema", "custom", "python_expr"
    validator_config: dict[str, Any] = field(default_factory=dict)
    # Metadata
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "invariant": self.invariant,
            "severity": self.severity.value,
            "enabled": self.enabled,
            "tags": self.tags,
            "validator_type": self.validator_type,
            "validator_config": self.validator_config,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Contract":
        return cls(
            name=data["name"],
            description=data["description"],
            invariant=data["invariant"],
            severity=ContractSeverity(data.get("severity", "error")),
            enabled=data.get("enabled", True),
            tags=data.get("tags", []),
            validator_type=data.get("validator_type", "custom"),
            validator_config=data.get("validator_config", {}),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
        )


# Built-in contract validators
def validate_no_pii(embedding: "ExecutionEmbedding") -> ContractResult:
    """Check for potential PII in output.

    Detects common patterns like emails, phone numbers, SSNs, credit cards.
    Note: UUIDs are NOT flagged as PII (they are anonymized identifiers).
    API keys are flagged as WARNING (not ERROR) due to high false positive rate.
    """
    import time

    start = time.perf_counter()

    # Patterns with severity levels
    # NOTE: UUID is intentionally NOT included - it's an anonymized identifier, not PII
    patterns = {
        # High-confidence PII patterns (ERROR severity)
        "email": (
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            ContractSeverity.ERROR,
        ),
        "phone_us": (r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", ContractSeverity.ERROR),
        "phone_intl": (
            r"\b\+?\d{1,4}[\s.-]?\d{1,14}\b",  # International format
            ContractSeverity.WARNING,  # Higher false positive rate
        ),
        "ssn": (r"\b\d{3}-\d{2}-\d{4}\b", ContractSeverity.ERROR),
        "credit_card": (
            r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
            ContractSeverity.ERROR,
        ),
        # Lower-confidence patterns (WARNING severity - may be false positives)
        # API keys often match hash digests, base64 content, etc.
        # Only flag keys with known prefixes (sk-, api-, token-, secret-)
        "potential_api_key": (
            r"\b(?:sk-[a-zA-Z0-9_-]*|api-[a-zA-Z0-9_-]*|key-[a-zA-Z0-9_-]*|token-[a-zA-Z0-9_-]*|secret-[a-zA-Z0-9_-]{8,})\b",
            ContractSeverity.WARNING,
        ),
    }

    violations = []
    output_text = embedding.output_text or ""

    for pattern_name, (pattern, severity) in patterns.items():
        matches = re.findall(pattern, output_text)
        if matches:
            violations.append(
                ContractViolation(
                    contract_name="no-pii",
                    run_id=embedding.run_id,
                    severity=severity,
                    message=f"Potential PII detected: {pattern_name}",
                    details={
                        "pattern_type": pattern_name,
                        "match_count": len(matches),
                        "samples": matches[:3],  # Show first 3 matches
                    },
                )
            )

    elapsed = (time.perf_counter() - start) * 1000

    if violations:
        # Only FAIL if there are ERROR-level violations
        has_error = any(v.severity == ContractSeverity.ERROR for v in violations)
        status = ContractStatus.FAIL if has_error else ContractStatus.PASS
        message = f"Found {len(violations)} potential PII patterns"
        if not has_error:
            message += " (all low-confidence matches)"

        return ContractResult(
            contract_name="no-pii",
            run_id=embedding.run_id,
            status=status,
            message=message,
            violations=violations,
            evaluation_time_ms=elapsed,
        )

    return ContractResult(
        contract_name="no-pii",
        run_id=embedding.run_id,
        status=ContractStatus.PASS,
        message="No PII detected",
        evaluation_time_ms=elapsed,
    )


def validate_output_format(
    embedding: "ExecutionEmbedding", *, format_type: str = "json"
) -> ContractResult:
    """Validate output format compliance.

    Args:
        embedding: Execution to validate
        format_type: Expected format ("json", "python", "markdown")
    """
    import time

    start = time.perf_counter()

    output_text = embedding.output_text or ""

    if format_type == "json":
        try:
            json.loads(output_text)
            status = ContractStatus.PASS
            message = "Valid JSON output"
        except json.JSONDecodeError as e:
            status = ContractStatus.FAIL
            message = f"Invalid JSON: {e}"
    elif format_type == "python":
        # Basic Python syntax check
        try:
            compile(output_text, "<string>", "exec")
            status = ContractStatus.PASS
            message = "Valid Python syntax"
        except SyntaxError as e:
            status = ContractStatus.FAIL
            message = f"Invalid Python: {e}"
    elif format_type == "markdown":
        # Check for basic markdown structure
        has_headers = bool(re.search(r"^#+\s", output_text, re.MULTILINE))
        has_content = len(output_text.strip()) > 0
        if has_headers or has_content:
            status = ContractStatus.PASS
            message = "Valid markdown content"
        else:
            status = ContractStatus.FAIL
            message = "Empty or invalid markdown"
    else:
        status = ContractStatus.SKIP
        message = f"Unknown format type: {format_type}"

    elapsed = (time.perf_counter() - start) * 1000

    return ContractResult(
        contract_name=f"output-format-{format_type}",
        run_id=embedding.run_id,
        status=status,
        message=message,
        evaluation_time_ms=elapsed,
    )


def validate_response_quality(
    embedding: "ExecutionEmbedding",
    *,
    min_length: int = 10,
    max_length: int = 100000,
    required_patterns: list[str] | None = None,
    forbidden_patterns: list[str] | None = None,
) -> ContractResult:
    """Validate response quality metrics.

    Args:
        embedding: Execution to validate
        min_length: Minimum output length
        max_length: Maximum output length
        required_patterns: Patterns that must be present
        forbidden_patterns: Patterns that must not be present
    """
    import time

    start = time.perf_counter()

    output_text = embedding.output_text or ""
    violations = []

    # Check length
    if len(output_text) < min_length:
        violations.append(
            ContractViolation(
                contract_name="response-quality",
                run_id=embedding.run_id,
                severity=ContractSeverity.WARNING,
                message=f"Output too short: {len(output_text)} < {min_length}",
                details={"actual_length": len(output_text), "min_length": min_length},
            )
        )

    if len(output_text) > max_length:
        violations.append(
            ContractViolation(
                contract_name="response-quality",
                run_id=embedding.run_id,
                severity=ContractSeverity.WARNING,
                message=f"Output too long: {len(output_text)} > {max_length}",
                details={"actual_length": len(output_text), "max_length": max_length},
            )
        )

    # Check required patterns
    if required_patterns:
        for pattern in required_patterns:
            if not re.search(pattern, output_text):
                violations.append(
                    ContractViolation(
                        contract_name="response-quality",
                        run_id=embedding.run_id,
                        severity=ContractSeverity.ERROR,
                        message=f"Missing required pattern: {pattern}",
                    )
                )

    # Check forbidden patterns
    if forbidden_patterns:
        for pattern in forbidden_patterns:
            if re.search(pattern, output_text):
                violations.append(
                    ContractViolation(
                        contract_name="response-quality",
                        run_id=embedding.run_id,
                        severity=ContractSeverity.ERROR,
                        message=f"Forbidden pattern found: {pattern}",
                    )
                )

    elapsed = (time.perf_counter() - start) * 1000

    if violations:
        return ContractResult(
            contract_name="response-quality",
            run_id=embedding.run_id,
            status=ContractStatus.FAIL,
            message=f"Quality check failed with {len(violations)} issues",
            violations=violations,
            evaluation_time_ms=elapsed,
        )

    return ContractResult(
        contract_name="response-quality",
        run_id=embedding.run_id,
        status=ContractStatus.PASS,
        message="Response quality OK",
        evaluation_time_ms=elapsed,
    )


# Validator registry
VALIDATORS: dict[str, Callable] = {
    "no-pii": validate_no_pii,
    "output-format-json": lambda e: validate_output_format(e, format_type="json"),
    "output-format-python": lambda e: validate_output_format(e, format_type="python"),
    "output-format-markdown": lambda e: validate_output_format(
        e, format_type="markdown"
    ),
    "response-quality": validate_response_quality,
}


def evaluate_contract(
    contract: Contract, embedding: "ExecutionEmbedding"
) -> ContractResult:
    """Evaluate a contract against an execution.

    Args:
        contract: Contract to evaluate
        embedding: Execution to check

    Returns:
        ContractResult with pass/fail status
    """
    if not contract.enabled:
        return ContractResult(
            contract_name=contract.name,
            run_id=embedding.run_id,
            status=ContractStatus.SKIP,
            message="Contract is disabled",
        )

    # Look up validator
    validator = VALIDATORS.get(contract.name)

    if validator is None:
        # Try to use validator_type and config
        if contract.validator_type == "regex":
            return _evaluate_regex_contract(contract, embedding)
        elif contract.validator_type == "json_schema":
            return _evaluate_json_schema_contract(contract, embedding)
        elif contract.validator_type == "python_expr":
            return _evaluate_python_expr_contract(contract, embedding)
        else:
            return ContractResult(
                contract_name=contract.name,
                run_id=embedding.run_id,
                status=ContractStatus.SKIP,
                message=f"No validator found for contract: {contract.name} (type: {contract.validator_type})",
            )

    try:
        # Apply config if any
        if contract.validator_config:
            # For response-quality, pass config params
            if contract.name == "response-quality":
                return validator(embedding, **contract.validator_config)
            elif contract.name.startswith("output-format-"):
                return validator(embedding, **contract.validator_config)

        return validator(embedding)
    except Exception as e:
        logger.error(f"Error evaluating contract {contract.name}: {e}")
        return ContractResult(
            contract_name=contract.name,
            run_id=embedding.run_id,
            status=ContractStatus.ERROR,
            message=f"Evaluation error: {e}",
        )


def _evaluate_regex_contract(
    contract: Contract, embedding: "ExecutionEmbedding"
) -> ContractResult:
    """Evaluate a regex-based contract."""
    import time

    start = time.perf_counter()

    config = contract.validator_config
    pattern = config.get("pattern", "")
    field_name = config.get("field", "output_text")
    should_match = config.get("should_match", True)

    text = getattr(embedding, field_name, "") or ""

    try:
        matches = bool(re.search(pattern, text))
        elapsed = (time.perf_counter() - start) * 1000

        if should_match:
            if matches:
                return ContractResult(
                    contract_name=contract.name,
                    run_id=embedding.run_id,
                    status=ContractStatus.PASS,
                    message="Pattern matched",
                    evaluation_time_ms=elapsed,
                )
            else:
                return ContractResult(
                    contract_name=contract.name,
                    run_id=embedding.run_id,
                    status=ContractStatus.FAIL,
                    message="Pattern not found",
                    evaluation_time_ms=elapsed,
                )
        else:
            if matches:
                return ContractResult(
                    contract_name=contract.name,
                    run_id=embedding.run_id,
                    status=ContractStatus.FAIL,
                    message="Unexpected pattern found",
                    evaluation_time_ms=elapsed,
                )
            else:
                return ContractResult(
                    contract_name=contract.name,
                    run_id=embedding.run_id,
                    status=ContractStatus.PASS,
                    message="Pattern correctly absent",
                    evaluation_time_ms=elapsed,
                )
    except re.error as e:
        elapsed = (time.perf_counter() - start) * 1000
        # Invalid pattern is a configuration error, not a runtime error
        return ContractResult(
            contract_name=contract.name,
            run_id=embedding.run_id,
            status=ContractStatus.FAIL,
            message=f"Invalid regex pattern configuration: {e}",
            evaluation_time_ms=elapsed,
        )


def _evaluate_json_schema_contract(
    contract: Contract, embedding: "ExecutionEmbedding"
) -> ContractResult:
    """Evaluate a JSON schema contract."""
    import time

    start = time.perf_counter()

    try:
        import jsonschema
    except ImportError:
        return ContractResult(
            contract_name=contract.name,
            run_id=embedding.run_id,
            status=ContractStatus.SKIP,
            message="jsonschema package not installed - contract skipped",
        )

    schema = contract.validator_config.get("schema", {})
    output_text = embedding.output_text or ""

    try:
        data = json.loads(output_text)
        jsonschema.validate(data, schema)
        elapsed = (time.perf_counter() - start) * 1000
        return ContractResult(
            contract_name=contract.name,
            run_id=embedding.run_id,
            status=ContractStatus.PASS,
            message="Output conforms to schema",
            evaluation_time_ms=elapsed,
        )
    except json.JSONDecodeError as e:
        elapsed = (time.perf_counter() - start) * 1000
        return ContractResult(
            contract_name=contract.name,
            run_id=embedding.run_id,
            status=ContractStatus.FAIL,
            message=f"Invalid JSON: {e}",
            evaluation_time_ms=elapsed,
        )
    except jsonschema.ValidationError as e:
        elapsed = (time.perf_counter() - start) * 1000
        return ContractResult(
            contract_name=contract.name,
            run_id=embedding.run_id,
            status=ContractStatus.FAIL,
            message=f"Schema validation failed: {e.message}",
            evaluation_time_ms=elapsed,
        )


@dataclass
class ContractRegistry:
    """Registry for managing contracts."""

    contracts: dict[str, Contract] = field(default_factory=dict)

    def add(self, contract: Contract) -> None:
        """Add a contract to the registry."""
        contract.updated_at = datetime.now(timezone.utc).isoformat()
        self.contracts[contract.name] = contract

    def remove(self, name: str) -> bool:
        """Remove a contract by name."""
        if name in self.contracts:
            del self.contracts[name]
            return True
        return False

    def get(self, name: str) -> Contract | None:
        """Get a contract by name."""
        return self.contracts.get(name)

    def list_all(self, *, enabled_only: bool = False) -> list[Contract]:
        """List all contracts."""
        contracts = list(self.contracts.values())
        if enabled_only:
            contracts = [c for c in contracts if c.enabled]
        return sorted(contracts, key=lambda c: c.name)

    def enable_by_tags(self, tags: list[str]) -> int:
        """Enable all contracts matching any of the given tags.

        Returns count of contracts enabled.
        """
        count = 0
        for contract in self.contracts.values():
            if any(t in contract.tags for t in tags) and not contract.enabled:
                contract.enabled = True
                contract.updated_at = datetime.now(timezone.utc).isoformat()
                count += 1
        return count

    def disable_by_tags(self, tags: list[str]) -> int:
        """Disable all contracts matching any of the given tags.

        Returns count of contracts disabled.
        """
        count = 0
        for contract in self.contracts.values():
            if any(t in contract.tags for t in tags) and contract.enabled:
                contract.enabled = False
                contract.updated_at = datetime.now(timezone.utc).isoformat()
                count += 1
        return count

    def get_by_tags(self, tags: list[str]) -> list[Contract]:
        """Get all contracts matching any of the given tags."""
        return [c for c in self.contracts.values() if any(t in c.tags for t in tags)]

    def verify_embedding(
        self, embedding: "ExecutionEmbedding", *, tags: list[str] | None = None
    ) -> list[ContractResult]:
        """Verify an embedding against all applicable contracts.

        Args:
            embedding: Execution to verify
            tags: Only check contracts with these tags (None = all)

        Returns:
            List of ContractResults
        """
        results = []

        for contract in self.contracts.values():
            # Filter by tags if specified
            if tags and not any(t in contract.tags for t in tags):
                continue

            result = evaluate_contract(contract, embedding)
            results.append(result)

        return results

    def verify_index(
        self,
        index: "CoordinateIndex",
        *,
        limit: int = 1000,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Verify all embeddings in an index.

        Args:
            index: CoordinateIndex to verify
            limit: Maximum embeddings to check
            tags: Only check contracts with these tags

        Returns:
            Summary dict with pass/fail counts and violations
        """
        embeddings = index.list_all(limit=limit)

        all_results: list[ContractResult] = []
        pass_count = 0
        fail_count = 0
        skip_count = 0
        error_count = 0
        all_violations: list[ContractViolation] = []

        for embedding in embeddings:
            results = self.verify_embedding(embedding, tags=tags)
            all_results.extend(results)

            for result in results:
                if result.status == ContractStatus.PASS:
                    pass_count += 1
                elif result.status == ContractStatus.FAIL:
                    fail_count += 1
                    all_violations.extend(result.violations)
                elif result.status == ContractStatus.SKIP:
                    skip_count += 1
                else:
                    error_count += 1

        return {
            "total_checks": len(all_results),
            "pass": pass_count,
            "fail": fail_count,
            "skip": skip_count,
            "error": error_count,
            "violations": [v.to_dict() for v in all_violations],
            "violations_by_severity": _count_by_severity(all_violations),
        }


@dataclass(frozen=True)
class _SafeEmbeddingView:
    """Narrow, read-only view exposed to contract expressions."""

    input_text: Any
    output_text: Any
    run_id: str
    provider: Any
    run_kind: Any


_SAFE_CALLABLES: dict[str, Callable[..., Any]] = {
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "min": min,
    "max": max,
    "abs": abs,
    "sum": sum,
    "any": any,
    "all": all,
    "sorted": sorted,
    "reversed": reversed,
    "enumerate": enumerate,
    "zip": zip,
    "range": range,
}

_ALLOWED_EMBEDDING_FIELDS = frozenset(
    {
        "input_text",
        "output_text",
        "run_id",
        "provider",
        "run_kind",
    }
)


def _build_safe_contract_namespace(
    embedding: "ExecutionEmbedding",
) -> dict[str, Any]:
    """Build the read-only namespace exposed to contract expressions."""
    safe_embedding = _SafeEmbeddingView(
        input_text=embedding.input_text,
        output_text=embedding.output_text,
        run_id=embedding.run_id,
        provider=embedding.provider,
        run_kind=embedding.run_kind,
    )
    return {
        "embedding": safe_embedding,
        "input_text": safe_embedding.input_text,
        "output_text": safe_embedding.output_text,
        "run_id": safe_embedding.run_id,
        "provider": safe_embedding.provider,
        "run_kind": safe_embedding.run_kind,
        **_SAFE_CALLABLES,
    }


def _evaluate_python_expr_contract(
    contract: Contract, embedding: "ExecutionEmbedding"
) -> ContractResult:
    """Evaluate a Python expression contract with a tiny AST interpreter.

    The expression can reference: embedding, input_text, output_text.
    Should return True/False or raise an exception.

    Expressions are parsed to AST, validated against a narrow allowlist, then
    interpreted directly without calling Python's eval().
    """
    import time

    start = time.perf_counter()

    expr = contract.validator_config.get("expression", "True")
    safe_namespace = _build_safe_contract_namespace(embedding)

    try:
        tree = ast.parse(expr, mode="eval")
        _validate_safe_ast(tree)
        result = _evaluate_safe_expression(tree.body, safe_namespace)

        elapsed = (time.perf_counter() - start) * 1000

        if result:
            return ContractResult(
                contract_name=contract.name,
                run_id=embedding.run_id,
                status=ContractStatus.PASS,
                message="Expression evaluated to True",
                evaluation_time_ms=elapsed,
            )
        return ContractResult(
            contract_name=contract.name,
            run_id=embedding.run_id,
            status=ContractStatus.FAIL,
            message="Expression evaluated to False",
            evaluation_time_ms=elapsed,
        )
    except SyntaxError as e:
        elapsed = (time.perf_counter() - start) * 1000
        return ContractResult(
            contract_name=contract.name,
            run_id=embedding.run_id,
            status=ContractStatus.ERROR,
            message=f"Expression syntax error: {e}",
            evaluation_time_ms=elapsed,
        )
    except ValueError as e:
        elapsed = (time.perf_counter() - start) * 1000
        return ContractResult(
            contract_name=contract.name,
            run_id=embedding.run_id,
            status=ContractStatus.ERROR,
            message=f"Unsafe expression: {e}",
            evaluation_time_ms=elapsed,
        )
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        return ContractResult(
            contract_name=contract.name,
            run_id=embedding.run_id,
            status=ContractStatus.ERROR,
            message=f"Expression evaluation error: {e}",
            evaluation_time_ms=elapsed,
        )


# Allowed AST node types for safe expression evaluation.
# Note: ast.Num, ast.Str, ast.Bytes, ast.NameConstant, ast.Ellipsis were
# deprecated in Python 3.8+ and replaced by ast.Constant. Removed for Python 3.13+.
# ast.Index was deprecated in Python 3.9 and removed - subscripts use the value directly.
_SAFE_AST_NODES = frozenset(
    [
        ast.Expression,
        ast.Constant,
        ast.Name,
        ast.Attribute,
        ast.Load,
        ast.Subscript,
        ast.Slice,
        ast.List,
        ast.Tuple,
        ast.Set,
        ast.Dict,
        ast.UnaryOp,
        ast.UAdd,
        ast.USub,
        ast.Not,
        ast.BinOp,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.BoolOp,
        ast.And,
        ast.Or,
        ast.Compare,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.Is,
        ast.IsNot,
        ast.In,
        ast.NotIn,
        ast.IfExp,
        ast.Call,
        ast.keyword,
    ]
)


def _evaluate_safe_expression(node: ast.AST, safe_namespace: dict[str, Any]) -> Any:
    """Interpret a validated expression AST without delegating to eval()."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in safe_namespace:
            raise ValueError(f"Unknown name '{node.id}'")
        return safe_namespace[node.id]
    if isinstance(node, ast.Attribute):
        base_value = _evaluate_safe_expression(node.value, safe_namespace)
        if not isinstance(base_value, _SafeEmbeddingView):
            raise ValueError("Only safe embedding fields are accessible")
        if node.attr not in _ALLOWED_EMBEDDING_FIELDS:
            raise ValueError(f"Access to embedding.{node.attr} is not allowed")
        return getattr(base_value, node.attr)
    if isinstance(node, ast.Subscript):
        value = _evaluate_safe_expression(node.value, safe_namespace)
        index = _evaluate_safe_expression(node.slice, safe_namespace)
        return value[index]
    if isinstance(node, ast.Slice):
        return slice(
            _evaluate_safe_expression(node.lower, safe_namespace)
            if node.lower is not None
            else None,
            _evaluate_safe_expression(node.upper, safe_namespace)
            if node.upper is not None
            else None,
            _evaluate_safe_expression(node.step, safe_namespace)
            if node.step is not None
            else None,
        )
    if isinstance(node, ast.List):
        return [
            _evaluate_safe_expression(element, safe_namespace) for element in node.elts
        ]
    if isinstance(node, ast.Tuple):
        return tuple(
            _evaluate_safe_expression(element, safe_namespace) for element in node.elts
        )
    if isinstance(node, ast.Set):
        return {
            _evaluate_safe_expression(element, safe_namespace) for element in node.elts
        }
    if isinstance(node, ast.Dict):
        result: dict[Any, Any] = {}
        for key_node, value_node in zip(node.keys, node.values, strict=True):
            if key_node is None:
                raise ValueError("Dict unpacking is not allowed")
            key = _evaluate_safe_expression(key_node, safe_namespace)
            value = _evaluate_safe_expression(value_node, safe_namespace)
            result[key] = value
        return result
    if isinstance(node, ast.UnaryOp):
        operand = _evaluate_safe_expression(node.operand, safe_namespace)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.Not):
            return not operand
        raise ValueError(f"Unary operator {type(node.op).__name__} is not allowed")
    if isinstance(node, ast.BinOp):
        left = _evaluate_safe_expression(node.left, safe_namespace)
        right = _evaluate_safe_expression(node.right, safe_namespace)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        if isinstance(node.op, ast.Mod):
            return left % right
        raise ValueError(f"Binary operator {type(node.op).__name__} is not allowed")
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result: Any = True
            for value in node.values:
                result = _evaluate_safe_expression(value, safe_namespace)
                if not result:
                    return result
            return result
        if isinstance(node.op, ast.Or):
            result: Any = False
            for value in node.values:
                result = _evaluate_safe_expression(value, safe_namespace)
                if result:
                    return result
            return result
        raise ValueError(f"Boolean operator {type(node.op).__name__} is not allowed")
    if isinstance(node, ast.Compare):
        left = _evaluate_safe_expression(node.left, safe_namespace)
        for operator, comparator in zip(node.ops, node.comparators, strict=True):
            right = _evaluate_safe_expression(comparator, safe_namespace)
            if isinstance(operator, ast.Eq):
                ok = left == right
            elif isinstance(operator, ast.NotEq):
                ok = left != right
            elif isinstance(operator, ast.Lt):
                ok = left < right
            elif isinstance(operator, ast.LtE):
                ok = left <= right
            elif isinstance(operator, ast.Gt):
                ok = left > right
            elif isinstance(operator, ast.GtE):
                ok = left >= right
            elif isinstance(operator, ast.Is):
                ok = left is right
            elif isinstance(operator, ast.IsNot):
                ok = left is not right
            elif isinstance(operator, ast.In):
                ok = left in right
            elif isinstance(operator, ast.NotIn):
                ok = left not in right
            else:
                raise ValueError(
                    f"Comparison operator {type(operator).__name__} is not allowed"
                )
            if not ok:
                return False
            left = right
        return True
    if isinstance(node, ast.IfExp):
        branch = (
            node.body
            if _evaluate_safe_expression(node.test, safe_namespace)
            else node.orelse
        )
        return _evaluate_safe_expression(branch, safe_namespace)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only direct calls to allowlisted helpers are allowed")
        func_name = node.func.id
        func = _SAFE_CALLABLES.get(func_name)
        if func is None:
            raise ValueError(f"Calls to '{func_name}' are not allowed")
        if any(keyword.arg is None for keyword in node.keywords):
            raise ValueError("Argument unpacking is not allowed")
        args = [_evaluate_safe_expression(arg, safe_namespace) for arg in node.args]
        kwargs = {
            keyword.arg: _evaluate_safe_expression(keyword.value, safe_namespace)
            for keyword in node.keywords
            if keyword.arg is not None
        }
        return func(*args, **kwargs)
    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def _validate_safe_ast(tree: ast.AST) -> None:
    """Validate that AST contains only safe node types.

    Raises ValueError if unsafe nodes (imports, function defs, etc.) are found.
    Also rejects method calls and arbitrary attribute traversal so expressions stay
    inside the narrow helper/field contract.
    """
    for node in ast.walk(tree):
        if type(node) not in _SAFE_AST_NODES:
            node_name = type(node).__name__
            unsafe_patterns = {
                "Import": "import statements",
                "ImportFrom": "from...import statements",
                "FunctionDef": "function definitions",
                "AsyncFunctionDef": "async function definitions",
                "ClassDef": "class definitions",
                "Lambda": "lambda expressions",
                "Yield": "yield expressions",
                "YieldFrom": "yield from expressions",
                "Await": "await expressions",
                "Global": "global statements",
                "Nonlocal": "nonlocal statements",
                "Exec": "exec statements",
                "Delete": "del statements",
                "Assign": "assignment statements",
                "AugAssign": "augmented assignment (+=, etc.)",
                "AnnAssign": "annotated assignment",
            }
            reason = unsafe_patterns.get(node_name, f"{node_name} nodes")
            raise ValueError(f"Expression contains forbidden {reason}")

        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                raise ValueError(
                    f"Access to dunder attributes ({node.attr}) is not allowed"
                )
            if not isinstance(node.value, ast.Name) or node.value.id != "embedding":
                raise ValueError("Only embedding.<field> attribute access is allowed")
            if node.attr not in _ALLOWED_EMBEDDING_FIELDS:
                raise ValueError(f"Access to embedding.{node.attr} is not allowed")

        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                raise ValueError("Method calls are not allowed in contract expressions")
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only direct calls to allowlisted helpers are allowed")
            if node.func.id not in _SAFE_CALLABLES:
                raise ValueError(f"Calls to '{node.func.id}' are not allowed")
            if any(keyword.arg is None for keyword in node.keywords):
                raise ValueError("Argument unpacking is not allowed")


def _count_by_severity(violations: list[ContractViolation]) -> dict[str, int]:
    """Count violations by severity level."""
    counts: dict[str, int] = {}
    for v in violations:
        key = v.severity.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def create_default_contracts() -> list[Contract]:
    """Create default behavioral contracts.

    These are standard contracts that are useful for most DSPx applications.
    """
    return [
        Contract(
            name="no-pii",
            description="Outputs should not contain PII (emails, phones, SSNs)",
            invariant="output_text does not contain email, phone, SSN, or credit card patterns",
            severity=ContractSeverity.ERROR,
            tags=["security", "privacy"],
        ),
        Contract(
            name="output-format-json",
            description="Outputs should be valid JSON",
            invariant="output_text is valid JSON",
            severity=ContractSeverity.WARNING,
            tags=["format"],
            enabled=False,  # Disabled by default, enable for JSON-expected runs
        ),
        Contract(
            name="response-quality",
            description="Responses should meet quality thresholds",
            invariant="output_text has reasonable length and no error patterns",
            severity=ContractSeverity.INFO,
            tags=["quality"],
            validator_config={
                "min_length": 1,
                "forbidden_patterns": [r"ERROR:", r"Exception:", r"Traceback"],
            },
        ),
    ]


def save_contracts(contracts: list[Contract], path: Path) -> None:
    """Save contracts to a JSON file."""
    data = [c.to_dict() for c in contracts]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_contracts(path: Path) -> list[Contract]:
    """Load contracts from a JSON file."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Contract.from_dict(d) for d in data]
