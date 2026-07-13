"""
干草浮窗 — 喂食功能的鼠标交互组件

四阶段生命周期:
  1. 跟随鼠标 — 半透明，随光标移动，等待放置
  2. 已放置 — 不透明，固定位置，等待小鸡来吃
  3. 消失动画 — 小鸡吃完后，干草→干草2→停留→消失
  4. 消失 — 窗口关闭
"""

from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPixmap, QPainter, QCursor
from PyQt5.QtCore import Qt, QTimer, QRect, pyqtSignal

# ── 常量 ──────────────────────────────────────────
HAY_CELL_SIZE       = 16      # 干草原图尺寸
HAY_SCALE           = 3       # 缩放倍数（16×3 = 48）
HAY_FOLLOW_MS       = 16      # 跟随鼠标刷新间隔（~60fps）
HAY_DISAPPEAR_MS    = 300     # 干草2停留时长（消失动画）


class HayWidget(QWidget):
    """干草浮窗 — 跟随鼠标 / 放置后等待小鸡进食 / 消失动画"""

    placed    = pyqtSignal(int, int)    # 放置信号 (干草中心x, 干草中心y)
    cancelled = pyqtSignal()           # 取消信号（右键取消放置）
    dismissed = pyqtSignal()           # 消失动画完成信号（通知 ChickenPet 清理引用）

    def __init__(self, hay_path: str, hay2_path: str,
                 boundary_rect: QRect = None, parent=None):
        """
        Args:
            hay_path: Objects-干草.png 的路径
            hay2_path: Objects-干草2.png 的路径（消失动画用）
            boundary_rect: 干草中心允许放置的范围（屏幕坐标），None=不限制
        """
        super().__init__(parent)
        self._display_size = HAY_CELL_SIZE * HAY_SCALE
        self._following = True       # True=跟随鼠标, False=已放置
        self._boundary_rect = boundary_rect

        # 加载并缩放干草图片
        pixmap1 = QPixmap(hay_path)
        if pixmap1.isNull():
            raise FileNotFoundError(f"无法加载干草图片: {hay_path}")
        self._pixmap1 = pixmap1.scaled(
            self._display_size, self._display_size,
            Qt.KeepAspectRatio,
            Qt.FastTransformation,
        )

        pixmap2 = QPixmap(hay2_path)
        if pixmap2.isNull():
            raise FileNotFoundError(f"无法加载干草图片: {hay2_path}")
        self._pixmap2 = pixmap2.scaled(
            self._display_size, self._display_size,
            Qt.KeepAspectRatio,
            Qt.FastTransformation,
        )

        # 当前绘制的图片（跟随/放置阶段用干草1，消失动画时切换为干草2）
        self._pixmap = self._pixmap1

        self._init_window()

        # 鼠标跟随定时器
        self._follow_timer = QTimer(self)
        self._follow_timer.timeout.connect(self._follow_mouse)
        self._follow_timer.start(HAY_FOLLOW_MS)

        # 消失动画定时器（单次，切换到干草2后延迟关闭）
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._on_dismiss_timer)

    # ═══════════════ 初始化 ═══════════════

    def _init_window(self):
        """透明无边框浮窗，可接收鼠标事件（与 EmotePopup 不同）"""
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        # ⚠️ 不设置 WA_TransparentForMouseEvents — 需要接收左右键点击
        self.setFixedSize(self._display_size, self._display_size)

    # ═══════════════ 鼠标跟随 ═══════════════

    def _follow_mouse(self):
        """将窗口中心对齐到鼠标光标位置（受 boundary_rect 限制）"""
        if self._following:
            pos = QCursor.pos()
            cx, cy = pos.x(), pos.y()
            # clamp 干草中心到有效放置区域
            if self._boundary_rect is not None:
                r = self._boundary_rect
                cx = max(r.left(), min(cx, r.right()))
                cy = max(r.top(), min(cy, r.bottom()))
            self.move(cx - self._display_size // 2,
                      cy - self._display_size // 2)

    # ═══════════════ 点击处理 ═══════════════

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._following:
            # 左键：放置干草
            self._following = False
            self._follow_timer.stop()
            center_x = self.x() + self._display_size // 2
            center_y = self.y() + self._display_size // 2
            self.placed.emit(center_x, center_y)
            self.update()  # 重绘（从半透明变不透明）
        elif event.button() == Qt.RightButton:
            # 右键：取消放置
            self._dismiss()
            self.cancelled.emit()

    # ═══════════════ 绘制 ═══════════════

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._following:
            painter.setOpacity(0.65)   # 跟随期间半透明
        else:
            painter.setOpacity(1.0)    # 放置后/消失动画期间不透明
        painter.drawPixmap(0, 0, self._pixmap)
        painter.end()

    # ═══════════════ 公开方法 ═══════════════

    def current_center(self):
        """返回干草当前中心坐标（全局屏幕坐标），始终基于窗口实际位置。"""
        return self.x() + self._display_size // 2, self.y() + self._display_size // 2

    def dismiss(self):
        """立即关闭（用于取消喂食、退出应用等路径，不走消失动画）"""
        self._dismiss()

    def start_dismiss_animation(self):
        """开始消失动画：切换到干草2 → 停留 HAY_DISAPPEAR_MS → 关闭。
        由 ChickenPet._on_feeding_done() 在进食动画完成后调用。
        关闭前会发射 dismissed 信号，通知 ChickenPet 清理引用。
        """
        self._following = False
        self._follow_timer.stop()
        self._pixmap = self._pixmap2      # 切换到干草2
        self.update()                      # 立即重绘
        self._dismiss_timer.start(HAY_DISAPPEAR_MS)

    # ═══════════════ 私有方法 ═══════════════

    def _on_dismiss_timer(self):
        """消失动画计时器触发 → 发射 dismissed → 关闭窗口"""
        self.dismissed.emit()
        self._dismiss()

    def _dismiss(self):
        self._following = False
        self._follow_timer.stop()
        self._dismiss_timer.stop()
        self.close()

    # ═══════════════ 属性 ═══════════════

    @property
    def is_placed(self) -> bool:
        """是否已放置（不再跟随鼠标）"""
        return not self._following

    @property
    def display_size(self) -> int:
        return self._display_size
