# summary: "Defines Pydantic contracts for Forge work orders, issue specs, plans, and manifests."
# read_when:
#   - "Changing Forge artifact schemas, routing fields, requirements, or capability status models."

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class RedactionReport(BaseModel):
    detected: bool = False
    notes: List[str] = Field(default_factory=list)


class Intent(BaseModel):
    deliverable: Literal[
        "python_cli",
        "library",
        "server",
        "workflow",
        "optimizer",
        "integration",
        "eval_harness",
    ] = "python_cli"
    evidence_level: Literal["smoke", "unit", "golden", "eval", "perf"] = "smoke"
    risk_profile: Literal["safe_default", "power_user"] = "safe_default"
    offline_default: bool = True


class ProgramRef(BaseModel):
    id: str
    title: Optional[str] = None
    label: Optional[str] = None


class Routing(BaseModel):
    mode: Literal["auto", "suggest", "manual"] = "auto"
    strategy: Literal["single_primary", "primary_with_satellites", "multi_primary"] = (
        "single_primary"
    )
    primary_project: str = "core"
    secondary_projects: List[str] = Field(default_factory=list)
    reasoning: List[str] = Field(default_factory=list)
    program: Optional[ProgramRef] = None


class Constraint(BaseModel):
    id: str
    text: str


class Requirement(BaseModel):
    id: str
    text: str
    rationale: Optional[str] = None
    priority: Literal["must", "should", "could"] = "must"


class AcceptanceTest(BaseModel):
    id: str
    given: str
    when: str
    then: str


class ResourceRef(BaseModel):
    id: str
    kind: str
    ref: str


class Outputs(BaseModel):
    out_dir: str


class WorkOrder(BaseModel):
    schema_version: int = 0
    fingerprint: str
    id: str
    run_id: str
    title: str

    raw_input: str
    sanitized_input: str
    redaction_report: RedactionReport = Field(default_factory=RedactionReport)

    intent: Intent = Field(default_factory=Intent)
    routing: Routing = Field(default_factory=Routing)
    constraints: List[Constraint] = Field(default_factory=list)
    requirements: List[Requirement] = Field(default_factory=list)
    acceptance_tests: List[AcceptanceTest] = Field(default_factory=list)
    resources: List[ResourceRef] = Field(default_factory=list)
    outputs: Outputs


class WorkOrderDoc(BaseModel):
    work_order: WorkOrder


class IssueSpec(BaseModel):
    schema_version: int = 0
    local_id: str
    project_key: str
    title: str
    description_md: str
    labels: List[str] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)
    fingerprint: str


class IssueSpecDoc(BaseModel):
    issue_spec: IssueSpec


class CapabilityStatus(BaseModel):
    implemented: bool
    configured: bool
    permitted: bool


class PlanDoc(BaseModel):
    schema_version: int = 0
    workorder_id: str
    workorder_fingerprint: str
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    steps: List[Dict[str, Any]] = Field(default_factory=list)


class ManifestDoc(BaseModel):
    schema_version: int = 0
    workorder_id: str
    workorder_fingerprint: str
    created_at: str
    run_id: str
    gitlab: Dict[str, Any] = Field(default_factory=dict)
    issue_map: Dict[str, Any] = Field(default_factory=dict)
    decisions: Dict[str, Any] = Field(default_factory=dict)
