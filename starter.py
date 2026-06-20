import sys, os, json, re, time, subprocess, fnmatch, argparse, signal
from pathlib import Path

WIN = sys.platform == 'win32'
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit, QPushButton, QLabel, QLineEdit, QCheckBox, QListWidget,
    QInputDialog, QMenu, QFileDialog, QMessageBox, QSplitter, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QObject, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import (
    QFont, QColor, QTextCharFormat, QTextCursor, QPalette,
    QIcon, QPixmap, QPainter, QBrush,
)

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_p = argparse.ArgumentParser()
_p.add_argument('-c', '--config')
_args, _ = _p.parse_known_args()

if '__compiled__' in dir() or getattr(sys, 'frozen', False):
    SCRIPT_DIR = Path(sys.argv[0]).resolve().parent
else:
    SCRIPT_DIR = Path(__file__).resolve().parent
CFG_PATH = Path(_args.config).resolve() if _args.config else SCRIPT_DIR / 'starter_config.json'
ROOT = SCRIPT_DIR

_RE_ANSI = re.compile(r'(\x1b\[[0-9;]*m)')
_RE_CODE = re.compile(r'\x1b\[([0-9;]*)m')
_COLORS = {
    30: '#4e4e4e', 31: '#cd3131', 32: '#0dbc79', 33: '#e5e510',
    34: '#2472c8', 35: '#bc3fbc', 36: '#11a8cd', 37: '#e5e5e5',
    90: '#666666', 91: '#f14c4c', 92: '#23d18b', 93: '#f5f543',
    94: '#3b8eea', 95: '#d670d6', 96: '#29b8db', 97: '#ffffff',
}
_EXTS = {
    '.py', '.js', '.ts', '.tsx', '.jsx', '.json', '.html', '.css',
    '.toml', '.yaml', '.yml', '.cfg', '.ini', '.env', '.sql',
    '.rs', '.go', '.java', '.kt', '.rb', '.php', '.c', '.cpp', '.h',
}
_SKIP_DIRS = {'__pycache__', '.git', 'node_modules', '.venv', 'venv', '.idea', '.vscode'}

_ico_run = _ico_stop = None


def _make_dot(color):
    px = QPixmap(12, 12)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, 8, 8)
    p.end()
    return QIcon(px)


_proc_objs = {}

def _tree_stats(pid):
    if not _PSUTIL:
        return None, None
    try:
        if pid not in _proc_objs:
            _proc_objs[pid] = psutil.Process(pid)
        p = _proc_objs[pid]
        mem = p.memory_info().rss
        cpu = p.cpu_percent(interval=0)
        for c in p.children(recursive=True):
            try:
                if c.pid not in _proc_objs:
                    _proc_objs[c.pid] = c
                ch = _proc_objs[c.pid]
                mem += ch.memory_info().rss
                cpu += ch.cpu_percent(interval=0)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                _proc_objs.pop(c.pid, None)
        return mem / (1024 * 1024), cpu
    except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
        _proc_objs.pop(pid, None)
        return None, None


def _flush_dead():
    for pid in [k for k, v in _proc_objs.items() if not v.is_running()]:
        del _proc_objs[pid]


def load_config():
    if CFG_PATH.exists():
        try:
            return json.loads(CFG_PATH.read_text('utf-8'))
        except Exception:
            pass
    return {'services': []}

def save_config(cfg):
    CFG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), 'utf-8')


class ReaderThread(QThread):
    line = pyqtSignal(str)
    done = pyqtSignal(int)

    def __init__(self, proc):
        super().__init__()
        self._proc = proc

    def run(self):
        try:
            for raw in iter(self._proc.stdout.readline, b''):
                try: text = raw.decode('utf-8', errors='replace')
                except Exception: text = raw.decode('cp1251', errors='replace')
                text = text.rstrip('\n\r')
                if text:
                    self.line.emit(text)
        except Exception:
            pass
        try: rc = self._proc.wait(timeout=5)
        except Exception: rc = -1
        self.done.emit(rc)


class FileWatcher(QObject):
    changed = pyqtSignal(str)

    def __init__(self, path, excludes, parent=None):
        super().__init__(parent)
        self._dir = path
        self._exc = list(excludes)
        self._snap = self._scan()
        self._t = QTimer(self)
        self._t.setInterval(1500)
        self._t.timeout.connect(self._tick)
        self._t.start()

    def set_excludes(self, exc):
        self._exc = list(exc)
        self._snap = self._scan()

    def stop(self):
        self._t.stop()

    def _excluded(self, rel, fp):
        name = os.path.basename(rel)
        from_root = os.path.relpath(fp, str(ROOT)).replace('\\', '/')
        for pat in self._exc:
            for c in (rel, from_root, name):
                if fnmatch.fnmatch(c, pat):
                    return True
            for r in (rel, from_root):
                segs = r.split('/')
                for i in range(len(segs)):
                    if fnmatch.fnmatch('/'.join(segs[:i+1]), pat):
                        return True
        return False

    def _scan(self):
        out = {}
        for dp, dns, fns in os.walk(self._dir):
            dns[:] = [d for d in dns if d not in _SKIP_DIRS]
            for f in fns:
                if os.path.splitext(f)[1].lower() not in _EXTS:
                    continue
                fp = os.path.join(dp, f)
                rel = os.path.relpath(fp, self._dir).replace('\\', '/')
                if self._excluded(rel, fp):
                    continue
                try: out[rel] = os.path.getmtime(fp)
                except OSError: pass
        return out

    def _tick(self):
        cur = self._scan()
        for k, v in cur.items():
            prev = self._snap.get(k)
            if prev is None or v > prev:
                self.changed.emit(os.path.join(self._dir, k))
                self._snap = cur
                return
        for k in set(self._snap) - set(cur):
            self.changed.emit(os.path.join(self._dir, k))
            self._snap = cur
            return
        self._snap = cur


class HomeTab(QWidget):
    start_all = pyqtSignal()
    stop_all = pyqtSignal()
    restart_all = pyqtSignal()
    clear_all = pyqtSignal()

    def __init__(self, tabs, parent=None):
        super().__init__(parent)
        self._tabs = tabs
        self._setup()
        self._poll = QTimer(self)
        self._poll.setInterval(2000)
        self._poll.timeout.connect(self._refresh)
        self._poll.start()

    def _setup(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(10, 10, 10, 10)
        lo.setSpacing(8)

        hdr = QLabel('Services')
        hdr.setFont(QFont('Segoe UI' if WIN else 'sans-serif', 14, QFont.Weight.Bold))
        hdr.setStyleSheet('color:#e5e5e5;')
        lo.addWidget(hdr)

        row = QHBoxLayout()
        row.setSpacing(6)
        btns = [
            ('Start All', self.start_all),
            ('Stop All', self.stop_all),
            ('Restart All', self.restart_all),
            ('Clear Logs', self.clear_all),
        ]
        for label, sig in btns:
            b = QPushButton(label)
            b.setFixedHeight(30)
            b.clicked.connect(sig.emit)
            row.addWidget(b)
        row.addStretch()
        lo.addLayout(row)

        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(['Service', 'Status', 'PID', 'Uptime', 'CPU', 'Memory'])
        h = self.tbl.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 6):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setStyleSheet(
            'QTableWidget{gridline-color:#333}'
            'QTableWidget::item{padding:4px 8px}'
            'QHeaderView::section{background:#2d2d2d;border:1px solid #333;padding:4px 8px}'
        )
        self.tbl.cellDoubleClicked.connect(self._goto)
        lo.addWidget(self.tbl)

        self.lbl = QLabel('')
        self.lbl.setStyleSheet('color:#999;font-size:11px;')
        lo.addWidget(self.lbl)

    def _svc_tabs(self):
        out = []
        for i in range(self._tabs.count()):
            w = self._tabs.widget(i)
            if isinstance(w, ServiceTab):
                out.append((i, w))
        return out

    def _refresh(self):
        if _PSUTIL:
            _flush_dead()
        tabs = self._svc_tabs()
        self.tbl.setRowCount(len(tabs))
        tot_mem = 0.0
        nr = 0
        for row, (_, tab) in enumerate(tabs):
            s = tab.get_status()
            self.tbl.setItem(row, 0, QTableWidgetItem(s['name']))

            si = QTableWidgetItem('Running' if s['running'] else 'Stopped')
            si.setForeground(QColor('#0dbc79' if s['running'] else '#666'))
            self.tbl.setItem(row, 1, si)
            self.tbl.setItem(row, 2, QTableWidgetItem(str(s['pid']) if s['pid'] else '-'))

            up = s['uptime']
            if up is not None:
                h, r = divmod(up, 3600)
                m, sec = divmod(r, 60)
                self.tbl.setItem(row, 3, QTableWidgetItem(f'{h:02d}:{m:02d}:{sec:02d}'))
            else:
                self.tbl.setItem(row, 3, QTableWidgetItem('-'))

            cpu = s.get('cpu')
            if cpu is not None:
                ci = QTableWidgetItem(f'{cpu:.1f}%')
                if cpu > 80: ci.setForeground(QColor('#cd3131'))
                elif cpu > 40: ci.setForeground(QColor('#e5e510'))
                self.tbl.setItem(row, 4, ci)
            else:
                self.tbl.setItem(row, 4, QTableWidgetItem('-'))

            mem = s.get('memory')
            if mem is not None:
                tot_mem += mem
                self.tbl.setItem(row, 5, QTableWidgetItem(f'{mem:.1f} MB'))
            else:
                self.tbl.setItem(row, 5, QTableWidgetItem('-'))

            if s['running']:
                nr += 1

        n = len(tabs)
        if n == 0:
            self.lbl.setText('No services')
        else:
            t = f'{nr}/{n} running'
            if tot_mem > 0:
                t += f'  |  {tot_mem:.1f} MB'
            self.lbl.setText(t)

    def _goto(self, row, _):
        tabs = self._svc_tabs()
        if 0 <= row < len(tabs):
            self._tabs.setCurrentIndex(tabs[row][0])


class ServiceTab(QWidget):
    config_changed = pyqtSignal()
    status_changed = pyqtSignal()

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._proc = None
        self._reader = None
        self._watcher = None
        self._fg = None
        self._bold = False
        self._t0 = None
        self._bounce = QTimer(self)
        self._bounce.setSingleShot(True)
        self._bounce.setInterval(1000)
        self._bounce.timeout.connect(self._auto_restart)
        self._uptimer = QTimer(self)
        self._uptimer.setInterval(1000)
        self._uptimer.timeout.connect(self._tick_uptime)
        self._init_ui()
        self._load_cfg()

    def _init_ui(self):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(6, 6, 6, 6)
        lo.setSpacing(4)

        bar = QHBoxLayout()
        self.btn_go = QPushButton('Start')
        self.btn_go.setFixedWidth(70)
        self.btn_go.clicked.connect(self.start)
        self.btn_kill = QPushButton('Stop')
        self.btn_kill.setFixedWidth(70)
        self.btn_kill.clicked.connect(self.stop)
        self.btn_re = QPushButton('Restart')
        self.btn_re.setFixedWidth(70)
        self.btn_re.clicked.connect(self.restart)
        self.chk_watch = QCheckBox('Auto-reload')
        self.chk_watch.toggled.connect(self._toggle_watch)
        self.chk_boot = QCheckBox('Auto-start')
        self.chk_boot.toggled.connect(self._toggle_boot)
        btn_cls = QPushButton('Clear')
        btn_cls.setFixedWidth(55)
        btn_cls.clicked.connect(self.cls)
        bar.addWidget(self.btn_go)
        bar.addWidget(self.btn_kill)
        bar.addWidget(self.btn_re)
        bar.addSpacing(10)
        bar.addWidget(self.chk_watch)
        bar.addWidget(self.chk_boot)
        bar.addStretch()
        bar.addWidget(btn_cls)
        lo.addLayout(bar)

        for lbl, attr, ph in [
            ('Cmd:', 'inp_cmd', ''),
            ('Dir:', 'inp_cwd', ''),
            ('Watch:', 'inp_watch', 'empty = same as Dir'),
        ]:
            r = QHBoxLayout()
            r.addWidget(QLabel(lbl))
            inp = QLineEdit()
            inp.setPlaceholderText(ph)
            inp.editingFinished.connect(self._field_changed)
            setattr(self, attr, inp)
            r.addWidget(inp)
            if lbl in ('Dir:', 'Watch:'):
                b = QPushButton('...')
                b.setFixedWidth(30)
                target = attr
                b.clicked.connect(lambda _, t=target: self._browse(t))
                r.addWidget(b)
            lo.addLayout(r)

        sp = QSplitter(Qt.Orientation.Vertical)
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setMaximumBlockCount(5000)
        self.out.setFont(QFont('Consolas' if WIN else 'Monospace', 9))
        self.out.setStyleSheet('background:#1e1e1e;color:#d4d4d4;')
        sp.addWidget(self.out)

        irow = QHBoxLayout()
        self.inp_stdin = QLineEdit()
        self.inp_stdin.setPlaceholderText('stdin...')
        self.inp_stdin.setFont(QFont('Consolas' if WIN else 'Monospace', 9))
        self.inp_stdin.returnPressed.connect(self._send_stdin)
        self.inp_stdin.setEnabled(False)
        btn_send = QPushButton('Send')
        btn_send.setFixedWidth(50)
        btn_send.clicked.connect(self._send_stdin)
        self.btn_send = btn_send
        iw = QWidget()
        iw.setLayout(irow)
        irow.setContentsMargins(0, 0, 0, 0)
        irow.addWidget(self.inp_stdin)
        irow.addWidget(btn_send)
        sp.addWidget(iw)

        box = QGroupBox('Exclusions')
        bl = QVBoxLayout(box)
        bl.setContentsMargins(4, 4, 4, 4)
        self.exc = QListWidget()
        self.exc.setMaximumHeight(100)
        bl.addWidget(self.exc)
        eb = QHBoxLayout()
        ba = QPushButton('+ Pattern')
        ba.clicked.connect(self._exc_add)
        bf = QPushButton('+ Folder')
        bf.clicked.connect(self._exc_folder)
        bd = QPushButton('- Remove')
        bd.clicked.connect(self._exc_del)
        eb.addWidget(ba); eb.addWidget(bf); eb.addWidget(bd); eb.addStretch()
        bl.addLayout(eb)
        sp.addWidget(box)
        sp.setStretchFactor(0, 3)
        sp.setStretchFactor(1, 0)
        sp.setStretchFactor(2, 1)
        lo.addWidget(sp)

        self.lbl_st = QLabel('Stopped')
        lo.addWidget(self.lbl_st)
        self._set_btns(False)

    def _load_cfg(self):
        self.inp_cmd.setText(self._cfg.get('command', ''))
        self.inp_cwd.setText(self._cfg.get('cwd', ''))
        self.inp_watch.setText(self._cfg.get('watch_dir', ''))
        self.chk_watch.setChecked(self._cfg.get('auto_restart', False))
        self.chk_boot.setChecked(self._cfg.get('auto_start', False))
        self.exc.clear()
        for p in self._cfg.get('watch_exclude', []):
            self.exc.addItem(p)

    def _save_cfg(self):
        self._cfg['command'] = self.inp_cmd.text().strip()
        self._cfg['cwd'] = self.inp_cwd.text().strip()
        self._cfg['watch_dir'] = self.inp_watch.text().strip()
        self._cfg['auto_restart'] = self.chk_watch.isChecked()
        self._cfg['auto_start'] = self.chk_boot.isChecked()
        self._cfg['watch_exclude'] = [self.exc.item(i).text() for i in range(self.exc.count())]

    def _cwd(self):
        c = self.inp_cwd.text().strip()
        if not c: return str(ROOT)
        return c if os.path.isabs(c) else str(ROOT / c)

    def _log(self, text):
        cur = self.out.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        if cur.position() > 0:
            cur.insertText('\n')
        for part in _RE_ANSI.split(text):
            m = _RE_CODE.fullmatch(part)
            if m:
                codes = [int(x) for x in m.group(1).split(';') if x] if m.group(1) else [0]
                for c in codes:
                    if c == 0: self._fg = None; self._bold = False
                    elif c == 1: self._bold = True
                    elif c in _COLORS: self._fg = _COLORS[c]
                    elif c == 39: self._fg = None
                continue
            if not part: continue
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(self._fg or '#d4d4d4'))
            if self._bold: fmt.setFontWeight(700)
            cur.insertText(part, fmt)
        self.out.setTextCursor(cur)
        self.out.ensureCursorVisible()

    def cls(self):
        self.out.clear()
        self._fg = None
        self._bold = False

    def start(self):
        if self._proc and self._proc.poll() is None:
            return
        cmd = self.inp_cmd.text().strip()
        if not cmd:
            self._log('\x1b[31mNo command\x1b[0m')
            return
        cwd = self._cwd()
        if not os.path.isdir(cwd):
            self._log(f'\x1b[31mDir not found: {cwd}\x1b[0m')
            return
        self._log(f'\x1b[36m--- Starting: {cmd}\x1b[0m')
        self._log(f'\x1b[36m    CWD: {cwd}\x1b[0m')
        env = os.environ.copy()
        env.update({'FORCE_COLOR': '1', 'CLICOLOR_FORCE': '1', 'PYTHONUNBUFFERED': '1'})
        env.update(self._cfg.get('env', {}))
        kw = dict(cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                  stderr=subprocess.STDOUT, shell=True, env=env)
        if WIN:
            kw['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kw['preexec_fn'] = os.setsid
        try:
            self._proc = subprocess.Popen(cmd, **kw)
        except Exception as e:
            self._log(f'\x1b[31mFailed: {e}\x1b[0m')
            self._set_btns(False)
            return
        self._t0 = time.time()
        self._uptimer.start()
        self._reader = ReaderThread(self._proc)
        self._reader.line.connect(self._log)
        self._reader.done.connect(self._exited)
        self._reader.start()
        self._set_btns(True)
        self._watch_start()
        self.status_changed.emit()

    def stop(self):
        self._watch_stop()
        self._bounce.stop()
        if not self._proc: return
        pid = self._proc.pid
        self._log(f'\x1b[33m--- Stopping PID {pid}\x1b[0m')
        try:
            if WIN:
                subprocess.Popen(
                    ['taskkill', '/F', '/T', '/PID', str(pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
        except Exception: pass
        self._proc = None
        self._t0 = None
        self._uptimer.stop()
        self._set_btns(False)
        self.lbl_st.setText('Stopped')
        self.status_changed.emit()

    def restart(self):
        self.stop()
        QTimer.singleShot(300, self.start)

    def _auto_restart(self):
        self._log('\x1b[35m--- Auto-reload\x1b[0m')
        self.stop()
        QTimer.singleShot(300, self.start)

    def _exited(self, rc):
        self._uptimer.stop()
        self._t0 = None
        self._proc = None
        c = '32' if rc == 0 else '31'
        self._log(f'\x1b[{c}m--- Exited ({rc})\x1b[0m')
        self._set_btns(False)
        self.lbl_st.setText(f'Exited ({rc})')
        self.status_changed.emit()

    def _watch_start(self):
        if not self.chk_watch.isChecked(): return
        wd = self.inp_watch.text().strip() or self._cfg.get('cwd', '')
        if not wd: wd = self._cwd()
        if not os.path.isabs(wd): wd = str(ROOT / wd)
        if not os.path.isdir(wd):
            self._log(f'\x1b[31m--- Bad watch dir: {wd}\x1b[0m')
            return
        self._watch_stop()
        ex = [self.exc.item(i).text() for i in range(self.exc.count())]
        self._watcher = FileWatcher(wd, ex, self)
        self._watcher.changed.connect(self._on_changed)
        self._log(f'\x1b[36m--- Watching: {wd}\x1b[0m')

    def _watch_stop(self):
        if self._watcher:
            self._watcher.stop()
            self._watcher = None

    def _on_changed(self, path):
        if not self._bounce.isActive():
            rel = os.path.relpath(path, str(ROOT)).replace('\\', '/')
            self._log(f'\x1b[35m--- Changed: {rel}\x1b[0m')
        self._bounce.start()

    def get_status(self):
        alive = self._proc is not None and self._proc.poll() is None
        pid = self._proc.pid if alive else None
        up = int(time.time() - self._t0) if self._t0 and alive else None
        mem, cpu = _tree_stats(pid) if alive and pid else (None, None)
        return {'name': self._cfg.get('name', ''), 'running': alive,
                'pid': pid, 'uptime': up, 'memory': mem, 'cpu': cpu}

    def is_running(self):
        return self._proc is not None and self._proc.poll() is None

    def _set_btns(self, on):
        self.btn_go.setEnabled(not on)
        self.btn_kill.setEnabled(on)
        self.btn_re.setEnabled(on)
        self.inp_stdin.setEnabled(on)
        self.btn_send.setEnabled(on)
        if on and self._proc:
            self.lbl_st.setText(f'PID {self._proc.pid}')

    def _tick_uptime(self):
        if self._t0 and self._proc and self._proc.poll() is None:
            e = int(time.time() - self._t0)
            self.lbl_st.setText(f'PID {self._proc.pid} | {e//3600:02d}:{e%3600//60:02d}:{e%60:02d}')

    def _send_stdin(self):
        if not self._proc or self._proc.poll() is not None:
            return
        text = self.inp_stdin.text()
        self.inp_stdin.clear()
        self._log(f'\x1b[33m> {text}\x1b[0m')
        try:
            self._proc.stdin.write((text + '\n').encode())
            self._proc.stdin.flush()
        except Exception:
            pass

    def _field_changed(self):
        self._save_cfg()
        self.config_changed.emit()

    def _toggle_watch(self, on):
        self._cfg['auto_restart'] = on
        self.config_changed.emit()
        if on and self._proc and self._proc.poll() is None:
            self._watch_start()
        elif not on:
            self._watch_stop()

    def _toggle_boot(self, on):
        self._cfg['auto_start'] = on
        self.config_changed.emit()

    def _exc_add(self):
        t, ok = QInputDialog.getText(self, 'Exclusion', 'Pattern:')
        if ok and t.strip():
            self.exc.addItem(t.strip())
            self._exc_save()

    def _exc_folder(self):
        d = QFileDialog.getExistingDirectory(self, 'Exclude', self._cwd())
        if d:
            try:
                wd = self.inp_watch.text().strip()
                if wd and not os.path.isabs(wd): wd = str(ROOT / wd)
                base = wd if wd else self._cwd()
                self.exc.addItem(os.path.relpath(d, base).replace('\\', '/') + '/*')
            except ValueError:
                self.exc.addItem(d)
            self._exc_save()

    def _exc_del(self):
        r = self.exc.currentRow()
        if r >= 0:
            self.exc.takeItem(r)
            self._exc_save()

    def _exc_save(self):
        self._cfg['watch_exclude'] = [self.exc.item(i).text() for i in range(self.exc.count())]
        self.config_changed.emit()
        if self._watcher:
            self._watcher.set_excludes(self._cfg['watch_exclude'])

    def _browse(self, target):
        d = QFileDialog.getExistingDirectory(self, 'Select', self._cwd())
        if d:
            getattr(self, target).setText(d)
            self._field_changed()

    def cleanup(self):
        self.stop()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('RtedStarter')
        self.setMinimumSize(750, 500)
        self.resize(950, 650)

        self._cfg = load_config()
        self._tw = QTabWidget()
        self._tw.setMovable(True)
        self._tw.tabBar().tabMoved.connect(self._moved)
        self._tw.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tw.customContextMenuRequested.connect(self._ctx)
        self.setCentralWidget(self._tw)

        self._home = HomeTab(self._tw, self)
        self._tw.addTab(self._home, 'Home')
        self._home.start_all.connect(self._all_start)
        self._home.stop_all.connect(self._all_stop)
        self._home.restart_all.connect(self._all_restart)
        self._home.clear_all.connect(self._all_clear)

        plus = QPushButton('+')
        plus.setFixedSize(28, 28)
        plus.clicked.connect(self._add)
        self._tw.setCornerWidget(plus, Qt.Corner.TopRightCorner)

        for s in self._cfg.get('services', []):
            self._mk_tab(s)

        self._ict = QTimer(self)
        self._ict.setInterval(2000)
        self._ict.timeout.connect(self._icons)
        self._ict.start()

        QTimer.singleShot(500, self._autostart)

    def _mk_tab(self, cfg):
        t = ServiceTab(cfg, self)
        t.config_changed.connect(self._persist)
        t.status_changed.connect(self._icons)
        i = self._tw.addTab(t, cfg.get('name', 'Service'))
        self._tw.setTabIcon(i, _ico_stop)
        return i

    def _add(self):
        name, ok = QInputDialog.getText(self, 'New', 'Name:')
        if not ok or not name.strip(): return
        s = {'name': name.strip(), 'command': '', 'cwd': '',
             'auto_restart': False, 'auto_start': False,
             'watch_dir': '', 'watch_exclude': []}
        self._cfg.setdefault('services', []).append(s)
        self._tw.setCurrentIndex(self._mk_tab(s))
        self._persist()

    def _ctx(self, pos):
        i = self._tw.tabBar().tabAt(pos)
        if i < 1: return
        m = QMenu(self)
        a_ren = m.addAction('Rename')
        a_del = m.addAction('Delete')
        m.addSeparator()
        a_l = m.addAction('Move Left')
        a_r = m.addAction('Move Right')
        a_l.setEnabled(i > 1)
        a_r.setEnabled(i < self._tw.count() - 1)
        a = m.exec(self._tw.tabBar().mapToGlobal(pos))
        if a == a_ren:
            n, ok = QInputDialog.getText(self, 'Rename', 'Name:', text=self._tw.tabText(i))
            if ok and n.strip():
                self._tw.setTabText(i, n.strip())
                self._tw.widget(i)._cfg['name'] = n.strip()
                self._persist()
        elif a == a_del:
            if QMessageBox.question(self, '', f'Delete "{self._tw.tabText(i)}"?') == QMessageBox.StandardButton.Yes:
                self._tw.widget(i).cleanup()
                self._tw.removeTab(i)
                self._persist()
        elif a == a_l and i > 1:
            self._tw.tabBar().moveTab(i, i-1)
        elif a == a_r:
            self._tw.tabBar().moveTab(i, i+1)

    def _moved(self, fr, to):
        if fr == 0 or to == 0:
            self._tw.tabBar().moveTab(to, fr)
            return
        self._persist()

    def _persist(self):
        svcs = []
        for i in range(self._tw.count()):
            w = self._tw.widget(i)
            if not isinstance(w, ServiceTab): continue
            w._save_cfg()
            c = dict(w._cfg)
            c['name'] = self._tw.tabText(i)
            svcs.append(c)
        self._cfg['services'] = svcs
        save_config(self._cfg)

    def _icons(self):
        for i in range(self._tw.count()):
            w = self._tw.widget(i)
            if isinstance(w, ServiceTab):
                self._tw.setTabIcon(i, _ico_run if w.is_running() else _ico_stop)

    def _autostart(self):
        for i in range(self._tw.count()):
            w = self._tw.widget(i)
            if isinstance(w, ServiceTab) and w._cfg.get('auto_start'):
                w.start()

    def _each(self, fn):
        for i in range(self._tw.count()):
            w = self._tw.widget(i)
            if isinstance(w, ServiceTab): fn(w)

    def _all_start(self):
        self._each(lambda t: t.start() if not t.is_running() else None)

    def _all_stop(self):
        self._each(lambda t: t.stop() if t.is_running() else None)

    def _all_restart(self):
        self._each(lambda t: t.restart())

    def _all_clear(self):
        self._each(lambda t: t.cls())

    def closeEvent(self, ev):
        self._each(lambda t: t.cleanup())
        ev.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    p.setColor(QPalette.ColorRole.WindowText, QColor(212, 212, 212))
    p.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(35, 35, 35))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(50, 50, 50))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(212, 212, 212))
    p.setColor(QPalette.ColorRole.Text, QColor(212, 212, 212))
    p.setColor(QPalette.ColorRole.Button, QColor(45, 45, 45))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(212, 212, 212))
    p.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(p)
    _ico_run = _make_dot('#0dbc79')
    _ico_stop = _make_dot('#666666')
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
