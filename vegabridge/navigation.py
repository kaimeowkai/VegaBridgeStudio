"""Local IDE navigation. Never follows links into generated or private folders."""
import os
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QLabel
from .project import SKIP, TEXT_SUFFIXES


def project_files(root, limit=5000):
    root = Path(root).resolve()
    result = []
    for folder, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [name for name in sorted(dirs) if name not in SKIP and not name.startswith('.')
                   and not (Path(folder)/name).is_symlink() and not (Path(folder)/name).is_junction()]
        for name in sorted(files):
            path = Path(folder)/name
            if name.startswith('.') or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(root) or path.stat().st_size > 2_000_000:
                    continue
            except OSError:
                continue
            result.append(path.relative_to(root).as_posix())
            if len(result) >= limit:
                return sorted(result)
    return sorted(result)


def match_score(query, text):
    query, text = query.casefold().strip(), text.casefold()
    if not query:
        return 0
    if query in text:
        return 1000 - text.index(query)
    position = 0
    gaps = 0
    for char in query:
        found = text.find(char, position)
        if found < 0:
            return None
        gaps += found-position
        position = found+1
    return 500-gaps


class Picker(QDialog):
    """Keyboard-first picker. Entries are (label, detail, payload)."""
    def __init__(self, title, entries, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(720, 460)
        self.entries = entries
        self.chosen = None
        layout = QVBoxLayout(self)
        self.query = QLineEdit()
        self.query.setPlaceholderText('Type to filter • ↑/↓ to select • Enter to open • Esc to cancel')
        layout.addWidget(self.query)
        self.results = QListWidget()
        layout.addWidget(self.results)
        self.hint = QLabel()
        layout.addWidget(self.hint)
        self.query.textChanged.connect(self.refresh)
        self.query.returnPressed.connect(self.choose)
        self.results.itemActivated.connect(lambda _: self.choose())
        self.query.installEventFilter(self)
        self.refresh()

    def refresh(self):
        self.results.clear()
        matches = []
        for title, detail, payload in self.entries:
            score = match_score(self.query.text(), title+' '+detail)
            if score is not None:
                matches.append((score, title, detail, payload))
        matches.sort(key=lambda row: (-row[0], row[1].casefold()))
        for _, title, detail, payload in matches[:150]:
            item = QListWidgetItem(title + ('    '+detail if detail else ''))
            item.setData(Qt.ItemDataRole.UserRole, payload)
            self.results.addItem(item)
        self.hint.setText(f'{len(matches)} matches' + (' • showing first 150' if len(matches)>150 else ''))
        self.results.setCurrentRow(0)

    def eventFilter(self, watched, event):
        from PySide6.QtCore import QEvent
        if watched is self.query and event.type() == QEvent.Type.KeyPress and event.key() in {Qt.Key.Key_Up, Qt.Key.Key_Down}:
            step = 1 if event.key() == Qt.Key.Key_Down else -1
            self.results.setCurrentRow(max(0,min(self.results.count()-1,self.results.currentRow()+step)))
            return True
        return super().eventFilter(watched,event)

    def choose(self):
        item = self.results.currentItem()
        if item:
            self.chosen = item.data(Qt.ItemDataRole.UserRole)
            self.accept()
