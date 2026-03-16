# Code Review: refactor/plan-priority-architecture

Branch contains 5 substantive commits covering address parsing (P5), shipment workflow
service (P2), a config reload bug fix, printer discovery models (P3), and shipping tab
coordinator extraction (P1). P4 (config bootstrap consolidation) is partially done —
the three helper functions are in `core/config.py` but no standalone P4 commit is present.

---

## What is well-executed

**P5 — Address parsing split.** `AddressComponentParser` and `GoogleAddressLookup` are
clean, independently importable, and tested in isolation. The `has_conventional_street`
fix correctly gates `establishment`/`point_of_interest` out of `street2` for standard
addresses. `AddressParser` retained as a thin facade is the right call.

**P2 — ShipmentWorkflow service.** The service owns all business logic cleanly. The
`on_progress`/`on_warning` callback pattern is the right choice for a pure Python
service. `ShipmentWorker` is now a thin Qt adapter — that's the correct boundary.
`easypost.errors.ApiError` (correcting the old `APIError` typo from the worker) is a
silent correctness fix worth noting.

**Config reload bug fix.** `ShippingTab.reload_config()` correctly recreates `gmaps`,
`address_parser`, and `shipment_service`. The `_setup_autocomplete()` call inside
`reload_config()` ensures the new `gmaps` client is wired into the completer. The
default-weight-preservation logic is a nice touch.

**P3 — PrinterInfo model.** `PrinterTransport` enum (USB only for now), no
`is_available` field, no `match_reason` field — the model is lean and directly
addresses all three concerns raised in the prior plan feedback. `USB_SUFFIX_PATTERN`
as a module-level constant is cleaner than instantiating it per-call.

**P1 — Coordinator extraction.** `ShippingStatusPresenter`, `AddressLookupCoordinator`,
and `ShipmentFlowCoordinator` are well-named. The lambda accessors (`get_address_parser`,
`get_shipment_service`, etc.) correctly solve the reload problem — coordinators always
call through to the current service instance rather than holding a stale reference.

---

## Issues

### 1. Dead status bar message in `_open_settings`

`main_window.py:71`:
```python
self.status_bar.showMessage("Settings saved successfully", 3000)
self._apply_font_from_config()
if self.shipping_tab.reload_config():
    self.status_bar.showMessage("Settings saved successfully", 3000)
```

The first `showMessage` call on line 71 is always immediately overwritten — either by
the success message on line 75 or the degraded message on lines 77–80. Remove line 71.

### 2. `easypost.errors.ApiError` not caught in `_refund_shipment`

`ShipmentFlowCoordinator._refund_shipment` (for the dialog-print path) catches only
`Exception`, not `easypost.errors.ApiError` specifically:

```python
except Exception as error:  # pylint: disable=broad-exception-caught
    self._status_presenter.set_status("Refund failed", "error")
    QMessageBox.critical(...)
```

This is functional but inconsistent with `ShipmentWorkflow.refund_after_failure` which
catches `easypost.errors.ApiError` explicitly. For the dialog path the broad catch is
acceptable — note it as intentional or tighten it to match the workflow service.

### 3. `NullPrinterBackend` belongs in a dedicated module

`printer_service.py` defines both `PrinterService` and `NullPrinterBackend`. The null
backend is a backend implementation and belongs alongside `linux.py` / `windows.py` in
`printing/backends/`. Leaving it in `printer_service.py` means `base.py` and the
backend files form an incomplete set that requires reading `printer_service.py` to get
the full picture.

### 4. `display_name` is always equal to `system_name`

`PrinterService._build_printer_info` sets `display_name=printer_name` unconditionally.
There is currently no transformation that would make them differ. Either:
- Remove `display_name` from `PrinterInfo` until there is a use case that needs it, or
- Document what transformation would populate it differently (e.g., stripping USB VID:PID
  suffixes for cleaner UI display — which is actually a natural use case given the
  `usb_id` field).

### 5. `worker_factory` parameter is untested

`ShipmentFlowCoordinator` accepts `worker_factory: Callable[..., ShipmentWorker]` as a
constructor parameter, making the worker injectable for testing. This is good design.
But there are no tests for `ShipmentFlowCoordinator` and no tests that exercise the
`worker_factory` seam. The parameter exists but provides no tested value yet. Either
add a test that uses a mock factory, or note it as pending for when the coordinator
tests are written.

### 6. `logo_path` existence check duplicated between worker and workflow

`ShipmentWorker.run()` checks `os.path.exists(self.logo_path)` before passing
`logo_path` to `ShipmentWorkflowInput`. `ShipmentWorkflow.prepare_label()` checks
`os.path.exists(workflow_input.logo_path)` again. The existence check belongs in one
place. The workflow service should own it (it already does), so the worker can drop its
guard and pass `logo_path` directly:

```python
# worker: just pass it
logo_path=self.logo_path,

# workflow: already checks existence
if workflow_input.logo_path and os.path.exists(workflow_input.logo_path):
```

---

## What is not yet implemented

- **P4** — `__main__.py` still contains its own orchestration around the moved helpers.
  The three functions are in `core/config.py` but the stated P4 goal of "consolidate
  config bootstrap" is only half-done.
- **P1 tests** — no unit tests for `AddressLookupCoordinator`, `ShipmentFlowCoordinator`,
  or `ShippingStatusPresenter`.

---

## Summary

The branch is in good shape. The two correctness items to address before merge are:

1. Remove the dead `showMessage` call on `main_window.py:71`.
2. Resolve the `display_name == system_name` redundancy in `PrinterInfo` — either
   populate it meaningfully (strip USB suffix) or drop the field.

The `NullPrinterBackend` location and the duplicated logo-path guard are minor cleanups
that can follow in a subsequent commit.
