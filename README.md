# fitness-ledger

一个极简、Git 原生的力量训练记录工程。它把 Codex（或其他代码 Agent）当作自然语言入口，把结构化文本文件当作数据库。

## 它解决什么

同一个动作常有很多名字，但“名字相似”不代表“数据可直接比较”。本项目把一条动作记录拆成三层：

1. **动作身份**：`machine_chest_press`（器械推胸）
2. **动作变体**：`angle=incline`、`posture=seated`、`laterality=bilateral`
3. **具体器械**：如 `Life Fitness / Insignia Chest Press`

因此“上斜器械推胸”和“坐姿胸推机”可以归到同一动作家族做总量统计，同时按角度和器械分别比较表现。

对于“Y举”这类没有统一叫法的动作，系统不会为了匹配词典而硬套名称。Agent 会先确认主要训练部位，必要时补问器械、姿势或运动轨迹；确认后把它保存为用户自定义动作。自定义动作和传统动作在记录、统计上地位相同，只是定义来源可追溯。

## 每次记录先做动作对齐

用户不需要每次使用完全相同的动作名称。解析器会同时查询 `catalog/exercises.json` 的规范名/别名和历史日志中的 `reported_name`，尽量把简称、品牌叫法或措辞变化对齐到已有的唯一 `exercise_id`。如果新叫法可能对应多个动作，Agent 会先展示候选并询问；只有确认无法归入已有动作后，才创建新 ID。

长期趋势默认按 `exercise_id + variant + equipment + sequence` 分组。同一基本动作可以跨叫法连续追踪，但不同角度、姿势、握法、单双侧、具体器械或顺序角色不会被误合并成同一条 PR 曲线。每条日志仍保留原始 `reported_name`，因此任何归一化决定都可以审计和纠正。

## 为什么选这些文件

- `catalog/exercises.json`：规范动作、别名、允许的变体。JSON 便于 Agent 和脚本可靠修改。
- `data/workouts/YYYY/MM/YYYY-MM-DD.jsonl`：每行是一条动作记录。追加简单、Git 冲突小、可用任何语言分析。
- `scripts/fitness.ps1`：Windows 自带 PowerShell 即可运行，无数据库、服务或第三方依赖。
- `AGENTS.md`：告诉 Agent 如何理解、消歧、记录和维护词典。
- `knowledge/`：带来源和版本记录的长期训练知识；肌肥大计划以 ACSM 2026 为当前原则。
- `knowledge/exercise-order.md`：动作顺序对力量与肌肥大的证据，以及胸背日优先级模板。
- `profile/training-preferences.json`：用户确认的长期训练偏好，例如胸背日优先肌群轮换。

## 最短使用路径

直接对 Codex 说：

> 记录今天训练：力健上斜推胸机，40kg 12次，45kg 10次两组，最后一组 RIR 1。

Agent 会先解析动作，再调用脚本落盘。你也可以自己使用 CLI：

```powershell
# 看一个自然语言名称会被识别成什么
powershell -ExecutionPolicy Bypass -File .\scripts\fitness.ps1 resolve -Exercise "力健上斜推胸机"

# 12x40 表示 12 次 × 40 kg；@2 表示 RIR 2
powershell -ExecutionPolicy Bypass -File .\scripts\fitness.ps1 add `
  -Exercise "上斜器械推胸" `
  -Sets "12x40@2","10x45@1","10x45@1" `
  -Equipment "Life Fitness Insignia" `
  -Notes "座椅 4 档"

# 查看最近记录和汇总
powershell -ExecutionPolicy Bypass -File .\scripts\fitness.ps1 recent -Limit 10
powershell -ExecutionPolicy Bypass -File .\scripts\fitness.ps1 stats -Exercise "器械推胸"

# 修改词典后做一致性检查
powershell -ExecutionPolicy Bypass -File .\scripts\fitness.ps1 validate
```

计时组写作 `30s`，自重组写作 `12xbw`。`-WarmupCount 2` 会把前两组标成热身组。重量统一按 kg 存储。

单侧动作可写成 `R:8x20,L:8x20,R:7x20,L:8x20`。没有写左右时，Agent 按双侧动作记录；写明左右时，每侧数据独立保存，并保留对应轮次。

器械品牌不进入动作别名。例如“豪斯特推胸”仍可保留为原始叫法，同时用 `-ResolveAs "器械推胸" -Equipment "HOIST"` 归一。窄距、宽距和对握等握法会作为独立变体参与统计分组。

## 目录

```text
fitness-ledger/
├── AGENTS.md
├── catalog/exercises.json
├── data/workouts/.gitkeep
├── docs/data-model.md
├── examples/example-workout.jsonl
├── knowledge/hypertrophy-training.md
├── scripts/fitness.ps1
└── tests/smoke.ps1
```

## Git 工作流

一次训练结束后：

```powershell
git diff
git add data catalog
git commit -m "workout: 2026-08-05 push"
```

动作词典的变更和训练记录可以分开提交，便于审查别名是否被错误合并。真实训练数据位于 `data/`，**应当提交到 Git**；不要把它加入 `.gitignore`。

## 当前边界

第一版专注力量训练：次数、重量、RIR、计时组和热身标记。它不猜测左右两边重量的含义，也不自动换算器械配重片。如果一句话存在两种合理解释，Agent 应先询问，而不是静默写入错误数据。

动作词典允许用户自定义动作，不要求每个动作都有国际统一名称。自定义动作在确认训练部位和最小动作定义之前不会落盘。
