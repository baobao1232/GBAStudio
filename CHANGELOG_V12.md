# GBA Studio v12

## Main UI
- Reorganized the workspace into a compact ROM control sidebar and a larger asset review workspace.
- Moved Community Profile actions into the advanced tools menu.
- Simplified the primary actions: scan/extract, analyze selected file, resume project, stop scan, and confirm asset.
- Kept image, audio, text, and hex preview in the asset browser.

## Deep Scan and recovery
- Moved iterative candidate scanning to a dedicated QThread worker so the GUI remains responsive.
- Added safe stop between nodes.
- Added per-node checkpoints and persistent queue recovery.
- Keeps a stable copy of the selected source under `Sources/` in the scan project.
- Splits large ROM inputs into 8 MiB segments and caps iterative nodes at 8 MiB.
- Defaults to 120 nodes per run and depth 4; remaining queue entries can be scanned in another run.
- Failed or missing inputs are not marked as successfully processed. Failed hashes are released for retry.
- Added recovery for legacy scan projects containing an error node whose hash was incorrectly marked processed.

## Verification
- `python -m compileall -q .`
- `python -m unittest discover -s tests -v` — 21 tests passed.
- GUI runtime was not exercised in the build environment because PySide6 is not installed there. The Windows installer installs dependencies from `requirements.txt`.
