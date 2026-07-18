# CLAUDE.md

此文件为 Claude Code（claude.ai/code）在此仓库中工作时提供指引。

## 项目概述

星露谷小鸡桌宠 — 基于 PyQt5 的 Windows 桌面透明宠物。一只从星露谷物语中走出来的白色小鸡，会在屏幕上自由走动、发呆，支持鼠标拖拽（快速拖拽1秒触发一团乱麻表情）、点击互动（爱心表情）、长按互动（省略号+逃跑）、系统托盘管理、设置面板自定义。

## 项目架构

```
星露谷桌宠/
├── README.md                  # 用户文档（安装/使用/FAQ）
├── install.bat                # 一键安装脚本（自动装依赖+建快捷方式）
├── settings.json              # 用户配置文件（由程序自动读写）
├── requirements.txt           # PyQt5（Pillow 仅用于生成 .ico，开发依赖）
├── .gitignore                 # 忽略 __pycache__/、*.pid、启动日志.txt、settings.json、build/dist/
├── assets/
    ├── white_chicken.png      # 小鸡精灵图（64×112 像素，7行×4列）
    ├── white_chicken.ico      # 桌面快捷方式 + 托盘图标（walk_down_0 第一帧）
    ├── Emotes.png             # 表情精灵图（64×256 像素，4列×16行）
    ├── Objects-干草.png        # 干草图标（16×16，喂食功能用）
    └── Objects-干草2.png       # 干草变体（16×16，干草消失动画用）
└── src/
    ├── __init__.py
    ├── main.py                # 入口：单实例锁、启动日志、pythonw 兼容
    ├── chicken_pet.py         # 主窗口：透明置顶、拖拽、托盘、鼠标穿透
    ├── chicken_ai.py          # AI 状态机：IDLE ⇄ WALK / HEART / RUNAWAY / FEEDING
    ├── animation.py           # 动画管理器：精灵图加载、帧切换、方向映射
    ├── hay_widget.py          # 干草浮窗（跟随鼠标/放置/消失动画 → dismiss）
    ├── emote_popup.py         # 表情弹窗：三阶段动画（出现→逐帧播放→消失）
    ├── settings_manager.py    # 设置持久化（JSON 读写）
    └── settings_dialog.py     # 图形化设置面板（Qt Dialog）
```

### 精灵图布局（7行×4列，每帧16×16，默认4倍缩放→64×64）

| 行 | 动画 | 帧数 | 说明 |
|----|------|------|------|
| 0 | WALK_DOWN | 4 | 向下走，4帧循环 (200ms/帧) |
| 1 | WALK_RIGHT | 4 | 向右走，4帧循环 |
| 2 | WALK_UP | 4 | 向上走，4帧循环 |
| 3 | WALK_LEFT | 4 | 向左走，4帧循环 |
| 4 | IDLE (下/右) | 2 | 向下&向右站立，取前2帧慢速交替 (800ms/帧) |
| 5 | IDLE (上/左) | 2 | 向上&向左站立，取前2帧慢速交替 (800ms/帧) |
| 6 | EAT | 4 | 进食动画（喂食触发，4帧各播一次 200ms/帧，共 800ms） |

> **站立的方向映射**：向下→行4列0-1，向右→行4列2-3，向上→行5列0-1，向左→行5列2-3。行4用于站立，行6为进食动画（EAT），由喂食功能触发。

### 表情精灵图布局（Emotes.png, 4列×16行, 每格16×16, 默认3倍缩放→48×48）

| 行 | 表情 | 帧数 | 说明 |
|----|------|------|------|
| 0 | 气泡弹出 | 4 | 表情出现/消失的过渡动画 |
| 3 | 😵 一团乱麻 | 4 | 用户快速拖拽小鸡持续1秒后显示 |
| 4 | ❗ 感叹号 | 4 | — |
| 5 | ❤️ 爱心 | 4 | 用户短按点击小鸡时显示 |
| 8 | 😊 笑脸 | 4 | 喂食进食动画完成后显示 |
| 10 | 💬 省略号 | 4 | 用户长按2秒小鸡时显示 |
| 0-2, 6-7, 9, 11-15 | 其他表情 | — | 16种星露谷表情，待后续使用 |

### 数据流

```
用户拖拽 / AI tick
       ↓
  ChickenAI（状态机决策）
       ↓  anim_changed 信号
  AnimationManager（切换动画 + 推进帧）
       ↓  frame_updated 信号
  ChickenPet.paintEvent（重绘窗口）
```

## 运行方式

```bash
# 方式零：下载 Release exe 直接双击运行 🚀（推荐普通用户，无需安装 Python）
#         从 https://github.com/Penguin123121/Stardew-Valley-Chicken-Pet/releases 下载

# 方式一：双击桌面快捷方式（推荐开发者，无任何弹窗）
#         桌面上的「星露谷小鸡桌宠.lnk」

# 方式二：命令行（在项目根目录执行）
pythonw -m src.main

# 方式三：调试模式（有控制台输出）
python -m src.main
```

**依赖安装：**

```bash
# 一键安装（推荐）
双击 install.bat

# 或手动安装
pip install PyQt5
```

## 核心设计要点

### 1. 动画系统（`animation.py`）

- **走路**：4 帧快速循环，`QTimer` 每 200ms 推进一帧
- **站立**：方向相关的 2 帧对慢速交替，800ms/帧（`IDLE_TICKS=4`），通过 tick 计数器控制切换节奏，不切换帧时不发射信号不重绘
- **进食**：`Anim.EAT`（行6）由喂食功能触发，4帧各播一次（200ms/帧，共800ms），播完即退出。`EAT_TICKS` 保留待后续调节进食速度
- `current_frame()` 根据当前动画类型和方向动态计算该取哪个 (row, col)
- `Anim` 类集中定义所有动画常量，`IDLE_MAP` 字典统一管理方向→帧映射
- **`set_animation` 的 idle 重置**：即使动画类型相同（IDLE→IDLE），也始终重置 `_idle_tick` 和 `_idle_col`，防止帧切换节奏被打乱（如爱心结束后恢复 IDLE 时计数器未归零导致跳帧加速）

### 2. AI 状态机（`chicken_ai.py`）

```
IDLE (时长由活跃度决定, 0.5~5s)
  ├── P%概率 ──→ WALKING (2~5.6s)
  │               ├── 30%概率 → WALKING（换方向，连续走路）
  │               └── 70%概率 → IDLE
  └── (1-P)%概率 → IDLE（发呆更久）

P = 30%~90%, 由活跃度等级 (1-10) 控制

(外部: 用户短按点击) ──→ HEART(1600ms, ❤️) ──→ 恢复到之前状态
(外部: 快速拖拽≥1秒) ──→ HEART(1600ms, 😵) ──→ 恢复到之前状态（不挣脱鼠标，单次拖拽最多一次）
(外部: 用户长按2秒) ──→ HEART(省略号, 1600ms) → RUNAWAY(快跑2秒) → 恢复到之前状态
(外部: 托盘「喂食」+ 放置) ──→ FEEDING(approach→eating, ~2s) → 恢复到之前状态
```

- 每 80ms 一个 tick，状态时长用随机 tick 数控制
- 行走时遇到屏幕边缘自动反弹，同时切换方向动画
- `move_request` 信号通知主窗口移动位置，`anim_changed` 信号通知动画管理器切换
- **啄食（EATING）已重新启用**：精灵图行6现在用于进食动画，由喂食功能触发，持续 800ms（`EATING_TOTAL_MS=800`，4帧×200ms各播一次）
- **喂食（FEEDING）**：两个子阶段 — `approaching`（轴对齐导航走向干草）→ `eating`（播放行6进食动画 800ms）。`start_feeding(hay_cx, hay_cy)` 外部触发（干草中心坐标），仅 IDLE/WALKING 态可进入。使用 `_pre_heart_state` 机制保存/恢复之前状态。导航优先走距离更远的轴（`_feeding_primary_axis`），每 tick 向目标移动 `_move_speed` 像素，到达紧公差（4px + 嘴部偏移 `BEAK_OFFSET`）后吸附到位并进入进食。`food_reached` 信号在到达时通知主窗口清除干草（立即消失），`feeding_done` 在进食动画播完后通知状态恢复。`cancel_feeding()` 用于用户右键取消喂食。
- **`is_busy` 扩展**：HEART、RUNAWAY、FEEDING 三种状态下均为 busy，阻止所有用户交互和菜单操作。
- **连续走路**：一段走路结束后 30% 概率直接开始下一段走路（方向改变），让走路时间占比更多，行为更活跃
- **活跃度系统**：`set_active_level(1-10)` 控制两个维度：
  - 走路概率：等级 1=30%, 等级 5=57%, 等级 10=90%
  - 站立时长：等级 1=3~5s, 等级 5≈1.8~3.2s, 等级 10=0.5~1s
  - 在 `_apply_settings()` 中应用，保存后立即生效
- **AI 暂停机制**：`pause()` / `resume()` 控制 tick 是否推进。用户按住小鸡时暂停 AI，松手或触发表情后恢复。`_tick()` 开头检查 `_paused` 标志，为 True 则直接 return。
- **HEART 状态**：`enter_heart()` 外部触发，固定持续 `HEART_TOTAL_MS=1600`ms（20 tick × 80ms，与表情动画同步），期间动画冻结，AI 禁止移动。**进入 HEART 前自动保存 `_pre_heart_state` 和 `_pre_heart_direction`**，结束后恢复到点击前的状态。恢复时通过 `_enter_state(prev_state, prev_dir)` 传入保存的方向参数。
- **RUNAWAY 状态**：`enter_runaway()` 由省略号表情结束后调用，持续 `RUNAWAY_TOTAL_MS=2000`ms，以 2.5 倍速在随机方向移动（含边缘反弹），结束后恢复之前状态。
- `is_busy` 属性用于去重（HEART 或 RUNAWAY 期间忽略所有用户交互）

> ⚠️ **黄金规则 ⑤**：当桌宠要改变移动方向时，必须先在对应的 tick 中切换动画（emit `anim_changed`），再执行移动（emit `move_request`）。不能先移动后切换动画，也不能只移动不切换动画。这条规则适用于所有会产生位移的状态（WALKING、RUNAWAY、FEEDING approaching），包括同轴方向反转和目标跨过小鸡导致的隐式方向变化。任何新增位移逻辑时也必须遵守此规则。

### 3. 单实例锁（`main.py`）

- 启动时写 PID 到 `.pet_lock.pid`
- 再次启动时检测 PID 对应进程是否仍在运行（同时检查 `python.exe` 和 `pythonw.exe`）
- `atexit.register(remove_lock)` + `signal` 处理器确保退出时清理锁文件
- 锁文件无效（PID 不存在或不可读）时自动清理

### 4. 启动日志（`main.py`）

- 因为使用 `pythonw.exe` 无控制台，`stderr` 和 `print` 不可见
- 自定义 `_LogTee` 类将 stderr 同时写入 `启动日志.txt`
- 关键启动步骤（导入 PyQt5、创建窗口等）均记录日志，方便排查 `pythonw` 下的启动问题
- PyQt5 导入失败时用 `ctypes.windll.user32.MessageBoxW` 弹出原生错误框

### 5. 窗口特性（`chicken_pet.py`）

- **透明无边框**：`Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool` + `WA_TranslucentBackground`
- **鼠标穿透**：Win32 API `WS_EX_TRANSPARENT`，通过托盘菜单开关
- **系统托盘**：右键菜单（显示/隐藏、始终置顶、鼠标穿透、🌿 喂食、设置、退出），双击恢复显示
- **关闭最小化到托盘**：`closeEvent` 忽略关闭，改为 `hide()`
- **首次显示延迟**：`showEvent` 中延迟 100ms 执行 Windows API 设置，确保 `winId()` 有效
- **按下即冻结**：`mousePressEvent` 中立即 freeze 动画 + pause AI，确保按住期间画面不动、不走动
- **始终置顶强化**：`_topmost_timer`（每 3 秒）调用 `SetWindowPos(HWND_TOPMOST)` 刷新窗口层级，解决 `Qt.WindowStaysOnTopHint` 无法防御后来打开的 topmost 窗口（如任务管理器）遮挡小鸡的问题。定时器在开启置顶时启动，关闭置顶时停止，`_quit()` 中也会停止
- **busy 状态气泡反馈**：当小鸡在爱心/逃跑/喂食状态时，用户点击托盘「🌿 喂食」会弹出系统托盘气泡提示（"小鸡正在互动中，等它结束再喂吧~"），避免用户困惑"点了为什么没反应"

### 5.1 表情弹窗 + 动画冻结（`emote_popup.py` + `animation.py`）

> ⚠️ **黄金规则 ①**：任何表情功能的运作都不能影响桌宠原本的行为。表情开始前和结束后的 AI 状态、动画状态必须完全一致，桌宠的站立/行走等行为在表情结束后必须无缝恢复。修改表情相关代码时，必须验证这一规则不被破坏。
>
> ⚠️ **黄金规则 ②**：任何表情效果在触发时，都要和小鸡本体绑定，随着小鸡一起移动。弹窗位置通过 `_sync_emote_position()` 统一管理，在拖拽（`mouseMoveEvent`）和 AI 移动（`_on_ai_move`）时实时同步。新表情功能开发时也必须遵守此规则。
>
> ⚠️ **黄金规则 ④**：所有表情相关功能（包括出现方式、消失方式、持续时间、三阶段动画结构）都要与最初设置爱心表情的相关内容保持一致。所有表情都通过 `_trigger_emote(emote_row, post_action)` 统一入口触发，三阶段动画参数固定（出现4帧→表情逐帧4帧(3tick/帧,≈1s)→消失4帧=1600ms）。修改表情功能时，必须验证此规则不被破坏。

用户按下小鸡后，**动画立刻冻结在当前帧 + AI 暂停**，后续根据持时判定爱心/省略号。表情实现为独立透明浮窗（`Qt.Tool` + `WA_TranslucentBackground` + `WA_TransparentForMouseEvents`）。

**完整时序**（总计 1600ms，20 tick×80ms）：

```
按下 → freeze() 冻结帧 + pause() 暂停AI
  ↓
气泡出现 (320ms, 行0 正放, 4帧)
  ↓
表情动画 (~1s, 行5/行10 4帧逐帧播放一次，每帧停留~250ms)
  ↓
气泡消失 (320ms, 行0 倒放, 4帧)
  ↓
finished → unfreeze() 解冻帧 → 应用 pending_anim → 鸡恢复AI行为
```

**三阶段动画**：

| 阶段 | 时长 | 精灵图 | 说明 |
|------|------|--------|------|
| 出现 | 320ms | 行0 帧0→3 正放 | 气泡弹出过渡动画 |
| 表情 | ~1s | 表情行 帧0-3 逐帧播放一次 | 每帧停留 3 tick (~240ms)，4帧≈1s |
| 消失 | 320ms | 行0 帧3→0 倒放 | 气泡收起过渡动画 |

> 总时长 1600ms，与 `HEART_TOTAL_MS=1600` 匹配（20 tick × 80ms/tick）。

- **爱心表情（❤️）**：用户短按点击（<200ms，位移<3px）触发，行5，表情结束后恢复 AI 之前状态
- **省略号表情（💬）**：用户长按不放（2秒，位移<3px）触发，行10，表情结束后进入逃跑快跑2秒再恢复
- **一团乱麻表情（😵）**：用户快速拖拽（≥20px/80ms，连续13次≈1秒）触发，行3。表情不挣脱鼠标，单次拖拽最多一次。表情结束后若用户仍在拖拽则保持动画冻结，等松手才恢复
- 表情弹窗显示在小鸡头顶中央（`chicken.x + width/2 - display_size/2`）
- 弹窗默认缩放 3 倍（16×16 → 48×48）
- **位置同步**：`_sync_emote_position()` 统一管理弹窗位置，在拖拽移动（`mouseMoveEvent`）和 AI 移动（`_on_ai_move`）时实时更新，确保弹窗始终跟随小鸡
- 弹窗引用存为 `self._current_emote` 实例属性，防止 Python GC 提前回收
- `finished` 信号触发后调用 `_on_emote_finished()` → `unfreeze()` 解冻 + 根据 `_post_emote_action` 决定后续动作（`None`=恢复常态 / `"runaway"`=进入快跑） + `deleteLater()` 清理
- 退出时 `_quit()` 主动关闭表情弹窗，防止残留
- 若鸡已在逃跑状态（`RUNAWAY`），重复点击/长按被忽略；**爱心状态（`HEART`）期间允许拖拽小鸡**（见下方"爱心动画期间拖拽"）

**统一表情入口 `_trigger_emote(emote_row, post_action)`**：
所有表情（爱心、省略号、一团乱麻、未来新增）都通过此方法触发，保证三阶段动画参数一致（黄金规则④）。
- `_trigger_heart()` → `_trigger_emote(emote_row=5, post_action=None)`
- `_on_hold_timeout()` → `_trigger_emote(emote_row=10, post_action="runaway")`
- `_on_drag_sample_tick()` → `_trigger_emote(emote_row=3, post_action=None)`（快速拖拽满1秒）

**省略号 + 逃跑完整时序**（总计约 5 秒）：

```
按下 → freeze() + pause()
  ↓ (2秒等待)
长按2秒触发 → resume() + enter_heart() → _ignore_mouse=True 挣脱鼠标
  ↓
气泡出现 (320ms, 行0 正放)
  ↓
省略号动画 (~1s, 行10 逐帧播放一次, 每帧~250ms 💬)
  ↓
气泡消失 (320ms, 行0 倒放)
  ↓
finished → unfreeze() 解冻 → enter_runaway() 快跑2秒 (2.5倍速)
  ↓
RUNAWAY 结束 → 恢复到长按前的 AI 状态
```

**拖拽 + 一团乱麻完整时序**（总计约 2.6 秒）：

```
按下 → freeze() + pause()
  ↓
位移 ≥ 3px → 切换拖拽模式 + 启动 80ms 采样定时器
  ↓ (连续快速拖拽 13 tick，≈1秒)
每 80ms: 计算鼠标位移
  ├── ≥ 20px → fast_ticks+1（满13触发）
  └── < 20px → fast_ticks=0（重置，慢下来就得重新攒）
  ↓
满13次快速tick → _trigger_emote(行3, post_action=None) — 不挣脱鼠标!
  ↓
气泡出现 (320ms, 行0 正放)
  ↓
一团乱麻动画 (~1s, 行3 逐帧播放一次, 每帧~250ms 😵)
  ↓
气泡消失 (320ms, 行0 倒放)
  ↓
finished → 检查 _dragging 标志:
  ├── 仍在拖拽 → 跳过 unfreeze（保持帧冻结！） → 等松手时 mouseRelease 解冻
  └── 已松手 → unfreeze() 解冻 → AI 从 HEART 恢复

松手时：stop 采样定时器 + 若 _drag_emote_active 为 False（表情已播完）→ unfreeze + resume
```

> **关键设计点**：
> - 快速阈值 `_DRAG_FAST_PX=20`（≈250 px/s），是小鸡正常行走的 10 倍，慢速拖拽不会误触
> - `_drag_emote_triggered` 在首次触发后保持 True，阻止同一轮拖拽再次触发，只在松手时重置
> - `_drag_emote_active` 标志表情播放中状态，松手时若为 True 则不解冻，等 `_on_emote_finished` 处理
> - 表情结束后 `_on_emote_finished` 检测 `self._dragging`，若仍在拖拽则跳过 `unfreeze()`，画面保持冻结直到松手

**爱心动画期间拖拽**（`chicken_pet.py`，`_dragging_during_emote` 标志）：

> 用户点击小鸡触发爱心表情后，在爱心动画持续期间（1600ms）可以拖动小鸡移动位置，且拖拽不会触发任何其他表情（不会出现一团乱麻、省略号等）。

```
爱心动画播放中（AI=HEART, 动画=冻结）
  ↓
mousePressEvent → is_busy=True + is_heart=True → 进入爱心拖拽模式
  ├── 设置 _dragging_during_emote = True
  ├── 不 freeze（已在爱心触发时冻结）、不 pause（HEART 需要 tick 计时）
  └── 不启动 hold_timer / drag_sample_timer（禁止触发其他表情）
  ↓
mouseMoveEvent → 移动小鸡 + _sync_emote_position() 同步表情位置
  ↓
  情况A: 爱心动画先结束
    _on_emote_finished → 检测 _dragging_during_emote=True → 跳过 unfreeze
    → AI 从 HEART 恢复到 IDLE/WALKING → _on_ai_move 被 _dragging_during_emote 阻止
    → 等用户松手 → mouseReleaseEvent → unfreeze 解冻
  ↓
  情况B: 用户先松手
    mouseReleaseEvent → _dragging_during_emote=False
    ├── _current_emote 不为 None（表情还在播）→ 跳过 unfreeze
    └── 等 _on_emote_finished → 正常 unfreeze 解冻
```

> **关键设计点**：
> - `_dragging_during_emote` 独立于 `_dragging`，避免与正常拖拽逻辑冲突
> - 爱心拖拽期间 `_drag_sample_timer` 永远不会启动，确保不会触发一团乱麻
> - `_on_ai_move` 也会检查 `_dragging_during_emote`，防止 HEART 结束后 AI 移动小鸡覆盖拖拽位置
> - 逃跑（RUNAWAY）期间仍然是完全忽略鼠标交互（`is_busy && !is_heart`）

**动画冻结机制**（`animation.py`）：

- `freeze()` → `_frozen += 1`（引用计数），`_next_frame()` 直接 return，`set_animation()` 记录待应用到 `_pending_anim/_pending_direction`
- `unfreeze()` → `_frozen -= 1`，降到 0 时自动应用冻结期间最后记录的动画，恢复正常帧推进
- **嵌套冻结**：引用计数机制支持多次 freeze/unfreeze 嵌套（HEART 冻结 + 拖拽冻结），只有计数归零才真正解冻
- 冻结时 `current_frame()` 始终返回冻结那一刻的帧画面
- **设计要点**：冻结期间 AI 可能发出多次 `anim_changed`（如 HEART 开始时→IDLE，HEART 结束时→IDLE），`set_animation()` 始终记录最新的一次，`unfreeze()` 时应用，确保解冻后动画状态与 AI 状态同步

**点击 vs 拖拽 vs 长按判定**（`chicken_pet.py`）：

```
mousePressEvent
  ├── is_busy && !is_heart? ──是──→ return（逃跑中忽略一切交互）
  ├── is_heart? ──是──→ 爱心拖拽模式（_dragging_during_emote=True）
  │                     ├── 不 freeze/pause（已在爱心触发时处理）
  │                     └── 不启动任何计时器（禁止触发其他表情）
  └── 正常流程:
        freeze() 冻结帧 + pause() 暂停AI + 记录起点 + 启动2秒计时器
           ↓
      ┌─ 2秒计时器触发（位移<3px）→ _on_hold_timeout() → 省略号 💬 + 逃跑
      │
      └─ mouseMoveEvent → 位移 ≥ 3px ?
           ↓ 是
        取消长按计时 + 切换拖拽模式 + 启动80ms采样定时器
           │
           ├── 每80ms: 位移 ≥ 20px ? ──是──→ 快速tick+1 ──满13次?──→ 😵 一团乱麻
           │                              │                  （不挣脱鼠标）
           │                              └── < 20px → 重置计数为0
           │
           └── 继续拖拽中...
                  ↓
    mouseReleaseEvent → 取消计时器
           ↓
      拖拽中? ──是──→ 停止采样 + unfreeze + resume（若表情已结束则解冻）
           ↓ 否
      持时 < 200ms? ──是──→ _trigger_heart()（❤️ 爱心）
           ↓ 否
           └──→ unfreeze() + resume()（按住>200ms但<2s松手，不出表情）
```

> **注意**：按下瞬间就 freeze + pause，确保整个按住期间画面不动。拖拽期间表情结束后也**保持冻结**（`_on_emote_finished` 检测 `self._dragging` 或 `self._dragging_during_emote` 为 True 则跳过 unfreeze），等用户松手才解冻恢复。`_drag_emote_triggered` 标志确保单次拖拽表情最多触发一次，只在松手时重置。爱心动画期间拖拽通过 `_dragging_during_emote` 标志独立管理，不会触发任何其他表情。

### 5.2 喂食功能（`hay_widget.py` + `chicken_pet.py` + `chicken_ai.py`）

用户通过托盘菜单"🌿 喂食"触发干草放置，小鸡自动走向干草并播放进食动画。

**完整时序**：

```
右键托盘 → 点击「🌿 喂食」
  ↓
HayWidget 创建，半透明跟随鼠标（每 16ms 更新位置）
  │   **AI 同时立即开始追踪光标位置**（80ms 定时器更新目标）
  ├── 左键 → 放置干草（变不透明）→ placed 信号
  │     ↓
  │   _on_hay_placed → _ensure_above_hay() 确保小鸡层级在干草之上
  │     ↓
  │   ChickenAI 状态切换：进入 FEEDING(approaching)
  │     ├── 轴对齐导航：先走距离更远的轴（dx vs dy 比较）
  │     ├── 每 tick 移动 move_speed 像素，到达紧公差(4px)切换轴
  │     └── 两轴都到 → 吸附精确位置 → _enter_eating_phase()
  │           ↓
  │         food_reached 信号 → _on_food_reached → 仅停止追踪定时器
  │           │   **干草保持显示**（小鸡对着干草吃）
  │           ↓
  │         FEEDING(eating)：播放行6进食动画 4帧各播一次（200ms/帧，共800ms）
  │           ↓
  │         _enter_state(prev_state) 先恢复 AI 状态（退出 FEEDING）
  │           ↓
  │         feeding_done 信号 → _on_feeding_done()
  │           ├── **干草消失动画**：start_dismiss_animation() → 干草切为干草2 → 300ms → dismissed → 关闭
  │           └── **笑脸表情（并行）**：freeze 动画 + _trigger_emote(行8) → 三阶段表情(1600ms)
  │                 ↓
  │               _on_emote_finished() → unfreeze 动画 → AI 恢复之前状态
  │
  └── 右键 → 取消 → cancelled 信号 → dismiss() 立即关闭（不走消失动画）
        → AI 恢复之前状态
```

**关键设计点**：
- HayWidget **不设置** `WA_TransparentForMouseEvents`（需要接收点击），与 EmotePopup 不同
- **小鸡层级始终在干草之上**：通过 `_ensure_above_hay()` 使用 Windows API `SetWindowPos(..., HWND_TOP)` 将小鸡窗口推到绝对顶层。在 `_start_feeding`（干草show后）、`_on_ai_move`（小鸡移动后）、`_on_hay_placed`（干草放置后）三个节点调用
- **进食动画期间干草保持显示**：`_on_food_reached()` 仅停止追踪定时器，不调用 dismiss
- **进食完成后先恢复 AI 状态再发射信号**：`_tick_feeding` 中 `_enter_state(prev)` 在 `feeding_done.emit()` 之前执行，确保 `_on_feeding_done` 中调用 `_trigger_emote` 时 `is_busy` 为 False
- 喂食期间 `is_busy = True`（FEEDING 加入 busy 状态组），阻止所有用户交互
- 已有喂食流程时再次点击菜单 → `_start_feeding()` 检查 `_feeding_active` 并 return
- busy 期间（爱心/逃跑/已喂食中）菜单点击会弹出托盘气泡提示，告知用户原因
- 干草缩放 3 倍（16×16 → 48×48，与表情弹窗一致）
- **干草消失动画**：`start_dismiss_animation()` → 切换到干草2 → 300ms 单次定时器 → `dismissed` 信号 → `_dismiss()` 关闭。`dismiss()` 保留用于取消/退出路径（立即关闭）
- **笑脸表情**：Emotes.png 第8行，进食完成后与干草消失动画并行触发。由 `_on_feeding_done` 中手动 `freeze()` + `_trigger_emote(row=8)`
- ⚠️ **黄金规则⑤**：`_tick_feeding_approach()` 中每次 tick 都会检测同轴方向是否反转（目标跨过小鸡），若反转则先 emit `anim_changed` 切换动画再 emit `move_request` 执行移动
- **干草放置边界限制**：`_start_feeding()` 中根据小鸡移动范围 + 嘴部偏移反算干草中心有效区域（`hay_boundary` QRect），传入 `HayWidget`。跟随鼠标时 `_follow_mouse()` 自动 clamp 干草中心到有效区域内，确保放置后小鸡一定能走到。`current_center()` 始终返回窗口实际中心（不再直接返回 `QCursor.pos()`）。**修复了屏幕边缘放置干草导致小鸡永久卡死的 bug。**

### 6. 设置系统（`settings_manager.py` + `settings_dialog.py`）

> ⚠️ **黄金规则 ③**：设置面板中的所有选项都要在用户调整并保存后立即生效，不需要重启桌宠。`_apply_settings()` 中必须覆盖所有设置项的处理，包括缩放（重新加载精灵图+调整窗口大小）、速度、活跃度、窗口特性等。

| 设置项 | 默认值 | 说明 |
|--------|--------|------|
| `scale` | 4 | 缩放倍数（16×16 → 64×64），范围 2-6 |
| `always_on_top` | True | 窗口始终置顶 |
| `click_through` | False | 鼠标穿透 |
| `anim_speed` | 200 | 动画帧间隔 (ms)，范围 100-500 |
| `move_speed` | 3 | 行走速度 (像素/tick)，范围 2-8 |
| `active_level` | 5 | 活跃度 1-10，控制走路概率和站立时长 |
| `autostart` | False | 开机自动启动（通过 Startup 文件夹快捷方式实现） |
| `position_x/y` | 200 | 上次关闭时的窗口位置，自动保存 |

- 设置保存在 `settings.json`，启动时加载，损坏/不存在时静默回退默认值
- 修改设置后通过 `_apply_settings()` 统一重新加载并应用到所有组件，**所有选项立即生效无需重启**
- **开机自启**：勾选后在 `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\` 创建 `.lnk` 快捷方式（指向 `pythonw.exe -m src.main`），取消勾选则删除。关键路径（Python、项目根、图标）均通过 `sys.executable` + `__file__` 动态推导，不再依赖硬编码路径，换电脑/换目录也能正常工作。实现代码在 `settings_dialog.py` 模块级函数中

## 踩坑经验

### ⚠️ GC 回收导致弹窗不显示
**现象**：`EmotePopup` 创建后闪一下立刻消失。
**根因**：局部变量 `emote = EmotePopup(...)` 函数返回后被 Python GC 回收，Qt 来不及渲染。
**修复**：存为实例属性 `self._current_emote` 保持引用，`finished` 信号触发后 `deleteLater()` 释放。

### ⚠️ 动画冻结导致 AI 状态不同步
**现象**：爱心动画结束后小鸡走路动画播放但位置不动。
**根因**：`freeze()` 期间 `set_animation()` 直接 return，AI 发出的所有 `anim_changed` 信号被丢弃。解冻后 AnimationManager 的 `_anim` 仍指向冻结前的旧动画，与 AI 当前状态不一致。
**修复**：冻结期间 `set_animation()` 改为记录 `_pending_anim/_pending_direction`，`unfreeze()` 时自动应用最后一次记录。

### ⚠️ HEART 结束后状态被重置
**现象**：走路中点鸡，爱心结束后小鸡进入站立，不再走路。
**根因**：HEART 结束硬编码 `_enter_state(IDLE)`，之前的状态丢失。
**修复**：`_enter_state(HEART)` 中在 `self._state = state` **之前**保存 `_pre_heart_state` 和 `_pre_heart_direction`（此时 `self._state` 还是旧值），HEART 结束后 `_enter_state(prev_state, prev_dir)` 恢复。

### ⚠️ IDLE 帧切换突然变快
**现象**：站立时帧切换频率随机变快，从正常的 800ms/帧变成 200ms 甚至更短。
**根因**：`set_animation()` 中 `self._anim == anim`（同为 IDLE）时不重置 `_idle_tick` 和 `_idle_col`。当 AI 发出 `IDLE→IDLE`（连续两次发呆）或 Heart 解冻恢复为 IDLE 时，旧的 tick 计数器被保留，只需少量 tick 就触发帧切换。
**修复**：`set_animation()` 中对 IDLE 动画始终重置 `_idle_tick=0, _idle_col=0`（无论 `_anim` 是否改变），同时 AI 中去掉 IDLE→IDLE 的 20% 概率逻辑。

### ⚠️ 拖拽表情结束后小鸡画面恢复帧切换
**现象**：拖拽触发一团乱麻后，表情播完小鸡立刻开始切换帧动画，但用户还在拖拽中。
**根因**：`_on_emote_finished()` 中无条件调用 `self._anim.unfreeze()`，忽略了拖拽场景下用户仍在按住鼠标的事实。
**修复**：`_on_emote_finished()` 中加入 `if not self._dragging` 守卫，拖拽期间表情结束也跳过 unfreeze，等 `mouseReleaseEvent` 中松手时再解冻。同时引入 `_drag_emote_active` 标志协调松手时是否解冻的判定。

### ⚠️ 屏幕边缘放置干草导致小鸡永久卡死
**现象**：用户在屏幕边缘放置干草后，小鸡走到边缘被 clamp 住，永远到不了干草位置，FEEDING 状态无法退出，只能重启。
**根因**：`_tick_feeding_approach()` 中屏幕边缘 clamp 阻止小鸡继续前进，干草目标位置超出小鸡移动范围，无超时机制。
**修复**：从源头限制干草放置位置。`_start_feeding()` 中计算干草中心有效区域（小鸡移动边界 + 嘴部偏移反算），传入 `HayWidget._follow_mouse()` 中 clamp；`current_center()` 改为始终返回窗口实际中心。确保放置后小鸡一定能导航到达。

### ⚠️ 置顶切换后鼠标穿透失效
**现象**：勾选鼠标穿透后再点击始终置顶，鼠标又能控制小鸡了，但设置面板中穿透仍然打勾。
**根因**：`_apply_always_on_top()` 通过 `hide() → setWindowFlags() → show()` 重建了原生窗口句柄（HWND），导致之前通过 `_apply_click_through()` 设置的 `WS_EX_TRANSPARENT` 扩展样式在新 HWND 上丢失。
**修复**：① 当置顶标志未实际变化时跳过窗口重建，避免无意义的 HWND 重建；② 当确实需要重建窗口时，延迟 150ms 用 `QTimer.singleShot` 自动重新调用 `_apply_click_through()` 恢复穿透样式。

### ⚠️ exe 放在桌面污染桌面文件
**现象**：PyInstaller 打包的 exe 放在桌面运行时，`settings.json`、`启动日志.txt`、`.pet_lock.pid` 全部出现在桌面。
**根因**：打包模式下 `_user_root = os.path.dirname(sys.executable)` 即 exe 所在目录，所有用户数据写在 exe 旁边。
**修复**：引入 `_get_user_data_dir()` 函数，将用户数据目录改为 `%APPDATA%\StardewValleyChickenPet\`。`main.py` 和 `settings_manager.py` 各有一份相同实现（避免跨文件导入依赖）。`Settings._migrate_old_settings()` 自动将旧位置的 settings.json 迁移到新位置。

## PyInstaller 打包

项目支持用 PyInstaller 打包为单个 `.exe` 文件，用户无需安装 Python 即可运行。

### 路径兼容机制

所有文件路径通过 `getattr(sys, 'frozen', False)` 检测运行环境：
- **打包模式**（`sys.frozen = True`）：只读资源（精灵图）从 `sys._MEIPASS` 读取；可写文件（`settings.json`、锁文件、日志）写入 `%APPDATA%\StardewValleyChickenPet\`（即 `C:\Users\<用户名>\AppData\Roaming\StardewValleyChickenPet\`），避免污染 exe 所在文件夹
- **源码模式**：可写文件写入项目根目录（与之前行为一致）
- **自动迁移**：`Settings.__init__` 中检测旧位置（exe/项目旁）是否有 `settings.json`，若新位置尚无则自动复制迁移

涉及文件：`main.py`（`_get_user_data_dir`/`_project_root`/`_user_root`/`LOCK_FILE`/`LOG_FILE`）、`chicken_pet.py`（`_resolve_asset`）、`settings_manager.py`（`_get_user_data_dir`/`Settings.__init__`/`_migrate_old_settings`）、`settings_dialog.py`（开机自启快捷方式路径）

### 打包命令

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "StardewValleyChickenPet" --icon assets/white_chicken.ico --add-data "assets;assets" src/main.py
```

生成的 exe 在 `dist/` 目录，约 35MB。发布时通过 `gh release create` 上传。

> `.gitignore` 中已排除 `build/`、`dist/`、`*.spec`。

## 最近完成

- ✅ 用户数据目录迁移至 `%APPDATA%` — exe 放桌面不再污染桌面（settings.json/日志/锁文件进 AppData）
- ✅ 切换始终置顶后鼠标穿透样式丢失修复 — 重建 HWND 后自动重新应用 `WS_EX_TRANSPARENT`
- ✅ 干草放置边界限制 — 修复屏幕边缘喂食卡死 bug
- ✅ PyInstaller 单文件打包支持（`sys._MEIPASS` 路径兼容）
- ✅ GitHub Release v1.0.0（含 exe 一键下载）
- ✅ 重新启用进食动画（精灵图行6 = EAT）
- ✅ 桌面快捷方式 + 自定义图标（walk_down_0 第一帧）
- ✅ 动态路径（不再硬编码用户/目录名，换电脑也能跑）
- ✅ 始终置顶强化（`HWND_TOPMOST` 定时刷新，防被其他窗口遮挡）
- ✅ busy 状态托盘气泡反馈
- ✅ Pillow 从运行时依赖移除
- ✅ README.md + install.bat 一键安装脚本

## 后续修改方向

- 可能增加更多行为状态（如睡觉、跟随鼠标等）
- 多皮肤/角色切换（替换精灵图即可，配置加 `skin` 字段）
- 好感度系统（点击+1，喂食+3，长按-2）
- 音频系统（走路/表情/进食音效）
- 可能添加更多表情（问号、音符等）
- GitHub Actions 自动打包发布（CI 自动构建 exe 并创建 Release）
