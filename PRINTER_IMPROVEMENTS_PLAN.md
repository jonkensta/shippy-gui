# System Print Dialog Option (Shift+Click)

## Summary
Add an optional system print dialog that can be invoked by holding Shift while clicking "Create Label," while preserving the current quick-print path. The worker thread continues to handle quick prints in the background and delegates to the UI thread only when the dialog path is requested.

## Public API / Interface Changes
- UI behavior: "Create Label" supports **Shift+Click** to open the system print dialog.
- Tooltip mentions the Shift+Click option.
- `ShipmentWorker` gains `label_ready` signal for hand-off to the UI thread.
- `printer_manager.py` gains `print_image_with_dialog()` helper.

## Detailed Implementation

### 1) Dialog Printing Utilities
File: `src/shippy_gui/printing/printer_manager.py`

- `print_image_with_dialog(img, parent_widget, preferred_printer_name) -> str`:
    - Shows `QPrintDialog`.
    - Returns `"printed"`, `"failed"`, or `"canceled"`.
- `_print_with_qprinter(img, printer) -> bool`:
    - Converts PIL to `QImage` using `ImageQt`.
    - Auto-rotates landscape images to portrait for consistency.
    - Scales and centers the image on the page.

### 2) Worker Thread Delegation
File: `src/shippy_gui/workers/shipment_worker.py`

- Signal: `label_ready = Signal(object, str, object)` (image, printer_name, shipment_object).
- `run()` logic:
    - If `use_dialog=True`: Emits `label_ready` and returns immediately.
    - If `use_dialog=False`: Prints in background and emits `success`.
- Contract: `label_ready` is only emitted when `use_dialog` is `True`.

### 3) UI Integration
File: `src/shippy_gui/shipping_tab.py`

- `_create_label()`: Detects `Qt.ShiftModifier` to set `use_dialog`.
- `_on_label_ready(image, printer_name, shipment)`:
    - Calls `print_image_with_dialog`.
    - On success: Calls `_on_shipment_success`.
    - On cancel/fail: Requests refund via EasyPost and shows targeted `QMessageBox`.
    - Relies on worker's `finished` signal for UI cleanup (re-enabling button).

## Edge Cases
- **Refunds:** Handled in the UI thread for the dialog path if the user cancels or the system print fails.
- **UI State:** The "Create Label" button is re-enabled by the worker's `finished` signal, which is safe because the dialog is modal.
- **Auto-rotation:** Priority is given to matching the quick-print portrait orientation.
