"""Behavioral contracts for Oracle.

Contracts define invariants that should hold true across executions.
They enable verification of behavioral properties like:
- No PII in outputs
- Deterministic responses for same inputs
- Output format compliance
- Response quality thresholds
"""

from __future__ import annotations

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

    Detects common patterns like emails, phone numbers, SSNs, API keys.
    """
    import time

    start = time.perf_counter()

    patterns = {
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "phone_us": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
        "phone_intl": r"\b\+?\d{1,4}[\s.-]?\d{1,14}\b",  # International format
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "credit_card": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
        "api_key": r"\b[A-Za-z0-9]{32,}\b",  # Common API key patterns
        "uuid": r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
    }

    violations = []
    output_text = embedding.output_text or ""

    for pattern_name, pattern in patterns.items():
        matches = re.findall(pattern, output_text)
        if matches:
            violations.append(
                ContractViolation(
                    contract_name="no-pii",
                    run_id=embedding.run_id,
                    severity=ContractSeverity.ERROR,
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
        return ContractResult(
            contract_name="no-pii",
            run_id=embedding.run_id,
            status=ContractStatus.FAIL,
            message=f"Found {len(violations)} PII violations",
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


def _evaluate_python_expr_contract(
    contract: Contract, embedding: "ExecutionEmbedding"
) -> ContractResult:
    """Evaluate a Python expression contract.

    The expression can reference: embedding, input_text, output_text.
    Should return True/False or raise an exception.
    """
    import time

    start = time.perf_counter()

    expr = contract.validator_config.get("expression", "True")

    try:
        # Safe-ish evaluation with limited namespace
        result = eval(
            expr,
            {"__builtins__": {}},
            {
                "embedding": embedding,
                "input_text": embedding.input_text,
                "output_text": embedding.output_text,
                "run_id": embedding.run_id,
                "provider": embedding.provider,
                "run_kind": embedding.run_kind,
            },
        )
        elapsed = (time.perf_counter() - start) * 1000

        if result:
            return ContractResult(
                contract_name=contract.name,
                run_id=embedding.run_id,
                status=ContractStatus.PASS,
                message="Expression evaluated to True",
                evaluation_time_ms=elapsed,
            )
        else:
            return ContractResult(
                contract_name=contract.name,
                run_id=embedding.run_id,
                status=ContractStatus.FAIL,
                message="Expression evaluated to False",
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
