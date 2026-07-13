"""
动画管理器 - 加载精灵图并管理帧动画
精灵图布局 (64×112, 4列×7行, 每帧16×16):
  行0: 向下走  行1: 向右走  行2: 向上走  行3: 向左走
  行4: 向下&向右站立（原啄食行，啄食已废弃）
  行5: 向上&向左站立
  行6: 进食（喂食触发，4帧循环）

站立动画按方向选择帧对，慢速交替:
  向下 → 行4 列0-1
  向右 → 行4 列2-3
  向上 → 行5 列0-1
  向左 → 行5 列2-3
"""

from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, QTimer, QObject, pyqtSignal


# ==========================================
# 动画类型常量
# ==========================================
class Anim:
    WALK_DOWN  = 0   # 向下走
    WALK_RIGHT = 1   # 向右走
    WALK_UP    = 2   # 向上走
    WALK_LEFT  = 3   # 向左走
    EAT        = 6   # 进食（精灵图行6，4帧循环）
    IDLE       = 5   # 站立

    # 方向 -> (sprite_row, col_start, col_end)
    IDLE_MAP = {
        0: (4, 0, 1),   # 向下 -> eat_0, eat_1
        1: (4, 2, 3),   # 向右 -> eat_2, eat_3
        2: (5, 0, 1),   # 向上 -> idle_0, idle_1
        3: (5, 2, 3),   # 向左 -> idle_2, idle_3
    }

    IDLE_TICKS = 4    # 站立切换间隔 (200ms × 4 = 800ms)
    EAT_TICKS  = 2    # 进食切换间隔 (200ms × 2 = 400ms)，保留待后续调节进食速度


# ==========================================
# 动画管理器
# ==========================================
class AnimationManager(QObject):
    """小鸡精灵动画管理器"""

    frame_updated = pyqtSignal()

    def __init__(self, sprite_path: str, frame_w: int = 16, frame_h: int = 16,
                 scale: int = 4, speed_ms: int = 200):
        super().__init__()
        self.frame_w = frame_w
        self.frame_h = frame_h
        self.scale = scale
        self._frames: dict[tuple[int, int], QPixmap] = {}
        self._num_cols = 0
        self._num_rows = 0

        self._sprite_path = sprite_path
        self._anim = Anim.IDLE
        self._frame_index = 0

        # 冻结控制（引用计数，支持嵌套 freeze/unfreeze）
        self._frozen = 0
        self._pending_anim = None      # 冻结期间记录的待应用动画
        self._pending_direction = 0

        # 站立 / 啄食 共用方向
        self._idle_direction = 2
        self._idle_tick = 0
        self._idle_col = 0     # 0 或 1（帧对中的索引）

        self._load_sprite(sprite_path)

        self._timer = QTimer()
        self._timer.timeout.connect(self._next_frame)
        self._timer.start(speed_ms)

    # ---- 精灵图加载 ----------------------------------------------

    def _load_sprite(self, path: str):
        sheet = QPixmap(path)
        if sheet.isNull():
            raise FileNotFoundError(f"无法加载精灵图: {path}")

        self._num_cols = sheet.width() // self.frame_w
        self._num_rows = sheet.height() // self.frame_h
        display_w = self.frame_w * self.scale
        display_h = self.frame_h * self.scale

        for row in range(self._num_rows):
            for col in range(self._num_cols):
                x, y = col * self.frame_w, row * self.frame_h
                frame = sheet.copy(x, y, self.frame_w, self.frame_h)
                scaled = frame.scaled(
                    display_w, display_h,
                    Qt.KeepAspectRatio,
                    Qt.FastTransformation
                )
                self._frames[(row, col)] = scaled

    # ---- 动画控制 ------------------------------------------------

    def set_animation(self, anim: int, direction: int = 0):
        """切换到指定动画类型（冻结状态下记录待应用）"""
        if self._frozen > 0:
            self._pending_anim = anim
            self._pending_direction = direction
            return
        if anim < 0 or anim >= self._num_rows:
            anim = Anim.IDLE

        if self._anim != anim:
            self._anim = anim
            self._frame_index = 0

        # 站立：始终重置帧切换计数器（避免因 _anim 未变而跳帧变快）
        if anim == Anim.IDLE:
            self._idle_tick = 0
            self._idle_col = 0
            if direction in Anim.IDLE_MAP:
                self._idle_direction = direction

    # ---- 帧推进 --------------------------------------------------

    def _next_frame(self):
        """帧切换

        走路:  4 帧快速循环 (200ms/帧)
        站立:  方向对应的 2 帧慢速交替 (800ms/帧, IDLE_TICKS=4)

        冻结状态下不做任何帧推进。
        """
        if self._frozen > 0:
            return
        if self._anim == Anim.IDLE:
            # 站立：方向相关的 2 帧慢速交替
            self._idle_tick += 1
            if self._idle_tick >= Anim.IDLE_TICKS:
                self._idle_tick = 0
                self._idle_col = 1 - self._idle_col   # 0 <-> 1
                self.frame_updated.emit()
            # 没到 tick 数: 不发射信号，不重绘
        else:
            # 走路：4 帧正常循环
            self._frame_index = (self._frame_index + 1) % self._num_cols
            self.frame_updated.emit()

    # ---- 帧获取 --------------------------------------------------

    def current_frame(self) -> QPixmap:
        """获取当前应显示的帧"""
        if self._anim == Anim.IDLE:
            # 站立：方向对应的 2 帧
            row, col_start, _ = Anim.IDLE_MAP.get(
                self._idle_direction, (5, 0, 1))
            col = col_start + self._idle_col
        else:
            # 走路：4 帧循环
            row = min(self._anim, self._num_rows - 1)
            col = self._frame_index % self._num_cols
        return self._frames.get((row, col))

    def first_frame(self, anim: int = None) -> QPixmap:
        """获取指定动画的第0帧（托盘图标用）"""
        if anim is None:
            anim = Anim.IDLE
        if anim == Anim.IDLE:
            row, col_start, _ = Anim.IDLE_MAP.get(2, (5, 0, 1))
            return self._frames.get((row, col_start))
        row = min(anim, self._num_rows - 1)
        return self._frames.get((row, 0))

    # ---- 属性 ----------------------------------------------------

    @property
    def display_width(self) -> int:
        return self.frame_w * self.scale

    @property
    def display_height(self) -> int:
        return self.frame_h * self.scale

    @property
    def current_anim(self) -> int:
        return self._anim

    def set_speed(self, ms: int):
        self._timer.setInterval(max(ms, 50))

    def reload_scale(self, new_scale: int):
        """重新加载精灵图缩放（设置面板修改大小时立即生效）"""
        if new_scale == self.scale:
            return
        self.scale = new_scale
        self._frames.clear()
        self._load_sprite(self._sprite_path)
        self.frame_updated.emit()

    # ---- 冻结控制 ------------------------------------------------

    def freeze(self):
        """冻结动画 — 帧不再推进，set_animation 记录为 pending，画面停留在当前帧。
        支持嵌套调用（引用计数），每次 freeze 需对应一次 unfreeze。"""
        self._frozen += 1

    def unfreeze(self):
        """解冻动画 — 引用计数减 1，降到 0 时恢复正常帧推进并应用 pending 动画。
        支持嵌套调用（与 freeze 成对使用）。"""
        if self._frozen > 0:
            self._frozen -= 1
        if self._frozen == 0 and self._pending_anim is not None:
            pending_anim = self._pending_anim
            pending_direction = self._pending_direction
            self._pending_anim = None
            self._pending_direction = 0
            self.set_animation(pending_anim, pending_direction)
