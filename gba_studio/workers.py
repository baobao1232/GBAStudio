"""Background worker used by the V10 asset extraction interface."""
from PySide6.QtCore import QThread, Signal


class FullAutoScanWorker(QThread):
    progress = Signal(str, int, str)
    finished_results = Signal(object)
    failed = Signal(str)

    def __init__(self, rom):
        super().__init__()
        self.rom = rom

    def run(self):
        try:
            from .auto_extractor import run_full_auto_scan
            result = run_full_auto_scan(
                self.rom,
                progress_callback=lambda stage, percent, detail: self.progress.emit(
                    stage, percent, detail
                ),
            )
            self.finished_results.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class IterativeScanWorker(QThread):
    progress = Signal(int, int, int, str, str)
    finished_results = Signal(object)
    failed = Signal(str)

    def __init__(self, source_file, project_root, max_depth=4, max_nodes=1200, seed_files=None):
        super().__init__()
        import threading
        self.source_file = str(source_file)
        self.project_root = str(project_root)
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.seed_files = [str(x) for x in (seed_files or [])]
        self.stop_event = threading.Event()

    def request_stop(self):
        self.stop_event.set()

    def run(self):
        try:
            from .candidate_workbench import run_iterative_scan
            result = run_iterative_scan(
                self.source_file, self.project_root,
                max_depth=self.max_depth, max_nodes=self.max_nodes, seed_files=self.seed_files,
                progress_callback=lambda done, total, pending, status, name:
                    self.progress.emit(done, total, pending, status, name),
                stop_event=self.stop_event,
            )
            self.finished_results.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
