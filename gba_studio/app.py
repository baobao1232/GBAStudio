from pathlib import Path
import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QMessageBox, QProgressBar, QFrame,
    QSplitter, QListWidget, QListWidgetItem, QStackedWidget, QTextEdit,
    QPlainTextEdit, QSlider, QDoubleSpinBox, QInputDialog, QTreeWidget, QTreeWidgetItem
)
try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    MULTIMEDIA_AVAILABLE = True
except Exception:
    QMediaPlayer = QAudioOutput = None
    MULTIMEDIA_AVAILABLE = False

from .rom import GbaRom
from .workers import FullAutoScanWorker, IterativeScanWorker
from .auto_extractor import export_full_auto_scan

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'}
TEXT_EXTS = {'.txt', '.csv', '.json', '.md', '.xml', '.ini', '.yaml', '.yml', '.asm', '.c', '.h'}
AUDIO_EXTS = {'.wav', '.mp3', '.mid', '.midi', '.ogg', '.flac', '.aac', '.m4a'}


class GbaStudio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.rom = None
        self.worker = None
        self.deep_worker = None
        self.result = None
        self.output_dir = None
        self.asset_root = None
        self._preview_source = QPixmap()
        self._selected_path = None
        self.profile_dir = Path(__file__).resolve().parent.parent / 'profiles'
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.setWindowTitle('GBA Studio v12 — Universal ROM Asset Studio')
        self.setMinimumSize(1120, 720)
        self.resize(1500, 940)
        self.setAcceptDrops(True)
        self._build_ui()

    def _build_ui(self):
        root = QWidget(); outer = QHBoxLayout(root)
        outer.setContentsMargins(16, 16, 16, 16); outer.setSpacing(14)
        split = QSplitter(Qt.Horizontal); split.setChildrenCollapsible(False); outer.addWidget(split)

        left = QWidget(); layout = QVBoxLayout(left)
        layout.setContentsMargins(14, 10, 14, 10); layout.setSpacing(13)
        top = QHBoxLayout(); brand = QLabel('GBA STUDIO')
        brand.setStyleSheet('font-size:25px;font-weight:800;letter-spacing:2px;color:#e8edf5;')
        version = QLabel('V12'); version.setStyleSheet('color:#8da4c2;font-weight:700;padding:6px 10px;background:#26364d;border-radius:6px;')
        top.addWidget(brand); top.addWidget(version); top.addStretch(); layout.addLayout(top)
        intro = QLabel('ROM EXTRACTION'); intro.setStyleSheet('font-size:17px;font-weight:700;color:#cbd5e1;')
        desc = QLabel('Chọn ROM và quét tự động. GBA Studio sẽ tự tìm, phân tích tiếp dữ liệu con và gom asset để xem trước.')
        desc.setWordWrap(True); desc.setStyleSheet('font-size:13px;color:#94a3b8;')
        layout.addWidget(intro); layout.addWidget(desc)

        panel = QFrame(); panel.setObjectName('panel')
        panel.setStyleSheet('QFrame#panel{background:#172235;border:1px solid #2c3b52;border-radius:14px;}')
        pl = QVBoxLayout(panel); pl.setContentsMargins(18,18,18,18); pl.setSpacing(12)
        self.drop_label = QLabel('KÉO THẢ ROM GBA VÀO ĐÂY'); self.drop_label.setAlignment(Qt.AlignCenter); self.drop_label.setMinimumHeight(86)
        self.drop_label.setStyleSheet('border:2px dashed #526780;border-radius:10px;color:#9fb1c8;font-size:15px;font-weight:700;')
        pl.addWidget(self.drop_label)
        self.rom_name = QLabel('Chưa chọn ROM'); self.rom_name.setStyleSheet('font-size:15px;font-weight:700;color:#e2e8f0;')
        self.rom_info = QLabel(''); self.rom_info.setWordWrap(True); self.rom_info.setStyleSheet('color:#94a3b8;font-size:12px;')
        pl.addWidget(self.rom_name); pl.addWidget(self.rom_info)
        buttons = QHBoxLayout(); self.open_btn = QPushButton('Chọn ROM'); self.extract_btn = QPushButton('QUÉT & TRÍCH XUẤT'); self.extract_btn.setEnabled(False)
        self.open_btn.clicked.connect(self.open_rom_dialog); self.extract_btn.clicked.connect(self.start_extraction)
        self.open_btn.setMinimumHeight(42); self.extract_btn.setMinimumHeight(42)
        self.open_btn.setStyleSheet('QPushButton{background:#33465f;color:#f1f5f9;border:0;border-radius:8px;padding:10px 14px;font-weight:700;} QPushButton:hover{background:#405976;}')
        self.extract_btn.setStyleSheet('QPushButton{background:#2563a6;color:white;border:0;border-radius:8px;padding:10px 14px;font-weight:800;} QPushButton:hover{background:#3278c0;} QPushButton:disabled{background:#39485c;color:#8795a8;}')
        buttons.addWidget(self.open_btn); buttons.addWidget(self.extract_btn,1); pl.addLayout(buttons); layout.addWidget(panel)
        self.progress = QProgressBar(); self.progress.setRange(0,100); self.progress.setValue(0); self.progress.hide()
        self.progress.setStyleSheet('QProgressBar{background:#202d40;border:0;border-radius:6px;height:16px;color:#e2e8f0;text-align:center;} QProgressBar::chunk{background:#3182ce;border-radius:6px;}')
        layout.addWidget(self.progress)
        self.status = QLabel('Sẵn sàng'); self.status.setStyleSheet('color:#a8b6c9;font-size:13px;'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.result_path = QLabel(''); self.result_path.setWordWrap(True); self.result_path.setTextInteractionFlags(Qt.TextSelectableByMouse); self.result_path.setStyleSheet('color:#8fb7a7;font-size:11px;'); layout.addWidget(self.result_path)
        open_folder = QPushButton('Mở thư mục assets'); open_folder.clicked.connect(self.open_output_folder)
        open_folder.setStyleSheet('QPushButton{background:#23634f;color:white;border:0;border-radius:7px;padding:9px 14px;font-weight:700;}'); layout.addWidget(open_folder)
        layout.addStretch(); footer = QLabel('GBA Studio v12 • Quét nền • Tự lưu tiến trình'); footer.setStyleSheet('color:#64748b;font-size:11px;'); layout.addWidget(footer)
        split.addWidget(left)

        # Asset browser + multi-format preview
        review = QFrame(); review.setObjectName('reviewPanel')
        review.setStyleSheet('QFrame#reviewPanel{background:#111e30;border:1px solid #2c3b52;border-radius:12px;}')
        rv = QVBoxLayout(review); rv.setContentsMargins(14,14,14,14); rv.setSpacing(9)
        title = QLabel('ASSET BROWSER'); title.setStyleSheet('font-size:18px;font-weight:800;color:#e2e8f0;')
        self.review_count = QLabel('Chưa có dữ liệu — hãy chọn ROM và trích xuất hoặc mở thư mục assets')
        self.review_count.setStyleSheet('font-size:12px;color:#94a3b8;'); rv.addWidget(title); rv.addWidget(self.review_count)
        toolbar = QHBoxLayout()
        self.choose_folder_btn = QPushButton('Chọn thư mục'); self.choose_file_btn = QPushButton('Chọn file để preview')
        for b in (self.choose_folder_btn, self.choose_file_btn):
            b.setStyleSheet('QPushButton{background:#263b56;color:#e5edf7;border:1px solid #405675;border-radius:6px;padding:7px 10px;font-weight:600;} QPushButton:hover{background:#345477;}')
        self.choose_folder_btn.clicked.connect(self.choose_asset_folder); self.choose_file_btn.clicked.connect(self.choose_preview_file)
        self.deep_scan_btn = QPushButton('Phân tích file đang chọn')
        self.batch_scan_btn = QPushButton('QUÉT SÂU TOÀN BỘ')
        self.tree_scan_btn = QPushButton('Quét tiếp dự án')
        self.stop_scan_btn = QPushButton('Dừng quét'); self.stop_scan_btn.setEnabled(False)
        self.confirm_candidate_btn = QPushButton('Đánh dấu đã xác minh')
        for b in (self.deep_scan_btn, self.batch_scan_btn, self.tree_scan_btn, self.confirm_candidate_btn, self.stop_scan_btn):
            b.setStyleSheet('QPushButton{background:#31513f;color:#e5f5eb;border:1px solid #47745a;border-radius:6px;padding:7px 10px;font-weight:600;} QPushButton:hover{background:#3b684e;}')
        self.deep_scan_btn.clicked.connect(self.deep_scan_selected_candidate)
        self.batch_scan_btn.clicked.connect(self.deep_scan_all_candidates)
        self.tree_scan_btn.clicked.connect(self.continue_iterative_scan)
        self.confirm_candidate_btn.clicked.connect(self.confirm_selected_candidate)
        self.stop_scan_btn.clicked.connect(self.stop_iterative_scan)
        toolbar.addWidget(self.choose_folder_btn); toolbar.addWidget(self.choose_file_btn)
        toolbar.addWidget(self.batch_scan_btn); toolbar.addWidget(self.tree_scan_btn); toolbar.addWidget(self.stop_scan_btn); toolbar.addWidget(self.confirm_candidate_btn); toolbar.addStretch(); rv.addLayout(toolbar)
        profilebar = QHBoxLayout()
        self.create_profile_btn = QPushButton('Tạo Game Profile từ file đang chọn')
        self.import_profile_btn = QPushButton('Nhập Community Profile')
        self.export_profile_btn = QPushButton('Xuất Profile')
        self.scan_profile_btn = QPushButton('Quét ROM bằng Profile')
        for b in (self.create_profile_btn, self.import_profile_btn, self.export_profile_btn, self.scan_profile_btn):
            b.setStyleSheet('QPushButton{background:#4b3c70;color:#f3edff;border:1px solid #6b5798;border-radius:6px;padding:7px 9px;font-weight:600;} QPushButton:hover{background:#604b8d;}')
            profilebar.addWidget(b)
        self.create_profile_btn.clicked.connect(self.create_community_profile)
        self.import_profile_btn.clicked.connect(self.import_community_profile)
        self.export_profile_btn.clicked.connect(self.export_community_profile)
        self.scan_profile_btn.clicked.connect(self.scan_with_community_profiles)
        # Advanced profile actions are available from the menu, keeping the main workspace uncluttered.
        for profile_button in (self.create_profile_btn, self.import_profile_btn, self.export_profile_btn, self.scan_profile_btn):
            profile_button.setVisible(False)
        browser_split = QSplitter(Qt.Horizontal); browser_split.setChildrenCollapsible(False)
        self.scan_tree = QTreeWidget(); self.scan_tree.setHeaderLabels(['SCAN TREE']); self.scan_tree.setMinimumWidth(190)
        self.scan_tree.setStyleSheet('QTreeWidget{background:#0d1726;color:#dbe5f2;border:1px solid #2b3b50;border-radius:8px;} QTreeWidget::item{padding:5px;} QTreeWidget::item:selected{background:#244b73;}')
        self.scan_tree.itemDoubleClicked.connect(self.open_tree_node)
        browser_split.addWidget(self.scan_tree)
        self.asset_list = QListWidget(); self.asset_list.setMinimumWidth(220)
        self.asset_list.setStyleSheet('QListWidget{background:#0d1726;color:#dbe5f2;border:1px solid #2b3b50;border-radius:8px;padding:5px;} QListWidget::item{padding:7px;border-bottom:1px solid #1e2b3d;} QListWidget::item:selected{background:#244b73;color:white;}')
        self.asset_list.currentItemChanged.connect(self.preview_selected_asset); browser_split.addWidget(self.asset_list)
        preview_host = QWidget(); pv = QVBoxLayout(preview_host); pv.setContentsMargins(0,0,0,0); pv.setSpacing(8)
        self.preview_stack = QStackedWidget()
        self.image_preview = QLabel('Chọn file để xem preview'); self.image_preview.setAlignment(Qt.AlignCenter)
        self.image_preview.setMinimumSize(320,260); self.image_preview.setStyleSheet('background-color:#080f1b;border:1px solid #40516a;border-radius:8px;color:#8292a8;')
        self.preview_stack.addWidget(self.image_preview)
        self.text_preview = QTextEdit(); self.text_preview.setReadOnly(True); self.text_preview.setStyleSheet('QTextEdit{background:#080f1b;color:#dbe5f2;border:1px solid #40516a;border-radius:8px;font-family:Consolas,monospace;}')
        self.preview_stack.addWidget(self.text_preview)
        audio_page = QWidget(); av = QVBoxLayout(audio_page); av.addStretch()
        self.audio_title = QLabel('Chưa chọn file âm thanh'); self.audio_title.setAlignment(Qt.AlignCenter); self.audio_title.setStyleSheet('font-size:16px;font-weight:700;color:#dbe5f2;')
        av.addWidget(self.audio_title)
        self.audio_state = QLabel(''); self.audio_state.setAlignment(Qt.AlignCenter); self.audio_state.setStyleSheet('color:#94a3b8;'); av.addWidget(self.audio_state)
        audio_controls = QHBoxLayout(); self.play_btn = QPushButton('▶ Play'); self.stop_btn = QPushButton('■ Stop')
        self.play_btn.clicked.connect(self.toggle_audio); self.stop_btn.clicked.connect(self.stop_audio)
        audio_controls.addStretch(); audio_controls.addWidget(self.play_btn); audio_controls.addWidget(self.stop_btn); audio_controls.addStretch(); av.addLayout(audio_controls)
        self.seek_slider = QSlider(Qt.Horizontal); self.seek_slider.setRange(0,0); self.seek_slider.sliderMoved.connect(self.seek_audio); av.addWidget(self.seek_slider)
        volrow = QHBoxLayout(); volrow.addWidget(QLabel('Âm lượng')); self.volume_slider = QSlider(Qt.Horizontal); self.volume_slider.setRange(0,100); self.volume_slider.setValue(70); self.volume_slider.valueChanged.connect(self.set_volume); volrow.addWidget(self.volume_slider); av.addLayout(volrow); av.addStretch()
        self.preview_stack.addWidget(audio_page)
        self.hex_preview = QPlainTextEdit(); self.hex_preview.setReadOnly(True); self.hex_preview.setStyleSheet('QPlainTextEdit{background:#080f1b;color:#a9c4df;border:1px solid #40516a;border-radius:8px;font-family:Consolas,monospace;}')
        self.preview_stack.addWidget(self.hex_preview)
        pv.addWidget(self.preview_stack,1)
        zoomrow = QHBoxLayout(); zoomrow.addWidget(QLabel('Zoom ảnh'))
        self.zoom_spin = QDoubleSpinBox(); self.zoom_spin.setRange(0.25,16.0); self.zoom_spin.setSingleStep(0.25); self.zoom_spin.setValue(1.0); self.zoom_spin.setSuffix('×'); self.zoom_spin.valueChanged.connect(self._render_preview)
        zoomrow.addWidget(self.zoom_spin); zoomrow.addStretch(); pv.addLayout(zoomrow)
        browser_split.addWidget(preview_host); browser_split.setStretchFactor(0,0); browser_split.setStretchFactor(1,0); browser_split.setStretchFactor(2,1); browser_split.setSizes([220,280,760])
        rv.addWidget(browser_split,1)
        self.preview_info = QLabel(''); self.preview_info.setWordWrap(True); self.preview_info.setStyleSheet('color:#94a3b8;font-size:11px;'); rv.addWidget(self.preview_info)
        split.addWidget(review); split.setStretchFactor(0,0); split.setStretchFactor(1,1); split.setSizes([340,1160])
        self.setCentralWidget(root)
        self.setStyleSheet('QMainWindow{background:#0b1220;} QWidget{color:#dbe5f2;} QLabel{background:transparent;color:#cbd5e1;} QPushButton{font-size:12px;} QSplitter::handle{background:#26364b;width:4px;} QProgressBar{padding:2px;}')

        tools_menu = self.menuBar().addMenu('Công cụ nâng cao')
        for label, slot in (('Tạo Game Profile từ file đang chọn', self.create_community_profile),
                            ('Nhập Community Profile', self.import_community_profile),
                            ('Xuất Profile', self.export_community_profile),
                            ('Quét ROM bằng Profile', self.scan_with_community_profiles)):
            action = tools_menu.addAction(label)
            action.triggered.connect(slot)
        self.menuBar().setStyleSheet('QMenuBar{background:#101c2d;color:#dbe5f2;padding:4px;} QMenuBar::item:selected{background:#294766;} QMenu{background:#172235;color:#dbe5f2;border:1px solid #40516a;} QMenu::item:selected{background:#294766;}')

        self.audio_player = None; self.audio_output = None
        if MULTIMEDIA_AVAILABLE:
            self.audio_player = QMediaPlayer(self); self.audio_output = QAudioOutput(self)
            self.audio_player.setAudioOutput(self.audio_output); self.audio_output.setVolume(0.7)
            self.audio_player.positionChanged.connect(self._audio_position_changed)
            self.audio_player.durationChanged.connect(self._audio_duration_changed)
            self.audio_player.playbackStateChanged.connect(self._audio_state_changed)
        else:
            self.play_btn.setEnabled(False); self.audio_state.setText('QtMultimedia không khả dụng — cài lại PySide6 đầy đủ để phát âm thanh.')

    def populate_asset_review(self, folder):
        self.asset_root = Path(folder); self.asset_list.clear(); self.scan_tree.clear()
        project_file = self.asset_root / 'scan_project.json'
        if project_file.exists():
            try:
                import json
                db=json.loads(project_file.read_text(encoding='utf-8'))
                root_item=QTreeWidgetItem([Path(db.get('source_rom','ROM')).name])
                self.scan_tree.addTopLevelItem(root_item); by_id={}
                for node in db.get('nodes',[]):
                    label=f"{node.get('id')} • {node.get('kind')} • {node.get('status')}"
                    item=QTreeWidgetItem([label]); item.setData(0,Qt.UserRole,node.get('file',''))
                    parent=by_id.get(node.get('parent_id'),root_item); parent.addChild(item); by_id[node['id']]=item
                self.scan_tree.expandToDepth(1)
            except Exception: pass
        files = sorted((p for p in self.asset_root.rglob('*') if p.is_file() and p.name not in ('asset_manifest.json','asset_manifest.csv')),
                       key=lambda p: (p.suffix.lower() not in IMAGE_EXTS, str(p).lower()))
        for path in files:
            rel = path.relative_to(self.asset_root); ext = path.suffix.lower()
            icon = '🖼  ' if ext in IMAGE_EXTS else ('♫  ' if ext in AUDIO_EXTS else ('T  ' if ext in TEXT_EXTS else '▧  '))
            item = QListWidgetItem(icon + str(rel)); item.setData(Qt.UserRole, str(path)); self.asset_list.addItem(item)
        self.review_count.setText(f'{len(files):,} file • {sum(p.suffix.lower() in IMAGE_EXTS for p in files):,} ảnh • {sum(p.suffix.lower() in AUDIO_EXTS for p in files):,} audio')
        if self.asset_list.count(): self.asset_list.setCurrentRow(0)
        else: self._clear_preview()

    def open_tree_node(self, item, column=0):
        value=item.data(0, Qt.UserRole)
        if value and Path(value).is_file(): self._add_external_file(value)

    def choose_asset_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Chọn thư mục assets hoặc dự án quét')
        if folder:
            self.output_dir = Path(folder)
            self.populate_asset_review(folder)

    def choose_preview_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Chọn file để preview', '', 'All files (*.*)')
        if path: self._add_external_file(path)

    def _add_external_file(self, path):
        p = Path(path)
        for i in range(self.asset_list.count()):
            if Path(self.asset_list.item(i).data(Qt.UserRole)) == p:
                self.asset_list.setCurrentRow(i); return
        item = QListWidgetItem('↗  ' + p.name); item.setData(Qt.UserRole, str(p)); self.asset_list.addItem(item); self.asset_list.setCurrentItem(item)

    def _start_iterative_worker(self, source, project, title, seed_files=None):
        if self.deep_worker and self.deep_worker.isRunning():
            return
        source = Path(source)
        if not source.is_file():
            QMessageBox.warning(self, 'Không tìm thấy file',
                                f'File nguồn không còn tồn tại:\n{source}\n\nHãy chọn lại ROM hoặc Candidate.')
            return
        self.status.setText(title)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.stop_scan_btn.setEnabled(True)
        self.deep_scan_btn.setEnabled(False)
        self.batch_scan_btn.setEnabled(False)
        self.tree_scan_btn.setEnabled(False)
        self.deep_worker = IterativeScanWorker(source, project, max_depth=4, max_nodes=1200, seed_files=seed_files)
        self.deep_worker.progress.connect(self.on_iterative_progress)
        self.deep_worker.finished_results.connect(self.on_iterative_finished)
        self.deep_worker.failed.connect(self.on_iterative_failed)
        self.deep_worker.finished.connect(self._iterative_thread_stopped)
        self.deep_worker.start()

    def deep_scan_all_candidates(self):
        """Queue every extracted .bin candidate and analyze them in batches."""
        if not self.output_dir or not self.output_dir.exists():
            QMessageBox.information(self, 'Chưa có dữ liệu', 'Hãy quét ROM trước hoặc mở thư mục Assets đã trích xuất.')
            return
        excluded = {'ROM_Dump', 'Nodes', 'DeepScanProject', 'Reviewed_Assets', 'Sources', 'SourceChunks'}
        candidates = []
        for path in self.output_dir.rglob('*.bin'):
            try:
                rel = path.relative_to(self.output_dir)
                if any(part in excluded for part in rel.parts):
                    continue
                if path.stat().st_size >= 32:
                    candidates.append(path)
            except OSError:
                continue
        candidates = sorted(set(candidates), key=lambda p: str(p).lower())
        if not candidates:
            QMessageBox.information(self, 'Không có Candidate', 'Không tìm thấy file .bin phù hợp trong thư mục Assets.')
            return
        source = self.rom.path if self.rom and self.rom.path.is_file() else None
        if source is None:
            for name in ('*.gba', '*.rom', '*.bin'):
                found = list((self.output_dir / 'ROM_Dump').glob(name)) if (self.output_dir / 'ROM_Dump').exists() else []
                if found:
                    source = found[0]
                    break
        if source is None:
            # Use the first candidate as project root; all remaining files are batch-seeded.
            source = candidates[0]
        project = self.output_dir
        self._start_iterative_worker(source, project,
            f'Đang đưa {len(candidates):,} Candidate vào hàng đợi Deep Scan…', seed_files=candidates)

    def deep_scan_selected_candidate(self):
        if not self._selected_path:
            QMessageBox.information(self, 'Chưa chọn file', 'Chọn một file BIN/Candidate trong danh sách trước.')
            return
        source = Path(self._selected_path)
        if source.suffix.lower() not in ('.bin', '.dat', '.gba', '.rom'):
            QMessageBox.information(self, 'Không phải file nhị phân',
                                    'Hãy chọn file Candidate dạng .bin, .dat hoặc ROM. Ảnh và báo cáo không cần Deep Scan.')
            return
        base = self.output_dir if self.output_dir and self.output_dir.exists() else source.parent
        project = base if (base / 'scan_project.json').exists() else base / (source.stem + '_AssetProject')
        self._start_iterative_worker(source, project, f'Đang phân tích {source.name}…')

    def continue_iterative_scan(self):
        # Prefer the source recorded by an opened scan project, even if the original
        # ROM/Candidate has since been moved. V12 keeps a stable copy under Sources/.
        base = self.output_dir if self.output_dir and self.output_dir.exists() else None
        project = None
        source = None
        if base and (base / 'scan_project.json').is_file():
            project = base
            try:
                import json
                db = json.loads((base / 'scan_project.json').read_text(encoding='utf-8'))
                for candidate in (db.get('source_copy'), db.get('source_rom')):
                    if candidate and Path(candidate).is_file():
                        source = Path(candidate)
                        break
                if source is None:
                    for item in db.get('queue', []):
                        candidate = item.get('path')
                        if candidate and Path(candidate).is_file():
                            source = Path(candidate)
                            break
            except Exception:
                source = None
        if source is None:
            source = self.rom.path if self.rom else self._selected_path
        if source and Path(source).suffix.lower() not in ('.gba', '.bin', '.dat', '.rom'):
            source = None
        if not source or not Path(source).is_file():
            source, _ = QFileDialog.getOpenFileName(
                self, 'Chọn lại ROM hoặc Candidate để tiếp tục', '',
                'GBA ROM / Candidate (*.gba *.bin *.dat *.rom);;All files (*.*)')
            if not source:
                return
        if project is None:
            source = Path(source)
            base = self.output_dir if self.output_dir and self.output_dir.exists() else source.parent
            project = base if (base / 'scan_project.json').exists() else base / (source.stem + '_AssetProject')
        self._start_iterative_worker(source, project, 'Đang tiếp tục phân tích các Candidate còn chờ…')

    def stop_iterative_scan(self):
        if self.deep_worker and self.deep_worker.isRunning():
            self.deep_worker.request_stop()
            self.status.setText('Đang dừng an toàn sau node hiện tại…')
            self.stop_scan_btn.setEnabled(False)

    def on_iterative_progress(self, done, total, pending, status, name):
        self.status.setText(f'Đã phân tích {done} node trong lượt này • Tổng {total} • Còn chờ {pending} • {status}: {name}')

    def on_iterative_finished(self, result):
        self.progress.setRange(0, 100); self.progress.setValue(100)
        self.stop_scan_btn.setEnabled(False)
        self.deep_scan_btn.setEnabled(True); self.batch_scan_btn.setEnabled(True); self.tree_scan_btn.setEnabled(True)
        self.output_dir = Path(result['project_root'])
        self.result_path.setText(f"Dự án quét: {result['project_file']}")
        stats = result.get('stats', {})
        state = 'Đã dừng theo yêu cầu' if result.get('stopped') else 'Phân tích hoàn tất'
        self.status.setText(f"{state} • {stats.get('nodes_scanned', 0)} node đã quét • {stats.get('pending', 0)} đang chờ • {stats.get('errors', 0)} lỗi")
        self.populate_asset_review(self.output_dir)

    def _iterative_thread_stopped(self):
        worker = self.sender()
        if worker is not None:
            worker.deleteLater()
        self.deep_worker = None

    def on_iterative_failed(self, message):
        self.progress.setRange(0, 100); self.progress.setValue(0)
        self.stop_scan_btn.setEnabled(False)
        self.deep_scan_btn.setEnabled(True); self.batch_scan_btn.setEnabled(True); self.tree_scan_btn.setEnabled(True)
        self.status.setText('Không thể phân tích file nguồn.')
        QMessageBox.critical(self, 'Lỗi Deep Scan', message)

    def confirm_selected_candidate(self):
        if not self._selected_path or not self._selected_path.is_file():
            QMessageBox.information(self, 'Chưa chọn file', 'Hãy chọn file muốn xác minh trước.')
            return
        if not self.output_dir or not self.output_dir.exists():
            QMessageBox.information(self, 'Chưa có thư mục output', 'Hãy mở thư mục assets đã trích xuất trước.')
            return
        answer = QMessageBox.question(
            self, 'Xác minh asset',
            'Bạn xác nhận file đang chọn là asset đúng của game? File sẽ được sao chép vào Reviewed_Assets.',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return
        try:
            from .candidate_workbench import mark_candidate_confirmed
            target = mark_candidate_confirmed(self._selected_path, self.output_dir)
            self.status.setText(f'Đã lưu asset đã xác minh: {target.name}')
            self.result_path.setText(f'Asset đã xác minh: {target}')
        except Exception as exc:
            QMessageBox.critical(self, 'Lỗi lưu asset', f'{type(exc).__name__}: {exc}')

    def create_community_profile(self):
        if not self._selected_path or not self._selected_path.is_file():
            QMessageBox.information(self, 'Chưa chọn mẫu', 'Chọn file nhị phân ứng viên (.bin/.dat) trước.')
            return
        if self._selected_path.suffix.lower() not in {'.bin', '.dat', '.gba', '.rom'}:
            QMessageBox.warning(self, 'Sai định dạng mẫu', 'Profile cần mẫu nhị phân .bin/.dat/.gba/.rom, không dùng PNG preview.')
            return
        name, ok = QInputDialog.getText(self, 'Tạo Game Profile', 'Tên asset/profile:')
        if not ok or not name.strip(): return
        asset_type, ok = QInputDialog.getItem(self, 'Loại asset', 'Chọn loại:',
            ['sprite', 'tileset', 'map', 'palette', 'audio', 'text', 'animation', 'other'], 0, False)
        if not ok: return
        try:
            from .profile_manager import build_profile, save_profile
            info = self.rom.header_info() if self.rom else {}
            profile = build_profile(self._selected_path, name, asset_type,
                info.get('game_code', ''), info.get('detected_game', ''))
            target = save_profile(profile, self.profile_dir)
            QMessageBox.information(self, 'Profile đã tạo',
                f'Đã lưu profile cộng đồng:\n{target}\n\nProfile dùng exact byte signature. Các kết quả match vẫn là ứng viên cần xác minh.')
            self.status.setText(f'Đã tạo Community Profile: {target.name}')
        except Exception as exc:
            QMessageBox.critical(self, 'Không thể tạo profile', f'{type(exc).__name__}: {exc}')

    def import_community_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Nhập Community Profile', '', 'GBA Studio Profile (*.json)')
        if not path: return
        try:
            from .profile_manager import import_profile
            target = import_profile(path, self.profile_dir)
            QMessageBox.information(self, 'Đã nhập profile', f'Profile đã thêm vào thư viện:\n{target}')
            self.status.setText(f'Đã nhập profile: {target.name}')
        except Exception as exc:
            QMessageBox.critical(self, 'Profile không hợp lệ', f'{type(exc).__name__}: {exc}')

    def export_community_profile(self):
        from .profile_manager import list_profiles, export_profile
        profiles = list_profiles(self.profile_dir)
        if not profiles:
            QMessageBox.information(self, 'Chưa có profile', 'Hãy tạo hoặc nhập Community Profile trước.')
            return
        labels = [f"{x['name']} [{x['asset_type']}]" for x in profiles]
        chosen, ok = QInputDialog.getItem(self, 'Xuất Community Profile', 'Chọn profile:', labels, 0, False)
        if not ok: return
        idx = labels.index(chosen)
        path, _ = QFileDialog.getSaveFileName(self, 'Lưu profile để chia sẻ', profiles[idx]['name'] + '.gbaprofile.json', 'GBA Studio Profile (*.json)')
        if not path: return
        try:
            export_profile(profiles[idx]['path'], path)
            QMessageBox.information(self, 'Đã xuất', f'Profile chia sẻ đã lưu:\n{path}')
        except Exception as exc:
            QMessageBox.critical(self, 'Lỗi xuất profile', str(exc))

    def scan_with_community_profiles(self):
        if not self.rom:
            QMessageBox.information(self, 'Chưa nạp ROM', 'Nạp ROM trước khi quét profile.')
            return
        try:
            from .profile_manager import scan_all_profiles
            matches = scan_all_profiles(self.rom.data, self.profile_dir, self.rom.header_info().get("game_code", ""))
            out = (self.output_dir if self.output_dir and self.output_dir.exists() else self.rom.path.parent) / 'Community_Profile_Matches'
            out.mkdir(parents=True, exist_ok=True)
            import json, csv
            (out / 'matches.json').write_text(json.dumps({'matches': matches,
                'note': 'Exact signature matches are candidates, not verified semantic assets.'}, indent=2), encoding='utf-8')
            with (out / 'matches.csv').open('w', newline='', encoding='utf-8-sig') as f:
                w = csv.DictWriter(f, fieldnames=['profile', 'asset_type', 'offset', 'length', 'confidence'])
                w.writeheader(); w.writerows(matches)
            self._add_external_file(out / 'matches.json')
            self.status.setText(f'Community Profile: tìm thấy {len(matches)} exact signature matches.')
            QMessageBox.information(self, 'Quét profile hoàn tất',
                f'Tìm thấy {len(matches)} vị trí khớp chữ ký.\nKết quả: {out}\n\nĐây là candidate; cần preview và xác minh.')
        except Exception as exc:
            QMessageBox.critical(self, 'Lỗi quét profile', f'{type(exc).__name__}: {exc}')

    def _clear_preview(self):
        self._selected_path = None
        self.stop_audio(); self._preview_source = QPixmap(); self.image_preview.setText('Chọn file để xem preview'); self.image_preview.setPixmap(QPixmap())
        self.text_preview.clear(); self.hex_preview.clear(); self.preview_info.setText('')

    def preview_selected_asset(self, current, previous=None):
        if current is None: return
        self.stop_audio(); path = Path(current.data(Qt.UserRole)); self._selected_path = path
        try: size = path.stat().st_size
        except OSError: size = 0
        ext = path.suffix.lower()
        if ext in IMAGE_EXTS:
            pix = QPixmap(str(path))
            if not pix.isNull():
                self._preview_source = pix; self.preview_stack.setCurrentWidget(self.image_preview); self._render_preview()
                self.preview_info.setText(f'{path.name} • {pix.width()} × {pix.height()} px • {size:,} bytes • Nearest-neighbor')
                return
        if ext in AUDIO_EXTS:
            self.preview_stack.setCurrentIndex(2); self.audio_title.setText(path.name)
            self.audio_state.setText('Sẵn sàng phát' if self.audio_player else 'Không có bộ phát âm thanh')
            self.seek_slider.setValue(0); self.seek_slider.setRange(0,0)
            if self.audio_player:
                self.audio_player.setSource(QUrl.fromLocalFile(str(path.resolve())))
            self.preview_info.setText(f'{path.name} • audio • {size:,} bytes • {ext[1:].upper()}')
            return
        if ext in TEXT_EXTS:
            try:
                content = path.read_text(encoding='utf-8-sig', errors='replace')
                self.text_preview.setPlainText(content[:200000] + ('\n… (đã giới hạn preview ở 200.000 ký tự)' if len(content)>200000 else ''))
                self.preview_stack.setCurrentWidget(self.text_preview); self.preview_info.setText(f'{path.name} • văn bản • {size:,} bytes')
                return
            except OSError: pass
        try:
            raw = path.read_bytes()[:4096]
            lines=[]
            for off in range(0,len(raw),16):
                chunk=raw[off:off+16]; hx=' '.join(f'{b:02X}' for b in chunk); asc=''.join(chr(b) if 32<=b<127 else '.' for b in chunk)
                lines.append(f'{off:08X}  {hx:<47}  {asc}')
            self.hex_preview.setPlainText('\n'.join(lines) or '(file rỗng)')
            self.preview_stack.setCurrentWidget(self.hex_preview); self.preview_info.setText(f'{path.name} • hex preview 4 KiB đầu • {size:,} bytes')
        except OSError as exc:
            self.preview_stack.setCurrentWidget(self.hex_preview); self.hex_preview.setPlainText(str(exc))

    def _render_preview(self, *_):
        if self._preview_source.isNull(): return
        target = self.image_preview.contentsRect().size()
        if target.width() <= 0 or target.height() <= 0: return
        factor = self.zoom_spin.value()
        fit = self._preview_source.scaled(target, Qt.KeepAspectRatio, Qt.FastTransformation)
        w = max(1, int(fit.width() * factor)); h = max(1, int(fit.height() * factor))
        scaled = fit.scaled(w, h, Qt.KeepAspectRatio, Qt.FastTransformation)
        self.image_preview.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._preview_source.isNull(): self._render_preview()

    def play_audio(self):
        if self.audio_player:
            self.audio_player.play()

    def toggle_audio(self):
        if not self.audio_player: return
        if self.audio_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.audio_player.pause()
        else:
            self.audio_player.play()

    def stop_audio(self):
        if self.audio_player: self.audio_player.stop()

    def seek_audio(self, value):
        if self.audio_player: self.audio_player.setPosition(value)

    def set_volume(self, value):
        if self.audio_output: self.audio_output.setVolume(value/100.0)

    def _audio_position_changed(self, value):
        if not self.seek_slider.isSliderDown(): self.seek_slider.setValue(value)

    def _audio_duration_changed(self, value): self.seek_slider.setRange(0,value)
    def _audio_state_changed(self, state): self.play_btn.setText('Ⅱ Pause' if state == QMediaPlayer.PlaybackState.PlayingState else '▶ Play')

    def open_rom_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Chọn GBA ROM', '', 'GBA ROM (*.gba *.bin);;All files (*.*)')
        if path: self.load_rom(path)

    def load_rom(self, path):
        if (self.worker and self.worker.isRunning()) or (self.deep_worker and self.deep_worker.isRunning()): return
        try:
            self.rom = GbaRom(path); info = self.rom.header_info()
            self.rom_name.setText(info['title'] or self.rom.path.name)
            self.rom_info.setText(f"{self.rom.path.name} • {info['size_mib']} MiB • {info['detected_game']} • Code: {info['game_code']}")
            self.drop_label.setText('ĐÃ NẠP ROM — SẴN SÀNG TRÍCH XUẤT'); self.extract_btn.setEnabled(True)
            self.status.setText('Đã nạp ROM. Nhấn Trích xuất Assets để bắt đầu.')
            self.asset_list.clear(); self._clear_preview()
        except Exception as exc: QMessageBox.critical(self, 'Không thể mở ROM', str(exc))

    def start_extraction(self):
        if not self.rom or (self.worker and self.worker.isRunning()): return
        self.extract_btn.setEnabled(False); self.open_btn.setEnabled(False); self.progress.setValue(0); self.progress.show()
        self.asset_list.clear(); self.image_preview.setText('Đang trích xuất assets…'); self.preview_info.setText(''); self.status.setText('Đang quét và dựng assets…')
        self.worker = FullAutoScanWorker(self.rom); self.worker.progress.connect(self.on_progress)
        self.worker.finished_results.connect(self.on_scan_finished); self.worker.failed.connect(self.on_scan_failed); self.worker.start()

    def on_progress(self, stage, percent, detail):
        self.progress.setValue(percent); self.status.setText(f'{stage}: {detail}')

    def on_scan_finished(self, result):
        try:
            base = self.rom.path.with_name(self.rom.path.stem + '_Assets'); out=base; index=2
            while out.exists(): out=base.with_name(base.name+f'_{index}'); index+=1
            info=export_full_auto_scan(result,self.rom,out); summary=info.get('summary') or {}
            rendered_count=summary.get('rendered_assets',summary.get('png_assets',info.get('exported',0)))
            self.result_path.setText(f"Đã xuất {rendered_count:,} ảnh PNG; tổng hợp báo cáo tại: {out}")
            self.populate_asset_review(out); self.status.setText('Trích xuất hoàn tất. Các file được phân loại theo mức độ xác thực trong manifest.')
            self.progress.setValue(100); self.output_dir=out
        except Exception as exc: self.on_scan_failed(str(exc))
        finally: self.extract_btn.setEnabled(True); self.open_btn.setEnabled(True)

    def on_scan_failed(self, message):
        self.status.setText('Không thể hoàn tất trích xuất.'); self.extract_btn.setEnabled(bool(self.rom)); self.open_btn.setEnabled(True)
        QMessageBox.critical(self,'Lỗi trích xuất',message)

    def open_output_folder(self):
        if self.output_dir and self.output_dir.exists(): os.startfile(str(self.output_dir))
        else: self.choose_asset_folder()

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and any(u.toLocalFile().lower().endswith(('.gba','.bin')) for u in event.mimeData().urls()): event.acceptProposedAction()

    def dropEvent(self,event):
        for url in event.mimeData().urls():
            path=url.toLocalFile()
            if path.lower().endswith(('.gba','.bin')): self.load_rom(path); break


def run_app():
    import sys
    app=QApplication(sys.argv); app.setStyle('Fusion'); window=GbaStudio(); window.show(); sys.exit(app.exec())
