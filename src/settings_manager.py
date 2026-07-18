"""
设置管理器 - 负责读/写用户配置
"""

import json
import os
import sys
from pathlib import Path

# 默认设置
DEFAULT_SETTINGS = {
    "scale": 4,                # 缩放倍数 (像素 16×16 → 64×64)
    "always_on_top": True,     # 窗口始终置顶
    "click_through": False,    # 鼠标穿透（穿透后只能通过托盘操作）
    "anim_speed": 200,         # 动画帧间隔（毫秒）
    "move_speed": 3,           # 行走速度（像素/tick），范围2-8
    "active_level": 5,         # 活跃度 (1-10, 默认5)
    "autostart": False,        # 开机自动启动
    "position_x": 200,         # 初始X坐标
    "position_y": 200,         # 初始Y坐标
}


def _get_user_data_dir() -> str:
    """获取用户数据目录（%APPDATA%\StardewValleyChickenPet），
    不存在则自动创建。回退到 exe/项目 所在目录。"""
    appdata = os.environ.get('APPDATA', '')
    if appdata:
        data_dir = os.path.join(appdata, 'StardewValleyChickenPet')
    elif getattr(sys, 'frozen', False):
        data_dir = os.path.dirname(sys.executable)
    else:
        data_dir = str(Path(__file__).parent.parent)
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


class Settings:
    """应用设置管理器"""

    def __init__(self, filepath: str = None):
        if filepath is None:
            filepath = os.path.join(_get_user_data_dir(), "settings.json")
        self._path = filepath
        self.data = DEFAULT_SETTINGS.copy()
        self._migrate_old_settings()
        self.load()

    def _migrate_old_settings(self):
        """如果旧位置（exe/项目旁边）有 settings.json 而新位置没有，自动迁移"""
        if os.path.exists(self._path):
            return  # 新位置已有，不需要迁移
        if getattr(sys, 'frozen', False):
            old_path = os.path.join(os.path.dirname(sys.executable), "settings.json")
        else:
            old_path = str(Path(__file__).parent.parent / "settings.json")
        if os.path.exists(old_path) and old_path != self._path:
            import shutil
            try:
                shutil.copy2(old_path, self._path)
            except Exception:
                pass  # 迁移失败，使用默认值

    # ── 文件读写 ──────────────────────────────

    def load(self):
        """从磁盘加载设置，文件不存在或损坏时使用默认值"""
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.data.update(loaded)
            except (json.JSONDecodeError, IOError):
                pass  # 静默回退到默认值

    def save(self):
        """保存当前设置到磁盘"""
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except IOError:
            pass

    # ── 通用存取 ──────────────────────────────

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    # ── 便捷属性 ──────────────────────────────

    @property
    def scale(self) -> int:
        return self.data["scale"]

    @property
    def always_on_top(self) -> bool:
        return self.data["always_on_top"]

    @property
    def click_through(self) -> bool:
        return self.data["click_through"]

    @property
    def anim_speed(self) -> int:
        return self.data["anim_speed"]

    @property
    def move_speed(self) -> int:
        return self.data["move_speed"]

    @property
    def active_level(self) -> int:
        return self.data.get("active_level", 5)
