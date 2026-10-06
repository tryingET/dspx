# AK6607 typed image transport. Payload work runs only in the guarded clean `-I -S`
# worker (owner refinement 13975); see docs/proof/AK-6607/clean-worker/ for its own
# node map. Revision2's 159-case matrix is NOT fully executed (traceability-159.md).
# Scenarios map to real pytest assertions, not an installed pytest-bdd runner.
# Provider-free fixtures only. No live/visual-semantic/receiver permission follows.
Feature: Generation ingress and text-only ports deny image payload laundering
  Background:
    Given Decision118 retains the sole DSPyTypedLMAdapter
    And the inspected DSPy pins and lock remain unchanged
    And no live image request has operator authorization

  # tests/test_program_surfaces_image_inputs.py::test_image_examples_path_refuses_read_before_first_renderer
  Scenario: First loader ingress refuses image-enabled example acquisition
    Given image input declarations and an examples_path
    When the real intent loader is invoked
    Then it rejects before reading examples or calling the renderer
    And independent provider invoke and send spies observe zero entries
    # RED evidence13300 -> GREEN continuation-entity10.

  # tests/test_program_surfaces_image_inputs.py::test_malformed_image_examples_never_echo_payload_before_renderer
  Scenario: Loader syntax diagnostics do not echo image payloads to the CLI
    Given malformed synthetic image-bearing examples
    When the actual program-gen CLI invokes the real loader
    Then the output contains no image URI or base64 fragment
    And the renderer and provider effect spies remain untouched
    # RED evidence13300 -> GREEN continuation-entity10.

  # tests/test_stub_provider.py::test_direct_stub_rejects_malformed_image_union_before_fixture
  Scenario: Direct stub fixture text cannot bypass message preflight
    Given a malformed nominal request union and an explicit fixture response
    When the direct stub receives that request
    Then it reports preflight_rejected and dispatch_count zero
    And no fixture success is returned
    # RED ports-red.log -> GREEN continuation-entity10.

  # tests/test_stub_provider.py::test_stub_denies_nominal_parts_even_in_direct_fixture_mode
  Scenario: Stub refuses new parts messages even when they contain only text
    Given an exact ProviderPartsMessage with text or image parts
    When direct stub fixture or ordinary mode receives it
    Then one safe preflight rejection is retained with dispatch_count zero
    # GREEN continuation-entity10; no decoder or image transport success claimed.

  # tests/test_openai_compatible_provider.py::test_unintegrated_image_binding_cannot_dispatch_as_ordinary_text
  Scenario: Unknown image binding cannot silently route as ordinary HTTP text
    Given a nominal request with a non-null unintegrated image binding
    When the actual HTTP provider port receives it with an injected transport
    Then its preflight refuses before send rather than ignoring the binding
    # RED http-binding-red.log -> GREEN continuation-entity10; text v1 preserved.

  # tests/test_image_input_contract.py::test_relocated_open_ancestor_rejects_before_leaf_read
  Scenario: An opened ancestor moved outside the root cannot escape fd confinement
    Given an owned ancestor moved outside the root after directory open
    When the real bounded fd reader traverses that open description
    Then containment refusal precedes the leaf read
    # RED ancestor-red.log -> GREEN continuation-entity10.

  # tests/test_image_input_contract.py::test_existing_episode_materializer_denies_images_without_context
  Scenario: Existing episode materialization must deny unbound image inputs
    Given a synthetic image descriptor without the required image context
    When the existing episode materializer receives it
    Then fixed safe image refusal must precede legacy Image construction
    # GREEN for early refusal only; admitted shipped materialization is unintegrated.

  # tests/test_image_input_contract.py::test_supervised_prepare_source_membrane
  Scenario: Supervised preparation validates ordered sources without admission or effects
    Given a confined synthetic PNG file and canonical inline PNG
    And provider-free supervised privacy before source then admission then manifest
    When the real source helper prepares ordered text image text image text
    Then registered occurrences contain the exact bytes and dimensions in order
    And ordinary text and input commitments survive unchanged
    And no provider or HTTP client or dispatch admission is created

  Scenario Outline: Source validation is exercised independently of admission denial
    Given supervised provider-free preparation with a closed descriptor
    When the source contains <defect>
    Then the real source membrane rejects using a fixed safe input error
    And child-local spies see no forbidden target open or read or provider effect
    And remote and outside sources never reach decoder entry
    Examples:
      | defect                        |
      | remote image URL              |
      | absolute outside path         |
      | non-string encoded data       |
      | non-string media type         |
      | image list mixed with integer |

  # tests/test_program_surfaces_image_inputs.py::test_ordinary_identifier_error_is_useful_without_payload_or_context
  Scenario Outline: Useful text errors do not require echoing invalid fields
    Given an ordinary <format> intent with an invalid <role> identifier
    When the actual loader and CLI validate it
    Then the error explains valid Python identifiers without values paths or context
    And renderer provider and send spies remain untouched
    Examples:
      | format | role    |
      | JSON   | inputs  |
      | YAML   | inputs  |
      | JSON   | outputs |
      | YAML   | outputs |
    # Four actual RED tests then GREEN with fixed validator-type diagnostic mapping.

  # tests/test_image_input_contract.py::test_inherited_history_denies_preparation_before_materialization
  Scenario: A dirty parent history cannot be normalized by the image worker
    Given a test-owned sentinel in the actual parent global history
    When a supervised worker enters image privacy
    Then it refuses before materialization
    And the parent sentinel and all prior history remain unchanged

  # tests/test_image_privacy.py::test_actual_generated_predict_typed_image_to_ordered_fake_http
  Scenario: Synthetic admission refuses nonexact mock transport before client creation
    Given an actual parent-bound synthetic session
    When direct construction selects default custom or subclass transport
    Then client and default-transport spies see zero entries
    And the unconsumed ledger remains empty
    And exact MockTransport subsequently observes actual generated Predict typed pixels
    # Structural fixture evidence, not shipped-route parity or visual competence.

  # tests/test_openai_compatible_provider.py::test_direct_text_port_cold_invoke_without_provider_runtime
  Scenario: Direct text events do not introduce a higher-layer runtime dependency
    Given a fresh interpreter and explicit MockTransport fixture
    When the ordinary direct provider invokes once
    Then the fixture answer is returned without importing provider_runtime
    And no DSPy-free package-import or installed-wheel claim is made

  # Both shipped routes, complete privacy/custody fault matrix, artifacts/replay,
  # installed-wheel, host, live and receiver obligations remain open.

  # tests/test_image_worker.py, tests/test_image_execution.py::test_shipped_production_image_route_artifacts_and_integrity_replay
  Scenario: Shipped image routes run only in the guarded clean worker
    Given an audit-hooked caller and the owner synthetic fixture
    When either shipped route runs a PNG or JPEG input through Predict or ChainOfThought
    Then one send carries the exact image hash through the sole typed adapter
    And the caller observes zero pixel-bearing frames
    And any observer registered or armed inside the worker ends it with image_privacy
    # Clean-worker node map: docs/proof/AK-6607/clean-worker/clean-worker.feature.
