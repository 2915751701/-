import sys
import shutil
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QProgressBar, QMessageBox, QFileDialog, QLineEdit
)
from PySide6.QtCore import Qt, QThread, Signal

APP_NAME = "锅巴小公主"
APP_NAME_EN = "GuobaPrincess"


class InstallThread(QThread):
    progress = Signal(int)
    finished = Signal(bool, str)

    def __init__(self, target_dir):
        super().__init__()
        self.target_dir = Path(target_dir)

    def run(self):
        try:
            import pythoncom
            pythoncom.CoInitialize()

            if getattr(sys, "frozen", False):
                source = Path(sys._MEIPASS) / f"{APP_NAME_EN}.exe"
                if not source.exists():
                    source = Path(sys.executable).parent / f"{APP_NAME_EN}.exe"
            else:
                source = Path(__file__).resolve().parent.parent / "dist" / f"{APP_NAME_EN}.exe"

            self.progress.emit(10)

            if not source.exists():
                self.finished.emit(False, f"找不到安装源: {source}")
                return

            self.target_dir.mkdir(parents=True, exist_ok=True)
            self.progress.emit(40)

            target_exe = self.target_dir / f"{APP_NAME_EN}.exe"
            shutil.copy2(source, target_exe)
            self.progress.emit(70)

            desktop = Path.home() / "Desktop"
            start_menu = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            self._create_shortcut(target_exe, desktop / f"{APP_NAME}.lnk")
            self._create_shortcut(target_exe, start_menu / f"{APP_NAME}.lnk")
            self.progress.emit(100)
            self.finished.emit(True, str(self.target_dir))
        except Exception as e:
            self.finished.emit(False, str(e))

    def _create_shortcut(self, target, shortcut_path):
        import pythoncom
        from win32com.shell import shell
        pythoncom.CoInitialize()
        shortcut_com = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink,
            None,
            pythoncom.CLSCTX_INPROC_SERVER,
            shell.IID_IShellLink
        )
        shortcut_com.SetPath(str(target))
        persist = shortcut_com.QueryInterface(pythoncom.IID_IPersistFile)
        persist.Save(str(shortcut_path), 0)


class InstallerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME}安装程序")
        self.setFixedSize(480, 260)
        layout = QVBoxLayout(self)

        self.label = QLabel(f"欢迎使用 {APP_NAME}", self)
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit(self)
        default_path = Path.home() / "AppData" / "Local" / APP_NAME_EN
        self.path_edit.setText(str(default_path))
        path_layout.addWidget(self.path_edit)
        browse_btn = QPushButton("浏览…", self)
        browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.btn = QPushButton("安装", self)
        self.btn.clicked.connect(self._install)
        layout.addWidget(self.btn)

        self.thread = None

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择安装路径", self.path_edit.text())
        if path:
            self.path_edit.setText(path)

    def _install(self):
        target = self.path_edit.text().strip()
        if not target:
            QMessageBox.warning(self, "提示", "请选择安装路径")
            return
        self.btn.setEnabled(False)
        self.label.setText("正在安装，请稍候...")
        self.thread = InstallThread(target)
        self.thread.progress.connect(self.progress.setValue)
        self.thread.finished.connect(self._done)
        self.thread.start()

    def _done(self, success, msg):
        self.btn.setEnabled(True)
        if success:
            QMessageBox.information(
                self, "安装完成",
                f"安装成功！\n桌面和开始菜单已创建快捷方式。\n安装路径: {msg}"
            )
            self.label.setText("安装完成")
            self.btn.setText("完成")
            self.btn.clicked.disconnect()
            self.btn.clicked.connect(QApplication.quit)
        else:
            QMessageBox.critical(self, "安装失败", f"错误: {msg}")
            self.label.setText("安装失败")


def main():
    app = QApplication(sys.argv)
    w = InstallerWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
