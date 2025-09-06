DSPx Architecture Overview
==========================

This document gives multiple “views” of the system to help contributors and users quickly build a mental model. These diagrams complement docs/VISION.md (principles, roadmap).

1) Architecture Layers (Unified)
--------------------------------

```mermaid
graph TD
  subgraph RootCLI
    DSPX["dspx (root CLI)"]
  end

  subgraph Services
    SigSvc["SignatureService"]
    RefineSvc["RefineService"]
    CodegenSvc["CodegenService"]
    MermaidSvc["MermaidWorkflowService"]
    AgentSvc["AgentService"]
  end

  subgraph Core
    Config["Config Loader"]
    Tracing["Tracing"]
    ProviderReg["ProviderRegistry"]
    ToolReg["ToolRegistry"]
    LMBase["LMBase (interface)"]
    DTOs["DTOs (Requests/Results)"]
  end

  subgraph Providers
    Codex["CodexExecLM"]
    Claude["ClaudeHeadlessLM"]
    Gemini["GeminiCLILM"]
    Multi["MultiProviderLM"]
  end

  subgraph Tools
    ToolA["retrieve_stub"]
    ToolB["python_exec_stub"]
  end

  subgraph External
    CodexCLI["codex CLI"]
    ClaudeCLI["claude CLI"]
    GeminiCLI["gemini CLI"]
    DSPy["DSPy"]
    MLflow["MLflow"]
  end

  subgraph Artifacts
    Gen["generated/*.py"]
  end

  DSPX --> Config
  Config --> Tracing
  Config --> ProviderReg
  Services --> DTOs
  Services --> DSPy
  AgentSvc --> ToolReg
  MermaidSvc --> Gen
  SigSvc --> Gen
  RefineSvc --> Gen
  CodegenSvc --> Gen

  DSPy --> ProviderReg
  ProviderReg --> LMBase
  LMBase --> Codex
  LMBase --> Claude
  LMBase --> Gemini
  LMBase --> Multi
  Multi --> Codex
  Multi --> Claude
  Multi --> Gemini

  ToolReg -.-> ToolA
  ToolReg -.-> ToolB

  Codex --> CodexCLI
  Claude --> ClaudeCLI
  Gemini --> GeminiCLI

  Tracing --> MLflow
```
2) Unified CLI Map
------------------

```mermaid
graph LR
  DSPX["dspx"] --> Sig["signature"]
  Sig --> SigGen["gen"]
  Sig --> SigRef["refine"]
  DSPX --> Mermaid["mermaid"]
  Mermaid --> MGen["gen"]
  Mermaid --> MSig["sig"]
  DSPX --> Code["codegen"]
  DSPX --> Agent["agent"]
  DSPX --> Tools["tools"]
  DSPX --> Prov["providers"]
```

3) Signature Generation Sequence
--------------------------------

```mermaid
sequenceDiagram
  participant U as User
  participant CLI as dspx signature gen
  participant Conf as Config Loader
  participant Tr as Tracing
  participant Reg as ProviderRegistry
  participant LM as Provider (LM)
  participant Vibe as vibe-dspy
  participant DSPy as DSPy
  participant ML as MLflow

  U->>CLI: run with prompt
  CLI->>Conf: load_config_env
  CLI->>Tr: enable_mlflow_from_env
  CLI->>Reg: create_from_env
  Reg->>LM: build LM (Codex/Claude/Gemini/Multi)
  CLI->>DSPy: dspy.configure(lm=LM)
  CLI->>Vibe: generate_signature(prompt)
  Vibe-->>CLI: code (Signature)
  CLI->>ML: log params/artifacts
  CLI-->>U: print or write signature code
```

4) Plugin & Extension Points
----------------------------

```mermaid
graph LR
  subgraph Plugins
    ProvPlugin["Provider Plugins"]
    ToolPlugin["Tool Plugins"]
  end

  subgraph Registries
    ProvReg["ProviderRegistry"]
    ToolReg["ToolRegistry"]
  end

  subgraph Runtime
    Services["Services"]
    DSPy["DSPy"]
  end

  subgraph Providers
    Codex["CodexExecLM"]
    Claude["ClaudeHeadlessLM"]
    Gemini["GeminiCLILM"]
    Multi["MultiProviderLM"]
  end

  ProvPlugin --> ProvReg
  ToolPlugin --> ToolReg

  Services --> ProvReg
  Services --> ToolReg
  Services --> DSPy

  ProvReg --> Codex
  ProvReg --> Claude
  ProvReg --> Gemini
  ProvReg --> Multi

  ToolReg --> ToolRuntime["Tools at runtime"]
```

5) OpenAPI Tooling Flow (proposed)
----------------------------------

```mermaid
graph TD
  Load["openapi.load(spec)"] --> Parse["Parse spec (OpenAPI 3)"]
  Parse --> Ops["Register operations as tools"]
  Ops --> ToolReg["ToolRegistry"]
  Call["openapi.call(opId, params, body)"] --> Validate["Validate input per schema"]
  Validate --> HTTPX["httpx request"]
  HTTPX --> Result["typed result"]
  Result --> MLflow["trace/log"]
  ToolReg --> AgentSvc["Agent/Services use tools"]
  style Load fill:#74c0fc,stroke:#339af0,color:#000
  style Call fill:#74c0fc,stroke:#339af0,color:#000
```

6) Data Contracts (DTOs)
------------------------

```mermaid
classDiagram
  class SignatureGenRequest {
    +prompt: str
    +options: GenerationOptions
  }
  class SignatureGenResult {
    +code: str
    +metadata: dict
  }
  class WorkflowGenRequest {
    +mermaid_text: str
    +variants: list~str~
    +options: GenerationOptions
  }
  class WorkflowGenResult {
    +program_paths: list~str~
    +graph: dict
  }
  class OpenAPICallRequest {
    +opId: str
    +params: dict
    +body: dict
    +auth: dict
  }
  class OpenAPICallResult {
    +status: int
    +headers: dict
    +body: any
  }
  class GenerationOptions {
    +provider: str
    +timeout: int
    +budget: float
  }
```
