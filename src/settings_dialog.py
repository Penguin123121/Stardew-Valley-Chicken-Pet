"""
设置对话框 - 图形化设置面板
"""

import os
import sys
import subprocess

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QCheckBox, QPushButton, QGroupBox,
)
from PyQt5.QtCore import Qt

from src.settings_manager import Settings

# ── 开机自启 ──────────────────────────────────
_STARTUP_FOLDER = os.path.join(
    os.environ.get('APPDATA', ''),
    'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup'
)
_SHORTCUT_NAME = '星露谷小鸡桌宠.lnk'

# 项目根目录 — 从当前文件位置动态推导（src/settings_dialog.py → 上一级 → 项目根）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# pythonw.exe 路径 — 与 python.exe 在同一目录
_PYTHONW = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
_ICON_PATH = os.path.join(_PROJECT_ROOT, 'assets', 'white_chicken.ico')


def _get_shortcut_path() -> str:
    return os.path.join(_STARTUP_FOLDER, _SHORTCUT_NAME)


def _check_autostart() -> bool:
    """检查 Startup 文件夹中是否存在开机自启快捷方式"""
    return os.path.exists(_get_shortcut_path())


def _set_autostart(enable: bool):
    """创建或删除 Startup 文件夹中的快捷方式"""
    shortcut_path = _get_shortcut_path()
    if enable:
        # 用 PowerShell 创建 .lnk 快捷方式（动态路径，不绑定具体用户/目录）
        ps_cmd = (
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$s = $ws.CreateShortcut("{shortcut_path}"); '
            f'$s.TargetPath = "{_PYTHONW}"; '
            f'$s.Arguments = "-m src.main"; '
            f'$s.WorkingDirectory = "{_PROJECT_ROOT}"; '
            f'$s.WindowStyle = 7; '
            f'$s.IconLocation = "{_ICON_PATH}"; '
            f'$s.Save()'
        )
        subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_cmd],
            capture_output=True,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
    else:
        try:
            os.remove(shortcut_path)
        except OSError:
            pass


class SettingsDialog(QDialog):
    """小鸡桌宠设置面板"""

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings

        self.setWindowTitle("小鸡桌宠 - 设置")
        self.setFixedSize(400, 520)
        self.setWindowFlags(
            Qt.Dialog
            | Qt.WindowCloseButtonHint
            | Qt.WindowTitleHint
        )

        self._init_ui()
        self._load_values()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── 外观 ──────────────────────────────
        appearance = QGroupBox("外观")
        app_layout = QVBoxLayout(appearance)
        app_layout.setSpacing(8)

        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("小鸡大小:"))
        self._scale_slider = QSlider(Qt.Horizontal)
        self._scale_slider.setRange(2, 6)
        self._scale_slider.setTickInterval(1)
        self._scale_label = QLabel("4x")
        self._scale_label.setFixedWidth(30)
        scale_layout.addWidget(self._scale_slider)
        scale_layout.addWidget(self._scale_label)
        self._scale_slider.valueChanged.connect(
            lambda v: self._scale_label.setText(f"{v}x")
        )
        app_layout.addLayout(scale_layout)
        layout.addWidget(appearance)

        # ── 行为 ──────────────────────────────
        behavior = QGroupBox("行为")
        beh_layout = QVBoxLayout(behavior)
        beh_layout.setSpacing(8)

        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("动画速度:"))
        self._speed_slider = QSlider(Qt.Horizontal)
        self._speed_slider.setRange(100, 500)
        self._speed_slider.setTickInterval(50)
        self._speed_label = QLabel("200ms")
        self._speed_label.setFixedWidth(50)
        speed_layout.addWidget(self._speed_slider)
        speed_layout.addWidget(self._speed_label)
        self._speed_slider.valueChanged.connect(
            lambda v: self._speed_label.setText(f"{v}ms")
        )
        beh_layout.addLayout(speed_layout)

        # 活跃度滑块
        active_layout = QHBoxLayout()
        active_layout.addWidget(QLabel("活跃度:"))
        self._active_slider = QSlider(Qt.Horizontal)
        self._active_slider.setRange(1, 10)
        self._active_slider.setTickInterval(1)
        self._active_label = QLabel("5")
        self._active_label.setFixedWidth(20)
        active_layout.addWidget(self._active_slider)
        active_layout.addWidget(self._active_label)
        self._active_slider.valueChanged.connect(
            lambda v: self._active_label.setText(str(v))
        )
        beh_layout.addLayout(active_layout)

        # 移动速度滑块
        move_layout = QHBoxLayout()
        move_layout.addWidget(QLabel("移动速度:"))
        self._move_slider = QSlider(Qt.Horizontal)
        self._move_slider.setRange(2, 8)
        self._move_slider.setTickInterval(1)
        self._move_label = QLabel("3")
        self._move_label.setFixedWidth(20)
        move_layout.addWidget(self._move_slider)
        move_layout.addWidget(self._move_label)
        self._move_slider.valueChanged.connect(
            lambda v: self._move_label.setText(str(v))
        )
        beh_layout.addLayout(move_layout)
        layout.addWidget(behavior)

        # ── 窗口 ──────────────────────────────
        window_group = QGroupBox("窗口")
        win_layout = QVBoxLayout(window_group)
        win_layout.setSpacing(8)

        self._top_cb = QCheckBox("窗口始终置顶")
        win_layout.addWidget(self._top_cb)

        self._through_cb = QCheckBox("鼠标穿透（穿透后只能用托盘操作）")
        win_layout.addWidget(self._through_cb)

        self._autostart_cb = QCheckBox("开机自动启动小鸡桌宠")
        win_layout.addWidget(self._autostart_cb)

        layout.addWidget(window_group)
        layout.addStretch()

        # ── 按钮 ──────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("保存")
        save_btn.setDefault(True)
        save_btn.setFixedWidth(80)
        save_btn.clicked.connect(self._save_and_close)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _load_values(self):
        self._scale_slider.setValue(self._settings.get("scale", 4))
        self._speed_slider.setValue(self._settings.get("anim_speed", 200))
        self._active_slider.setValue(self._settings.get("active_level", 5))
        self._move_slider.setValue(self._settings.get("move_speed", 3))
        self._top_cb.setChecked(self._settings.get("always_on_top", True))
        self._through_cb.setChecked(self._settings.get("click_through", False))
        self._autostart_cb.setChecked(_check_autostart())

    def _save_and_close(self):
        self._settings.set("scale", self._scale_slider.value())
        self._settings.set("anim_speed", self._speed_slider.value())
        self._settings.set("active_level", self._active_slider.value())
        self._settings.set("move_speed", self._move_slider.value())
        self._settings.set("always_on_top", self._top_cb.isChecked())
        self._settings.set("click_through", self._through_cb.isChecked())
        self._settings.set("autostart", self._autostart_cb.isChecked())
        _set_autostart(self._autostart_cb.isChecked())
        self.accept()
