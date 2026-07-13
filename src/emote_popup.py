"""
表情弹窗 - 小鸡被点击后在头顶显示表情动画
三阶段: 气泡出现（行0正放）→ 表情4帧逐帧播放一次 → 气泡消失（行0倒放）

Emotes.png: 64×256, 4列×16行, 每格16×16
  行0: 气泡弹出动画（4帧，用于出现/消失）
  行3: 😵 一团乱麻表情（快速拖拽1秒触发）
  行4: ❗ 感叹号表情
  行5: ❤️ 爱心表情（点击触发）
  行10: 💬 省略号表情（长按2秒触发）

阶段时长（每帧80ms）:
  阶段0 出现: 4帧 × 80ms = 320ms
  阶段1 表情: 4帧 × 3ticks/帧 × 80ms ≈ 960ms（逐帧0→1→2→3，每帧停留~250ms，不循环）
  阶段2 消失: 4帧 × 80ms = 320ms
  总计: 4 + 12 + 4 = 20 ticks = 1600ms
"""

from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPixmap, QPainter
from PyQt5.QtCore import Qt, QTimer, pyqtSignal

# ── 常量 ──────────────────────────────────────────
BUBBLE_ROW       = 0   # 气泡动画所在行
CELL_SIZE        = 16  # 精灵图单元格像素
FRAME_MS         = 80  # 每帧间隔（毫秒）
APPEAR_FRAMES    = 4   # 出现帧数 (4×80=320ms)
DISAPPEAR_FRAMES = 4   # 消失帧数 (4×80=320ms)
EMOTE_FRAMES     = 4   # 表情帧数（逐帧播放一次）
EMOTE_FRAME_TICKS = 3   # 每帧停留 tick 数 (3×80ms=240ms≈250ms, 4帧≈1s)


class EmotePopup(QWidget):
    """表情浮窗 — 显示在小鸡头顶，三阶段动画结束后自动关闭"""

    # 动画完成信号
    finished = pyqtSignal()

    def __init__(self, emotes_path: str, scale: int = 3, emote_row: int = 5, parent=None):
        """
        Args:
            emotes_path: Emotes.png 精灵图路径
            scale: 缩放倍数 (默认3 → 16×3=48 像素)
            emote_row: 表情所在行号 (默认5=爱心, 10=省略号)
        """
        super().__init__(parent)
        self._scale = max(scale, 1)
        self._emote_row = emote_row
        self._display_size = CELL_SIZE * self._scale

        # 状态
        self._phase = 0         # 0=出现, 1=表情, 2=消失
        self._frame_index = 0   # 当前帧索引（出现/消失阶段用）
        self._emote_index = 0   # 表情阶段当前帧 (0→1→2→3，逐帧播放)
        self._emote_tick = 0    # 当前表情帧已停留 tick 数

        # 帧缓存 {(row, col): QPixmap}
        self._frames: dict = {}
        self._load_sprite(emotes_path)
        self._init_window()

        # 动画定时器
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(FRAME_MS)

    # ═══════════════ 初始化 ═══════════════

    def _load_sprite(self, path: str):
        """加载表情精灵图，按 16×16 切帧并缩放缓存"""
        sheet = QPixmap(path)
        if sheet.isNull():
            raise FileNotFoundError(f"无法加载表情图: {path}")

        cols = sheet.width() // CELL_SIZE
        rows = sheet.height() // CELL_SIZE
        dw = self._display_size

        for row in range(rows):
            for col in range(cols):
                x, y = col * CELL_SIZE, row * CELL_SIZE
                frame = sheet.copy(x, y, CELL_SIZE, CELL_SIZE)
                self._frames[(row, col)] = frame.scaled(
                    dw, dw,
                    Qt.KeepAspectRatio,
                    Qt.FastTransformation,
                )

    def _init_window(self):
        """设置透明无边框浮窗，鼠标事件穿透"""
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFixedSize(self._display_size, self._display_size)

    # ═══════════════ 三阶段动画 ═══════════════

    def _tick(self):
        """每 FRAME_MS 调用一次，推进动画阶段"""
        if self._phase == 0:
            # —— 阶段0: 气泡出现（行0 帧0→3）——
            self._frame_index += 1
            if self._frame_index >= APPEAR_FRAMES:
                self._phase = 1
                self._emote_index = 0
            self.update()

        elif self._phase == 1:
            # —— 阶段1: 每帧停留 EMOTE_FRAME_TICKS tick，4帧逐帧播放一次（≈1s）——
            self._emote_tick += 1
            if self._emote_tick >= EMOTE_FRAME_TICKS:
                self._emote_tick = 0
                self._emote_index += 1
                if self._emote_index >= EMOTE_FRAMES:
                    self._phase = 2
                    self._frame_index = APPEAR_FRAMES - 1
            self.update()

        elif self._phase == 2:
            # —— 阶段2: 气泡消失（行0 帧3→0 倒放）——
            self._frame_index -= 1
            if self._frame_index < 0:
                self._timer.stop()
                self.finished.emit()
                self.close()
                return
            self.update()

    # ═══════════════ 绘制 ═══════════════

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        if self._phase == 1:
            # 表情阶段 → 逐帧索引，从左到右各播一次
            col = self._emote_index
            frame = self._frames.get((self._emote_row, col))
        else:
            # 出现/消失 → 气泡动画
            col = max(0, min(self._frame_index, APPEAR_FRAMES - 1))
            frame = self._frames.get((BUBBLE_ROW, col))

        if frame and not frame.isNull():
            painter.drawPixmap(0, 0, frame)
        painter.end()

    # ═══════════════ 属性 ═══════════════

    @property
    def display_size(self) -> int:
        return self._display_size
