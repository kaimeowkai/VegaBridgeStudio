import re
from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextFormat
from PySide6.QtWidgets import QWidget, QPlainTextEdit, QTextEdit


class Syntax(QSyntaxHighlighter):
    def highlightBlock(self, text):
        rules = [
            (r'\b(?:import|from|export|default|const|let|var|function|return|if|else|for|while|class|new|async|await|try|catch|throw|true|false|null|undefined|def|self|with|as|in)\b', "#c5a3ff"),
            (r'\b\d+(?:\.\d+)?\b', "#eebc7a"),
            (r'\b[A-Z][A-Za-z0-9_]*\b', "#8dd6e6"),
            (r'"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27|`[^`]*`', "#a8d89a"),
            (r'//.*$|#.*$', "#718597")]
        for pattern, color in rules:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)
        comment = QTextCharFormat()
        comment.setForeground(QColor("#718597"))
        self.setCurrentBlockState(0)
        start = 0 if self.previousBlockState() == 1 else text.find("/*")
        while start >= 0:
            end = text.find("*/", start + (0 if self.previousBlockState() == 1 and start == 0 else 2))
            if end == -1:
                self.setCurrentBlockState(1)
                self.setFormat(start, len(text) - start, comment)
                break
            self.setFormat(start, end + 2 - start, comment)
            start = text.find("/*", end + 2)


class Gutter(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_gutter(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self, path=None):
        super().__init__()
        self.path = path
        self.setFont(QFont("Cascadia Code", 11))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 2)
        self.gutter = Gutter(self)
        self.syntax = Syntax(self.document())
        self.blockCountChanged.connect(self.update_margin)
        self.updateRequest.connect(self.update_gutter)
        self.cursorPositionChanged.connect(self.highlight_line)
        self.update_margin()
        self.highlight_line()

    def gutter_width(self):
        return 20 + self.fontMetrics().horizontalAdvance("9") * len(str(max(1, self.blockCount())))

    def update_margin(self, *_):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def update_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_margin()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = self.contentsRect()
        self.gutter.setGeometry(QRect(rect.left(), rect.top(), self.gutter_width(), rect.height()))

    def paint_gutter(self, event):
        painter = QPainter(self.gutter)
        painter.fillRect(event.rect(), QColor("#121b26"))
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor("#718397"))
                painter.drawText(0, top, self.gutter.width() - 10, self.fontMetrics().height(), Qt.AlignmentFlag.AlignRight, str(number + 1))
            block = block.next()
            top, number = bottom, number + 1
            bottom = top + int(self.blockBoundingRect(block).height())

    def highlight_line(self):
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor("#1a2838"))
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Tab and not event.modifiers():
            self.insertPlainText("  ")
        elif event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and not event.modifiers():
            before = self.textCursor().block().text()
            indent = re.match(r"\s*", before).group()
            super().keyPressEvent(event)
            self.insertPlainText(indent + ("  " if before.rstrip().endswith(("{", ":")) else ""))
        else:
            super().keyPressEvent(event)
