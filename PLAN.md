# Plan: Harden Initial Address Parse Against Dropped Fields

## Summary

The current risk is concentrated in the one-time Google parse path used after a user selects an autocomplete suggestion. The application currently:

1. fetches autocomplete predictions with `googlemaps.Client.places_autocomplete(...)`
2. stores only the human-readable `prediction["description"]`
3. reparses that free-form description with `googlemaps.Client.geocode(address_string, region="us")`
4. maps only a narrow subset of `address_components`

This makes the workflow vulnerable to field loss, especially for unit/subpremise and institution-style addresses, because the selected suggestion's stable identifier is discarded and the second request is made against a lossy display string.

The hardening plan is to preserve the selected prediction's `place_id`, resolve the selected place by `place_id` during the one-time parse, expand component extraction to cover the documented variants we care about, and preserve user-entered values once populated.

## Current Implementation Facts

- Autocomplete uses `places_autocomplete(input_text=..., components={"country": "US"})` in `src/shippy_gui/widgets/autocomplete.py`.
- The completer currently reduces predictions to `prediction["description"]`, discarding `place_id` and structured formatting.
- Selection in `src/shippy_gui/shipping_tab.py` calls `_load_address(selected_address)` with a plain string.
- The parser in `src/shippy_gui/core/addresses.py` calls `gmaps.geocode(address_string, region="us")` and maps only:
  - `street_number`
  - `subpremise`
  - `route`
  - `locality`
  - `administrative_area_level_1`
  - `postal_code`
  - `country`
- After fields are written into `AddressForm`, no further Google processing occurs. Shipment creation uses the current form values and only sends them to EasyPost.

## Relevant External Specification and Documentation

Primary sources to code against:

1. Google Maps Python client docs: `Client.places_autocomplete(...)`
   - Source: https://googlemaps.github.io/google-maps-services-python/docs/
   - Relevant contract:
     - returns a list of predictions
     - each prediction can be used to recover a stable `place_id`
     - supports `session_token`, `components`, `location`, `radius`, and `strict_bounds`

2. Google Maps Python client docs: `Client.geocode(address=None, place_id=None, ...)`
   - Source: https://googlemaps.github.io/google-maps-services-python/docs/
   - Relevant contract:
     - geocoding can be requested by `place_id`
     - `region` biases results but does not strictly restrict them

3. Google Geocoding API request/response docs
   - Source: https://developers.google.com/maps/documentation/geocoding/requests-geocoding
   - Relevant contract:
     - do not parse `formatted_address` programmatically
     - consume `address_components[]`
     - component count, order, and even presence can vary between requests over time
     - parsers must select components by type, not by array position

4. Google Places Autocomplete docs
   - Source: https://developers.google.com/maps/documentation/places/web-service/legacy/autocomplete
   - Relevant contract:
     - autocomplete predictions are selection aids for a user, not canonical postal-address records
     - predictions include stable place identifiers intended for follow-up requests
     - the canonical follow-up is a place-identifier-based lookup, not reparsing the display string

## Design Goals

- Keep Google involvement limited to user convenience during lookup plus a single resolution step at selection time.
- Eliminate the extra ambiguity introduced by reparsing a display string.
- Reduce the chance that apartment/unit/facility information disappears during the initial parse.
- Preserve manual user edits after field population.
- Continue allowing EasyPost verification as the downstream address validator.
- Avoid broad architectural changes outside the address lookup path.

## Non-Goals

- Do not add continuous Google revalidation while the user edits fields.
- Do not replace EasyPost verification.
- Do not migrate to the new Places API in this change set unless the existing Python client proves insufficient.
- Do not add speculative normalization rules that could rewrite user input after population.

## Proposed Implementation

### 1. Preserve structured autocomplete results instead of flattening to description strings

Change the autocomplete layer so each visible suggestion retains:

- `description`
- `place_id`
- optional `structured_formatting` if present
- optional `types` if present

Implementation shape:

- introduce a lightweight prediction model or typed dict in `widgets/autocomplete.py` or `core/models.py`
- keep the popup text as the human-readable description
- keep a `list[AutocompletePrediction]` in the completer that is always parallel to the `QStringListModel` string list
- do not attempt to change `QCompleter.activated(str)`; keep Qt's built-in signal unchanged
- add a helper on the completer, such as `get_prediction_for_text(description: str)`, that resolves the selected description back to the stored prediction
- resolution strategy: scan the parallel prediction list for the first exact description match
- if duplicate descriptions are ever observed in practice, log them at debug level and use the first match deterministically for now

Reasoning:

- the current design throws away the only stable identifier Google gives us for the selected result
- a follow-up lookup by `place_id` is closer to the selected place than a new free-form geocode against `description`
- keeping the completer's activation signal unchanged is the smallest Qt-compatible change

### 2. Resolve the selected place using `geocode(place_id=...)`

Revise the parser contract in `core/addresses.py`:

- current: `AddressParser.__call__(address_string: str) -> Optional[ParsedAddress]`
- target: accept either a prediction object or a `{description, place_id}` pair

Decision:

- preferred path: if `place_id` is available, call `gmaps.geocode(place_id=place_id)`
- fallback path: if only text is available, call the current `gmaps.geocode(address=description, region="us")`
- explicitly do not switch this change set to `gmaps.place(place_id=..., fields=[...])`

Reasoning:

- this keeps compatibility with current UI behavior during the transition
- it also provides a safe fallback for edge cases where the selected event only yields text
- `place(place_id=...)` is the canonical autocomplete follow-up in Google's Places guidance, but using `geocode(place_id=...)` keeps this project on the existing geocode response shape and avoids introducing a second parsing contract in the same change set
- if `geocode(place_id=...)` proves insufficient during validation, Place Details can be evaluated in a follow-up change with explicit field selection and session-token support

### 3. Expand component extraction with documented type-based fallbacks

Revise `parse_address_components()` so it selects by type and supports more than one candidate source for each form field.

Field mapping plan:

- `street1`
  - primary: `street_number + route`
  - fallback: `premise` when route/number are missing and the result is still address-like
- `street2`
  - primary: `subpremise`
  - fallback candidates to preserve rather than drop silently:
    - `floor`
    - `room`
    - `post_box` if surfaced
    - `establishment`
    - `point_of_interest`
  - formatting rule: keep the Google-provided value verbatim; do not invent normalization beyond minimal joining
  - IBP-specific rule: when facility-like types such as `establishment` or `point_of_interest` are present, prefer preserving that value in `street2` rather than dropping it, because prison and correctional facility names are core to this app's use case
- `city`
  - ordered candidates:
    - `locality`
    - `postal_town` only as a harmless non-US fallback; it is not expected for IBP's Texas-focused usage
    - `sublocality_level_1` only as a last resort and only if no city-like field is present
- `state`
  - `administrative_area_level_1.short_name`
- `zipcode`
  - `postal_code`
  - append `postal_code_suffix` when present using ZIP+4 format
- `country`
  - `country.short_name`

Rules:

- selection must be by component type membership, not array order
- multiple values for the same logical field should be handled deterministically with explicit priority
- log unmapped component types at debug level for future refinement, explicitly including facility-related types such as `establishment` and `point_of_interest` when they are present but not consumed

### 4. Preserve manual information rather than clearing first

The current flow clears the whole form before setting parsed values.

Planned change:

- replace `address_form.clear(); address_form.set_address(parsed)` with a merge-style population path
- only overwrite fields for which the parser produced a non-empty value
- do not erase name/company fields during address lookup

Reasoning:

- if Google omits a component, the current behavior guarantees the field becomes blank
- merge semantics make the parse additive rather than destructive

UI rule:

- the quick lookup should populate address fields only
- recipient `name` and `company` should never be wiped by a lookup action
- full clearing remains appropriate only on explicit reset paths such as the existing post-success cleanup in `_on_shipment_success`

### 5. Surface ambiguity without silently degrading data

Add explicit status/warning behavior for partial parses:

- if required fields are missing after parse, continue populating what was found
- show a warning listing the missing fields
- if supplemental components like `subpremise` were absent, do not treat that as a failure, but do not erase an existing `street2`

Optional plan item if straightforward during implementation:

- show the selected autocomplete description in the status text, but do not retain it as a source of truth after fields are populated

### 6. Keep Google processing one-shot after selection

Lock in the behavioral guarantee:

- Google calls happen only:
  - during autocomplete suggestions
  - once at selection time to resolve the selected place
- after fields are populated, editing form fields must not trigger Google calls
- shipment creation must continue using `AddressForm.get_address()` and EasyPost verification only

This is already mostly true; implementation work should avoid introducing regressions here.

### 7. Note billing/session-token implications explicitly

Current-state note:

- `places_autocomplete(...)` is designed to participate in a session-token-based flow when paired with a place-details follow-up request
- this plan intentionally stays with `geocode(place_id=...)`, so no session-token wiring is added in this change set

Decision:

- document this explicitly in code comments or implementation notes
- accept the current billing model for now because correctness and data preservation are the higher-priority issue
- revisit session-token support only if the app later moves to `place(place_id=...)` or request volume makes autocomplete cost optimization necessary

## Proposed Public/Internal Interface Changes

These are internal repo interfaces rather than user-facing APIs, but they should be treated as stable within the app:

1. `GoogleMapsLookupWorker.results_ready`
   - current: emits a string list of descriptions
   - planned: emits `list[AutocompletePrediction]` or equivalent structured payload

2. `GoogleMapsCompleter`
   - add internal storage for a structured prediction list parallel to the visible string list
   - keep `QCompleter.activated(str)` unchanged
   - expose a helper to retrieve the stored prediction from the activated description text

3. `AddressParser`
   - current input: raw address string
   - planned input: structured selected prediction, with fallback support for raw text

4. `AddressForm.set_address()`
   - current behavior: overwrite provided fields after an external clear
   - planned addition: support merge semantics directly, e.g. `set_address(data, clear_missing=False)` or a separate `merge_address(data)` method

## Implementation Sequence

1. Introduce a typed prediction representation.
2. Update autocomplete worker/completer to retain `place_id` alongside display text using a parallel structured prediction list.
3. Update `ShippingTab._load_address()` to recover the selected prediction from the activated description and pass structured data into the parser.
4. Update `AddressParser` to geocode by `place_id` first, with text-geocode fallback.
5. Add parser unit tests with fixture dictionaries covering component extraction, ZIP+4, facility names, and partial data.
6. Expand type-based component extraction and ZIP+4 handling.
7. Change form population from destructive clear-and-set to non-destructive merge behavior.
8. Add logging around missing/unused address component types.
9. Verify shipment creation path remains unchanged apart from receiving better-populated fields.
10. Update `README.md` or in-repo docs only if the user-visible behavior changes enough to warrant explanation.

## Test Cases and Validation Scenarios

Implementation should add a small `pytest`-based unit test module for `AddressParser.parse_address_components()` using fixture dictionaries. This part of the code is straightforward to test without Qt or network setup and should be treated as a concrete deliverable, not an optional improvement.

Core scenarios to validate:

1. Standard street address
   - input prediction resolves to `street_number`, `route`, `locality`, `administrative_area_level_1`, `postal_code`
   - expected: all core fields populate correctly

2. Address with apartment or unit
   - result includes `subpremise`
   - expected: `street2` is populated and not dropped

3. ZIP+4 address
   - result includes `postal_code` and `postal_code_suffix`
   - expected: ZIP is stored as `12345-6789`

4. Facility or institution-style address
   - input includes prison or correctional-facility-style data, potentially surfaced through `establishment` or `point_of_interest`
   - expected: parser degrades gracefully, preserves institution-identifying information, and warns rather than clearing fields

5. Partial parse over existing manual edits
   - existing `street2`, `name`, or `company` already entered
   - parser omits those fields
   - expected: existing values remain intact

6. Text-only fallback path
   - no `place_id` available
   - expected: parser still functions using description geocode with current behavior as fallback

7. No geocode result
   - expected: warning/error shown, existing manual field values preserved

8. Post-population editing
   - user manually changes fields after lookup
   - expected: no Google calls are triggered

9. Shipment creation regression check
   - expected: `ShipmentWorker` receives only `AddressForm.get_address()` data and performs EasyPost verification as before

10. Duplicate description predictions
   - autocomplete returns two predictions with the same visible description
   - expected: the completer resolves deterministically to the first stored match and logs the collision at debug level

## Risks and Mitigations

- Risk: different predictions may share the same visible description.
  - Mitigation: store structured predictions in a list parallel to the visible model, resolve deterministically to the first exact description match, and log collisions so the behavior can be improved later if needed.

- Risk: `geocode(place_id=...)` may return slightly different component coverage than text geocoding for some places.
  - Mitigation: keep a text-geocode fallback behind explicit logic and log mismatches during validation.

- Risk: Google component types vary over time.
  - Mitigation: centralize mapping rules and write tests/fixtures around representative payloads instead of assuming a fixed response shape.

- Risk: merge behavior may leave stale values when the user intentionally wants a clean replace.
  - Mitigation: keep the existing explicit form reset action for full clearing; lookup itself should remain non-destructive.

## Acceptance Criteria

- Selecting an autocomplete result uses its stable identifier when available for the one-time parse.
- The app no longer depends on reparsing only the displayed description string in the normal path.
- `street2` and ZIP+4 data are preserved when Google returns the relevant component types.
- A lookup does not blank previously entered `name`, `company`, or address subfields that the parser failed to return.
- No Google calls are made after the address has been populated into the individual fields.
- Shipment creation continues to rely only on the populated form data plus EasyPost verification.

## Assumptions and Defaults

- Assume the existing `googlemaps` Python client remains in use for this change.
- Assume Google Places Autocomplete is still the desired UX for search suggestions.
- Assume EasyPost verification remains the only downstream address validation step after form population.
- Default to US-focused behavior, matching the current `components={"country": "US"}` autocomplete filter and `region="us"` geocode bias.
- Default to preserving existing user-entered field content when the parse is incomplete.
- Default to the smallest Qt-compatible integration: keep `QCompleter.activated(str)` unchanged and recover the structured prediction inside the completer/UI layer.

## TODO

- [ ] Add a structured autocomplete prediction type that preserves `description`, `place_id`, and relevant Google metadata.
- [ ] Update the autocomplete worker/completer to store predictions in a list parallel to the visible string list.
- [ ] Keep `QCompleter.activated(str)` unchanged and recover the selected prediction from the activated description.
- [ ] Update `ShippingTab._load_address()` to prefer structured selected predictions over raw text.
- [ ] Update `AddressParser` to resolve by `place_id` first and fall back to text geocoding only when needed.
- [ ] Expand `address_components` parsing for ZIP+4, facility names, and documented fallback component types.
- [ ] Change lookup population from destructive clear-and-set to non-destructive merge behavior.
- [ ] Add debug logging for duplicate descriptions and unmapped Google component types.
- [ ] Add unit tests for parser component extraction and lookup edge cases.
- [ ] Run targeted validation and confirm shipment creation still uses only form data plus EasyPost verification.
