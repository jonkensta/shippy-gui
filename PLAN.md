# Refactor Plan: Priority Architecture Cleanup

## Summary

This plan covers the five highest-value refactors for improving maintainability without changing the product scope:

1. split Google transport from address-component parsing logic
2. move shipment workflow logic out of `ShipmentWorker.run()` into a testable service layer
3. consolidate startup/config bootstrap responsibilities
4. replace string-only printer handling with a richer printer model
5. split `ShippingTab` into coordinator-style components

It also includes one adjacent bug fix that should be folded into the refactor sequence because it is directly tied to configuration ownership:

6. reload `ShippingTab` API clients after settings are saved so updated API keys take effect without restarting

The goal is to reduce widget complexity, isolate business logic from Qt plumbing, and make future changes safer to test and review.

## Guiding Constraints

- Preserve current user-visible behavior unless a change is explicitly called out.
- Keep refactors incremental and shippable in small commits.
- Prefer extracting pure Python services first, then rewiring UI code around them.
- Do not mix unrelated behavior changes into the refactor commits.
- Keep Linux and Windows printer behavior intact during the structural changes unless a step explicitly changes printer interfaces.

## Target End State

After all five items and the config reload fix are complete:

- `ShippingTab` is a small UI composition layer rather than the primary owner of all lookup/shipping logic.
- shipment creation/refund/print orchestration is executable and testable outside a `QThread`
- printers are represented by a typed model instead of raw strings across the stack
- startup/config bootstrap logic has one clear owner
- address lookup transport and address parsing are separately testable components

## Priority 5: Split `ShippingTab`

### Problem

`ShippingTab` currently owns too many responsibilities:

- API client initialization
- address lookup orchestration
- shipping workflow initiation
- refund-related UI handling
- status message presentation
- worker signal wiring

This makes it the hardest file to change safely.

### Refactor target

Reduce `ShippingTab` to a composition root that owns widgets and delegates behavior.

### Proposed decomposition

Create the following collaborators:

- `ShippingTabPresenter` or `ShippingTabState`
  - owns status text / status type updates
  - centralizes status-setting rules
- `AddressLookupCoordinator`
  - owns autocomplete hookup
  - resolves selected prediction
  - invokes address lookup service
  - populates `AddressForm`
  - reports parse warnings and failures
- `ShipmentFlowCoordinator`
  - validates form + shipment controls
  - creates and wires the worker
  - handles success/error UI transitions and presents refund outcomes returned by the workflow layer

`ShippingTab` should keep only:

- widget construction
- controller construction
- top-level signal hookup
- accessors for config and shared widgets

### Implementation sequence

1. extract status-setting logic into a presenter/helper first
2. extract address lookup flow second
3. extract shipment flow third
4. shrink `ShippingTab` to orchestration only

### Acceptance criteria

- `ShippingTab` becomes materially smaller and easier to scan
- behavior remains unchanged
- non-Qt decision logic used by the coordinators is extracted into helpers/services that are testable without Qt
- the coordinators themselves may still depend on Qt widgets such as `AddressForm`, `QLineEdit`, and `ShipmentControls`, and that is acceptable

## Priority 2: Move shipment workflow out of `ShipmentWorker.run()`

### Problem

`ShipmentWorker.run()` currently mixes:

- EasyPost address creation
- EasyPost verification policy
- shipment purchase
- refund policy
- label download
- logo overlay
- print branching logic
- Qt thread/signal concerns

This makes business logic hard to test independently from threading.

### Refactor target

Create a pure workflow service, then keep the worker as a Qt wrapper.

### Proposed design

Add a new service such as `ShipmentWorkflow` that exposes a callback-based method:

- `execute(..., on_progress=...) -> ShipmentWorkflowResult`

The callback form is preferred so the workflow remains pure Python while the worker continues to own Qt signal emission.

Suggested result model:

- `ShipmentWorkflowResult`
  - `status`
  - `message`
  - `shipment`
  - `image`
  - `refund_requested`

Suggested supporting enums/models:

- `ShipmentWorkflowStatus`
- `ShipmentWorkflowWarning`
- `ShipmentWorkflowError`

### Ownership split

- `ShipmentWorkflow` owns shipment business policy, including refund-on-failure decisions and EasyPost interactions.
- `ShipmentFlowCoordinator` owns only the UI response to workflow outcomes.

### Worker role after refactor

`ShipmentWorker` should:

- accept workflow dependencies and input models
- call the workflow service inside `run()`
- translate workflow results into Qt signals
- preserve the existing `label_ready(image, printer_name, shipment)` signal contract exactly
- no longer own detailed shipping business rules

### Implementation sequence

1. define typed result/status models
2. move non-Qt workflow steps into the new service
3. adapt `ShipmentWorker` to delegate to the service
4. keep current signal contract stable during the transition

### Acceptance criteria

- shipment workflow can be tested without Qt threads
- `ShipmentWorker.run()` becomes a thin adapter
- refund and error policy are preserved exactly

## Priority 4: Introduce a richer printer model

### Problem

Printer discovery and selection still move around as raw `str` names, but the code now already depends on additional printer semantics:

- display name
- matching/availability
- filtered vs unfiltered state
- USB identity matching on Windows

Using bare strings will become harder to maintain as printer logic grows.

### Refactor target

Introduce a typed `PrinterInfo` model and push that through the service/backend layers.

### Proposed model

Add `PrinterInfo` in a stable core/printing model module with fields such as:

- `system_name: str`
- `display_name: str`
- `is_default: bool = False`
- `transport: PrinterTransport | None = None`
- `usb_id: str | None = None`

Add a `PrinterTransport` enum rather than using free-form strings.

`PrinterInfo` is for discovery and selection only. The final OS print handoff should still pass `system_name: str` into the backend print call.

### Interface changes

Refactor toward:

- backend `get_available_printers() -> list[PrinterInfo]`
- service `get_available_printers() -> list[PrinterInfo]`
- UI converts `PrinterInfo` to combo-box entries

To keep rollout safe, this can be staged:

1. introduce `PrinterInfo`
2. keep backend returning strings initially and adapt them into `PrinterInfo` in the service layer
3. later move native metadata into backends

### Acceptance criteria

- printer-related code no longer depends on string parsing outside clearly defined backend matching helpers
- dropdown selection logic uses `PrinterInfo` identity rather than raw string assumptions
- no `is_available` or `match_reason` fields are added unless the discovery API is intentionally broadened beyond currently available printers

## Priority 3: Consolidate startup/config bootstrap logic

### Problem

Config responsibilities are spread across:

- `__main__.py`
- `core/config.py`
- `core/config_manager.py`
- `settings_dialog.py`

The split is workable, but bootstrap policy and app-start behavior are not owned in one place.

### Refactor target

Consolidate startup/config bootstrap policy without adding an unnecessary application service class.

### Proposed design

Keep the top-level orchestration in `__main__.py`, but move lower-level bootstrap helpers into config modules with clearer ownership:

- `core/config.py`
  - path resolution
  - file parsing
  - example-config loading/bootstrap helpers
  - logging-path resolution helpers if needed
- `ConfigManager`
  - save/load mechanics only
- `__main__.py`
  - linear startup orchestration
  - settings-dialog retry flow
  - application creation and final launch

### Migration path

1. move `_initialize_config()` and `_load_packaged_example_config()` into `core/config.py` or a closely related config helper module
2. move logging-path resolution into a config helper so `__main__.py` no longer derives it manually
3. keep `main()` as a readable linear startup script
4. add a `ShippingTab.reload_config()` path and call it from `MainWindow._open_settings()` after a successful save so API clients are refreshed in-process

### Acceptance criteria

- startup configuration flow has one obvious owner
- `__main__.py` remains readable and becomes shorter in its helper logic
- settings/config save behavior remains unchanged
- saving settings updates `gmaps`, `address_parser`, and `shipment_service` in the active `ShippingTab` without requiring an application restart

## Priority 1: Split Google transport from address parsing

### Problem

`AddressParser` currently does both:

- Google geocode transport calls
- transformation of `address_components` into app fields

That couples external I/O and parsing logic together.

### Refactor target

Separate lookup transport from component parsing.

### Proposed design

Split into:

- `GoogleAddressLookup`
  - owns geocode-by-place-id
  - owns geocode-by-text fallback
  - returns raw Google geocode payloads or address components
- `AddressComponentParser`
  - owns pure component parsing
  - no Google client dependency

Then `ShippingTab` or `AddressLookupController` composes them.

### Suggested interface

- `GoogleAddressLookup.lookup(prediction_or_text) -> list[dict] | None`
- `AddressComponentParser.parse(address_components) -> ParsedAddress`

This keeps the current `str | AutocompletePrediction` union at the transport boundary; the win here is separation of concerns, not a narrower signature.

### Acceptance criteria

- component parsing is independently importable and testable as a pure class
- existing parser tests can migrate incrementally rather than being rewritten wholesale
- transport fallback logic is isolated from field-mapping logic
- address parsing rules are easier to extend without touching network code

## Recommended Commit Order

1. `refactor: split address lookup transport from parsing`
2. `refactor: move shipment workflow into service layer`
3. `bugfix: reload shipping services after settings save`
4. `refactor: consolidate config bootstrap helpers`
5. `refactor: introduce printer info model`
6. `refactor: extract shipment tab status and coordinator helpers`
7. `test: expand coverage for refactored services and coordinators`
8. `docs: update architecture notes if needed`

## Test Strategy

### Existing behavior to preserve

- address lookup still populates fields the same way
- EasyPost verification/refund behavior remains unchanged
- printer refresh and filtering behavior remain unchanged
- settings load/save behavior remains unchanged
- startup config bootstrap behavior remains unchanged

### New tests to add during refactor

- coordinator-level tests for address lookup and shipment initiation behavior where Qt widgets are still involved
- pure helper/service tests for non-Qt decision logic extracted from those coordinators
- pure workflow tests for shipment success/failure/refund branches
- service tests for config bootstrap decisions
- parser-only tests for address-component conversion
- printer model adaptation tests once `PrinterInfo` is introduced

### Regression checks after each major step

- `uv run mypy src`
- `uv run black src`
- `uv run pylint src`
- `QT_QPA_PLATFORM=offscreen uv run python -m unittest discover -s tests`

## Risks and Controls

### Risk: refactor mixes behavior change with structure change
- Control: extract pure helpers/services first and keep interfaces stable during the first pass

### Risk: Qt signal wiring becomes harder to trace during transition
- Control: preserve current signal names and hookup points until the last cleanup step in each refactor

### Risk: printer model migration ripples too broadly
- Control: introduce `PrinterInfo` as an adapter layer before changing backend signatures everywhere

### Risk: config bootstrap changes affect first-run behavior
- Control: keep bootstrap acceptance tests/manual checklist and do not change `config.ini` creation semantics

## Assumptions

- No new product features are part of this work; this is structural refactoring only.
- Existing tests are the base safety net and should be expanded as services become more pure.
- Backward compatibility for current config files and runtime behavior is required.
- The current branch-based, atomic-commit workflow remains in force for the eventual implementation.

## TODO

- [ ] Split Google transport lookup from address-component parsing first.
- [ ] Introduce a pure `ShipmentWorkflow` service with a progress callback and adapt `ShipmentWorker` into a thin Qt wrapper.
- [ ] Define typed shipment workflow result/status models without UI-only fields such as `needs_dialog_print`.
- [ ] Preserve the existing `label_ready(image, printer_name, shipment)` signal contract during the workflow refactor.
- [ ] Move refund business policy into `ShipmentWorkflow` and keep only refund UI handling in the shipment coordinator layer.
- [ ] Consolidate startup/config bootstrap helpers without introducing an unnecessary application service class.
- [ ] Add a `ShippingTab.reload_config()` path and invoke it after successful settings saves.
- [ ] Introduce `PrinterInfo` and `PrinterTransport`, but keep final OS printing string-based via `system_name`.
- [ ] Extract status presentation out of `ShippingTab`.
- [ ] Extract address lookup orchestration into an `AddressLookupCoordinator`.
- [ ] Extract shipment initiation/orchestration into a `ShipmentFlowCoordinator`.
- [ ] Add/expand tests for each newly extracted service, helper, and coordinator.
- [ ] Run full lint/type/test validation after each refactor stage.
