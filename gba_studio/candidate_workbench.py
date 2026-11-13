"""Persistent iterative candidate discovery for GBA ROM data.

Each scan result is retained as a node. Decompressed children can be scanned
again, with provenance (parent id, transform, and offsets) recorded in a JSON
project database. Heuristic classifications are never promoted automatically.
"""
from __future__ import annotations
import csv, hashlib, json, shutil, time
from collections import deque
from pathlib import Path

from .auto_extractor import scan_compressed_streams, scan_rom_pointers
from .graphics_scanner import scan_graphics, scan_palettes
from .graphics import decode_tiles, decode_palette, save_tiles_png
from .extended_assets import export_extended_assets

PROJECT_FILE = "scan_project.json"

def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def analyze_candidate_file(candidate_path, output_root=None, max_depth=2):
    source = Path(candidate_path)
    if not source.is_file(): raise FileNotFoundError(source)
    data = source.read_bytes()
    if not data: raise ValueError("Candidate file is empty")
    if len(data) > 16 * 1024 * 1024:
        raise ValueError("Candidate exceeds 16 MiB deep-scan safety limit; extract a smaller region first")
    out = Path(output_root) if output_root else source.with_name(source.stem + "_DeepScan")
    out.mkdir(parents=True, exist_ok=True)
    (out / "Source").mkdir(exist_ok=True)
    source_copy = out / "Source" / source.name
    if source.resolve() != source_copy.resolve(): shutil.copy2(source, source_copy)

    pointer_info = scan_rom_pointers(data)
    compressed = scan_compressed_streams(data, max_candidates=1000, max_output=8*1024*1024)
    palettes = scan_palettes(data, max_results=300, step=2)
    graphics = {str(bpp): scan_graphics(data, bpp, block_size=block, step=step, max_results=120 if bpp==4 else 80)
                for bpp, block, step in ((4,0x400,0x100),(8,0x800,0x200))}

    ptr_dir=out/"Pointer_Tables"; ptr_dir.mkdir(exist_ok=True)
    (ptr_dir/"pointer_scan.json").write_text(json.dumps({"source":str(source),"reference_count":pointer_info["reference_count"],"table_count":pointer_info["table_count"],"tables":[{"start":f"0x{x['start']:08X}","count":x["count"],"targets":[f"0x{v:08X}" for v in x["targets"]]} for x in pointer_info["tables"]]},indent=2),encoding="utf-8")

    stream_dir=out/"Nested_Compressed"; stream_dir.mkdir(exist_ok=True); nested=[]
    for i,e in enumerate(compressed,1):
        name=f"{i:05d}_{e['format']}_{e['offset']:08X}.bin"; (stream_dir/name).write_bytes(e['data'])
        nested.append({"format":e['format'],"offset":e['offset'],"compressed_size":e['compressed_size'],"decoded_size":e['decoded_size'],"file":name})
    (stream_dir/"index.json").write_text(json.dumps(nested,indent=2),encoding="utf-8")

    gfx_dir=out/"Graphics_Candidates"; gfx_dir.mkdir(exist_ok=True); gfx_rows=[]
    for bpp_key,entries in graphics.items():
        bpp=int(bpp_key); unit=32 if bpp==4 else 64
        for e in entries:
            off,size=e['offset'],e['size']; raw=data[off:off+size]; stem=f"{bpp}bpp_{off:08X}"
            (gfx_dir/f"{stem}.bin").write_bytes(raw)
            need=32 if bpp==4 else 512
            near=[p for p in palettes if abs(p['offset']-off)<0x10000 and p['offset']+need<=len(data)]
            pal=decode_palette(data[min(near,key=lambda p:abs(p['offset']-off))['offset']:][:need]) if near else None
            tiles=decode_tiles(raw[:len(raw)//unit*unit],bpp)
            save_tiles_png(tiles,16,gfx_dir/f"{stem}.png",palette=pal,scale=2,transparent_index=0)
            gfx_rows.append({"bpp":bpp,"offset":off,"size":size,"score":e['score'],"bin":f"{stem}.bin","png":f"{stem}.png"})
    (gfx_dir/"index.json").write_text(json.dumps(gfx_rows,indent=2),encoding="utf-8")
    extended=export_extended_assets(data,out)
    manifest={"source_candidate":str(source),"source_size":len(data),"source_sha256":_sha(data),"analysis_depth":max_depth,
      "pointer_references":pointer_info['reference_count'],"pointer_tables":pointer_info['table_count'],
      "nested_compressed_streams":len(compressed),"graphics_candidates":len(gfx_rows),"extended":extended,
      "classification":"candidate_analysis","offset_basis":"selected candidate file",
      "note":"Heuristic candidates only. Offsets are relative to selected source file; full semantic decoding requires game-specific formats."}
    (out/"candidate_analysis.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return {"directory":str(out),"summary":manifest}

def run_iterative_scan(source_file, project_root=None, max_depth=4, max_nodes=1200,
                       max_file_bytes=8*1024*1024, progress_callback=None, stop_event=None,
                       seed_files=None):
    """Bounded, resumable iterative scan. Failed/missing inputs never poison dedupe."""
    source = Path(source_file).expanduser().resolve()
    original_source = source
    if not source.is_file():
        raise FileNotFoundError(f"Không tìm thấy file nguồn: {source}\nHãy chọn lại ROM hoặc Candidate.")
    root = Path(project_root).expanduser().resolve() if project_root else source.parent / (source.stem + "_AssetProject")
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / PROJECT_FILE
    if db_path.exists():
        try:
            db = json.loads(db_path.read_text(encoding='utf-8'))
        except Exception:
            backup = db_path.with_suffix('.corrupt.json')
            shutil.copy2(db_path, backup)
            db = {}
    else:
        db = {}
    db.setdefault('schema', 2)
    db.setdefault('created_at', time.time())
    db['source_rom'] = str(original_source)
    nodes = db.setdefault('nodes', [])
    edges = db.setdefault('edges', [])
    seen = db.setdefault('processed_hashes', {})
    queue = db.setdefault('queue', [])
    db.setdefault('limits', {})
    db['limits'].update({'max_depth': max_depth, 'max_nodes': max_nodes, 'max_file_bytes': max_file_bytes})

    # Persist a stable copy of the chosen root input inside the project.
    sources_dir = root / 'Sources'
    sources_dir.mkdir(exist_ok=True)
    stable_source = sources_dir / source.name
    if source != stable_source.resolve():
        if not stable_source.exists() or _sha(stable_source.read_bytes()) != _sha(source.read_bytes()):
            shutil.copy2(source, stable_source)
    source = stable_source.resolve()
    db['source_copy'] = str(source)
    source_bytes = source.read_bytes()
    source_hash = _sha(source_bytes)

    # Discard stale queued paths; they are recoverable by choosing the file again.
    valid_queue = []
    for item in queue:
        try:
            qp = Path(item.get('path', '')).expanduser()
            if qp.is_file() and qp.stat().st_size > 0:
                valid_queue.append(item)
        except OSError:
            continue
    queue[:] = valid_queue

    # A failed node must not block retrying the same content.
    for node in nodes:
        if node.get('status') == 'error':
            h = node.get('sha256')
            if h and seen.get(h) == node.get('id'):
                seen.pop(h, None)

    queued_hashes = {x.get('sha256') for x in queue}
    if source.stat().st_size > max_file_bytes:
        chunks_dir = root / 'SourceChunks'
        chunks_dir.mkdir(exist_ok=True)
        chunk_paths = sorted(chunks_dir.glob(f'{source.stem}_part_*.bin'))
        expected = (source.stat().st_size + max_file_bytes - 1) // max_file_bytes
        if len(chunk_paths) != expected or any(x.stat().st_size == 0 for x in chunk_paths):
            for old_chunk in chunk_paths:
                old_chunk.unlink(missing_ok=True)
            chunk_paths = []
            with source.open('rb') as stream:
                part = 0
                while True:
                    block = stream.read(max_file_bytes)
                    if not block:
                        break
                    part += 1
                    chunk = chunks_dir / f'{source.stem}_part_{part:03d}.bin'
                    chunk.write_bytes(block)
                    chunk_paths.append(chunk)
        for index, chunk in reversed(list(enumerate(chunk_paths, 1))):
            chash = _sha(chunk.read_bytes())
            if chash not in seen and chash not in queued_hashes:
                queue.insert(0, {'path': str(chunk.resolve()), 'parent_id': None,
                                 'kind': f'ROM_SEGMENT_{index}', 'depth': 0,
                                 'parent_ref': None, 'sha256': chash})
                queued_hashes.add(chash)
    elif source_hash not in seen and source_hash not in queued_hashes:
        queue.insert(0, {'path': str(source), 'parent_id': None, 'kind': 'SCAN_INPUT', 'depth': 0,
                         'parent_ref': None, 'sha256': source_hash})

    # Batch-seed every extracted binary candidate in one operation. This removes
    # the old requirement to manually select hundreds of individual .bin files.
    seeded = 0
    for candidate in (seed_files or []):
        try:
            cp = Path(candidate).expanduser().resolve()
            if not cp.is_file() or cp.stat().st_size < 32 or cp.stat().st_size > max_file_bytes:
                continue
            if cp == source:
                continue
            c_hash = _sha(cp.read_bytes())
            if c_hash in seen or c_hash in queued_hashes:
                continue
            queue.append({'path': str(cp), 'parent_id': None, 'kind': 'BATCH_CANDIDATE',
                          'depth': 0, 'parent_ref': None, 'sha256': c_hash})
            queued_hashes.add(c_hash)
            seeded += 1
        except OSError:
            continue

    def checkpoint():
        db['queue'] = queue
        db['updated_at'] = time.time()
        db['stats'] = {
            'nodes_total': len(nodes),
            'nodes_scanned': sum(n.get('status') == 'scanned' for n in nodes),
            'pending': len(queue),
            'errors': sum(n.get('status') == 'error' for n in nodes),
            'unique_hashes': len(seen),
            'max_nodes': max_nodes,
            'batch_seeded': seeded,
        }
        tmp = db_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding='utf-8')
        tmp.replace(db_path)

    processed_this_run = 0
    while queue and len(nodes) < max_nodes:
        if stop_event is not None and stop_event.is_set():
            db['stopped'] = True
            break
        item = queue.pop(0)
        path = Path(item.get('path', '')).expanduser()
        parent_id = item.get('parent_id')
        kind = item.get('kind', 'candidate')
        depth = int(item.get('depth', 0))
        if not path.is_file():
            db.setdefault('warnings', []).append(f"Missing input skipped: {path}")
            checkpoint()
            continue
        try:
            raw = path.read_bytes()
            if not raw:
                raise ValueError('File rỗng')
            if len(raw) > max_file_bytes:
                raise ValueError(f'File quá lớn ({len(raw):,} bytes); giới hạn hiện tại {max_file_bytes:,} bytes')
            digest = _sha(raw)
        except Exception as exc:
            db.setdefault('warnings', []).append(f"{path}: {type(exc).__name__}: {exc}")
            checkpoint()
            continue

        if digest in seen:
            child_id = seen[digest]
            if parent_id:
                edges.append({'parent_id': parent_id, 'child_id': child_id, 'relation': 'duplicate_content', 'source_file': str(path)})
            checkpoint()
            continue

        node_id = f"N{len(nodes)+1:06d}"
        node = {'id': node_id, 'parent_id': parent_id, 'kind': kind, 'depth': depth,
                'file': str(path), 'size': len(raw), 'sha256': digest,
                'status': 'scanning', 'created_at': time.time()}
        nodes.append(node)
        if parent_id:
            edges.append({'parent_id': parent_id, 'child_id': node_id, 'relation': kind, 'source_file': str(path)})
        checkpoint()
        try:
            if depth > max_depth:
                node['status'] = 'depth_limit'
            else:
                out = root / 'Nodes' / node_id
                result = analyze_candidate_file(path, out, max_depth=depth)
                summary = result['summary']
                node['analysis_dir'] = str(out)
                node['summary'] = {k: summary.get(k, 0) for k in
                                   ('pointer_references', 'pointer_tables', 'nested_compressed_streams', 'graphics_candidates')}
                node['status'] = 'scanned'
                node['completed_at'] = time.time()
                processed_this_run += 1
                child_paths = []
                for folder_name in ('Nested_Compressed', 'Graphics_Candidates', 'Maps', 'Tilemap_Candidates'):
                    folder = out / folder_name
                    if folder.exists():
                        child_paths.extend(sorted(folder.rglob('*.bin')))
                child_count = 0
                known_queue_hashes = {x.get('sha256') for x in queue}
                for child in child_paths:
                    if len(nodes) + len(queue) >= max_nodes:
                        break
                    try:
                        cdata = child.read_bytes()
                    except OSError:
                        continue
                    if len(cdata) < 32 or len(cdata) > max_file_bytes:
                        continue
                    cd = _sha(cdata)
                    if cd in seen or cd in known_queue_hashes:
                        continue
                    rel = child.relative_to(out).as_posix()
                    queue.append({'path': str(child), 'parent_id': node_id, 'kind': 'decoded:' + rel,
                                  'depth': depth + 1, 'parent_ref': rel, 'sha256': cd})
                    known_queue_hashes.add(cd)
                    child_count += 1
                node['child_candidates_queued'] = child_count
        except Exception as exc:
            node['status'] = 'error'
            node['error'] = f"{type(exc).__name__}: {exc}"
            # Deliberately do not add failed content to processed_hashes.
        else:
            if node.get('status') == 'scanned':
                seen[digest] = node_id
        checkpoint()
        if progress_callback:
            progress_callback(processed_this_run, len(nodes), len(queue), node.get('status', 'unknown'), path.name)

    db['stopped'] = bool(stop_event is not None and stop_event.is_set())
    checkpoint()
    return {'project_file': str(db_path), 'project_root': str(root), 'stats': db['stats'],
            'nodes': nodes, 'stopped': db['stopped'], 'batch_seeded': seeded}

def mark_candidate_confirmed(candidate_path, output_root):
    source=Path(candidate_path); root=Path(output_root)/"Reviewed_Assets"; root.mkdir(parents=True,exist_ok=True)
    target=root/source.name
    if target.exists():
        i=2
        while (root/f"{source.stem}_{i}{source.suffix}").exists(): i+=1
        target=root/f"{source.stem}_{i}{source.suffix}"
    shutil.copy2(source,target); index=root/"reviewed_assets.csv"; exists=index.exists()
    with index.open('a',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f)
        if not exists: w.writerow(["source_file","reviewed_file","status"])
        w.writerow([str(source),target.name,"user_confirmed"])
    return target
