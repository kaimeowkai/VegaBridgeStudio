import re
from .theme import editor_color
from PySide6.QtCore import Qt, QRect, QSize, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextFormat
from PySide6.QtWidgets import QWidget, QPlainTextEdit, QTextEdit


class Syntax(QSyntaxHighlighter):
    def highlightBlock(self, text):
        rules = [
            (r'\b(?:import|from|export|default|const|let|var|function|return|if|else|for|while|class|new|async|await|try|catch|throw|true|false|null|undefined|def|self|with|as|in|interface|type|extends|implements|readonly|public|private|protected|namespace|template|typename|struct|enum|virtual|override|constexpr|static|using|auto|void|int|double|bool|include|define)\b', "#c5a3ff"),
            (r'\b\d+(?:\.\d+)?\b', "#eebc7a"),
            (r'\b[A-Z][A-Za-z0-9_]*\b', "#8dd6e6"),
            (r'"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27|`[^`]*`', "#a8d89a"),
            (r'//.*$|#.*$', "#718597")]
        for pattern, color in rules:
            fmt = QTextCharFormat()
            role = {'#c5a3ff':'keyword', '#eebc7a':'number', '#8dd6e6':'type', '#a8d89a':'string', '#718597':'muted'}[color]
            fmt.setForeground(QColor(editor_color(role, color)))
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)
        comment = QTextCharFormat()
        comment.setForeground(QColor(editor_color('muted', "#718597")))
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

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            block=self.editor.firstVisibleBlock()
            y=event.position().y()
            while block.isValid():
                top=self.editor.blockBoundingGeometry(block).translated(self.editor.contentOffset()).top()
                if top<=y<top+self.editor.blockBoundingRect(block).height():
                    self.editor.toggle_breakpoint(block.blockNumber()+1)
                    return
                block=block.next()


class CodeEditor(QPlainTextEdit):
    breakpointsChanged=Signal(object)
    def __init__(self, path=None):
        super().__init__()
        self.path = path
        self.breakpoints=set()
        self.debug_line=None
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
        return 34 + self.fontMetrics().horizontalAdvance("9") * len(str(max(1, self.blockCount())))

    def toggle_breakpoint(self,line=None):
        line=line or self.textCursor().blockNumber()+1
        if line in self.breakpoints:self.breakpoints.remove(line)
        else:self.breakpoints.add(line)
        self.gutter.update()
        self.breakpointsChanged.emit(sorted(self.breakpoints))

    def set_debug_line(self,line=None):
        self.debug_line=line
        self.highlight_line()
        self.gutter.update()

    def refresh_theme(self):
        self.syntax.rehighlight()
        self.highlight_line()
        self.gutter.update()

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
        painter.fillRect(event.rect(), QColor(editor_color('background', "#121b26")))
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                if number+1 in self.breakpoints:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor('#e65a62'))
                    painter.drawEllipse(3,top+3,10,10)
                painter.setPen(QColor(editor_color('muted', "#718397")))
                painter.drawText(0, top, self.gutter.width() - 10, self.fontMetrics().height(), Qt.AlignmentFlag.AlignRight, str(number + 1))
            block = block.next()
            top, number = bottom, number + 1
            bottom = top + int(self.blockBoundingRect(block).height())

    def highlight_line(self):
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor(editor_color('line', "#1a2838")))
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        selections=[selection]
        if self.debug_line and 1<=self.debug_line<=self.blockCount():
            stopped=QTextEdit.ExtraSelection()
            stopped.format.setBackground(QColor('#72531c'))
            stopped.format.setForeground(QColor('#ffffff'))
            stopped.format.setProperty(QTextFormat.Property.FullWidthSelection,True)
            stopped.cursor=self.textCursor()
            stopped.cursor.setPosition(self.document().findBlockByNumber(self.debug_line-1).position())
            stopped.cursor.clearSelection()
            selections.append(stopped)
        self.setExtraSelections(selections)

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
