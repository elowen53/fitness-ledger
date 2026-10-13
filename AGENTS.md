# train-logbook Agent 约定

本项目名为「train-logbook」，是用户的训练事实账本。Agent 的任务是把自然语言训练描述安全地转为结构化记录，并维护可审计的动作词典。

## 知识库使用

- 设计、调整或评价以肌肉肥大为目标的训练前，必须先读取 `knowledge/hypertrophy-training.md`。
- 2026 ACSM 指南是当前原则，2009 渐进模型只用于补充具体操作；冲突时采用新版。
- 必须区分 ACSM 结论、项目启发式规则和用户事实，不把其中一类冒充另一类。
- 训练计划不是已完成事实。除非用户随后报告实际完成情况，否则不要把计划写入 `data/workouts/`。
- 新证据导致规则变化时，更新知识文档的“最后核对”和“版本记录”，不要静默覆盖来源与适用范围。
- 设计训练前读取 `profile/training-preferences.json`。用户个人策略优先用于个体化方案，但不要把其中的个人解释表述成通用科学结论。

## 每次记录必须遵循的流程

1. 读取 `catalog/exercises.json`，或调用 `scripts/train-logbook.sh resolve --exercise <原始叫法> --json`。
2. 将动作拆成：规范动作 `exercise_id`、变体、具体器械。不要为每个品牌或角度创建新的规范动作。
3. 只有在结果唯一且语义合理时才写入。脚本返回 `ambiguous` 或 `unknown` 时，先向用户确认。
4. 使用脚本写入，不要手工拼 JSONL。macOS 与 Windows 的 WSL 均使用 `scripts/train-logbook.sh add`（调用 `scripts/train_logbook.py add`）。始终保留用户原话到 `reported_name`。
5. 严格按用户报告的先后顺序写入 `sequence`。即使某动作因等待确认而稍后补写，也必须保留它在原训练中的位置，不能使用落盘时间代替动作顺序。
6. 写入后运行 `validate`（`scripts/train-logbook.sh validate`）。若本轮包含多条动作，全部完成后再运行一次即可。
7. 简短回报日期、规范动作、变体、器械、顺序和组数；指出任何采用的假设。不要自动提交 Git，除非用户明确要求。

> 平台说明：本仓库维护统一的 Bash / Python 3 标准库实现，以 `scripts/train-logbook.sh` 为入口；macOS 原生执行，Windows 通过 WSL 执行。新功能或规则变更必须通过 `bash tests/smoke.sh` 和 `python3 -m unittest discover -s tests -p 'test_*.py'` 验证，Windows 下这两项检查也必须在 WSL 中运行。

## Windows 执行环境（2026-10-12 用户确认）

- Windows 下所有仓库 Git 命令、Shell 脚本和 Python 脚本统一在 WSL 中执行，使用 WSL 内的 Linux `git`、`bash` 和 `python3`，避免与 macOS 的执行约定冲突。
- 不使用 Windows 原生 Git、Git Bash、PowerShell 执行 Shell 脚本，或 Windows Python / `py.exe` 运行项目脚本和测试。PowerShell 可用于调用 `wsl.exe`，文件读取与编辑不受此运行环境规则限制。
- 在 WSL 中使用 Linux 路径；当前 Windows 仓库 `D:\fitness` 对应 `/mnt/d/fitness`。推荐调用形式为 `wsl.exe --cd /mnt/d/fitness --exec <命令及参数>`，具体示例见 `docs/agent-cli.md`。
- 沿用现有脚本与测试入口，不另建 Windows 专用实现。WSL 无法执行时先排查并报告阻塞，不自行改用 Windows 原生 Git、Shell 或 Python。

脚本命令、参数、组格式和常用调用示例集中记录在 `docs/agent-cli.md`。需要查询 CLI 用法时读取该文档，不要依赖面向用户的 `README.md`。

## 通过问答补充训练信息

用户已要求以 Agent 与用户问答的形式补充训练信息（2026-09-05）。执行细节见 `docs/training-dialogue.md`，偏好保存于 `profile/training-preferences.json` 的 `recording_preferences.information_collection`。

- 先读取本轮原话、相关历史和已确认偏好，整理已知信息，再一次询问一个最重要的缺口；用户已完整提供的信息不重复问，不要求填写整张表。
- 优先补齐实际日期、动作身份、实际顺序及每组数据。消歧与重量含义确认仍遵循原规则，不能为了加快问答而猜测或跳过。
- 既有默认 RIR、未说明左右时的双侧约定、单位约定和质量优先策略继续适用，不在每次问答中重新确认；历史的实际重量、次数、休息和质量状态不能直接充当本次事实。
- 每次训练有三项固定确认（2026-10-11，见 profile 的 `recording_preferences.session_checks` 与 `docs/training-dialogue.md`）：本次重点推进的 1–2 个动作及推进变量（`--focus --overload-lever`，当天随之为 `overload`）；只针对重点动作（无重点时前 1–2 个动作）问动作质量；器械设置用一句“和上次一样吗”统一确认，首次使用的器械才问具体设置。三项均可跳过，跳过时不推定。
- 必要信息齐全后，可按相关性逐轮询问实际休息等其他可选信息；用户说“不记得”“跳过”“直接记录”时，不继续追问可选项、不编造值。可选信息不阻塞核心记录。
- 用户未明确评价动作质量时，不能把未回答当作“质量保持”；模板和执行标准缺失也不自动填充。已说明质量改善或主动降重时，保留原话并按现有质量规则处理。
- 信息充分且用户已要求记录时，直接使用脚本保存并校验，简短回报，不再增加一次通用的“是否确认提交”问答。Git 提交和推送仍按用户明确授权处理，问答不扩大授权。
- 此流程只调整信息收集方式；动作归一化、原话保留、实际顺序、左右分别记录、未知动作确认、历史保护和计划/事实分离等原则不变。

## 动作对齐与长期身份

- 每次记录都必须先做动作对齐，不能直接用本次字面名称创建记录。解析时同时检查动作词典的规范名/别名和历史日志的 `reported_name`；历史中已确认过的不同叫法也应优先复用原 `exercise_id`。
- `exercise_id` 是跨时间线保持稳定的动作身份。同一基本动作即使简称、全称、品牌描述或中英文写法发生变化，也不得创建重复 ID；用户原话继续保存在每条记录的 `reported_name` 中。
- 名称不同但疑似同一动作时，先向用户展示拟对齐的规范动作，以及变体、器械或动作轨迹上的关键差异，并询问是否对齐。用户确认后复用已有 ID；若该叫法语义稳定，再加入 `aliases`，否则只保留为历史 `reported_name`。
- 只有查过词典和历史记录、排除已有动作，并获得用户对动作含义的确认后，才能创建新 `exercise_id`。`unknown` 不代表可以无确认自动新增；`ambiguous` 必须先消歧。
- 用户没有说是新动作或新器械时，未说明的器械名、器械类型、角度、姿势和握法按本人历史中最常用的补全（2026-10-11 确认，见 profile 的 `recording_preferences.equipment_variant_inference`）。`add` 自动执行：依次参考同一叫法、同一器械、同一动作的历史，前两级取最常用值，同一动作级只在历史只有一种值时补全；在同一器械、同一动作两级，若可比历史中有该变体字段（角度、姿势、握法）为空的记录，视为存在常规做法，不补全该变体，避免偶尔一次的特殊做法（如肱骨外旋）扩散到普通记录；补全的字段写入 `inferred_fields` 并在回报中说明。用户给出的器械名若被唯一一个更常用的历史器械名包含（如“龙门架”与“龙门架钢线”），统一为历史名。脚本报告无法唯一补全时，向用户展示候选并询问；用户明确说是新器械、新做法或不确定时，使用 `--no-infer`。历史记录用 `align` 预览、`align --apply` 按同一规则补全。
- 品牌、机型、角度、姿势、握法和单双侧通常不是新动作身份，而是 `equipment` 或 `variant`。若这些差异改变长期可比性，仍复用基本动作 ID，但分开建立趋势。
- 长期进步比较的默认可比键为 `exercise_id + variant + equipment + sequence role + weight_basis`。顺序角色由脚本按实际顺序推导：`opener`（第 1 个动作）、`muscle_first`（当天首次训练该部位）、`muscle_after`（同部位已练过），不是原始序号。只有可比键一致时，才直接比较重量、次数、组数、RIR 或 `volume_load`；跨键数据只能作为不同上下文，不能合并判定 PR 或退步。
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
- 组类型前缀：`top:` 顶组、`bo:` 降重组（back-off）、`drop:` 递减组、`rp:` rest-pause、`myo:` myo-reps 小组；未标即普通工作组 `straight`。只有用户描述了这种结构时才标，不能因为后一组重量较低就自行推断为降重组。热身组不标组类型。
- 力竭后的半程次数写在完整次数后：`8x20+3p`；用户说明位置时用 `+3lp`（拉伸端）或 `+3sp`（收缩端）。半程不计入 `reps`。
- 力竭方式后缀（可选，仅用户主动说明时）：`!t` 技术力竭、`!a` 绝对力竭（推不动为止）、`!e` 力竭后延伸（加半程、强迫次数等）。不与 `@RIR>0` 同用；不为此追问。
- “45kg 10次两组”展开为两个 `10x45`。
- “最后一组 RIR 1”只把 `@1` 加在最后一组；不要传播到全部组。
- `12xbw` 表示自重 12 次；`30s` 表示 30 秒计时组。
- 用户未指明左/右时，默认是双侧动作，记录 `laterality=bilateral`。
- 用户明确写出左手、右手、左腿或右腿时，记录 `laterality=unilateral`，每侧分别落组，不合并或取平均。CLI 使用 `R:8x20`、`L:8x20` 表示右侧/左侧；同侧出现的先后次序自动保存为 `round`。
- 窄距、宽距、对握等会影响可比性的握法写入 `variant.grip`，不要只留在自由文本中。
- 未说明单位的配重默认 kg，但在回报中明确这一假设。
- 已确认的重量口径使用 `weight_basis`（单只、每侧、合计或器械标示）保存；不同口径分开统计，未知口径不猜测。
- 用户规则（2026-10-11，见 profile 的 `recording_preferences.weight_basis_default`）：重量口径按器械类型固定，不论是否分左右手，不再询问。挂片和插片器械（`machine`）、钢线/龙门架配重（`cable`，用户确认属于插片）、杠铃记总重 `total`；哑铃记单只 `per_implement`。`add` 在口径省略或为 `unknown` 时自动应用（器械类型可来自原话、历史补全或词典中只对应一种口径的类型），并在 `inferred_fields.weight_basis` 标明 `convention`；用户当次明确说明其他口径时以用户为准。器械类型无法确定时口径保持 `unknown`，不猜测。
- 热身组通过 `--warmup-count` 标记，不计入默认训练量统计。
- 失败组可记录实际完成次数；额外语义写入 `notes`，不捏造 RIR。
- 用户已确认所有工作组均练至力竭：未报告 RIR 时由脚本按 profile 默认记录 `rir=0` 并保留 `rir_source=profile_default`，不再询问或留空（2026-08-18 确认，见 `profile/training-preferences.json` 的 `recording_preferences.rir_default`）。

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
- 品牌名、健身房自定义编号和座椅档位通常属于 `equipment` 或 `notes`，不是别名。座椅、靠垫、握把位置等用户报告的器械设置用 `--setup 键=值` 保存；用户确认“和上次一样”时用 `--setup-same-as-last`。可先运行 `setup` 命令查看上次设置并问一次是否相同；用户未回答时不沿用。
- 当原始叫法含品牌或临时描述、但动作身份已由上下文唯一确认时，使用 `add --exercise <原话> --resolve-as <规范动作名>`；这样既保留 `reported_name`，也不污染别名。
- 若新动作无法归入现有 `exercise_id`，添加稳定的英文 snake_case ID、中文规范名、动作模式、主要肌群、器械类型、别名及支持的变体。
- 自定义动作不要求存在国际通用英文名。ID 只需稳定、可读；不要为了显得标准而编造“官方名称”。
- `primary_muscles` 使用现有英文肌群词汇；常用值包括 `front_delts`、`side_delts`、`rear_delts`、`chest`、`lats`、`back`、`traps`、`biceps`、`triceps`、`quads`、`hamstrings`、`glutes`。`traps`（斜方肌）于 2026-10-11 按用户确认加入：耸肩记 `traps`，Kelso 耸肩记 `traps` + `back`。无法准确映射时先询问，不自行提升解剖精度。
- 不因拼写差异或中英文差异创建重复动作。

## 数据安全

- 日志采用追加写入。除非用户明确要求纠错，不覆盖或删除既有训练事实。
- 纠错时先定位精确 `id`，说明将修改哪一条，再做最小变更。
- 不将健康推断、疼痛诊断或用户未陈述的信息写成事实。
- 停训期：`report` 合并 `data/day-notes/` 中 `training_status: "paused"` 的区间和超过 21 天的训练空档，输出 `layoffs` 与 `return_phase`。跨停训期的同动作对比一律重新建立基准，停训前数字只放在 `pre_layoff_reference` 作参考，不判定 PR 或退步；复训后的训练彼此比较。复训期内回报表现时说明处于复训期。
- 用户确认：没有训练记录的日期就是休息日。做日历、周报或恢复分析时，缺少训练记录的日期直接标记为 `rest_day`；不要为休息日创建空的 `data/workouts/` 记录。

## 动作顺序与优先级

- `sequence` 是一次训练内从 1 开始的动作序号，是训练事实的一部分。
- 新记录使用版本 2，实际日期保存为 `training_date`，录入时刻保存为 `recorded_at`；只有用户提供真实时刻才填 `performed_at`。旧版本继续读取，不自动迁移。
- 展示训练日、复盘表现和寻找可比历史时，按 `sequence` 排序；`performed_at` 只表示记录中的时间戳，不能替代训练顺序。
- 同一天的 `sequence` 不得重复。用户未提供顺序时才询问，不按动作类别自行重排。
- 设计顺序前读取 `knowledge/exercise-order.md`。当前结论是：先做动作通常有利于该动作的力量发展，但没有可靠证据显示顺序会显著改变肌肉肥大。
- 当前分化以 profile 的 `training_split` 为准（2026-10-11 用户确认：推/拉交替）。胸背同日轮换（`priority_rotation.chest_back_day`）已停用，模板与轮换状态仅作历史；设计训练时不按它推进顺序，用户恢复胸背同日并确认后才重新启用。
- 比较进步时必须匹配顺序角色；胸部优先日不直接与背部优先日的同动作表现判定进步或退步。
- 轮换启用时，只有训练实际完成后才更新 `last_completed_priority` 和 `next_priority`；生成计划本身不推进轮换状态。

## 动作质量与渐进优先级

- 设计和评价训练时读取 `profile/training-preferences.json` 的 `progression_preferences`。用户确认的个人优先级是：**动作质量 > 完成数量 > 工作重量**。这是用户个人训练策略，不得表述成 ACSM 的通用科学结论。
- 动作质量是后续渐进的前提。只有质量保持或提高时，增加次数、组数或重量才判为有效进步；不能为了完成更多次数或更大重量接受明显的动作质量下降。
- 用户明确报告“动作优化/质量显著提升”并因此降低工作重量时，将该动作判为大的进步而不是退步。仍须如实记录较低重量和实际次数，并把质量改善写入 `notes`；不得篡改 `volume_load` 或把较低重量伪装成加重。
- 质量优化会改变可比基线。后续趋势应优先与优化后的动作做法、变体、器械和顺序角色比较；旧的较高重量只能作为不同质量上下文，不能直接用于判定新基线退步。
- 仅有重量下降、没有用户明确报告质量改善时，不自动推断动作优化，也不擅自判定为进步或退步。

## 训练日类型标记

- 每条新建训练记录使用 `day_type`：标准日 `standard`、渐进超负荷日 `overload` 或减载日 `deload`。没有日期记录的日期是休息日，不写空文件。
- 测试/PR 和技术练习不是肌肥大核心日类型；偶尔测试或练习时，用 `tags`/`notes` 记录目的。技术练习若同时是有意降压恢复，才标 `deload`。
- `overload` 和 `deload` 是带意图的相对标签，不以单日重量或容量的偶然波动自动推定。必须保留可比的动作、变体、器械和顺序角色，并在 `day_type_basis` 或 `notes` 中说明依据。
- 渐进超负荷优先按动作级判断：训练日可以只让一个或少数优先动作增加次数、负重或组数，其余动作维持基线即可；`day_type=overload` 不表示当天所有动作都必须进步。此“选择性推进”是项目启发式，不得表述为已被直接试验证明优于全动作推进。
- `overload` 时由重点推进动作的 `progression_target.lever`（`load`/`reps`/`sets`/`density`）记录推进变量；同日其他动作省略 `--day-type` 即继承当天类型。`report` 的 `target_lever_moved` 只在可比时判断该变量的数字是否提高，`target_effective` 再按“质量优先”判断是否为有效推进（数字提高且质量确认保持或提高才为真，质量下降为假，质量未知为空）；`next_target` 是按双重渐进给出的下次建议，属于计划，不写入日志，比较被阻断、新基线或质量未确认时不建议推进；`deload` 的核心是有意降低训练压力以减轻疲劳、促进恢复，没有统一适用于所有人的百分比。
- 容量和重量分开统计：总次数、工作组、`weight_kg × reps`、RIR/RPE；不同器械或变体不得直接比较 `volume_load` 或 PR。详细定义见 `knowledge/training-day-types.md`。
