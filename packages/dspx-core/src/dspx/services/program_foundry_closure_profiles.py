"""Finite historical receipt identities; data only, never execution selection.

Source identity digests commit to all eight module hashes and lock identity;
dependency digest commits to each version/wheel/payload-count/payload/RECORD.
Recovered statically from the exact Git blobs documented in the AK-5511 design.
"""

PROFILES = {
    "6c3473ca17bf03325698e3e1a8419a8abc915938": {
        "tree": "dc9098779ec5b500d82ed914d8bba7857d276b85",
        "version": "0.1.6",
        "source_sha256": "a434543edffa64f8fa5e8bddb7b46b8672dbd6be8b4bccec81cbafc937613628",
    },
    "80cc409da976028263da884ed633bef0806cd986": {
        "tree": "552f2f6675cb770776a329bb3cd5c6e8073844f5",
        "version": "0.1.6",
        "source_sha256": "a3f9b81ce89d2c582932338d8101d32d1e7c9ac48095e4a32f504ef0e732d6f4",
    },
    "777388ad9c692b0657e6b6e1d4820b15fcb6641d": {
        "tree": "a564fb0314292c739bebcd4b9362e5b3315974a9",
        "version": "0.1.6.dev0",
        "source_sha256": "5c73f459433dd8fba7ff892de13ca5b3602d8319a4ef97714927b5c72aba3cb3",
    },
}
DEPENDENCY_SHA256 = "91129cb9f1fd158f0f9f62d30cee3b4fdc8dccc58233211eebb65cbfc2a30e20"
# Only historically needed family semantics; no arbitrary user pattern/endpoint code.
FAMILIES = {
    "foundry-dspy-lm-auth-local-vllm": {
        "route": "local-vllm",
        "endpoint": None,
        "timeout": 60.0,
        "auth_provider": "none",
        "model_pattern": r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}",
    },
    "foundry-dspy-lm-auth-github-copilot": {
        "route": "github-copilot",
        "endpoint": "492c0bc03782d6829c9555ed9da0d359510619c2beb561c89505495cb241871d",
        "timeout": 60.0,
        "auth_provider": "github-copilot",
        "model_pattern": r"(gemini|grok)-[a-z0-9][a-z0-9.-]{0,63}",
    },
}
