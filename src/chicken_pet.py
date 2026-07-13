"""
小鸡桌宠主窗口 - 透明、无边框、可交互的桌面宠物
"""

import ctypes
import sys
import time

from PyQt5.QtWidgets import (
    QWidget, QMenu, QSystemTrayIcon, QApplication,
)
from PyQt5.QtGui import (
    QPainter, QIcon, QCursor,
)
from PyQt5.QtCore import (
    Qt, QPoint, QTimer, QRect,
)

from src.animation import AnimationManager, Anim
from src.chicken_ai import ChickenAI, BEAK_OFFSET_X_RATIO, BEAK_OFFSET_Y_RATIO
from src.settings_manager import Settings
from src.settings_dialog import SettingsDialog
from src.emote_popup import EmotePopup
from src.hay_widget import HayWidget

# ── Windows API 常量（鼠标穿透 / 层级控制） ──────────────────
WS_EX_LAYERED     = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
GWL_EXSTYLE       = -20
HWND_TOP          = 0         # 将窗口置于 Z-order 顶层
HWND_TOPMOST      = -1        # 所有 topmost 窗口带的绝对顶层（比 HWND_TOP 更强）
SWP_NOMOVE        = 0x0002
SWP_NOSIZE        = 0x0001
SWP_NOACTIVATE    = 0x0010

_user32 = ctypes.windll.user32
_get_window_long = _user32.GetWindowLongW
_set_window_long = _user32.SetWindowLongW
_set_window_pos  = _user32.SetWindowPos


class ChickenPet(QWidget):
    """星露谷小鸡桌宠主窗口"""

    def __init__(self):
        super().__init__()

        # ── 加载设置 ──────────────────────────
        self._settings = Settings()

        # ── 动画管理器 ─────────────────────────
        sprite_path = self._resolve_asset("white_chicken.png")
        self._anim = AnimationManager(
            sprite_path,
            scale=self._settings.scale,
            speed_ms=self._settings.anim_speed,
        )

        # ── AI 控制器 ──────────────────────────
        self._ai = ChickenAI(
            self._screen_geometry(),
            move_speed=self._settings.move_speed,
            display_size=self._anim.display_width,
        )
        self._ai.set_active_level(self._settings.active_level)

        # ── 窗口状态 ──────────────────────────
        self._dragging = False
        self._drag_offset = QPoint()
        self._hidden = False
        self._first_show = True   # 首次 show 标记

        # ── 点击/拖拽/长按 检测 ──────────────
        self._click_pending = False    # 等待判定（短按=爱心/拖拽=移动/长按=省略号）
        self._click_pos = QPoint()     # 按下时的全局坐标
        self._click_time = 0.0         # 按下时刻 (time.time())
        self._current_emote = None     # 当前表情弹窗引用（防止GC回收）
        self._ignore_mouse = False     # 逃跑挣脱后忽略鼠标，直到用户松手
        self._post_emote_action = None # 表情结束后的动作 (None=恢复 / "runaway"=快跑)

        # 长按计时器（2秒后触发省略号）
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._on_hold_timeout)
        self._HOLD_MS = 2000           # 长按触发阈值（毫秒）

        # 拖拽表情检测（80ms 采样 + 速度判定）
        self._DRAG_SAMPLE_MS = 80          # 位置采样间隔（毫秒）
        self._DRAG_FAST_PX = 20            # 单次采样位移 ≥ 此值算"快速拖拽"（≈250 px/s）
        self._DRAG_FAST_TICKS_NEEDED = 13  # 连续快速 tick 数（13×80ms≈1秒）
        self._drag_sample_timer = QTimer(self)
        self._drag_sample_timer.timeout.connect(self._on_drag_sample_tick)
        self._drag_sample_pos = QPoint()       # 上一次采样时的位置
        self._drag_latest_pos = QPoint()       # mouseMoveEvent 持续更新的最新位置
        self._drag_fast_ticks = 0              # 连续快速 tick 计数
        self._drag_emote_triggered = False     # 单次拖拽中表情最多触发一次
        self._dragging_during_emote = False  # 爱心动画期间用户拖拽小鸡（禁止触发其他表情）
        self._current_hay = None           # 当前干草浮窗引用（防止 GC 回收）
        self._feeding_active = False       # 喂食流程进行中（防重复触发）

        # 喂食追踪定时器（80ms，与AI tick同步）
        self._feeding_track_timer = QTimer(self)
        self._feeding_track_timer.setInterval(80)
        self._feeding_track_timer.timeout.connect(self._track_food_position)

        # 置顶刷新定时器（解决后来打开的窗口遮挡小鸡的问题）
        self._topmost_timer = QTimer(self)
        self._topmost_timer.setInterval(3000)  # 每3秒刷新一次
        self._topmost_timer.timeout.connect(self._refresh_topmost)

        # ── 初始化（顺序很重要！） ──────────────
        self._init_window()
        self._init_tray()
        self._connect_signals()

        # 初始位置（验证是否在屏幕内）
        x = self._settings.get("position_x", 200)
        y = self._settings.get("position_y", 200)
        screen = self._screen_geometry()
        w = self._anim.display_width
        h = self._anim.display_height
        # 如果坐标超出屏幕范围，重置到屏幕中央
        if x < 0 or y < 0 or x + w > screen.right() or y + h > screen.bottom():
            x = (screen.width() - w) // 2
            y = (screen.height() - h) // 2
        self.move(x, y)
        self._ai.set_position(x, y)

    # ═══════════════ 窗口初始化 ═══════════════

    def _resolve_asset(self, filename: str) -> str:
        """查找资源文件路径（兼容 PyInstaller 打包和源码运行）"""
        import os
        if getattr(sys, 'frozen', False):
            # PyInstaller 打包：资源在 _MEIPASS 中
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, "assets", filename)

    def _init_window(self):
        """设置透明无边框窗口（仅设置属性，不涉及 Windows API）"""
        # 注意：不用 Qt.SubWindow！会和 FramelessWindowHint 冲突
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

        w = self._anim.display_width
        h = self._anim.display_height
        self.setFixedSize(w, h)

    def _init_tray(self):
        """初始化系统托盘"""
        # 使用 walk_down 第一帧（行0列0）作为托盘图标
        icon_pixmap = self._anim.first_frame(Anim.WALK_DOWN)
        if icon_pixmap is None:
            icon_pixmap = self._anim.first_frame(0)

        self._tray_icon = QSystemTrayIcon(self)
        if icon_pixmap:
            self._tray_icon.setIcon(QIcon(icon_pixmap))
        self._tray_icon.setToolTip("星露谷小鸡 - 桌宠")
        # 同时设置窗口图标（用于任务栏等系统级显示）
        self.setWindowIcon(QIcon(icon_pixmap))

        # ── 右键菜单 ──────────────────────────
        menu = QMenu()

        act_show = menu.addAction("显示/隐藏")
        act_show.triggered.connect(self._toggle_visible)

        menu.addSeparator()

        self._act_top = menu.addAction("始终置顶")
        self._act_top.setCheckable(True)
        self._act_top.setChecked(self._settings.always_on_top)
        self._act_top.triggered.connect(self._toggle_always_on_top)

        self._act_through = menu.addAction("鼠标穿透")
        self._act_through.setCheckable(True)
        self._act_through.setChecked(self._settings.click_through)
        self._act_through.triggered.connect(self._toggle_click_through)

        menu.addSeparator()

        act_feed = menu.addAction("🌿 喂食")
        act_feed.triggered.connect(self._start_feeding)

        menu.addSeparator()

        act_settings = menu.addAction("设置...")
        act_settings.triggered.connect(self._open_settings)

        menu.addSeparator()

        act_exit = menu.addAction("退出")
        act_exit.triggered.connect(self._quit)

        self._tray_menu = menu
        self._tray_icon.setContextMenu(menu)

        # 双击托盘 → 显示/隐藏
        self._tray_icon.activated.connect(self._on_tray_activated)

        self._tray_icon.show()

    def _connect_signals(self):
        """连接信号槽"""
        self._ai.anim_changed.connect(self._anim.set_animation)
        self._ai.move_request.connect(self._on_ai_move)
        self._ai.feeding_done.connect(self._on_feeding_done)
        self._ai.food_reached.connect(self._on_food_reached)
        self._anim.frame_updated.connect(self.update)

    # ═══════════════ 首次显示时的 Windows 设置 ═══════════════

    def showEvent(self, event):
        """窗口首次显示时，执行依赖 winId() 的设置"""
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            # 延迟执行：确保 native window handle 已创建
            QTimer.singleShot(100, self._apply_windows_settings)

    def _apply_windows_settings(self):
        """在窗口显示后设置 Windows 特有的窗口属性"""
        self._apply_always_on_top()
        self._apply_click_through()

    # ═══════════════ 核心逻辑 ═══════════════

    def _screen_geometry(self) -> QRect:
        return QApplication.primaryScreen().availableGeometry()

    def _on_ai_move(self, x: int, y: int):
        if not self._dragging and not self._dragging_during_emote:
            self.move(x, y)
        self._sync_emote_position()
        self._ensure_above_hay()   # 小鸡移动后确保层级在干草之上

    # ── 表情弹窗位置同步 ──────────────────

    def _sync_emote_position(self):
        """将当前表情弹窗同步到小鸡头顶中央"""
        if self._current_emote is not None:
            try:
                ex = self.x() + (self.width() - self._current_emote.display_size) // 2
                ey = self.y() - self._current_emote.display_size
                self._current_emote.move(ex, ey)
            except Exception:
                pass  # 弹窗可能已被销毁，静默忽略

    def _ensure_above_hay(self):
        """确保小鸡窗口始终在干草窗口层级之上。
        使用 HWND_TOP 将小鸡置于 topmost 窗口带的绝对顶层，
        比 SetWindowPos(chicken, hay, ...) 更可靠（不依赖干草 HWND 是否有效）。"""
        if self._current_hay is not None:
            try:
                chicken_hwnd = int(self.winId())
                if chicken_hwnd:
                    _set_window_pos(chicken_hwnd, HWND_TOP,
                                    0, 0, 0, 0,
                                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            except Exception:
                pass

    # ═══════════════ 绘制 ═══════════════════

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)

        frame = self._anim.current_frame()
        if frame and not frame.isNull():
            painter.drawPixmap(0, 0, frame)
        painter.end()

    # ═══════════════ 鼠标交互 ═══════════════

    # ── 点击/拖拽判定阈值 ──────────────────
    _CLICK_MAX_MS = 200     # 短按最大时长（毫秒）
    _CLICK_MAX_PX = 3       # 短按最大位移（像素，曼哈顿距离）

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 逃跑状态中忽略所有交互（爱心状态允许拖拽）
            if self._ai.is_busy and not self._ai.is_heart:
                return

            # 爱心动画期间按下：允许拖拽小鸡但不触发任何表情
            if self._ai.is_heart:
                self._dragging_during_emote = True
                self._drag_offset = event.globalPos() - self.pos()
                # 不 freeze（爱心触发时已冻结），不 pause（HEART 需要 tick 计时）
                # 不启动 hold_timer / drag_sample_timer（禁止触发其他表情）
                return

            # 立刻冻结动画 + 暂停AI（按住期间画面不动、不走动）
            self._anim.freeze()
            self._ai.pause()
            # 记录按下起点，延迟判定是点击、拖拽还是长按
            self._click_pending = True
            self._click_pos = event.globalPos()
            self._click_time = time.time()
            self._hold_timer.start(self._HOLD_MS)  # 启动2秒长按计时
        elif event.button() == Qt.RightButton:
            self._tray_menu.popup(QCursor.pos())

    def mouseMoveEvent(self, event):
        # 逃跑挣脱后忽略鼠标，直到用户松手
        if self._ignore_mouse:
            return

        # 爱心动画期间拖拽：移动小鸡但不触发其他表情
        if self._dragging_during_emote:
            if event.buttons() & Qt.LeftButton:
                new_pos = event.globalPos() - self._drag_offset
                self.move(new_pos)
                self._ai.set_position(new_pos.x(), new_pos.y())
                self._sync_emote_position()
            return

        if not self._click_pending and not self._dragging:
            return

        if event.buttons() & Qt.LeftButton:
            delta = event.globalPos() - self._click_pos
            if self._click_pending and delta.manhattanLength() >= self._CLICK_MAX_PX:
                # 位移超过阈值 → 切换到拖拽模式，取消长按计时，启动快速拖拽采样
                self._click_pending = False
                self._hold_timer.stop()
                self._dragging = True
                self._drag_offset = self._click_pos - self.pos()
                self._drag_sample_pos = event.globalPos()
                self._drag_latest_pos = event.globalPos()
                self._drag_fast_ticks = 0
                self._drag_sample_timer.start(self._DRAG_SAMPLE_MS)

            if self._dragging:
                self._drag_latest_pos = event.globalPos()
                new_pos = self._drag_latest_pos - self._drag_offset
                self.move(new_pos)
                self._ai.set_position(new_pos.x(), new_pos.y())
                self._sync_emote_position()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 逃跑挣脱后首次松手 → 重置忽略标志
            if self._ignore_mouse:
                self._ignore_mouse = False
                return

            # 爱心动画期间拖拽松手 → 结束拖拽，等表情结束后再解冻
            if self._dragging_during_emote:
                self._dragging_during_emote = False
                if self._current_emote is None:
                    # 表情已结束 → 解冻恢复动画
                    self._anim.unfreeze()
                # AI 不需要 resume（HEART 期间未暂停，正常 tick 中）
                self._settings.set("position_x", self.x())
                self._settings.set("position_y", self.y())
                return

            self._hold_timer.stop()  # 取消长按计时

            if self._dragging:
                # 拖拽结束 → 停止采样计时器，重置标记
                self._dragging = False
                self._drag_sample_timer.stop()
                self._drag_emote_triggered = False
                if self._current_emote is None:
                    self._anim.unfreeze()
                    self._ai.resume()
                # 否则表情还在播放，等 _on_emote_finished 解冻
                self._settings.set("position_x", self.x())
                self._settings.set("position_y", self.y())
            elif self._click_pending:
                self._click_pending = False
                elapsed_ms = (time.time() - self._click_time) * 1000
                if elapsed_ms <= self._CLICK_MAX_MS:
                    # 短按 → 爱心（_trigger_emote 内部恢复AI + 解冻）
                    self._trigger_heart()
                else:
                    # 按住 >200ms 但 <2s 松手 → 解冻 + 恢复AI，不出表情
                    self._anim.unfreeze()
                    self._ai.resume()

    def _trigger_heart(self):
        """用户点击小鸡 → 爱心表情"""
        self._trigger_emote(emote_row=5, post_action=None)

    def _on_hold_timeout(self):
        """长按2秒触发 → 省略号表情 + 逃跑"""
        self._click_pending = False
        self._ignore_mouse = True  # 挣脱鼠标：忽略后续拖拽/释放
        self._trigger_emote(emote_row=10, post_action="runaway")

    def _on_drag_sample_tick(self):
        """每 80ms 采样一次鼠标位置，连续快速拖拽满 1 秒触发表情。

        位置由 mouseMoveEvent 持续缓存到 _drag_latest_pos，定时器只做等间隔采样，
        无需调用 QCursor.pos()（省去 Win32 GetCursorPos syscall）。"""
        if not self._dragging:
            self._drag_sample_timer.stop()
            return

        delta = (self._drag_latest_pos - self._drag_sample_pos).manhattanLength()
        self._drag_sample_pos = self._drag_latest_pos

        if delta >= self._DRAG_FAST_PX:
            self._drag_fast_ticks += 1
            if self._drag_fast_ticks >= self._DRAG_FAST_TICKS_NEEDED and not self._drag_emote_triggered:
                self._drag_emote_triggered = True
                self._drag_sample_timer.stop()  # 已触发，无需继续采样
                self._trigger_emote(emote_row=3, post_action=None)
        else:
            # 慢下来就重置计数，保证是"持续快速"拖拽
            self._drag_fast_ticks = 0

    def _trigger_emote(self, emote_row: int, post_action: str = None):
        """统一表情入口：冻结帧 + 弹出表情 + AI 进入 HEART。

        Args:
            emote_row: Emotes.png 中的表情行号 (5=爱心, 10=省略号)
            post_action: 表情结束后的动作 (None=恢复常态, "runaway"=快跑)
        """
        # 去重：特殊状态（爱心/逃跑）中忽略
        if self._ai.is_busy:
            return

        # 1. 动画应已被调用方冻结（mousePressEvent 或 _on_feeding_done），此处无需再 freeze
        # 2. 恢复AI计时（HEART需要tick计数），然后进入HEART
        self._ai.resume()
        self._ai.enter_heart()

        # 3. 清理上一个表情弹窗（如有），创建新弹窗
        if self._current_emote is not None:
            try:
                self._current_emote.close()
            except Exception:
                pass
            self._current_emote = None

        emotes_path = self._resolve_asset("Emotes.png")
        self._current_emote = EmotePopup(
            emotes_path, scale=3, emote_row=emote_row, parent=None)
        self._sync_emote_position()
        self._current_emote.show()

        # 4. 记录表情结束后的动作，绑定完成回调
        self._post_emote_action = post_action
        self._current_emote.finished.connect(self._on_emote_finished)

    def _on_emote_finished(self):
        """表情动画结束 → 解冻帧动画 + 执行后续动作（恢复/逃跑）

        注意：如果用户仍在拖拽中（正常拖拽或爱心期间拖拽），保持动画冻结，
        等松手时 mouseReleaseEvent 再解冻。"""
        if not self._dragging and not self._dragging_during_emote:
            # 非拖拽场景（爱心/省略号）→ 正常解冻
            self._anim.unfreeze()
        # else: 拖拽中 → 跳过 unfreeze，等 mouseReleaseEvent 中松手时解冻

        if self._current_emote is not None:
            self._current_emote.deleteLater()
            self._current_emote = None

        # 拖拽表情结束 → _drag_emote_triggered 保持 True，阻止同一轮拖拽再次触发
        # 不再需要 _drag_emote_active — _current_emote is None 自然表明表情已结束

        # 省略号表情结束后 → 快速跑开
        if self._post_emote_action == "runaway":
            self._ai.enter_runaway()
        self._post_emote_action = None

    # ═══════════════ 喂食流程 ═══════════════

    def _start_feeding(self):
        """托盘菜单「🌿 喂食」→ 创建干草浮窗跟随鼠标。
        busy 期间（爱心/逃跑/已喂食中）忽略。
        干草创建后立即开始追踪，无需等待放置！"""
        if self._ai.is_busy or self._feeding_active:
            # 显示气泡提示，让用户知道为什么点不了
            if self._feeding_active:
                msg = "🐤 小鸡正在吃饭呢，等它吃完再喂吧~"
            elif self._ai.is_heart:
                msg = "🐤 小鸡正在互动中，等它结束再喂吧~"
            else:
                msg = "🐤 小鸡正在忙，等一会儿再喂吧~"
            self._tray_icon.showMessage("星露谷小鸡", msg,
                QSystemTrayIcon.Information, 2000)
            return
        # 清理上一个可能残留的干草
        if self._current_hay is not None:
            try:
                self._current_hay.close()
            except Exception:
                pass
            self._current_hay = None

        self._feeding_active = True
        hay_path = self._resolve_asset("Objects-干草.png")
        hay2_path = self._resolve_asset("Objects-干草2.png")

        # ── 计算干草中心的有效放置边界 ──
        # 小鸡嘴部偏移 = display_size × (28/64, 64/64)，干草中心需使小鸡目标在移动范围内
        screen = self._screen_geometry()
        margin = 10
        dw = self._anim.display_width
        beak_x = int(dw * BEAK_OFFSET_X_RATIO)
        beak_y = int(dw * BEAK_OFFSET_Y_RATIO)
        hay_boundary = QRect(
            screen.left() + margin + beak_x,
            screen.top() + margin + beak_y,
            screen.width() - margin * 2 - dw,
            screen.height() - margin * 2 - dw,
        )

        self._current_hay = HayWidget(hay_path, hay2_path,
                                      boundary_rect=hay_boundary, parent=None)
        self._current_hay.placed.connect(self._on_hay_placed)
        self._current_hay.cancelled.connect(self._on_hay_cancelled)
        self._current_hay.dismissed.connect(self._on_hay_dismissed)
        self._current_hay.show()
        self._ensure_above_hay()   # 确保小鸡在干草之上

        # 立即开始追踪光标位置！
        cx, cy = self._current_hay.current_center()
        self._ai.start_feeding(cx, cy)
        self._feeding_track_timer.start()

    def _track_food_position(self):
        """每80ms更新AI的食物目标坐标（干草跟随鼠标或已放置）"""
        if self._current_hay is None or not self._feeding_active:
            self._feeding_track_timer.stop()
            return
        cx, cy = self._current_hay.current_center()
        self._ai.update_food_target(cx, cy)

    def _on_hay_placed(self, center_x: int, center_y: int):
        """左键放置干草：干草停止跟随鼠标，AI继续追踪固定位置"""
        self._ensure_above_hay()   # 干草放置后确保小鸡在干草之上

    def _on_hay_cancelled(self):
        """用户右键取消了干草放置"""
        self._feeding_track_timer.stop()
        self._feeding_active = False
        self._ai.cancel_feeding()
        self._current_hay = None

    def _on_hay_dismissed(self):
        """干草消失动画完成 → 清理引用"""
        self._current_hay = None

    def _on_food_reached(self):
        """小鸡到达干草 → 停止追踪，干草保持显示（等进食动画完成后再消失）"""
        self._feeding_track_timer.stop()
        # 干草保持显示，等进食动画完成后再在 _on_feeding_done 中触发消失动画

    def _on_feeding_done(self):
        """进食动画播放完毕 → 干草消失动画 + 笑脸表情（并行）"""
        self._feeding_active = False

        # 1. 干草消失动画（干草 → 干草2 → 300ms → 消失）
        if self._current_hay is not None:
            try:
                self._current_hay.start_dismiss_animation()
            except Exception:
                pass
            # 不设为 None！消失动画完成后由 _on_hay_dismissed 清理引用

        # 2. 冻结动画（自动触发没有 mousePressEvent 预先冻结，需手动冻结）
        self._anim.freeze()

        # 3. 触发笑脸表情（Emotes.png 第8行，三阶段动画）
        self._trigger_emote(emote_row=8, post_action=None)

    # ═══════════════ 窗口特性 ═══════════════

    def _apply_always_on_top(self):
        """应用置顶设置"""
        flags = self.windowFlags()
        if self._settings.always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        pos = self.pos()
        self.hide()
        self.setWindowFlags(flags)
        self.move(pos)
        self.show()

        # 启动或停止置顶刷新定时器
        if self._settings.always_on_top:
            self._topmost_timer.start()
        else:
            self._topmost_timer.stop()

    def _refresh_topmost(self):
        """定时刷新 HWND_TOPMOST — 确保小鸡始终在所有窗口之上。
        解决 Qt.WindowStaysOnTopHint 的已知问题：后来打开的新窗口
        （尤其是其他 topmost 窗口）可能盖住小鸡。"""
        if not self._settings.always_on_top:
            return
        try:
            hwnd = int(self.winId())
            if hwnd:
                _set_window_pos(hwnd, HWND_TOPMOST,
                                0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        except Exception:
            pass

    def _apply_click_through(self):
        """应用鼠标穿透设置"""
        try:
            hwnd = int(self.winId())
            if hwnd == 0:
                return  # 窗口还没有有效的原生句柄，跳过
            ex_style = _get_window_long(hwnd, GWL_EXSTYLE)
            if self._settings.click_through:
                _set_window_long(
                    hwnd, GWL_EXSTYLE,
                    ex_style | WS_EX_TRANSPARENT | WS_EX_LAYERED
                )
            else:
                _set_window_long(
                    hwnd, GWL_EXSTYLE,
                    ex_style & ~WS_EX_TRANSPARENT
                )
        except Exception:
            pass  # 静默处理，Windows API 调用失败不影响使用

    # ═══════════════ 托盘菜单槽 ═══════════════

    def _toggle_visible(self):
        if self._hidden:
            self.show()
            self._hidden = False
        else:
            self.hide()
            self._hidden = True

    def _toggle_always_on_top(self):
        current = self._settings.always_on_top
        self._settings.set("always_on_top", not current)
        self._act_top.setChecked(not current)
        self._apply_always_on_top()

    def _toggle_click_through(self):
        current = self._settings.click_through
        self._settings.set("click_through", not current)
        self._act_through.setChecked(not current)
        self._apply_click_through()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._toggle_visible()

    def _open_settings(self):
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec_():
            self._apply_settings()

    def _apply_settings(self):
        """重新加载并应用设置（所有选项立即生效）"""
        self._settings.load()
        # 缩放：重新加载精灵图 + 调整窗口大小
        new_scale = self._settings.scale
        if new_scale != self._anim.scale:
            self._anim.reload_scale(new_scale)
            self.setFixedSize(self._anim.display_width, self._anim.display_height)
            self._ai.set_display_size(self._anim.display_width)
        # 动画速度
        self._anim.set_speed(self._settings.anim_speed)
        # 移动速度
        self._ai.set_move_speed(self._settings.move_speed)
        # 活跃度
        self._ai.set_active_level(self._settings.active_level)
        # 窗口特性
        self._apply_always_on_top()
        self._apply_click_through()

    def _quit(self):
        self._settings.set("position_x", self.x())
        self._settings.set("position_y", self.y())
        # 清理表情弹窗
        if self._current_emote is not None:
            try:
                self._current_emote.close()
            except Exception:
                pass
            self._current_emote = None
        # 清理所有定时器和浮窗
        self._feeding_track_timer.stop()
        self._topmost_timer.stop()
        if self._current_hay is not None:
            try:
                self._current_hay.dismiss()
            except Exception:
                pass
            self._current_hay = None
        self._tray_icon.hide()
        QApplication.quit()

    def closeEvent(self, event):
        """关闭 → 最小化到托盘"""
        event.ignore()
        self.hide()
        self._hidden = True
