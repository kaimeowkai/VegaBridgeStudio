import re
from PySide6.QtWidgets import QApplication
from vegabridge import theme
from vegabridge.editor import CodeEditor


def luminance(color):
    values=[int(color[i:i+2],16)/255 for i in [1,3,5]]
    values=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
    return sum(v*w for v,w in zip(values,[.2126,.7152,.0722]))


def contrast(a,b):
    lo,hi=sorted([luminance(a),luminance(b)])
    return (hi+.05)/(lo+.05)


def test_ten_distinct_themes_keep_source_readable_through_live_switches():
    app=QApplication.instance() or QApplication([])
    editor=CodeEditor();editor.setPlainText('const greeting = "Hello, developer";\nlaunchApp(20);')
    try:
        assert len(theme.THEMES)==10
        assert len({theme.stylesheet(name) for name in theme.THEMES})==10
        for name in theme.THEMES:
            c=theme.palette(name)
            assert all(re.fullmatch(r'#[0-9a-fA-F]{6}',value) for value in c.values())
            for role in ['fg','muted','keyword','number','type','string']:
                assert contrast(c[role],c['bg'])>=4.5,(name,role)
            assert contrast(c['fg'],c['panel'])>=4.5
            assert contrast(c['accent_text'],c['accent'])>=4.5
            theme.apply_theme(app,name);app.processEvents()
            assert theme.CURRENT==name
            assert theme.editor_color('background','wrong')==c['bg']
            assert editor.toPlainText().startswith('const greeting')
            assert name in theme.preview_html(name)
    finally:
        theme.apply_theme(app,'Harbor Dark');editor.deleteLater()
