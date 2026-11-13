# GBA Studio v12.1 — Universal ROM Asset Studio

Windows desktop tool for local Game Boy Advance ROM inspection, extraction candidates, asset preview, iterative scanning, and shareable community profiles. The original ROM is never modified.

## Quick start (Windows 10/11, 64-bit)

1. Install **Python 3.12 64-bit** from python.org. During setup, enable **Add Python to PATH**.
2. Extract this ZIP to a normal writable folder (not inside Program Files).
3. Run `INSTALL.bat` once. It creates a local `.venv` and installs the required packages.
4. Run `GBAStudio.bat`.
5. Choose a `.gba` ROM and click **QUÉT & TRÍCH XUẤT**. The first scan runs in the background.
6. Open the output folder and use Asset Browser to inspect images, audio, text, and binary files.

No ROM is uploaded. Processing is local. Use only ROM files you are legally allowed to use.

## v12.1 features

- GBA header inspection: title, game code, maker, version, checksum and SHA-256.
- Specialized extraction profiles currently included for **Harvest Moon: More Friends of Mineral Town (BFGE)** and **Pokémon FireRed USA (BPRE)**.
- Generic discovery for other ROMs: GBA LZ77 (`0x10`), GBA RLE (`0x30`), aligned GBA ROM pointers, BGR555 palette candidates, raw 4BPP/8BPP graphics candidates, likely map screenblocks, embedded WAV/MIDI signatures, possible PCM, and readable ASCII/UTF-16LE strings.
- Complete byte-for-byte ROM copy in `ROM_Dump/` so unsupported or unrecognized source bytes are preserved. This is preservation, not semantic decoding.
- Asset Browser: open an output folder or an individual file; nearest-neighbour image preview and zoom; audio controls via QtMultimedia; text preview; hex preview for other files.
- Iterative Scan Tree: every scan result is retained as a node with SHA-256, parent ID, depth, source file, child relationship, status and analysis summary. Decompressed streams, graphics binaries and map binaries are queued as child candidates and scanned automatically.
- Persistent scan project: `scan_project.json` checkpoints the queue and discovered nodes after every node. Reopen the project folder and click **Quét tiếp dự án** to continue pending work. ROMs larger than 8 MiB are split into source segments before analysis; each iterative node is limited to 8 MiB.
- Candidate Workbench: select a binary candidate and click **Phân tích file đang chọn**. Deep Scan runs on a background worker, keeps the UI responsive, supports safe stop after the current node, and saves progress automatically. Failed nodes are not added to the processed-hash index and can be retried.
- Candidate correlation: report nearest pointer targets, palette offsets and compressed-stream offsets relative to graphics candidates. This is a heuristic association report, not proof of ownership.
- Community Game Profiles: create, import and export JSON profiles; scan a ROM for exact byte signatures stored in profiles. Profiles are data-only JSON, not executable plug-ins.

## Community profile workflow

1. In Asset Browser, select a binary candidate (`.bin`, `.dat`, `.gba` or `.rom`) that you have reviewed.
2. Click **Tạo Game Profile từ file đang chọn**; enter a descriptive name and asset category.
3. The profile stores a short exact byte signature, game code/title (when a ROM is loaded), source filename and checksum.
4. Click **Xuất Profile** to save a `.gbaprofile.json` file and share it with another user.
5. Another user clicks **Nhập Community Profile** or places the JSON in `profiles/`.
6. Load a ROM and click **Quét ROM bằng Profile**. Exact signature matches are saved to `Community_Profile_Matches/matches.json` and `.csv`.

**Important:** exact-signature profiles find identical byte sequences only. If the source candidate was decompressed, rearranged, tiled, palette-transformed, or otherwise reconstructed, that byte sequence may not exist verbatim in the original ROM. A profile match is a candidate, not a full decoder. Do not share copyrighted ROM data; share only the small profile JSON and rules.

## Iterative scan workflow

1. Run the normal ROM extraction.
2. Click **QUÉT SÂU TOÀN BỘ** to queue all eligible `.bin` candidates automatically.
3. The tool scans candidates and eligible decoded child files, writing node folders under `Nodes/Nxxxxxx/`.
4. The left **SCAN TREE** panel shows parent/child discovery. Double-click a node to open its source file in Asset Browser.
5. Stop safely or close the app. The queue and node records are saved in `scan_project.json`; reopen the Assets folder and click **Quét tiếp dự án** to resume.
6. Use **Phân tích file đang chọn** only when investigating one specific file. Confirm actual assets manually; heuristic candidates are never automatically marked as verified.

Offsets recorded by a node are relative to that node’s input file. The parent chain is required to translate them back to original-ROM offsets.

## Output structure

```text
<ROM>_Assets/
  ROM_Dump/                    # exact source ROM copy
  Compressed/                  # validated decoded streams
  Graphics_4BPP/               # graphics candidates
  Graphics_8BPP/               # graphics candidates
  Pointer_Tables/              # pointer reports
  Maps/                        # likely tilemap candidates
  Audio/                       # embedded audio / possible PCM candidates
  Text/                        # readable string candidates
  Correlations/                # pointer/palette/stream proximity report
  Community_Profile_Matches/   # matches from imported community profiles
  Reviewed_Assets/             # files explicitly confirmed by user
  asset_manifest.json
  asset_manifest.csv
```

## What “universal” means — and does not mean

There is no reliable universal algorithm that can semantically decode every asset in every GBA ROM. Games may use different pointer layouts, custom compression, tilemaps, OAM structures, palette banks, animation formats, audio engines, and text encodings. Generic scanning can identify common structures and preserve all source bytes, but cannot guarantee every sprite/map/song/dialogue is correctly reconstructed. Complete semantic extraction requires a tested profile/decoder for each game family and revision.

Current built-in profile scope:

- **BFGE (MFoMT):** specialized sprite definition/OAM/tile/palette reconstruction.
- **BPRE (FireRed USA):** supported species front/back/shiny and trainer front sprite tables.
- **Other ROMs:** generic candidate discovery plus imported community signature profiles; no claim of complete game-specific decoding.

Map preview images may be tile-index diagnostics rather than fully rendered maps. Audio PCM guesses may be noisy. ASCII/UTF-16LE extraction will not decode custom game text tables. Exact signature profiles do not replace full game-specific parsers.

## Troubleshooting

- If `GBAStudio.bat` says dependencies are missing, run `INSTALL.bat` again.
- If Python is not found, install Python 3.12 64-bit and enable PATH, then reopen the terminal/session.
- If audio will not play, try WAV first; supported codecs depend on the Windows Qt multimedia backend.
- If a scan is slow, test a smaller candidate first. Deep scanning is limited to 8 MiB per input and 120 nodes per run; pending nodes remain queued for the next run.
- If a profile produces no matches, the sample bytes may have been compressed or transformed in the ROM.

## Tests

Run from this folder:

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The automated tests cover decoders, pointer discovery, candidate scanning, persistent iterative scan projects, retry after failed scans, missing-file recovery, profile JSON validation/signature matching, and correlation output. They do not substitute for testing each game against a real ROM and verifying every exported asset in-game.

## Third-party attribution and licensing

See `THIRD_PARTY_LICENSES/NOTICE.txt`. The FireRed extraction approach adapts ideas from `tjtwl/ROM-Asset-Extractor`; review and comply with its GPL-3.0 license terms when redistributing derivative code.
