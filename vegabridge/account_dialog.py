"""Native account picker and explicit browser-based ChatGPT authorization."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QMessageBox
from . import chatgpt_auth as auth
from .storage import save_settings

USAGE = "https://chatgpt.com/#settings/Usage"


class AccountDialog(QDialog):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio, self.job = studio, None
        self.setWindowTitle("ChatGPT accounts — VegaBridge Studio")
        self.resize(660, 390)
        layout = QVBoxLayout(self)
        title = QLabel("Use your ChatGPT plan")
        title.setObjectName("brand")
        layout.addWidget(title)
        info = QLabel("Eligible AI requests use your ChatGPT plan and its limits. Sign in and authorize VegaBridge Studio in your browser. This does not access your existing ChatGPT conversations. API keys and local models remain available.")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.accounts = QComboBox()
        layout.addWidget(self.accounts)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.signin = QPushButton("Continue with ChatGPT")
        self.signin.setObjectName("primary")
        self.signin.clicked.connect(self.connect_account)
        row.addWidget(self.signin)
        self.choose = QPushButton("Use selected account")
        self.choose.clicked.connect(self.use_selected)
        row.addWidget(self.choose)
        layout.addLayout(row)
        self.models = QComboBox()
        self.models.setMinimumWidth(300)
        layout.addWidget(self.models)
        refresh = QPushButton("Refresh available ChatGPT models")
        refresh.clicked.connect(self.refresh_models)
        layout.addWidget(refresh)
        row = QHBoxLayout()
        self.logout = QPushButton("Sign out selected account")
        self.logout.clicked.connect(self.sign_out)
        row.addWidget(self.logout)
        usage = QPushButton("Manage ChatGPT usage")
        usage.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(USAGE)))
        row.addWidget(usage)
        layout.addLayout(row)
        self.models.currentIndexChanged.connect(self.model_changed)
        self.reload()

    def reload(self):
        self.accounts.clear()
        self.accounts.addItem("Add another ChatGPT account…", "")
        selected = self.studio.settings.get("auth_account", "")
        for item in auth.list_accounts():
            self.accounts.addItem(item["label"] + " · " + item["clientSuffix"] + ("" if item["connected"] else " · signed out"), item["key"])
            if item["key"] == selected:
                self.accounts.setCurrentIndex(self.accounts.count() - 1)
        self.status.setText("Current assistant connection: " + self.studio.settings["auth_mode"])

    def connect_account(self):
        if self.job:
            return
        selected = self.accounts.currentData() or ""
        self.status.setText("Complete sign-in and permissions in your browser. Waiting up to five minutes…")
        self.signin.setEnabled(False)
        self.job = self.studio.start_job("ChatGPT sign-in", lambda runner, delta: auth.sign_in(runner, self.studio.authorization_requested.emit, selected), self.connected)
        self.job.failed.connect(self.status.setText)
        self.job.finished.connect(self.finished)

    def finished(self):
        self.job = None
        self.signin.setEnabled(True)

    def connected(self, result):
        self.studio.settings["auth_account"] = result["key"]
        if result["planEnabled"]:
            self.studio.settings["auth_mode"] = "ChatGPT plan"
        save_settings(self.studio.settings)
        self.reload()
        self.studio.refresh_assistant_identity()
        if result["planEnabled"]:
            if result["welcome"]:
                QMessageBox.information(self, "You’re using your ChatGPT plan", "Eligible AI requests in VegaBridge Studio use your ChatGPT plan. Manage usage and limits in ChatGPT settings.")
                auth.welcome_seen(result["key"])
            self.refresh_models()
        else:
            self.status.setText("Identity verified, but ChatGPT plan use was not granted. Continue with ChatGPT to authorize it, or use an API key / local model.")

    def use_selected(self):
        key = self.accounts.currentData()
        if not key or self.job:
            return
        def done(models):
            self.studio.clear_chat()
            self.studio.settings.update(auth_account=key, auth_mode="ChatGPT plan")
            save_settings(self.studio.settings)
            self.studio.refresh_assistant_identity()
            self.show_models(models)
        self.studio.start_job("Select ChatGPT account", lambda runner, delta: auth.available_models(key), done)

    def refresh_models(self):
        key = self.accounts.currentData()
        if key:
            self.studio.start_job("ChatGPT model catalog", lambda runner, delta: auth.available_models(key), self.show_models)

    def show_models(self, models):
        self.models.blockSignals(True)
        self.models.clear()
        for item in models:
            self.models.addItem(item["name"], item["slug"])
        idx = self.models.findData(self.studio.settings["model"])
        self.models.setCurrentIndex(max(0, idx))
        self.models.blockSignals(False)
        self.model_changed()
        self.status.setText("Using ChatGPT plan. Choose an available model above. Manage usage in ChatGPT settings.")

    def model_changed(self, *_):
        if self.models.currentData():
            self.studio.settings["model"] = self.models.currentData()
            save_settings(self.studio.settings)
            self.studio.refresh_assistant_identity()

    def sign_out(self):
        key = self.accounts.currentData()
        if not key or self.job or self.studio.ai_job:
            return
        def done(confirmed):
            if self.studio.settings["auth_account"] == key:
                self.studio.settings["auth_mode"] = "API key / local model"
                save_settings(self.studio.settings)
                self.studio.clear_chat()
            self.reload()
            self.studio.refresh_assistant_identity()
            self.status.setText("Signed out." if confirmed else "Signed out locally. Remote revocation was not confirmed; disconnect VegaBridge Studio in ChatGPT settings.")
        self.studio.start_job("Sign out ChatGPT account", lambda runner, delta: auth.sign_out(key), done)

    def reject(self):
        if self.job:
            self.job.cancelled.set()
        super().reject()
