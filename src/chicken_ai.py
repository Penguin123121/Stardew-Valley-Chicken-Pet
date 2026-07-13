"""
小鸡行为AI - 状态机驱动的小鸡行为决策
状态流转: IDLE ⇄ WALK (30%连续走路) / (外部触发) → HEART → 恢复到之前状态
          / (长按触发) → HEART(省略号) → RUNAWAY(快跑) → 恢复
"""

import random
from PyQt5.QtCore import QObject, QTimer, QPoint, QRect, pyqtSignal
from src.animation import Anim

# ── 特殊状态时长常量 ─────────────────────────
HEART_TOTAL_MS    = 1600  # 表情总时长（毫秒）= 4出现 + 12表情(3tick×4帧) + 4消失 = 20tick×80ms
RUNAWAY_TOTAL_MS  = 2000  # 逃跑快跑持续时长（毫秒）
RUNAWAY_SPEED_MUL = 2.5   # 逃跑速度倍率
EATING_TOTAL_MS   = 800   # 进食动画：4帧 × 200ms/帧 = 800ms，播完一轮就结束
BEAK_OFFSET_X_RATIO = 28 / 64   # 嘴部X偏移比例（相对小鸡显示尺寸）
BEAK_OFFSET_Y_RATIO = 64 / 64   # 嘴部Y偏移比例 = 1.0（小鸡底部）


class ChickenState:
    """行为状态常量"""
    IDLE    = "idle"
    WALKING = "walking"
    HEART   = "heart"     # 爱心状态（用户点击触发）
    RUNAWAY = "runaway"   # 逃跑状态（长按省略号后快跑）
    FEEDING = "feeding"   # 喂食状态（走向干草 + 进食）


class ChickenAI(QObject):
    """小鸡AI —— 决定「做什么」和「往哪走」"""

    # 信号: (动画类型, 方向)
    # direction: 0=下 1=右 2=上 3=左 — 仅 IDLE 时用于选择站立帧对
    anim_changed = pyqtSignal(int, int)
    move_request = pyqtSignal(int, int)
    feeding_done = pyqtSignal()   # 喂食完成（进食动画播完，状态已恢复）
    food_reached = pyqtSignal()  # 小鸡到达干草位置 → ChickenPet 清除干草

    def __init__(self, screen_rect: QRect, move_speed: int = 2,
                 display_size: int = 64, tick_ms: int = 80):
        super().__init__()
        self._screen = screen_rect
        self._move_speed = move_speed
        self._display_size = display_size
        self._pos = QPoint(200, 200)
        self._state = ChickenState.IDLE
        self._direction = 2  # 0=下 1=右 2=上 3=左 (默认朝上)

        self._tick_count = 0
        self._duration = 0
        self._move_dx = 0
        self._move_dy = 0

        # 暂停标志（用户按住小鸡时暂停AI，松手/表情触发后恢复）
        self._paused = False

        # 保存进入 HEART 前的状态，用于结束后恢复（变量名含 heart，实际用于所有特殊状态）
        self._pre_heart_state = None
        self._pre_heart_direction = 0

        # 喂食相关
        self._feeding_phase = "approaching"   # "approaching" | "eating"
        self._feeding_target_x = 0
        self._feeding_target_y = 0
        self._feeding_primary_axis = 'x'       # 优先走哪个轴: 'x' | 'y'

        # 活跃度参数（默认等级5）
        self._walk_probability = 0.57
        self._idle_min_ticks = 23
        self._idle_max_ticks = 40

        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(tick_ms)

        self._enter_state(ChickenState.IDLE)

    # ═══════════════ 公开方法 ═══════════════

    def current_position(self) -> QPoint:
        return QPoint(self._pos)

    def set_position(self, x: int, y: int):
        self._pos = QPoint(x, y)

    def set_screen_rect(self, rect: QRect):
        self._screen = rect

    def set_move_speed(self, speed: int):
        self._move_speed = speed

    def set_display_size(self, size: int):
        self._display_size = size

    def set_active_level(self, level: int):
        """设置活跃度 (1-10)，控制走路概率和站立时长。
        等级 1=懒散(30%走路,站3-5s)，等级 10=活跃(90%走路,站0.5-1s)"""
        level = max(1, min(10, level))
        # 走路概率: 0.30 ~ 0.90 (线性)
        self._walk_probability = 0.30 + (level - 1) * (0.60 / 9)
        # 站立时长: 级1=37-62tick(3-5s) → 级10=6-13tick(0.5-1s)
        self._idle_min_ticks = int(37 - (level - 1) * 31 / 9)
        self._idle_max_ticks = int(62 - (level - 1) * 49 / 9)

    # ── 暂停控制 ──────────────────────────

    def pause(self):
        """暂停AI计时（用户按住小鸡时调用），tick不推进状态"""
        self._paused = True

    def resume(self):
        """恢复AI计时（松手或触发表情后调用）"""
        self._paused = False

    @property
    def is_paused(self) -> bool:
        return self._paused

    # ── 特殊状态（外部触发） ──────────────────

    @property
    def is_heart(self) -> bool:
        """是否正处于爱心状态（用于点击去重）"""
        return self._state == ChickenState.HEART

    @property
    def is_busy(self) -> bool:
        """是否正处于特殊状态（爱心/逃跑/喂食），此期间忽略所有用户交互"""
        return self._state in (ChickenState.HEART, ChickenState.RUNAWAY,
                               ChickenState.FEEDING)

    def enter_heart(self):
        """外部调用：进入爱心状态，持续 HEART_TOTAL_MS 后自动回到之前状态"""
        if self._state == ChickenState.HEART:
            return  # 已在爱心状态，忽略
        self._enter_state(ChickenState.HEART)

    def enter_runaway(self):
        """外部调用：进入逃跑状态（在省略号表情结束后由 ChickenPet 调用），
        持续 RUNAWAY_TOTAL_MS 后自动回到正常状态。"""
        self._enter_state(ChickenState.RUNAWAY)

    def start_feeding(self, hay_cx: int, hay_cy: int):
        """外部调用：开始喂食 — 走向干草位置，到达后播放进食动画。

        Args:
            hay_cx, hay_cy: 干草中心坐标（屏幕坐标）
        仅在 IDLE/WALKING 状态下可触发。HEART/RUNAWAY/已 FEEDING 时忽略。
        """
        if self._state in (ChickenState.HEART, ChickenState.RUNAWAY,
                           ChickenState.FEEDING):
            return
        self.update_food_target(hay_cx, hay_cy)
        self._enter_state(ChickenState.FEEDING)

    def update_food_target(self, hay_center_x: int, hay_center_y: int):
        """更新食物目标坐标（干草在鼠标上时会随光标移动）。

        使用嘴部偏移计算小鸡该去的左上角坐标，使进食时嘴对准干草中心。
        """
        self._feeding_target_x = hay_center_x - int(self._display_size * BEAK_OFFSET_X_RATIO)
        self._feeding_target_y = hay_center_y - int(self._display_size * BEAK_OFFSET_Y_RATIO)

    def cancel_feeding(self):
        """取消喂食（用户右键取消了干草放置）→ 恢复到之前状态。"""
        if self._state == ChickenState.FEEDING:
            prev_state = self._pre_heart_state or ChickenState.IDLE
            prev_dir = self._pre_heart_direction
            self._enter_state(prev_state, prev_dir)

    # ═══════════════ 状态机核心 ═══════════════

    def _enter_state(self, state: str, direction: int = None):
        # 进入特殊状态前保存当前状态（用于结束后恢复）
        # 仅当从正常状态（非特殊状态）进入时才保存，避免嵌套覆盖
        if state in (ChickenState.HEART, ChickenState.RUNAWAY, ChickenState.FEEDING):
            if self._state not in (ChickenState.HEART, ChickenState.RUNAWAY,
                                   ChickenState.FEEDING):
                self._pre_heart_state = self._state
                self._pre_heart_direction = self._direction

        self._state = state
        self._tick_count = 0

        if state == ChickenState.IDLE:
            # IDLE: 时长由活跃度决定 (tick=80ms)
            self._duration = random.randint(
                self._idle_min_ticks, self._idle_max_ticks)
            self.anim_changed.emit(Anim.IDLE, self._direction)

        elif state == ChickenState.WALKING:
            self._duration = random.randint(25, 70)
            if direction is not None:
                self._direction = direction
            else:
                self._direction = random.randint(0, 3)
            anim_map = {0: Anim.WALK_DOWN, 1: Anim.WALK_RIGHT,
                        2: Anim.WALK_UP,  3: Anim.WALK_LEFT}
            self.anim_changed.emit(anim_map[self._direction], self._direction)
            self._pick_move_dir()

        elif state == ChickenState.HEART:
            # 爱心/省略号状态：固定时长，动画冻结，不移动
            tick_ms = self._timer.interval()
            self._duration = max(1, HEART_TOTAL_MS // tick_ms)
            self.anim_changed.emit(Anim.IDLE, self._direction)

        elif state == ChickenState.RUNAWAY:
            # 逃跑状态：固定时长，快速移动
            tick_ms = self._timer.interval()
            self._duration = max(1, RUNAWAY_TOTAL_MS // tick_ms)
            if direction is not None:
                self._direction = direction
            else:
                self._direction = random.randint(0, 3)
            anim_map = {0: Anim.WALK_DOWN, 1: Anim.WALK_RIGHT,
                        2: Anim.WALK_UP,  3: Anim.WALK_LEFT}
            self.anim_changed.emit(anim_map[self._direction], self._direction)
            self._pick_move_dir(int(self._move_speed * RUNAWAY_SPEED_MUL))

        elif state == ChickenState.FEEDING:
            # 喂食状态：先走向干草，到达后播放进食动画
            self._feeding_phase = "approaching"
            # 确定优先走的轴：距离更远的轴先走
            dx = self._feeding_target_x - self._pos.x()
            dy = self._feeding_target_y - self._pos.y()
            if abs(dx) >= abs(dy):
                self._feeding_primary_axis = 'x'
                self._direction = 1 if dx > 0 else 3  # 右 或 左
            else:
                self._feeding_primary_axis = 'y'
                self._direction = 0 if dy > 0 else 2  # 下 或 上
            anim_map = {0: Anim.WALK_DOWN, 1: Anim.WALK_RIGHT,
                        2: Anim.WALK_UP,  3: Anim.WALK_LEFT}
            self.anim_changed.emit(anim_map[self._direction], self._direction)
            self._pick_move_dir()
            # duration 不设上限，由到达检测控制退出

    def _tick(self):
        if self._paused:
            return  # 暂停期间不推进任何状态
        self._tick_count += 1

        if self._state == ChickenState.IDLE:
            self._tick_idle()
        elif self._state == ChickenState.WALKING:
            self._tick_walking()
        elif self._state == ChickenState.HEART:
            # 爱心结束 → 恢复到点击前的状态（保持方向）
            if self._tick_count >= self._duration:
                prev_state = self._pre_heart_state or ChickenState.IDLE
                prev_dir = self._pre_heart_direction
                self._enter_state(prev_state, prev_dir)
        elif self._state == ChickenState.RUNAWAY:
            self._tick_runaway()
        elif self._state == ChickenState.FEEDING:
            self._tick_feeding()

    def _tick_idle(self):
        if self._tick_count >= self._duration:
            # 走路概率由活跃度决定
            if random.random() < self._walk_probability:
                self._enter_state(ChickenState.WALKING)
            else:
                self._enter_state(ChickenState.IDLE)

    def _tick_walking(self):
        if self._tick_count >= self._duration:
            # 30% 概率连续走路（换方向），70% 进入站立
            if random.random() < 0.30:
                new_dir = random.randint(0, 3)
                self._enter_state(ChickenState.WALKING, new_dir)
            else:
                self._enter_state(ChickenState.IDLE)
            return

        margin = 10
        new_x = self._pos.x() + self._move_dx
        new_y = self._pos.y() + self._move_dy

        left   = self._screen.left() + margin
        top    = self._screen.top() + margin
        right  = self._screen.right() - self._display_size - margin
        bottom = self._screen.bottom() - self._display_size - margin

        bounced = False
        if new_x < left:
            new_x = left
            self._move_dx = abs(self._move_dx)
            self._direction = 1
            bounced = True
        elif new_x > right:
            new_x = right
            self._move_dx = -abs(self._move_dx)
            self._direction = 3
            bounced = True
        if new_y < top:
            new_y = top
            self._move_dy = abs(self._move_dy)
            self._direction = 0
            bounced = True
        elif new_y > bottom:
            new_y = bottom
            self._move_dy = -abs(self._move_dy)
            self._direction = 2
            bounced = True

        if bounced:
            anim_map = {0: Anim.WALK_DOWN, 1: Anim.WALK_RIGHT,
                        2: Anim.WALK_UP,  3: Anim.WALK_LEFT}
            self.anim_changed.emit(anim_map[self._direction], self._direction)

        self._pos = QPoint(int(new_x), int(new_y))
        self.move_request.emit(int(new_x), int(new_y))

    def _tick_runaway(self):
        """逃跑 tick：到时间后恢复之前状态，否则快速移动（含边缘反弹）"""
        if self._tick_count >= self._duration:
            prev_state = self._pre_heart_state or ChickenState.IDLE
            prev_dir = self._pre_heart_direction
            self._enter_state(prev_state, prev_dir)
            return

        margin = 10
        new_x = self._pos.x() + self._move_dx
        new_y = self._pos.y() + self._move_dy

        left   = self._screen.left() + margin
        top    = self._screen.top() + margin
        right  = self._screen.right() - self._display_size - margin
        bottom = self._screen.bottom() - self._display_size - margin

        bounced = False
        if new_x < left:
            new_x = left
            self._move_dx = abs(self._move_dx)
            self._direction = 1
            bounced = True
        elif new_x > right:
            new_x = right
            self._move_dx = -abs(self._move_dx)
            self._direction = 3
            bounced = True
        if new_y < top:
            new_y = top
            self._move_dy = abs(self._move_dy)
            self._direction = 0
            bounced = True
        elif new_y > bottom:
            new_y = bottom
            self._move_dy = -abs(self._move_dy)
            self._direction = 2
            bounced = True

        if bounced:
            anim_map = {0: Anim.WALK_DOWN, 1: Anim.WALK_RIGHT,
                        2: Anim.WALK_UP,  3: Anim.WALK_LEFT}
            self.anim_changed.emit(anim_map[self._direction], self._direction)

        self._pos = QPoint(int(new_x), int(new_y))
        self.move_request.emit(int(new_x), int(new_y))

    # ═══════════════ 喂食导航 + 进食 ═══════════════

    def _tick_feeding(self):
        """喂食 tick：approach 阶段走轴对齐导航 → eating 阶段播放进食动画"""
        if self._feeding_phase == "approaching":
            self._tick_feeding_approach()
        elif self._feeding_phase == "eating":
            # 注意：_tick_count 已在 _tick() 中 +1，此处不重复加
            tick_ms = self._timer.interval()
            eating_ticks = max(1, EATING_TOTAL_MS // tick_ms)
            if self._tick_count >= eating_ticks:
                # 进食结束 → 先恢复状态（退出 FEEDING），再通知外部
                prev_state = self._pre_heart_state or ChickenState.IDLE
                prev_dir = self._pre_heart_direction
                self._enter_state(prev_state, prev_dir)
                self.feeding_done.emit()

    def _tick_feeding_approach(self):
        """轴对齐导航：先走较远轴，对齐后切换另一轴，两轴都到则进入进食阶段。

        使用嘴部偏移计算目标，公差=4px（比旧的 display_size//2 ≈32px 精确得多）。
        """
        target_x, target_y = self._feeding_target_x, self._feeding_target_y
        tolerance = 4  # 紧公差（像素）
        dx = target_x - self._pos.x()
        dy = target_y - self._pos.y()

        # 两个轴都到达 → 吸附到精确位置 → 进入进食
        if abs(dx) <= tolerance and abs(dy) <= tolerance:
            self._pos = QPoint(target_x, target_y)
            self._enter_eating_phase()
            return

        direction_changed = False

        if self._feeding_primary_axis == 'x':
            if abs(dx) <= tolerance:
                # X轴到齐 → 切换到Y轴
                self._feeding_primary_axis = 'y'
                self._direction = 0 if dy > 0 else 2  # 下 或 上
                direction_changed = True
            else:
                new_dir = 1 if dx > 0 else 3  # 右 或 左
                if new_dir != self._direction:
                    self._direction = new_dir
                    direction_changed = True
                step = min(abs(dx), self._move_speed)
                self._pos.setX(self._pos.x() + (step if dx > 0 else -step))
        else:  # 'y'
            if abs(dy) <= tolerance:
                # Y轴到齐 → 切换到X轴
                self._feeding_primary_axis = 'x'
                self._direction = 1 if dx > 0 else 3  # 右 或 左
                direction_changed = True
            else:
                new_dir = 0 if dy > 0 else 2  # 下 或 上
                if new_dir != self._direction:
                    self._direction = new_dir
                    direction_changed = True
                step = min(abs(dy), self._move_speed)
                self._pos.setY(self._pos.y() + (step if dy > 0 else -step))

        # 屏幕边缘 clamp（复用正常走路边距逻辑）
        margin = 10
        left   = self._screen.left() + margin
        top    = self._screen.top() + margin
        right  = self._screen.right() - self._display_size - margin
        bottom = self._screen.bottom() - self._display_size - margin

        if self._pos.x() < left:
            self._pos.setX(left)
        elif self._pos.x() > right:
            self._pos.setX(right)
        if self._pos.y() < top:
            self._pos.setY(top)
        elif self._pos.y() > bottom:
            self._pos.setY(bottom)

        if direction_changed:
            anim_map = {0: Anim.WALK_DOWN, 1: Anim.WALK_RIGHT,
                        2: Anim.WALK_UP,  3: Anim.WALK_LEFT}
            self.anim_changed.emit(anim_map[self._direction], self._direction)
            self._pick_move_dir()

        self.move_request.emit(self._pos.x(), self._pos.y())

    def _enter_eating_phase(self):
        """切换到进食子阶段：播放行6进食动画，持续 EATING_TOTAL_MS"""
        self._feeding_phase = "eating"
        self._tick_count = 0
        self.food_reached.emit()  # 通知外部干草已被"吃到"
        self.anim_changed.emit(Anim.EAT, self._direction)

    def _pick_move_dir(self, speed=None):
        """根据方向设置移动速度（可选参数用于逃跑加速）"""
        s = speed if speed is not None else self._move_speed
        dirs = {0: (0, s), 1: (s, 0), 2: (0, -s), 3: (-s, 0)}
        self._move_dx, self._move_dy = dirs.get(self._direction, (0, s))
