"""Native Qt desktop workbench. All work runs locally unless the user sends AI chat."""
import argparse
import difflib
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, Slot, QSortFilterProxyModel, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QFont, QIcon, QPixmap, QTextCursor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QPlainTextEdit, QTextBrowser, QLineEdit, QComboBox, QTabWidget,
    QDockWidget, QToolBar, QTreeView, QFileDialog, QDialog, QFormLayout, QDialogButtonBox,
    QMessageBox, QSpinBox, QCheckBox, QSplitter, QGroupBox, QSizePolicy, QFileSystemModel, QListWidget, QListWidgetItem, QInputDialog)
from . import __version__
from .storage import load_settings, save_settings, SecretStore, user_dir, atomic_write
from .process import Runner, Cancelled
from .project import create_project, metadata, build, SKIP, TEXT_SUFFIXES, inside, safe_context
from .devices import LocalBridge, RemoteEmulator, endpoint
from .package import inspect_package
from .native_vm import NativeVm
from .assistant import stream_chat, validate_url, credential_name
from .editor import CodeEditor
from .theme import STYLE, THEMES, apply_theme
from .conversations import ConversationStore, INTRO
from .agent_host import AgentHost


class Job(QThread):
    line = Signal(str)
    result = Signal(object)
    failed = Signal(str)
    delta = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.cancelled = threading.Event()

    def run(self):
        try:
            result = self.fn(Runner(self.line.emit, self.cancelled), self.delta.emit)
            self.result.emit(result)
        except Cancelled:
            self.failed.emit("Cancelled")
        except Exception as error:
            self.failed.emit(str(error))


class ProjectFilter(QSortFilterProxyModel):
    def filterAcceptsRow(self, row, parent):
        index = self.sourceModel().index(row, 0, parent)
        return self.sourceModel().fileName(index) not in SKIP


def button(text, fn, primary=False):
    control = QPushButton(text)
    if primary:
        control.setObjectName("primary")
    control.clicked.connect(fn)
    return control


def label(text, kind="muted"):
    control = QLabel(text)
    control.setObjectName(kind)
    control.setWordWrap(True)
    return control


def read_only(text=""):
    control = QPlainTextEdit(text)
    control.setReadOnly(True)
    control.setFont(QFont("Cascadia Code", 10))
    control.setMaximumBlockCount(8000)
    return control


class SettingsDialog(QDialog):
    def __init__(self, settings, parent):
        super().__init__(parent)
        self.setWindowTitle("VegaBridge Studio — Settings")
        self.resize(770, 600)
        self.fields = {}
        self.settings = dict(settings)
        outer = QVBoxLayout(self)
        tabs = QTabWidget()
        outer.addWidget(tabs)
        def page(title, description):
            widget = QWidget()
            form = QFormLayout(widget)
            form.setSpacing(13)
            form.addRow(label(description))
            tabs.addTab(widget, title)
            return form
        def field(form, title, name, browse=False):
            entry = QLineEdit(str(settings[name]))
            self.fields[name] = entry
            if browse:
                row = QWidget()
                layout = QHBoxLayout(row)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.addWidget(entry)
                def choose():
                    if browse == "folder":
                        path = QFileDialog.getExistingDirectory(self, "Select " + title)
                    else:
                        path, _ = QFileDialog.getOpenFileName(self, "Select " + title)
                    if path:
                        entry.setText(path)
                layout.addWidget(button("Browse…", choose))
                form.addRow(title, row)
            else:
                form.addRow(title, entry)
        tools = page("Windows tools", "Use your installed Windows Node.js and Android platform-tools. Amazon's SDK is not bundled.")
        field(tools, "Node.js (node.exe)", "node", True)
        field(tools, "Device bridge (adb.exe)", "adb", True)
        field(tools, "Dedicated bridge port", "bridge_port")
        tools.addRow(label("USB: enable Developer Mode, select USB connection mode, and use a data cable. Wireless: choose TCP/IP on the device. Switching connection mode may require a reboot."))
        sdk = page("SDK tools", "Windows-native compilers and owner-supplied Vega target libraries. SDK source files remain outside the IDE distribution.")
        field(sdk, "Windows clang++ executable", "clang", True)
        field(sdk, "Imported SDK root (sysroot-* folders)", "sdk_root", "folder")
        field(sdk, "Matching Windows Hermes compiler (optional)", "hermes", True)
        field(sdk, "Windows OpenSSL (CMS verification)", "openssl", True)
        field(sdk, "TurboModule generator cli.js (optional)", "codegen", True)
        appearance = page("Appearance", "Choose a theme. Matrix uses neon green text on black backgrounds, including the editor and output panes.")
        theme = QComboBox()
        theme.addItems(THEMES)
        theme.setCurrentText(settings["theme"])
        self.fields["theme"] = theme
        appearance.addRow("Theme", theme)
        from .theme import palette,preview_html
        preview=QLabel()
        preview.setMinimumHeight(180)
        preview.setContentsMargins(18,12,18,12)
        def refresh_preview(name):
            c=palette(name)
            preview.setStyleSheet('background:'+c['bg']+';color:'+c['fg']+';border:1px solid '+c['border']+';border-radius:8px;')
            preview.setText(preview_html(name))
        theme.currentTextChanged.connect(refresh_preview)
        refresh_preview(theme.currentText())
        appearance.addRow(preview)
        appearance.addRow(label('Ten included themes. The preview updates here; Save applies your choice across the workspace, editor, assistant and task output.'))
        ai = page("AI assistant", "Connect with your own API key or a local compatible model server. Requests go only to the endpoint below; account costs and limits apply.")
        field(ai, "Base URL", "endpoint")
        protocol = QComboBox()
        protocol.addItems(["Responses", "Chat Completions"])
        protocol.setCurrentText(settings["protocol"])
        self.fields["protocol"] = protocol
        ai.addRow("API protocol", protocol)
        field(ai, "Model", "model")
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("Leave blank to keep stored key; enter a new key to replace it")
        ai.addRow("API key", self.key)
        self.forget = QCheckBox("Remove the saved API key")
        ai.addRow(self.forget)
        ai.addRow(label("Keys and local conversations use Windows CurrentUser encryption outside your projects. Workspace agent can read and edit current project source and control the selected developer target; Discussion only has no tools. Project changes preserve your discussion."))
        ai.addRow(button("Open official ChatGPT integration documentation", lambda: QDesktopServices.openUrl(QUrl("https://developers.openai.com/siwc/token-sharing-open-source"))))
        mode = QComboBox()
        mode.addItems(["API key / local model", "ChatGPT plan"])
        mode.setCurrentText(settings["auth_mode"])
        self.fields["auth_mode"] = mode
        ai.addRow("Connection", mode)
        ai.addRow(label("Use ChatGPT accounts in the assistant panel to sign in, select an account/model, manage usage or sign out. ChatGPT tokens are sent only to the official Responses API."))
        native = page("Native emulator", "Run Vega OS locally in Windows QEMU with your own SDK development images. No WSL, Docker or remote host is used. First boot may restart during setup.")
        field(native, "Windows QEMU executable", "qemu", True)
        field(native, "VVD image_files folder", "vega_images", "folder")
        field(native, "Writable VM folder (optional)", "vm_folder", "folder")
        field(native, "Local device port", "vm_port")
        accel = QComboBox()
        accel.addItems(["whpx", "tcg"])
        accel.setCurrentText(settings["vm_accel"])
        self.fields["vm_accel"] = accel
        native.addRow("Acceleration", accel)
        native.addRow(label("WHPX uses an already configured Windows hypervisor. TCG is software emulation and can be much slower. The IDE does not change Windows security or hypervisor settings. QEMU must include GTK, OpenGL and virgl support. SDK images stay read-only; VM data is saved separately."))
        emulator = page("Remote VVD (optional)", "Optional existing Ubuntu/macOS host using the official Amazon tools. The Native emulator tab configures the Windows VM.")
        field(emulator, "Optional SSH host", "ssh_host")
        field(emulator, "SSH port", "ssh_port")
        field(emulator, "SSH key (optional)", "ssh_key", True)
        field(emulator, "Vega CLI path on host", "vega_cli")
        field(emulator, "VVD serial", "emulator_serial")
        emulator.addRow(label("Uses existing SSH trust and key authentication with strict host verification. Set up the official SDK and SSH access yourself on that host. No SDK image or virtual machine is included."))
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(self.commit)
        controls.rejected.connect(self.reject)
        outer.addWidget(controls)

    def commit(self):
        try:
            for name, entry in self.fields.items():
                value = entry.currentText() if isinstance(entry, QComboBox) else entry.text().strip()
                if name in {"bridge_port", "ssh_port"}:
                    value = int(value)
                    if not 1 <= value <= 65535:
                        raise ValueError("Ports must be between 1 and 65535")
                self.settings[name] = value
            validate_url(self.settings["endpoint"])
            secrets = SecretStore()
            if self.forget.isChecked():
                secrets.remove(credential_name(self.settings))
            elif self.key.text():
                secrets.set(credential_name(self.settings), self.key.text())
            save_settings(self.settings)
            self.accept()
        except Exception as error:
            QMessageBox.warning(self, "Settings not saved", str(error))


class Studio(AgentHost, QMainWindow):
    authorization_requested = Signal(str)
    agent_requested = Signal(object)
    agent_ui_effect = Signal(object)
    agent_history = Signal(object)

    def __init__(self, project=None):
        super().__init__()
        self.setWindowTitle("VegaBridge Studio • Native Windows Preview")
        self.resize(1540, 960)
        self.setMinimumSize(1080, 720)
        self.settings = load_settings()
        self.authorization_requested.connect(lambda url: QDesktopServices.openUrl(QUrl(url)))
        self.agent_requested.connect(self.prepare_agent_tool)
        self.agent_ui_effect.connect(self.apply_agent_effect)
        self.agent_history.connect(self.agent_checkpoint)
        self.project = None
        self.jobs = set()
        self.history = []
        self.conversations=ConversationStore()
        self.chat_key=self.settings.get('chat_active','planning')
        self.conversation_label='Planning'
        self.conversation_project=''
        self.pending_prompt=''
        self._conversation_loading=False
        self.last_answer = ""
        self.ai_job = None
        self.vm_job = None
        self.native_vm = None
        self.awake_job = None
        self.source_snapshot = None
        self.last_package = None
        self._create_toolbar()
        self._create_workspace()
        self._create_project_dock()
        self._create_assistant_dock()
        self.chat_save_timer=QTimer(self)
        self.chat_save_timer.setSingleShot(True)
        self.chat_save_timer.setInterval(700)
        self.chat_save_timer.timeout.connect(self.save_conversation)
        self.prompt.textChanged.connect(lambda:self.chat_save_timer.start())
        self.load_conversation(self.chat_key,save_current=False)
        self._create_output_dock()
        self._create_menus()
        self.statusBar().showMessage("Ready  •  Community developer preview  •  Windows native")
        self.cursor_status = QLabel("UTF-8")
        self.statusBar().addPermanentWidget(self.cursor_status)
        if project:
            self.open_project(project)

    @Slot(object)
    def prepare_agent_tool(self,request):
        # Register real Qt slots on the QObject subclass. A plain Python mixin
        # callback must not be allowed to mutate widgets on an AI worker thread.
        AgentHost.prepare_agent_tool(self,request)

    @Slot(object)
    def apply_agent_effect(self,action):
        action()

    @Slot(object)
    def agent_checkpoint(self,history):
        AgentHost.agent_checkpoint(self,history)

    def _create_toolbar(self):
        toolbar = QToolBar("Workbench")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        brand = QLabel("  V  /  VEGABRIDGE   ")
        brand.setObjectName("eyebrow")
        toolbar.addWidget(brand)
        for title, fn in [("New project", self.new_project), ("Open", self.choose_project), ("Save all", self.save_all)]:
            toolbar.addAction(title, fn)
        toolbar.addSeparator()
        self.build_action = toolbar.addAction("Build package", self.build_project)
        self.run_action = toolbar.addAction("Install + run", self.run_project)
        toolbar.addSeparator()
        self.target = QComboBox()
        self.target.setMinimumWidth(220)
        self.target.setToolTip("Choose an online USB, wireless or emulator target")
        self.target.addItem("No device selected", None)
        toolbar.addWidget(self.target)
        toolbar.addAction("Refresh devices", self.refresh_devices)
        toolbar.addSeparator()
        toolbar.addAction("Settings", self.show_settings)
        self.cancel_action = toolbar.addAction("Cancel tasks", self.cancel_tasks)

    def _create_workspace(self):
        self.center = QTabWidget()
        self.center.setDocumentMode(True)
        self.setCentralWidget(self.center)
        self.editors = QTabWidget()
        self.editors.setTabsClosable(True)
        self.editors.setMovable(True)
        self.editors.tabCloseRequested.connect(self.close_editor)
        self.editors.currentChanged.connect(self.cursor_info)
        code_page = QWidget()
        layout = QVBoxLayout(code_page)
        layout.setContentsMargins(0, 0, 0, 0)
        find_row = QHBoxLayout()
        self.find = QLineEdit()
        self.find.setPlaceholderText("Find in current file  •  Ctrl+F")
        self.find.returnPressed.connect(self.find_next)
        find_row.addWidget(self.find)
        find_row.addWidget(button("Next", self.find_next))
        layout.addLayout(find_row)
        layout.addWidget(self.editors)
        self.center.addTab(code_page, "Code")
        welcome = QWidget()
        welcome_layout = QVBoxLayout(welcome)
        welcome_layout.setContentsMargins(42, 40, 42, 35)
        welcome_layout.addWidget(label("VEGABRIDGE STUDIO  /  0.2 PREVIEW", "eyebrow"))
        welcome_layout.addWidget(label("Build for Vega.\nWork from Windows.", "hero"))
        welcome_layout.addWidget(label("A focused workspace for your project, connected device, and coding assistant. Choose a JavaScript/TypeScript starter or an original sample template."))
        welcome_layout.addSpacing(20)
        for title, fn in [("Create a Vega project", self.new_project), ("Open an existing project", self.choose_project), ("Configure tools and AI", self.show_settings)]:
            control = button(title, fn, title.startswith("Create"))
            control.setMaximumWidth(330)
            welcome_layout.addWidget(control)
        welcome_layout.addStretch()
        welcome_layout.addWidget(label("WINDOWS BUILD   →   SIGNED VPKG   →   USB / WI-FI DEVICE", "eyebrow"))
        welcome_layout.addWidget(label("Independent community preview. Native Windows build, device tools and Vega VM host. JS/TS app builds, C/C++ cross compilation and TurboModule scaffolding tools. No Amazon SDK or device image is bundled."))
        self.editors.addTab(welcome, "Welcome")
        self._device_lab()

    def _device_lab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        head = QHBoxLayout()
        head.addWidget(label("DEVICE LAB", "eyebrow"))
        head.addStretch()
        head.addWidget(button("Capture screen", self.capture_screen, True))
        layout.addLayout(head)
        connect_row = QHBoxLayout()
        self.address = QLineEdit()
        self.address.setPlaceholderText("Wireless target: device IP or hostname:5555")
        self.address.returnPressed.connect(self.connect_device)
        connect_row.addWidget(self.address)
        connect_row.addWidget(button("Connect Wi-Fi", self.connect_device))
        connect_row.addWidget(button("Find USB devices", self.refresh_devices))
        layout.addLayout(connect_row)
        self.screen = QLabel("DEVICE SCREEN\n\nSelect a target, then capture its display.")
        self.screen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen.setMinimumHeight(220)
        self.screen.setStyleSheet("background:#090e15; color:#7390aa; border:1px solid #33475e; border-radius:8px;")
        self.screen.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.screen, 1)
        remote = QHBoxLayout()
        for text, key in [("Home", "KEY_HOMEPAGE"), ("Back", "KEY_BACK"), ("←", "KEY_LEFT"), ("↑", "KEY_UP"), ("OK", "KEY_ENTER"), ("↓", "KEY_DOWN"), ("→", "KEY_RIGHT")]:
            remote.addWidget(button(text, lambda checked=False, key=key: self.device_command("Remote " + key, "inputd-cli button_press " + key)))
        layout.addLayout(remote)
        session = QHBoxLayout()
        self.keep_awake = QCheckBox("Keep awake during testing (30 min)")
        self.keep_awake.setToolTip("Developer mode only: sends the non-navigation WAKEUP key every 45 seconds to this target. Ends when stopped, the target changes, Studio closes, or 30 minutes elapse. Does not change sleep settings or provide a production wake-lock API.")
        self.keep_awake.toggled.connect(self.toggle_keep_awake)
        session.addWidget(self.keep_awake)
        session.addWidget(button("Type text…", self.type_device_text))
        layout.addLayout(session)
        self.target.currentIndexChanged.connect(lambda: self.keep_awake.setChecked(False))
        actions = QHBoxLayout()
        for text, fn in [("Installed apps", lambda: self.device_command("Installed apps", "vpm list packages")), ("Running apps", lambda: self.device_command("Running apps", "vlcm list")), ("Install VPKG…", self.install_file), ("Stop project app", self.stop_app), ("Uninstall…", self.uninstall_app), ("Push file…", self.push_file), ("Pull file…", self.pull_file)]:
            actions.addWidget(button(text, fn))
        layout.addLayout(actions)
        self.center.addTab(page, "Device Lab")

        emulator = QWidget()
        em = QVBoxLayout(emulator)
        em.setContentsMargins(28, 28, 28, 28)
        em.addWidget(label("NATIVE WINDOWS EMULATOR", "eyebrow"))
        em.addWidget(label("Vega OS, on your PC.", "brand"))
        em.addWidget(label("Windows QEMU + Vega images • community preview", "pill"))
        em.addWidget(label("Configure your Windows QEMU executable and VVD image_files folder in Settings. Start the VM, wait for its ready screen, then connect it as a Device Lab target. Its writable app data persists in a separate VM folder."))
        native_row = QHBoxLayout()
        native_row.addWidget(button("Start native Vega VM", self.start_native_vm, True))
        native_row.addWidget(button("Stop native VM", self.stop_native_vm))
        native_row.addWidget(button("Connect VM to Device Lab", self.connect_native_vm))
        em.addLayout(native_row)
        em.addWidget(label("JavaScript app install, launch and graphics are being verified on this port. This does not establish hardware, DRM, purchasing, sensors, audio or Appstore certification parity. Always test release apps on physical Fire TV hardware."))
        em.addSpacing(25)
        em.addWidget(label("Optional supported-host connection", "eyebrow"))
        em.addWidget(label("If you already run Amazon's SDK on an Ubuntu or macOS host, configure SSH in Settings. These controls invoke its real Vega Virtual Device and then expose it as a Device Lab target. This is not a native Windows emulator."))
        row = QHBoxLayout()
        for action in ["start", "status", "stop"]:
            row.addWidget(button(action.title() + " official VVD", lambda checked=False, action=action: self.emulator_action(action)))
        row.addWidget(button("Discover VVD targets", self.refresh_emulator))
        em.addLayout(row)
        em.addWidget(button("Amazon emulator documentation", lambda: QDesktopServices.openUrl(QUrl("https://developer.amazon.com/docs/vega/2.0/run-apps"))))
        em.addStretch()
        self.center.addTab(emulator, "Emulator")

    def _create_project_dock(self):
        dock = QDockWidget("PROJECT", self)
        dock.setObjectName("project-dock")
        page = QWidget()
        layout = QVBoxLayout(page)
        self.project_name = label("No project open", "eyebrow")
        layout.addWidget(self.project_name)
        self.fs = QFileSystemModel(self)
        self.fs.setReadOnly(True)
        self.filter = ProjectFilter(self)
        self.filter.setSourceModel(self.fs)
        self.tree = QTreeView()
        self.tree.setModel(self.filter)
        self.tree.setHeaderHidden(True)
        for col in (1, 2, 3):
            self.tree.hideColumn(col)
        self.tree.doubleClicked.connect(lambda index: self.open_file(Path(self.fs.filePath(self.filter.mapToSource(index)))))
        layout.addWidget(self.tree)
        layout.addWidget(button("New source file…", self.new_file))
        layout.addWidget(label("Generated folders and signing keys are hidden from the project tree."))
        dock.setWidget(page)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        dock.setMinimumWidth(210)
        self.resizeDocks([dock], [240], Qt.Orientation.Horizontal)

    def _create_assistant_dock(self):
        dock = QDockWidget("DEVELOPMENT ASSISTANT", self)
        dock.setObjectName("assistant-dock")
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(label("Ask. Build. Run.", "eyebrow"))
        self.identity_label = label("")
        layout.addWidget(self.identity_label)
        layout.addWidget(button("ChatGPT accounts…", self.show_chatgpt_accounts))
        self.refresh_assistant_identity()
        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(False)
        self.chat.setPlainText(INTRO)
        layout.addWidget(self.chat, 1)
        self.agent_mode=QComboBox()
        self.agent_mode.addItems(['Workspace agent','Discussion only'])
        self.agent_mode.setCurrentText(self.settings.get('agent_mode','Workspace agent'))
        self.agent_mode.setToolTip('Workspace agent can read and edit current project source, create projects, build and control the selected developer device. Edits have private undo backups. Discussion only has no tools.')
        def mode_changed(value):
            self.settings['agent_mode']=value;save_settings(self.settings)
        self.agent_mode.currentTextChanged.connect(mode_changed)
        layout.addWidget(self.agent_mode)
        self.attach = QCheckBox("Attach current file or selection")
        layout.addWidget(self.attach)
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText("Create an app, change its design, build it, or run it on the emulator…")
        self.prompt.setFixedHeight(100)
        layout.addWidget(self.prompt)
        row = QHBoxLayout()
        self.send = button("Send", self.send_chat, True)
        row.addWidget(self.send)
        row.addWidget(button("New chat", self.clear_chat))
        row.addWidget(button("Stop",lambda:self.ai_job.cancelled.set() if self.ai_job else None))
        layout.addWidget(button("Saved conversations…",self.choose_conversation))
        layout.addLayout(row)
        self.apply = button("Review suggested file replacement…", self.review_edit)
        self.apply.setEnabled(False)
        layout.addWidget(self.apply)
        layout.addWidget(label("Conversations are saved locally with Windows encryption. Creating a project preserves your planning discussion."))
        layout.addWidget(button('Undo last assistant edit',self.undo_agent_edit))
        dock.setWidget(page)
        dock.setMinimumWidth(300)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.resizeDocks([dock], [360], Qt.Orientation.Horizontal)

    def _create_output_dock(self):
        dock = QDockWidget("OUTPUT & DEVICE CONSOLE", self)
        dock.setObjectName("output-dock")
        tabs = QTabWidget()
        self.output = read_only("VegaBridge Studio ready. Open a project and configure Windows tools to begin.")
        tabs.addTab(self.output, "Build & tasks")
        console = QWidget()
        layout = QVBoxLayout(console)
        layout.addWidget(label("Commands run on the selected target as its Developer Mode shell user. Enter commands yourself; AI has no console access."))
        row = QHBoxLayout()
        self.command = QLineEdit()
        self.command.setPlaceholderText("Device command, for example: uname -a")
        self.command.returnPressed.connect(self.run_console)
        row.addWidget(self.command)
        row.addWidget(button("Run on device", self.run_console))
        row.addWidget(button("Stream project logs", self.stream_logs))
        layout.addLayout(row)
        self.console = read_only()
        layout.addWidget(self.console)
        tabs.addTab(console, "Developer shell & logs")
        dock.setWidget(tabs)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.resizeDocks([dock], [200], Qt.Orientation.Vertical)

    def _create_menus(self):
        file_menu = self.menuBar().addMenu("File")
        entries = [("New project…", "Ctrl+Shift+N", self.new_project), ("Open project…", "Ctrl+O", self.choose_project), ("Save", "Ctrl+S", self.save_current), ("Save all", "Ctrl+Shift+S", self.save_all), ("New source file…", "Ctrl+N", self.new_file)]
        for text, key, fn in entries:
            action = QAction(text, self)
            action.setShortcut(key)
            action.triggered.connect(fn)
            file_menu.addAction(action)
        edit = self.menuBar().addMenu("Edit")
        find = QAction("Find", self)
        find.setShortcut("Ctrl+F")
        find.triggered.connect(self.find.setFocus)
        edit.addAction(find)
        edit.addAction("Settings…", self.show_settings)
        search = QAction("Search entire project…", self)
        search.setShortcut("Ctrl+Shift+F")
        search.triggered.connect(self.search_workspace)
        edit.addAction(search)
        view = self.menuBar().addMenu("View")
        for dock in self.findChildren(QDockWidget):
            view.addAction(dock.toggleViewAction())
        tools = self.menuBar().addMenu("Tools")
        tools.addAction("Inspect VPKG…", self.inspect_file)
        tools.addAction("Validate VPKG and CMS signature…", self.validate_vpkg)
        tools.addAction("SDK setup check…", self.check_environment)
        tools.addAction("Compile C / C++ source…", self.compile_native_source)
        tools.addAction("Generate TurboModule C++ from TypeScript…", self.generate_native_module)
        tools.addAction("Compile JavaScript to Hermes bytecode…", self.generate_bytecode)
        tools.addAction("ChatGPT accounts…", self.show_chatgpt_accounts)
        tools.addAction("Open local data folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(user_dir()))))
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("About", lambda: QMessageBox.information(self, "VegaBridge Studio", "VegaBridge Studio " + __version__ + "\nIndependent Windows developer workbench.\nNot affiliated with Amazon or OpenAI.\n\nJavaScript/TypeScript app templates, Windows LLVM C/C++ cross-compilation, device tools, native Vega VM, themes and ChatGPT sign-in.\nPlatform API integration and Amazon certification still require the relevant SDK contracts and release testing."))

    def error(self, text):
        self.output.appendPlainText("ERROR: " + text)
        self.statusBar().showMessage(text, 12000)

    def generate_native_module(self):
        from .codegen import generate_module
        source,_=QFileDialog.getOpenFileName(self,'Choose NativeModule TypeScript interface',str(self.project or Path.home()),'TypeScript (*.ts)')
        if not source:return
        destination=QFileDialog.getExistingDirectory(self,'Choose an empty output folder',str(self.project or Path.home()))
        if not destination:return
        namespace,ok=QInputDialog.getText(self,'C++ namespace','Namespace:',text='MyModule')
        if ok:
            settings=dict(self.settings)
            self.start_job('Generate native TurboModule scaffolding',lambda runner,delta:generate_module(source,destination,settings,runner,namespace))

    def generate_bytecode(self):
        from .codegen import compile_bytecode
        source,_=QFileDialog.getOpenFileName(self,'Choose bundled JavaScript',str(self.project or Path.home()),'JavaScript bundle (*.js *.bundle)')
        if not source:return
        destination,_=QFileDialog.getSaveFileName(self,'Save Hermes bytecode',str(Path(source).with_suffix('.hbc')),'Hermes bytecode (*.hbc)')
        if destination:
            settings=dict(self.settings)
            self.start_job('Compile Hermes bytecode',lambda runner,delta:compile_bytecode(source,destination,settings,runner))

    def start_job(self, title, fn, done=None, console=False, background=False):
        self.output.appendPlainText("\n── " + title + " ──")
        self.statusBar().showMessage(title + "…")
        job = Job(fn)
        job.background = background
        job.line.connect(self.console.appendPlainText if console else self.output.appendPlainText)
        job.failed.connect(self.error)
        if done:
            job.result.connect(done)
        else:
            job.result.connect(lambda result: self.output.appendPlainText(str(result)) if result else None)
        job.finished.connect(lambda: self.finish_job(job, title))
        self.jobs.add(job)
        job.start()
        return job

    def finish_job(self, job, title):
        self.jobs.discard(job)
        self.statusBar().showMessage(f"{title}: task ended. See output for result.", 6000)
        job.deleteLater()

    def cancel_tasks(self):
        for job in list(self.jobs):
            job.cancelled.set()
        self.output.appendPlainText("Cancellation requested for this app's active tasks.")

    def show_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            self.settings = dialog.settings
            apply_theme(QApplication.instance(), self.settings["theme"])
            self.refresh_assistant_identity()

    def show_chatgpt_accounts(self):
        from .account_dialog import AccountDialog
        if self.ai_job:
            self.error("Finish or cancel the current AI request before changing accounts.")
            return
        AccountDialog(self).exec()

    def search_workspace(self):
        from .workspace_tools import search_project
        if not self.project:
            self.error("Open a project before searching.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Search project — Ctrl+Shift+F")
        dialog.resize(900, 580)
        layout = QVBoxLayout(dialog)
        query = QLineEdit()
        query.setPlaceholderText("Find text across source files; generated folders are excluded")
        case = QCheckBox("Match case")
        results = QListWidget()
        status = label("Searches up to 5,000 source files and displays the first 1,000 results.")
        layout.addWidget(query)
        layout.addWidget(case)
        layout.addWidget(results, 1)
        layout.addWidget(status)
        def search():
            results.clear()
            matches = search_project(self.project, query.text(), case.isChecked())
            for match in matches:
                item = QListWidgetItem(f"{match['relative']}:{match['line']}  {match['text']}")
                item.setData(Qt.ItemDataRole.UserRole, match)
                results.addItem(item)
            status.setText(f"{len(matches)} matches. Double-click a result to open its line.")
        def navigate(item):
            match = item.data(Qt.ItemDataRole.UserRole)
            self.open_file(Path(match['path']))
            editor = self.current_editor()
            if editor:
                cursor = QTextCursor(editor.document().findBlockByNumber(match['line']-1))
                editor.setTextCursor(cursor)
                editor.centerCursor()
            dialog.accept()
        results.itemDoubleClicked.connect(navigate)
        query.returnPressed.connect(search)
        layout.addWidget(button("Find in project", search, True))
        dialog.exec()

    def check_environment(self):
        from .workspace_tools import doctor
        def done(items):
            dialog = QDialog(self)
            dialog.setWindowTitle("SDK setup check")
            dialog.resize(850, 520)
            layout = QVBoxLayout(dialog)
            layout.addWidget(label("Checks your configured tools. Optional compiler, verifier and image prerequisites are listed separately."))
            view = read_only('\n\n'.join(('READY  ' if item['ready'] else 'SETUP  ') + item['tool'] + '\n' + item['detail'] for item in items))
            layout.addWidget(view)
            layout.addWidget(button("Close", dialog.accept))
            dialog.exec()
        self.start_job("SDK setup check", lambda runner, delta: doctor(dict(self.settings), runner), done)

    def compile_native_source(self):
        from .native_build import compile_source
        source, _ = QFileDialog.getOpenFileName(self, "Select C or C++ source", str(self.project or Path.home()), "C/C++ (*.cpp *.cc *.cxx *.c)")
        if not source:
            return
        arch, ok = QInputDialog.getItem(self, "Vega target architecture", "Target", ["armv7", "aarch64", "x86_64"], 0, False)
        if not ok:
            return
        kind, ok = QInputDialog.getItem(self, "Native output", "Build as", ["Executable", "Shared library"], 0, False)
        if not ok:
            return
        destination, _ = QFileDialog.getSaveFileName(self, "Native ELF output", str(Path(source).with_suffix('.so' if kind=='Shared library' else '.elf')))
        if destination:
            self.start_job("Windows C/C++ cross-compilation", lambda runner, delta: compile_source(source, destination, dict(self.settings), runner, arch, kind=='Shared library'))

    def validate_vpkg(self):
        from .package import verify_package
        path, _ = QFileDialog.getOpenFileName(self, "Validate Vega package", str(self.project/'build' if self.project else Path.home()), "Vega package (*.vpkg)")
        if path:
            self.start_job("Validate package", lambda runner, delta: verify_package(path, dict(self.settings), runner), lambda result: self.output.appendPlainText(json.dumps(result, indent=2)))

    def refresh_assistant_identity(self):
        mode = self.settings.get("auth_mode", "API key / local model")
        self.identity_label.setText(("Using ChatGPT plan" if mode == "ChatGPT plan" else mode) + " · " + self.settings["model"] + '\nConversation: ' + self.conversation_label)

    def new_project(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Create a Vega project")
        dialog.resize(760, 460)
        form = QFormLayout(dialog)
        title = QLineEdit("My Vega App")
        identifier = QLineEdit("com.example.myvegaapp")
        folder = QLineEdit(str(Path.home() / "VegaProjects/MyVegaApp"))
        form.addRow("App title", title)
        form.addRow("Package ID", identifier)
        from .gallery import entries
        templates = QComboBox()
        templates.addItem("Blank JavaScript starter", "")
        for item in entries():
            templates.addItem(item["category"] + " · " + item["title"], item["id"])
        description = label("Choose a runnable starter. All 20 gallery projects include editable source and offline sample behavior.")
        templates.currentIndexChanged.connect(lambda: description.setText(next((e["description"] for e in entries() if e["id"] == templates.currentData()), "A minimal React Native screen and remote-button counter.")))
        form.addRow("Project template", templates)
        form.addRow(description)
        language = QComboBox()
        language.addItems(["JavaScript", "TypeScript"])
        form.addRow("App language", language)
        form.addRow("New or empty folder", folder)
        form.addRow(button("Choose folder…", lambda: folder.setText(QFileDialog.getExistingDirectory(dialog, "Choose an empty folder") or folder.text())))
        form.addRow(label("Creates a Kepler 4 JavaScript project. First build downloads its pinned npm dependencies and creates an encrypted development signing key in your local user data folder."))
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        form.addRow(controls)
        if dialog.exec():
            try:
                if self.save_before_switch():
                    self.open_project(create_project(folder.text(), title.text(), identifier.text(), templates.currentData(), language.currentText()),carry_conversation=True)
            except Exception as error:
                QMessageBox.warning(self, "Project not created", str(error))

    def choose_project(self):
        folder = QFileDialog.getExistingDirectory(self, "Open Vega project")
        if folder and self.save_before_switch():
            self.open_project(folder)

    def save_before_switch(self):
        dirty = any(isinstance(self.editors.widget(i), CodeEditor) and self.editors.widget(i).document().isModified() for i in range(self.editors.count()))
        if not dirty:
            return True
        answer = QMessageBox.question(self, "Unsaved source", "Save all changes before continuing?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        return self.save_all() if answer == QMessageBox.StandardButton.Save else True

    def open_project(self, folder,carry_conversation=False,allow_agent=False):
        if any(not job.background and not (allow_agent and job is self.ai_job) for job in self.jobs):
            QMessageBox.information(self, "Tasks running", "Finish or cancel running tasks before changing projects.")
            return
        try:
            root = Path(folder).resolve()
            data = metadata(root)
            self.save_conversation()
            self.project = root
            self.last_package = None
            self.project_name.setText(data["title"] + "\n" + data["id"])
            self.fs.setRootPath(str(root))
            self.tree.setRootIndex(self.filter.mapFromSource(self.fs.index(str(root))))
            while self.editors.count():
                self.editors.widget(0).deleteLater()
                self.editors.removeTab(0)
            # A conversation is independent of the selected project. Changing
            # projects must never silently reset the user's planning context.
            self.conversation_label=data['title']
            self.conversation_project=str(root)
            self.source_snapshot=None
            self.refresh_assistant_identity()
            self.save_conversation()
            self.open_file(next((root/name for name in ['index.tsx','index.ts','index.js'] if (root/name).is_file()), root/'index.js'))
            self.open_file(root / "manifest.toml")
            self.editors.setCurrentIndex(0)
            self.center.setCurrentIndex(0)
            self.setWindowTitle(data["title"] + " — VegaBridge Studio")
            self.output.appendPlainText("Project opened: " + str(root))
        except Exception as error:
            QMessageBox.warning(self, "Cannot open project", str(error))

    def current_editor(self):
        editor = self.editors.currentWidget()
        return editor if isinstance(editor, CodeEditor) else None

    def open_file(self, path):
        try:
            if not self.project or not path.is_file():
                return
            path = inside(self.project, path)
            if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 2_000_000:
                raise ValueError("The editor accepts source/text files up to 2 MB.")
            for i in range(self.editors.count()):
                if getattr(self.editors.widget(i), "path", None) == path:
                    self.editors.setCurrentIndex(i)
                    return
            editor = CodeEditor(path)
            editor.setPlainText(path.read_text(encoding="utf-8-sig"))
            editor.document().setModified(False)
            self.editors.addTab(editor, path.name)
            self.editors.setCurrentWidget(editor)
            editor.document().modificationChanged.connect(lambda dirty: self.mark_dirty(editor, dirty))
            editor.cursorPositionChanged.connect(self.cursor_info)
        except Exception as error:
            self.error(str(error))

    def mark_dirty(self, editor, dirty):
        index = self.editors.indexOf(editor)
        if index >= 0:
            self.editors.setTabText(index, editor.path.name + (" •" if dirty else ""))

    def save_editor(self, editor):
        try:
            path = inside(self.project, editor.path)
            atomic_write(path, editor.toPlainText().encode("utf-8"))
            editor.document().setModified(False)
            return True
        except Exception as error:
            self.error(str(error))
            return False

    def save_current(self):
        editor = self.current_editor()
        return self.save_editor(editor) if editor else True

    def save_all(self):
        for i in range(self.editors.count()):
            editor = self.editors.widget(i)
            if isinstance(editor, CodeEditor) and editor.document().isModified() and not self.save_editor(editor):
                return False
        return True

    def close_editor(self, index):
        editor = self.editors.widget(index)
        if isinstance(editor, CodeEditor) and editor.document().isModified():
            answer = QMessageBox.question(self, "Unsaved file", "Save " + editor.path.name + "?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Cancel or (answer == QMessageBox.StandardButton.Save and not self.save_editor(editor)):
                return
        self.editors.removeTab(index)
        editor.deleteLater()

    def new_file(self):
        if not self.project:
            return
        path, _ = QFileDialog.getSaveFileName(self, "New source file", str(self.project / "new-file.js"))
        if path:
            try:
                path = inside(self.project, path)
                if path.exists():
                    raise ValueError("Choose a new filename; existing files are not overwritten by this action.")
                atomic_write(path, b"")
                self.open_file(path)
            except Exception as error:
                self.error(str(error))

    def cursor_info(self, *_):
        editor = self.current_editor()
        if editor:
            cursor = editor.textCursor()
            self.cursor_status.setText(f"Ln {cursor.blockNumber()+1}, Col {cursor.positionInBlock()+1}    UTF-8    {editor.path.suffix}")

    def find_next(self):
        editor = self.current_editor()
        if editor and self.find.text():
            if not editor.find(self.find.text()):
                editor.moveCursor(QTextCursor.MoveOperation.Start)
                editor.find(self.find.text())

    def build_project(self, then_run=False):
        if not self.project or any(not job.background for job in self.jobs):
            self.error("Open a project and finish active tasks before building.")
            return
        if not self.save_all():
            return
        root, settings = self.project, dict(self.settings)
        def done(path):
            self.last_package = Path(path)
            self.output.appendPlainText("BUILD SUCCEEDED: " + path)
            if then_run:
                # The finished signal follows result; schedule after job cleanup.
                QTimer.singleShot(100, lambda: self.deploy(Path(path), launch=True))
        self.start_job("Build development VPKG", lambda runner, delta: build(root, settings, runner), done)

    def run_project(self):
        self.build_project(then_run=True)

    def target_snapshot(self):
        target = self.target.currentData()
        if not target:
            raise ValueError("Select an online device from Refresh devices or Discover VVD targets.")
        return dict(self.settings), dict(target)

    @staticmethod
    def bridge(snapshot, runner):
        settings, target = snapshot
        return (RemoteEmulator if target["kind"] == "Remote VVD" else LocalBridge)(settings, runner, target["serial"])

    def set_devices(self, found, remote=False, prefer=""):
        selected = {"serial": prefer} if prefer else self.target.currentData()
        keep = [self.target.itemData(i) for i in range(self.target.count()) if self.target.itemData(i) and (self.target.itemData(i)["kind"] == "Remote VVD") != remote]
        self.target.clear()
        self.target.addItem("Select target…", None)
        for item in keep + found:
            if remote and item in found:
                item = item | {"kind": "Remote VVD"}
            title = f'{item["kind"]} · {item["serial"]} ({item["state"]})'
            self.target.addItem(title, item if item["state"] == "device" else None)
            if selected and selected["serial"] == item["serial"] and item["state"] == "device":
                self.target.setCurrentIndex(self.target.count()-1)
        if self.target.currentIndex() == 0:
            for i in range(1, self.target.count()):
                if self.target.itemData(i):
                    self.target.setCurrentIndex(i)
                    break

    def refresh_devices(self):
        settings = dict(self.settings)
        self.start_job("Discover USB and wireless devices", lambda runner, delta: LocalBridge(settings, runner).devices(), self.set_devices)

    def connect_device(self):
        try:
            settings, address = dict(self.settings), endpoint(self.address.text())
            def connect(runner, delta):
                bridge = LocalBridge(settings, runner)
                bridge.connect(address)
                return bridge.devices()
            self.start_job("Connect wireless device", connect, lambda items: self.set_devices(items, prefer=address))
        except Exception as error:
            self.error(str(error))

    def device_command(self, title, command, timeout=60, console=False):
        try:
            snapshot = self.target_snapshot()
            self.start_job(title, lambda runner, delta: self.bridge(snapshot, runner).shell(command, timeout=timeout), console=console)
        except Exception as error:
            self.error(str(error))

    def run_console(self):
        command = self.command.text().strip()
        if command:
            self.device_command("Developer shell", command, timeout=120, console=True)

    def stream_logs(self):
        try:
            pkg = metadata(self.project)
            snapshot = self.target_snapshot()
            self.start_job("Live project logs (Cancel tasks to stop)", lambda runner, delta: self.bridge(snapshot, runner).shell("loggingctl log -v " + pkg["id"] + " -f", timeout=3600), console=True, background=True)
        except Exception as error:
            self.error(str(error))

    def deploy(self, path, launch=False):
        try:
            snapshot = self.target_snapshot()
            info = metadata(self.project) if launch else None
            def work(runner, delta):
                inspect_package(path)
                bridge = self.bridge(snapshot, runner)
                bridge.install(path)
                if launch:
                    bridge.launch(info["component"])
                return "Install verified. " + ("Launch requested; use Device Lab to inspect the screen." if launch else "")
            self.start_job("Install " + path.name, work)
        except Exception as error:
            self.error(str(error))

    def install_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Install development VPKG on selected device", str(self.project or Path.home()), "Vega package (*.vpkg)")
        if path:
            self.deploy(Path(path))

    def stop_app(self):
        try:
            info, snapshot = metadata(self.project), self.target_snapshot()
            self.start_job("Stop project app", lambda runner, delta: self.bridge(snapshot, runner).stop(info["id"]))
        except Exception as error:
            self.error(str(error))

    def uninstall_app(self):
        from PySide6.QtWidgets import QInputDialog
        identifier, ok = QInputDialog.getText(self, "Remove app from device", "Exact package ID:", text=metadata(self.project)["id"] if self.project else "")
        if not ok:
            return
        from .project import package_id
        try:
            package_id(identifier)
            snapshot = self.target_snapshot()
            if QMessageBox.warning(self, "Uninstall " + identifier, "Uninstall this app from " + snapshot[1]["serial"] + "? Its local app data may be removed.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Yes:
                self.start_job("Uninstall app", lambda runner, delta: self.bridge(snapshot, runner).shell("vpm uninstall " + identifier))
        except Exception as error:
            self.error(str(error))

    def push_file(self):
        from PySide6.QtWidgets import QInputDialog
        try:
            snapshot = self.target_snapshot()
            path, _ = QFileDialog.getOpenFileName(self, "Push file to selected device")
            if not path:
                return
            remote, ok = QInputDialog.getText(self, "Device destination", "Absolute device path:", text="/tmp/" + Path(path).name)
            if ok and remote.startswith("/"):
                self.start_job("Push file", lambda runner, delta: self.bridge(snapshot, runner).push(path, remote))
        except Exception as error:
            self.error(str(error))

    def pull_file(self):
        from PySide6.QtWidgets import QInputDialog
        try:
            snapshot = self.target_snapshot()
            remote, ok = QInputDialog.getText(self, "Pull file", "Absolute device source path:", text="/tmp/")
            if not ok or not remote.startswith("/"):
                return
            local, _ = QFileDialog.getSaveFileName(self, "Save device file", str(Path.home() / Path(remote).name))
            if local:
                self.start_job("Pull file", lambda runner, delta: self.bridge(snapshot, runner).pull(remote, local))
        except Exception as error:
            self.error(str(error))

    def capture_screen(self):
        try:
            snapshot = self.target_snapshot()
            folder = user_dir() / "captures"
            folder.mkdir(exist_ok=True)
            path = folder / (time.strftime("%Y%m%d-%H%M%S") + ".png")
            def show(path):
                pixmap = QPixmap(path)
                if pixmap.isNull():
                    self.error("Screenshot did not decode")
                    return
                self.screen.setPixmap(pixmap.scaled(self.screen.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                self.screen.setToolTip(path)
            is_native=snapshot[1]['serial']=='127.0.0.1:'+str(self.settings['vm_port'])
            native=self.native_vm
            def capture(runner,delta):
                if is_native:return (native or NativeVm.attach_managed(snapshot[0])).screenshot(path)
                return self.bridge(snapshot,runner).screenshot(path)
            self.start_job("Capture target screen",capture,show)
        except Exception as error:
            self.error(str(error))

    def type_device_text(self):
        try:
            snapshot=self.target_snapshot()
            text,ok=QInputDialog.getMultiLineText(self,'Type on selected device','Focus the app’s text field first. Enter text below; it will not be written to task logs.')
            if ok and text:
                self.start_job('Send text to device',lambda runner,delta:self.bridge(snapshot,runner).type_text(text))
        except Exception as error:
            self.error(str(error))

    def toggle_keep_awake(self,checked):
        if not checked:
            if self.awake_job:self.awake_job.cancelled.set()
            return
        try:
            if self.awake_job:raise RuntimeError('The previous test wake session is still stopping. Try again in a moment.')
            snapshot=self.target_snapshot()
            self.awake_job=self.start_job('Developer test wake session',lambda runner,delta:self.bridge(snapshot,runner).keep_awake(30),background=True)
            def finished():
                self.awake_job=None
                self.keep_awake.blockSignals(True)
                self.keep_awake.setChecked(False)
                self.keep_awake.blockSignals(False)
            self.awake_job.finished.connect(finished)
        except Exception as error:
            self.keep_awake.setChecked(False)
            self.error(str(error))

    def emulator_action(self, action):
        settings = dict(self.settings)
        self.start_job("Official remote VVD " + action, lambda runner, delta: RemoteEmulator(settings, runner).manage(action))

    def start_native_vm(self):
        if self.vm_job:
            self.error("A native VM is already running in this Studio window.")
            return
        try:
            self.native_vm=NativeVm.attach_managed(dict(self.settings))
            self.output.appendPlainText('Attached to the existing Studio-managed VM. A second VM was not started.')
            return
        except (OSError,ValueError,RuntimeError):
            pass
        vm = NativeVm(dict(self.settings))
        self.native_vm = vm
        self.vm_job = self.start_job("Native Windows Vega VM", lambda runner, delta: vm.run(runner), console=True, background=True)
        def finished():
            self.vm_job = None
            self.native_vm = None
        self.vm_job.finished.connect(finished)

    def stop_native_vm(self):
        if self.vm_job:
            self.vm_job.cancelled.set()
            self.output.appendPlainText("Stopping the native VM and flushing its private overlay disk…")
        else:
            from .native_vm import managed_vm_command
            self.start_job('Stop the owned native VM',lambda runner,delta:managed_vm_command('quit'))

    def connect_native_vm(self):
        self.address.setText("127.0.0.1:" + str(self.settings["vm_port"]))
        self.connect_device()
        self.center.setCurrentIndex(1)

    def refresh_emulator(self):
        settings = dict(self.settings)
        self.start_job("Discover official remote VVD", lambda runner, delta: RemoteEmulator(settings, runner).devices(), lambda items: self.set_devices(items, True))

    def inspect_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Inspect VPKG", str(self.project or Path.home()), "Vega package (*.vpkg)")
        if path:
            self.start_job("Inspect package payload digests", lambda runner, delta: json.dumps(inspect_package(path), indent=2))

    def clear_chat(self):
        if self.ai_job:
            self.ai_job.cancelled.set()
            return
        self.save_conversation()
        import uuid
        self.chat_key='chat-'+uuid.uuid4().hex
        self.settings['chat_active']=self.chat_key
        save_settings(self.settings)
        self.history, self.last_answer, self.source_snapshot = [], "", None
        self.pending_prompt=''
        self.chat.setPlainText(INTRO)
        self.prompt.clear()
        self.apply.setEnabled(False)
        self.save_conversation()

    def save_conversation(self):
        if self._conversation_loading or not hasattr(self,'chat') or not hasattr(self,'prompt'):
            return
        try:
            self.conversations.save(self.chat_key,self.conversation_label,self.history,self.chat.toPlainText(),
                                    self.pending_prompt or self.prompt.toPlainText(),self.conversation_project)
        except Exception as error:
            if hasattr(self,'output'):
                self.error('Conversation could not be saved locally: '+str(error))

    def load_conversation(self,key,save_current=True):
        if save_current:self.save_conversation()
        data=self.conversations.load(key)
        self._conversation_loading=True
        try:
            self.chat_key=key
            self.conversation_label=data.get('label','Conversation')
            self.conversation_project=data.get('project','')
            self.history=data.get('history',[])
            self.pending_prompt=''
            self.last_answer=''
            self.source_snapshot=None
            self.chat.setPlainText(data.get('display') or INTRO)
            self.prompt.blockSignals(True)
            self.prompt.setPlainText(data.get('draft',''))
            self.prompt.blockSignals(False)
            self.apply.setEnabled(False)
            self.settings['chat_active']=key
            save_settings(self.settings)
            self.refresh_assistant_identity()
        finally:
            self._conversation_loading=False

    def choose_conversation(self):
        if self.ai_job:
            self.error('Finish or cancel the assistant before switching conversations.')
            return
        self.save_conversation()
        dialog=QDialog(self)
        dialog.setWindowTitle('Saved conversations — private to this Windows user')
        dialog.resize(780,480)
        layout=QVBoxLayout(dialog)
        layout.addWidget(label('Planning chats, project conversations and archived chats are stored locally with Windows encryption. They are not part of source exports or GitHub uploads.'))
        listing=QListWidget()
        for item in self.conversations.list():
            entry=QListWidgetItem(item['label']+'  ·  '+item['updatedAt'][:19].replace('T',' '))
            entry.setData(Qt.ItemDataRole.UserRole,item['key'])
            listing.addItem(entry)
        layout.addWidget(listing)
        def restore():
            if listing.currentItem():
                self.load_conversation(listing.currentItem().data(Qt.ItemDataRole.UserRole))
                dialog.accept()
        listing.itemDoubleClicked.connect(lambda _:restore())
        layout.addWidget(button('Resume selected conversation',restore,True))
        dialog.exec()

    def send_chat(self):
        prompt = self.prompt.toPlainText().strip()
        if not prompt or self.ai_job:
            return
        try:
            settings = dict(self.settings)
            chatgpt = settings.get("auth_mode") == "ChatGPT plan"
            if chatgpt:
                settings.update(endpoint="https://api.openai.com/v1", protocol="Responses")
            agent=self.agent_mode.currentText()=='Workspace agent'
            if agent and settings['protocol']!='Responses':
                raise ValueError('Workspace agent needs a Responses-compatible endpoint. Change the protocol in Settings, or choose Discussion only.')
            key = "" if chatgpt else SecretStore().get(credential_name(settings))
            if not chatgpt and validate_url(settings["endpoint"]) == "https://api.openai.com/v1" and not key:
                QMessageBox.information(self, "Connect the coding assistant", "Add an API key in Settings → AI assistant, or configure a locally running model. Your message has been kept. Enter credentials only in the app's password field.")
                return
            message = prompt
            snapshot = None
            if self.attach.isChecked():
                editor = self.current_editor()
                if not editor or not self.project:
                    raise ValueError("Open a source file before attaching context.")
                text = editor.textCursor().selectedText().replace("\u2029", "\n") or editor.toPlainText()
                context = safe_context(self.project, editor.path, text)
                review = QDialog(self)
                review.setWindowTitle("Preview code sent to AI")
                review.resize(800, 600)
                layout = QVBoxLayout(review)
                layout.addWidget(label("Destination: " + validate_url(settings["endpoint"]) + "\nThis context and your current conversation will be sent when you continue."))
                layout.addWidget(read_only(context))
                controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
                controls.button(QDialogButtonBox.StandardButton.Ok).setText("Send this context")
                controls.accepted.connect(review.accept)
                controls.rejected.connect(review.reject)
                layout.addWidget(controls)
                if not review.exec():
                    return
                snapshot = (editor.path, editor.toPlainText())
                message += "\n\nUser-approved source context:\n" + context
            history = self.history + [{"role": "user", "content": message}]
            cursor = self.chat.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText("\nYOU\n" + prompt + "\n\nASSISTANT\n")
            self.chat.setTextCursor(cursor)
            self.pending_prompt=prompt
            self.prompt.clear()
            self.send.setEnabled(False)
            self.apply.setEnabled(False)
            self.source_snapshot = snapshot
            self.last_answer = ""
            def done(answer):
                if agent:
                    self.last_answer=answer['answer']
                    self.history=answer['history']
                    self.pending_prompt=''
                    self.save_conversation()
                    return
                self.last_answer = answer
                self.history = history + [{"role": "assistant", "content": answer}]
                self.pending_prompt=''
                self.save_conversation()
                self.apply.setEnabled(bool(snapshot and re.search(r"```[^\n]*\n[\s\S]+?```", answer)))
            def request(runner, delta):
                from .chatgpt_auth import access_token
                token = access_token(settings["auth_account"]) if chatgpt else key
                if agent:
                    from .agent import stream_agent
                    return stream_agent(settings,token,history,runner,delta,self.invoke_agent_tool,self.agent_history.emit)
                return stream_chat(settings, token, history, runner, delta)
            job = self.start_job("AI coding assistant", request, done)
            job.delta.connect(self.chat_delta)
            job.finished.connect(self.ai_finished)
            self.ai_job = job
        except Exception as error:
            self.error(str(error))

    def chat_delta(self, text):
        cursor = self.chat.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.chat.setTextCursor(cursor)
        self.chat.ensureCursorVisible()

    def undo_agent_edit(self):
        if self.ai_job:
            self.error('Finish or stop the assistant before undoing an edit.')
            return
        try:
            result=self.agent_action('undo_last_edit',{})
            self.output.appendPlainText('Assistant edit undone: '+result['path'])
        except Exception as error:self.error(str(error))

    def ai_finished(self):
        self.ai_job = None
        self.send.setEnabled(True)
        if self.pending_prompt:
            self.prompt.setPlainText(self.pending_prompt)
            self.pending_prompt=''
        self.save_conversation()

    def review_edit(self):
        if not self.source_snapshot:
            return
        path, before = self.source_snapshot
        self.open_file(path)
        editor = self.current_editor()
        if not editor or editor.path != path or editor.toPlainText() != before:
            self.error("The source changed since the request. Ask again with current context before applying an edit.")
            return
        blocks = re.findall(r"```[^\n]*\n([\s\S]*?)```", self.last_answer)
        if len(blocks) != 1:
            self.error("Review replacement needs exactly one complete file code block. Ask the assistant for that format.")
            return
        after = blocks[0].rstrip() + "\n"
        diff = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile=str(path.name), tofile=str(path.name) + " (suggested)"))
        dialog = QDialog(self)
        dialog.setWindowTitle("Review replacement — " + path.name)
        dialog.resize(950, 650)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Replaces the whole editor buffer. Review the diff, then save when ready. Ctrl+Z can undo the buffer change."))
        layout.addWidget(read_only(diff or "No changes"))
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        controls.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        layout.addWidget(controls)
        if dialog.exec():
            cursor = editor.textCursor()
            cursor.beginEditBlock()
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.insertText(after)
            cursor.endEditBlock()
            self.apply.setEnabled(False)

    def closeEvent(self, event):
        if self.jobs:
            self.cancel_tasks()
            self.statusBar().showMessage("Stopping active work. Close again after tasks finish.")
            event.ignore()
            return
        if self.save_before_switch():
            self.save_conversation()
            event.accept()
        else:
            event.ignore()


def main():
    parser = argparse.ArgumentParser(description="VegaBridge Studio native Windows workbench")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--smoke-test", action="store_true", help="Start UI offscreen and exit after checking construction")
    args = parser.parse_args()
    if args.smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("VegaBridge Studio")
    app.setOrganizationName("VegaBridge")
    app.setStyle("Fusion")
    apply_theme(app, load_settings()["theme"])
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "resources/vegabridge.ico")))
    guard = None
    if not args.smoke_test:
        from .instance import SingleInstance
        guard = SingleInstance()
        if not guard.acquire():
            return 0
    window = Studio(args.project)
    if guard:
        def activate():
            window.showNormal()
            window.raise_()
            window.activateWindow()
        guard.activated.connect(activate)
        app.aboutToQuit.connect(guard.close)
    window.show()
    if args.smoke_test:
        QTimer.singleShot(500, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
