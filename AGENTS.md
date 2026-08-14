# Fitness Ledger Agent Contract

本仓库是用户的训练事实账本。Agent 的任务是把自然语言训练描述安全地转为结构化记录，并维护可审计的动作词典。

## 知识库使用

- 设计、调整或评价以肌肉肥大为目标的训练前，必须先读取 `knowledge/hypertrophy-training.md`。
- 2026 ACSM 指南是当前原则，2009 渐进模型只用于补充具体操作；冲突时采用新版。
- 必须区分 ACSM 结论、项目启发式规则和用户事实，不把其中一类冒充另一类。
- 训练计划不是已完成事实。除非用户随后报告实际完成情况，否则不要把计划写入 `data/workouts/`。
- 新证据导致规则变化时，更新知识文档的“最后核对”和“版本记录”，不要静默覆盖来源与适用范围。
- 设计训练前读取 `profile/training-preferences.json`。用户个人策略优先用于个体化方案，但不要把其中的个人解释表述成通用科学结论。

## 每次记录必须遵循的流程

1. 读取 `catalog/exercises.json`，或调用 `scripts/fitness.ps1 resolve -Exercise <原始叫法> -Json`。
2. 将动作拆成：规范动作 `exercise_id`、变体、具体器械。不要为每个品牌或角度创建新的规范动作。
3. 只有在结果唯一且语义合理时才写入。脚本返回 `ambiguous` 或 `unknown` 时，先向用户确认。
4. 使用脚本写入，不要手工拼 JSONL。Windows 用 `scripts/fitness.ps1 add`，macOS / Linux 用 `scripts/fitness.sh add`（等价于 `scripts/fitness.py add`）。两个实现共享同一词典与数据格式，行为和校验规则一致。始终保留用户原话到 `reported_name`。
5. 严格按用户报告的先后顺序写入 `sequence`。即使某动作因等待确认而稍后补写，也必须保留它在原训练中的位置，不能使用落盘时间代替动作顺序。
6. 写入后运行 `validate`（Windows：`scripts/fitness.ps1 validate`；macOS / Linux：`scripts/fitness.sh validate`）。若本轮包含多条动作，全部完成后再运行一次即可。
7. 简短回报日期、规范动作、变体、器械、顺序和组数；指出任何采用的假设。不要自动提交 Git，除非用户明确要求。

> 平台说明：`scripts/fitness.py` 是 `scripts/fitness.ps1` 的跨平台镜像实现（macOS / Linux 用系统自带 python3 运行），新功能或规则变更必须同时更新两个脚本，并通过 `tests/smoke.ps1` 与 `tests/smoke.sh` 验证。

## 动作对齐与长期身份

- 每次记录都必须先做动作对齐，不能直接用本次字面名称创建记录。解析时同时检查动作词典的规范名/别名和历史日志的 `reported_name`；历史中已确认过的不同叫法也应优先复用原 `exercise_id`。
- `exercise_id` 是跨时间线保持稳定的动作身份。同一基本动作即使简称、全称、品牌描述或中英文写法发生变化，也不得创建重复 ID；用户原话继续保存在每条记录的 `reported_name` 中。
- 名称不同但疑似同一动作时，先向用户展示拟对齐的规范动作，以及变体、器械或动作轨迹上的关键差异，并询问是否对齐。用户确认后复用已有 ID；若该叫法语义稳定，再加入 `aliases`，否则只保留为历史 `reported_name`。
- 只有查过词典和历史记录、排除已有动作，并获得用户对动作含义的确认后，才能创建新 `exercise_id`。`unknown` 不代表可以无确认自动新增；`ambiguous` 必须先消歧。
- 品牌、机型、角度、姿势、握法和单双侧通常不是新动作身份，而是 `equipment` 或 `variant`。若这些差异改变长期可比性，仍复用基本动作 ID，但分开建立趋势。
- 长期进步比较的默认可比键为 `exercise_id + variant + equipment + sequence role`。只有可比键一致时，才直接比较重量、次数、组数、RIR 或 `volume_load`；跨键数据只能作为不同上下文，不能合并判定 PR 或退步。
- 若发现历史记录把同一动作拆成了不同 ID，或把不同动作错误合并到同一 ID，先定位具体记录并向用户说明，再做最小纠正；不要为了让趋势好看而静默改写历史。

## 非传统或用户自定义动作

“没有统一官方名称”不等于“不是有效动作”。遇到 `Y举`、教练自创名称、健身房黑话或仅在小范围使用的叫法时：

1. 不要仅凭字面或搜索到的相似动作强行归类，也不要擅自翻译成某个传统动作。
2. 至少询问并确认用户用它训练的主要部位，例如“三角肌中束和后束”。这是创建自定义动作的必要信息。
3. 如果同一叫法可能对应明显不同的动作，再询问最少的区分信息：使用什么器械、身体姿势，以及手臂或器械的大致运动轨迹。不要一次索取与归类无关的细节。
4. 用户确认后，在动作词典中创建 `naming_status: "user_defined"` 的动作。保留用户叫法作为 `canonical_name` 或别名，并写入简短 `definition`、用户确认的 `primary_muscles` 和 `target_basis: "user_confirmed"`。
5. 在定义完成前不要写入训练日志；不要用 `notes` 绕过未知动作校验。
6. 后续遇到相同叫法可直接匹配。若用户描述的训练部位或做法与既有定义冲突，应询问这是同一动作的新变体，还是另一个同名动作。

这里记录的是用户的训练意图和个人动作定义，不是医学或生物力学结论。Agent 回报时应说“按你的定义，主要训练……”，不要把未经验证的目标肌群表述成客观定论。

## 解析约定

- 组格式 `次数x重量kg@RIR`：`12x40@2`。
- “45kg 10次两组”展开为两个 `10x45`。
- “最后一组 RIR 1”只把 `@1` 加在最后一组；不要传播到全部组。
- `12xbw` 表示自重 12 次；`30s` 表示 30 秒计时组。
- 用户未指明左/右时，默认是双侧动作，记录 `laterality=bilateral`。
- 用户明确写出左手、右手、左腿或右腿时，记录 `laterality=unilateral`，每侧分别落组，不合并或取平均。CLI 使用 `R:8x20`、`L:8x20` 表示右侧/左侧；同侧出现的先后次序自动保存为 `round`。
- 窄距、宽距、对握等会影响可比性的握法写入 `variant.grip`，不要只留在自由文本中。
- 未说明单位的配重默认 kg，但在回报中明确这一假设。
- 单侧器械若用户只报一个数字，不猜测这是“每侧”还是“总重”；需要确认，或把解释写进 `notes`。
- 热身组通过 `-WarmupCount` 标记，不计入默认训练量统计。
- 失败组可记录实际完成次数；额外语义写入 `notes`，不捏造 RIR。

## 动作身份与变体

- `exercise_id` 回答“这是什么基本运动模式”。
- `variant.angle`：`flat | incline | decline | vertical | null`
- `variant.posture`：`standing | seated | lying | kneeling | null`
- `variant.laterality`：`bilateral | unilateral | alternating | null`
- `variant.grip`：常用值为 `narrow_neutral | narrow | wide | neutral | null`
- `equipment.name` 保存品牌、机型或用户用于区分器械的描述。
- 跨角度、跨器械的重量不可直接视为同一 PR。统计时默认按变体和器械分组。

## 维护动作词典

- 只有用户确认某叫法的含义后，才把它加入 `aliases`。
- 别名必须在整个词典中唯一；运行 `validate` 检查。
- 品牌名、健身房自定义编号和座椅档位通常属于 `equipment` 或 `notes`，不是别名。
- 当原始叫法含品牌或临时描述、但动作身份已由上下文唯一确认时，使用 `add -Exercise <原话> -ResolveAs <规范动作名>`；这样既保留 `reported_name`，也不污染别名。
- 若新动作无法归入现有 `exercise_id`，添加稳定的英文 snake_case ID、中文规范名、动作模式、主要肌群、器械类型、别名及支持的变体。
- 自定义动作不要求存在国际通用英文名。ID 只需稳定、可读；不要为了显得标准而编造“官方名称”。
- `primary_muscles` 使用现有英文肌群词汇；常用值包括 `front_delts`、`side_delts`、`rear_delts`、`chest`、`lats`、`back`、`biceps`、`triceps`、`quads`、`hamstrings`、`glutes`。无法准确映射时先询问，不自行提升解剖精度。
- 不因拼写差异或中英文差异创建重复动作。

## 数据安全

- 日志采用追加写入。除非用户明确要求纠错，不覆盖或删除既有训练事实。
- 纠错时先定位精确 `id`，说明将修改哪一条，再做最小变更。
- 不将健康推断、疼痛诊断或用户未陈述的信息写成事实。
- 用户确认：没有训练记录的日期就是休息日。做日历、周报或恢复分析时，缺少训练记录的日期直接标记为 `rest_day`；不要为休息日创建空的 `data/workouts/` 记录。

## 动作顺序与优先级

- `sequence` 是一次训练内从 1 开始的动作序号，是训练事实的一部分。
- 展示训练日、复盘表现和寻找可比历史时，按 `sequence` 排序；`performed_at` 只表示记录中的时间戳，不能替代训练顺序。
- 同一天的 `sequence` 不得重复。用户未提供顺序时才询问，不按动作类别自行重排。
- 设计顺序前读取 `knowledge/exercise-order.md`。当前结论是：先做动作通常有利于该动作的力量发展，但没有可靠证据显示顺序会显著改变肌肉肥大。
- 胸背日按 `profile/training-preferences.json` 的证据化模板轮换优先肌群。轮换状态（`last_completed_priority` / `next_priority`）以 profile 为准，本文件不复制其值，避免过期。
- 比较进步时必须匹配顺序角色；胸部优先日不直接与背部优先日的同动作表现判定进步或退步。
- 只有训练实际完成后才更新 `last_completed_priority` 和 `next_priority`；生成计划本身不推进轮换状态。
## 训练日类型标记

- 每条新建训练记录使用 `day_type`：标准日 `standard`、渐进超负荷日 `overload` 或减载日 `deload`。没有日期记录的日期是休息日，不写空文件。
- 测试/PR 和技术练习不是肌肥大核心日类型；偶尔测试或练习时，用 `tags`/`notes` 记录目的。技术练习若同时是有意降压恢复，才标 `deload`。
- `overload` 和 `deload` 是带意图的相对标签，不以单日重量或容量的偶然波动自动推定。必须保留可比的动作、变体、器械和顺序角色，并在 `day_type_basis` 或 `notes` 中说明依据。
- 渐进超负荷优先按动作级判断：训练日可以只让一个或少数优先动作增加次数、负重或组数，其余动作维持基线即可；`day_type=overload` 不表示当天所有动作都必须进步。此“选择性推进”是项目启发式，不得表述为已被直接试验证明优于全动作推进。
- `overload` 时记录 `overload_lever`（`load`/`reps`/`sets`/`density`）；`deload` 的核心是有意降低训练压力以减轻疲劳、促进恢复，没有统一适用于所有人的百分比。
- 容量和重量分开统计：总次数、工作组、`weight_kg × reps`、RIR/RPE；不同器械或变体不得直接比较 `volume_load` 或 PR。详细定义见 `knowledge/training-day-types.md`。
