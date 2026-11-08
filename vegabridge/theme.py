STYLE = """
QWidget { background: #101822; color: #dae4f0; font-family: 'Segoe UI'; font-size: 10pt; }
QMainWindow::separator { width: 4px; height: 4px; background: #283648; }
QLabel#brand { font-size: 19pt; font-weight: 650; color: #f1f6ff; }
QLabel#eyebrow { color: #65dec7; font-size: 9pt; font-weight: 650; }
QLabel#muted { color: #93a8bf; }
QLabel#hero { font-size: 30pt; font-weight: 650; color: #f1f6ff; }
QLabel#pill { color: #82e4cf; background: #193b39; padding: 6px 12px; border-radius: 10px; }
QToolBar { background: #162231; spacing: 8px; padding: 7px; border-bottom: 1px solid #2a3a4c; }
QToolButton { padding: 7px 11px; border-radius: 5px; }
QToolButton:hover { background: #294059; }
QPushButton { background: #25384c; padding: 7px 13px; border: 1px solid #3a5168; border-radius: 5px; }
QPushButton:hover { background: #334f69; border-color: #6fa0b8; }
QPushButton:pressed { background: #192e42; }
QPushButton#primary { background: #50d6b7; color: #0b2521; border: none; font-weight: 650; }
QPushButton#primary:hover { background: #83efd4; }
QPushButton:disabled, QToolButton:disabled { color: #637487; background: #192330; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextBrowser { border: 1px solid #304258; border-radius: 4px; padding: 6px; selection-background-color: #355f78; }
QLineEdit:focus, QPlainTextEdit:focus { border-color: #50d6b7; }
QComboBox { padding: 6px 10px; background: #1e2d40; min-height: 20px; }
QComboBox QAbstractItemView { background: #203146; selection-background-color: #365b73; }
QPlainTextEdit { background: #121b26; }
QTreeView, QListWidget { background: #131f2d; border: none; padding: 5px; }
QTreeView::item, QListWidget::item { padding: 5px; }
QTreeView::item:selected, QListWidget::item:selected { background: #27475b; }
QTabWidget::pane { border: 1px solid #2b3c50; }
QTabBar::tab { background: #172435; padding: 10px 17px; border-right: 1px solid #26384b; color: #92a9c2; }
QTabBar::tab:selected { color: #e5f5f2; background: #203446; border-top: 2px solid #57d8bc; }
QDockWidget::title { background: #1b2a3b; padding: 8px; color: #a4b7ca; }
QMenuBar, QMenu { background: #14202e; }
QMenuBar::item:selected, QMenu::item:selected { background: #2d4b63; }
QMenu::item { padding: 7px 23px; }
QStatusBar { background: #193c46; color: #bce5e6; }
QStatusBar QLabel { background: transparent; color: #bce5e6; padding: 3px; }
QSplitter::handle { background: #2a3b4d; }
QGroupBox { border: 1px solid #32485e; border-radius: 6px; margin-top: 17px; padding-top: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; color: #a8bfd4; }
QCheckBox { spacing: 9px; }
QScrollBar:vertical { background: #14202e; width: 11px; }
QScrollBar::handle:vertical { background: #3c5269; border-radius: 5px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { color: #f0f5ff; background: #2b4257; border: 1px solid #557b91; }
"""

# Semantic palettes keep editor, output, menus, selection and controls consistent.
PALETTES = {
 'Harbor Dark':dict(bg='#101822',panel='#1b2a3b',border='#3a5168',hover='#334f69',fg='#dae4f0',muted='#a4b7ca',accent='#50d6b7',accent_text='#0b2521',line='#203446',keyword='#c7a8ff',number='#ffce8b',type='#85d8ee',string='#98d9aa'),
 'Matrix':dict(bg='#000000',panel='#07170c',border='#285e38',hover='#123b20',fg='#00ff66',muted='#75b98b',accent='#00ff66',accent_text='#001207',line='#071a0d',keyword='#00ff66',number='#b5ff74',type='#39f596',string='#85e3a0'),
 'Daylight':dict(bg='#ffffff',panel='#e6edf4',border='#9aaec0',hover='#cddde9',fg='#162435',muted='#4b6075',accent='#006b59',accent_text='#ffffff',line='#edf3f9',keyword='#7136a8',number='#975612',type='#086c85',string='#287047'),
 'Midnight Blue':dict(bg='#0a1022',panel='#15223f',border='#3c527b',hover='#233c65',fg='#e3eaff',muted='#a5b5d5',accent='#8bb2ff',accent_text='#081023',line='#172848',keyword='#a9bdff',number='#f4cc91',type='#8bdfec',string='#a8deb8'),
 'Solar Ember':dict(bg='#211814',panel='#392922',border='#72503d',hover='#593b2c',fg='#f6e9d8',muted='#c4aa96',accent='#f0ab69',accent_text='#28170a',line='#3b2b23',keyword='#ffc089',number='#d7b5fc',type='#91d9d2',string='#b5d88a'),
 'Orchid Night':dict(bg='#211a2c',panel='#372945',border='#725486',hover='#503761',fg='#f4e7ff',muted='#c6afd5',accent='#d8a4fa',accent_text='#281334',line='#3e2d4b',keyword='#e0b0ff',number='#ffc99b',type='#9ddbdc',string='#b8dfac'),
 'Forest Canopy':dict(bg='#10211c',panel='#1d3b2b',border='#4c7156',hover='#2c5038',fg='#e5f4dd',muted='#b0c7ad',accent='#a0d38d',accent_text='#142a18',line='#203d2f',keyword='#b7df8f',number='#aedceb',type='#d7baf7',string='#f3d08e'),
 'Arctic Light':dict(bg='#f1f7fb',panel='#dceaf3',border='#8da9bb',hover='#c3dcea',fg='#193448',muted='#476174',accent='#166789',accent_text='#ffffff',line='#dcecf6',keyword='#57419a',number='#865110',type='#006d71',string='#286540'),
 'Rose Quartz':dict(bg='#fff6f5',panel='#f4e0e3',border='#ba8e9c',hover='#eac9d1',fg='#4b2f3d',muted='#785665',accent='#a03b68',accent_text='#ffffff',line='#f4e3e7',keyword='#903269',number='#875006',type='#27676e',string='#386b47'),
 'High Contrast':dict(bg='#000000',panel='#101010',border='#ffffff',hover='#123c6b',fg='#ffffff',muted='#dddddd',accent='#ffff00',accent_text='#000000',line='#152e45',keyword='#ffff00',number='#66eaff',type='#f7b7ff',string='#5cff9d')
}
THEMES = list(PALETTES)
CURRENT = THEMES[0]


def palette(name):
    return PALETTES.get(name,PALETTES[THEMES[0]])


def stylesheet(name):
    import re
    c=palette(name)
    groups={
      'bg':['#101822','#121b26','#131f2d','#14202e'],
      'panel':['#162231','#25384c','#1e2d40','#203146','#172435','#203446','#1b2a3b','#192330','#193b39','#192e42','#193c46'],
      'border':['#283648','#2a3a4c','#3a5168','#304258','#2b3c50','#26384b','#2a3b4d','#32485e','#3c5269','#557b91'],
      'hover':['#294059','#334f69','#2d4b63','#355f78','#365b73','#27475b'],
      'fg':['#dae4f0','#f1f6ff','#e5f5f2','#bce5e6','#f0f5ff'],
      'muted':['#93a8bf','#92a9c2','#a4b7ca','#a8bfd4','#637487','#6fa0b8'],
      'accent':['#65dec7','#82e4cf','#50d6b7','#83efd4','#57d8bc'],
      'accent_text':['#0b2521']}
    mapping={old:c[role] for role,values in groups.items() for old in values}
    result=re.sub(r'#[0-9a-f]{6}',lambda match:mapping.get(match[0],c['panel']),STYLE)
    result+=f"\nQAbstractItemView {{selection-color:{c['fg']};}} QLineEdit, QPlainTextEdit, QTextBrowser {{selection-color:{c['fg']};}} QCheckBox::indicator {{width:14px;height:14px;border:1px solid {c['border']};background:{c['bg']};}} QCheckBox::indicator:checked {{background:{c['accent']};}}"
    if name=='Matrix':result+="\nQWidget {font-family:'Cascadia Code';}"
    return result


def apply_theme(app,name):
    from PySide6.QtGui import QPalette,QColor
    global CURRENT
    CURRENT=name if name in PALETTES else THEMES[0]
    c=palette(CURRENT);native=QPalette()
    for role,key in [(QPalette.ColorRole.Window,'bg'),(QPalette.ColorRole.Base,'bg'),(QPalette.ColorRole.AlternateBase,'panel'),
                     (QPalette.ColorRole.Text,'fg'),(QPalette.ColorRole.WindowText,'fg'),(QPalette.ColorRole.Button,'panel'),
                     (QPalette.ColorRole.ButtonText,'fg'),(QPalette.ColorRole.Highlight,'hover'),(QPalette.ColorRole.HighlightedText,'fg')]:
        native.setColor(role,QColor(c[key]))
    app.setPalette(native);app.setStyleSheet(stylesheet(CURRENT))
    for widget in app.allWidgets():
        if hasattr(widget,'refresh_theme'):widget.refresh_theme()


def editor_color(role,default):
    c=palette(CURRENT)
    return c.get({'background':'bg'}.get(role,role),default)


def preview_html(name):
    c=palette(name)
    return (f"<h3 style='color:{c['fg']}'>{name}</h3>"
            f"<p style='color:{c['muted']}'>Editor · assistant · device output</p>"
            f"<p style='font-family:monospace;color:{c['fg']}'>"
            f"<span style='color:{c['keyword']}'>const</span> greeting = "
            f"<span style='color:{c['string']}'>&quot;Hello, developer&quot;</span>;<br/>"
            f"<span style='color:{c['type']}'>launchApp</span>(<span style='color:{c['number']}'>20</span>);</p>")
