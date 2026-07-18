"""
星露谷小鸡桌宠 - 入口文件

运行方式:
    python -m src.main       (推荐)
    python src/main.py       (备选)
"""

import sys
import os
import atexit
import signal
import traceback
from datetime import datetime

# ── 路径解析（兼容 PyInstaller 打包） ──
if getattr(sys, 'frozen', False):
    _project_root = sys._MEIPASS
    _exe_dir = os.path.dirname(sys.executable)
else:
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _exe_dir = _project_root


def _get_user_data_dir() -> str:
    """获取用户数据目录（%APPDATA%\StardewValleyChickenPet），
    不存在则自动创建。回退到 exe/项目 所在目录。"""
    appdata = os.environ.get('APPDATA', '')
    if appdata:
        data_dir = os.path.join(appdata, 'StardewValleyChickenPet')
    else:
        data_dir = _exe_dir
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


_user_root = _get_user_data_dir()

if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# ── 启动日志（确保 pythonw 无控制台时也能捕获错误） ──
LOG_FILE = os.path.join(_user_root, "启动日志.txt")


def _log(msg: str):
    """向日志文件追加一行（带时间戳）"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")
    except Exception:
        pass  # 日志写入失败不应阻止启动


# 将 stderr 同时输出到日志文件
class _LogTee:
    """同时写入原始 stderr 和日志文件（兼容 pythonw 下 stderr 为 None）"""
    def __init__(self, original, log_path):
        self._original = original
        self._log_path = log_path

    def write(self, data):
        try:
            if self._original is not None:
                self._original.write(data)
        except Exception:
            pass
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(data)
        except Exception:
            pass

    def flush(self):
        try:
            if self._original is not None:
                self._original.flush()
        except Exception:
            pass

    def close(self):
        try:
            if self._original is not None:
                self._original.close()
        except Exception:
            pass


# 尽早设置错误日志（在 QApplication 之前，因为导入也可能失败）
try:
    _log("==== 启动桌宠 ====")
    _log(f"Python: {sys.executable}")
    _log(f"工作目录: {os.getcwd()}")
    _log(f"项目目录: {_project_root}")
    sys.stderr = _LogTee(sys.stderr, LOG_FILE)  # type: ignore
except Exception:
    pass

# ── 导入 PyQt5 ──────────────────────────────────
try:
    from PyQt5.QtWidgets import QApplication, QMessageBox
    from PyQt5.QtGui import QFont
    _log("PyQt5 导入成功")
except Exception as e:
    _log(f"PyQt5 导入失败: {e}\n{traceback.format_exc()}")
    # 弹一个简单的消息框（不依赖 PyQt5）
    import ctypes
    ctypes.windll.user32.MessageBoxW(0,
        f"PyQt5 导入失败！\n\n请运行: pip install PyQt5\n\n错误: {e}",
        "星露谷桌宠 - 启动失败", 0x10)
    sys.exit(1)

from src.chicken_pet import ChickenPet

# ── 单实例锁文件 ──────────────────────────────
LOCK_FILE = os.path.join(_user_root, ".pet_lock.pid")


def check_existing_instance():
    """检查是否已有实例在运行（同时检查 python.exe 和 pythonw.exe）"""
    if not os.path.exists(LOCK_FILE):
        return False

    try:
        with open(LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
        import subprocess
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, shell=True
        )
        output_lower = result.stdout.lower()
        if "python.exe" in output_lower or "pythonw.exe" in output_lower:
            _log(f"检测到已有实例运行中 (PID={pid})")
            return True
    except (ValueError, FileNotFoundError, OSError):
        pass

    # 锁文件无效，清理
    try:
        os.remove(LOCK_FILE)
    except OSError:
        pass
    return False


def write_lock():
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    _log(f"写入锁文件 PID={os.getpid()}")


def remove_lock():
    try:
        os.remove(LOCK_FILE)
        _log("移除锁文件")
    except OSError:
        pass


def _safe_print(msg: str):
    """安全打印——兼容 pythonw（sys.stdout 为 None）"""
    try:
        if sys.stdout is not None:
            print(msg)
    except Exception:
        pass  # pythonw 下静默


def main():
    # 安全设置 stdout 编码
    try:
        if hasattr(sys.stdout, 'encoding') and sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            _log("stdout 已重配置为 utf-8")
    except Exception as e:
        _log(f"stdout 重配置失败（非致命）: {e}")

    # ── 检查是否已有实例在运行 ──────────────────
    if check_existing_instance():
        msg = "检测到小鸡已经在运行中！\n请查看系统托盘（任务栏右下角），\n双击小鸡图标即可让隐藏的小鸡重新出现。"
        _safe_print(msg)
        _log("检测到已有实例，退出")
        # 如果有 QApplication，弹消息框；否则用 Windows API
        try:
            app_temp = QApplication(sys.argv[:1])
            QMessageBox.information(None, "星露谷桌宠", msg)
        except Exception:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "星露谷桌宠", 0x40)
        return 0

    write_lock()
    atexit.register(remove_lock)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    _log("正在创建 QApplication...")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    font = QFont("Microsoft YaHei", 9)
    app.setFont(font)

    try:
        _log("正在创建 ChickenPet...")
        pet = ChickenPet()
        pet.show()
        _log("ChickenPet 已显示")
        _safe_print("小鸡桌宠已启动！在桌面找找看~")
        _safe_print("提示: 右键小鸡弹出菜单，右键系统托盘图标也有菜单。")
    except Exception as e:
        _log(f"启动失败: {e}\n{traceback.format_exc()}")
        _safe_print(f"启动失败: {e}")
        # 用 Windows 消息框报告错误（此时可能还没有 QApplication）
        try:
            QMessageBox.critical(None, "星露谷桌宠 - 启动失败",
                f"小鸡启动失败！\n\n错误: {e}\n\n详情请查看: {LOG_FILE}")
        except Exception:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,
                f"小鸡启动失败！\n\n错误: {e}\n\n详情请查看: {LOG_FILE}",
                "星露谷桌宠 - 启动失败", 0x10)
        remove_lock()
        return 1

    _log("进入 Qt 事件循环...")
    exit_code = app.exec_()
    _log(f"Qt 事件循环结束, exit_code={exit_code}")
    remove_lock()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

