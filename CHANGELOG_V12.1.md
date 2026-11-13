# GBA Studio v12.1 — Batch Deep Scan

## Main change
- Added **QUÉT SÂU TOÀN BỘ** to batch-enqueue extracted `.bin` candidates from the current Assets folder.
- Users no longer need to select and analyze each candidate individually.
- Candidate files are deduplicated by SHA-256 and processed through the persistent iterative queue.
- The scan can be stopped safely and resumed with **Quét tiếp dự án**.
- Increased the project-wide node ceiling from 120 to 1,200; per-node size remains capped at 8 MiB and maximum depth remains 4.
- Candidate inputs in `ROM_Dump`, `Nodes`, `Sources`, `SourceChunks`, and `Reviewed_Assets` are excluded from batch seeding to avoid re-queuing generated/internal files.

## Validation
- `python -m compileall -q .`
- `python -m unittest discover -s tests -v` — 22 tests passed.
- GUI runtime was not exercised in this build environment because PySide6 is not installed here.
