# 训练日类型与训练压力标记

最后核对：2026-08-24
适用范围：本项目的成人阻力训练记录与肌肉肥大分析。

## 先说结论

“渐进超负荷日”不是 ACSM 规定的固定日历名词。渐进超负荷是一个跨训练日的比较关系：在动作、变体、器械和顺序角色可比的前提下，有意提高了某个训练压力变量。不能因为某天重量较大、次数较多，或单日 `重量×次数` 较高，就自动把它标成超负荷日。

“减载日”则应保留为有意降低训练压力、帮助消除疲劳并为后续训练做准备的日子。国际 Delphi 共识给出的核心定义是“降低训练压力，以减轻生理和心理疲劳、促进恢复并提高后续准备度”；共识没有规定一个适用于所有人的固定百分比或固定周期。

ACSM 2026 强调持续执行、个体化和足够的周训练量，并没有要求复杂周期化或每周必须安排某一种特殊日。因此本项目的标签是可审计的项目数据约定，不冒充通用科学结论。

## 日类型词典

| `day_type` | 中文 | 定义与使用条件 |
| --- | --- | --- |
| `standard` | 标准/积累日 | 按当前计划完成常规刺激，没有明确的增加或降低意图。新记录未注明类型时默认此值；这不表示训练一定“有效”或“没有进步”。 |
| `overload` | 渐进超负荷日 | 用户或计划明确要增加至少一个动作或训练日变量：负重、次数、工作组数、训练密度，或在相同负重下提高完成量。必须能指出 `overload_lever` 和比较基线；不能只凭一次偶然的高重量推断。它不要求当天所有动作都进步。 |
| `deload` | 减载日 | 有意降低整体训练压力以管理疲劳、恢复和后续准备度。通常保留动作模式，但减少工作组、降低接近力竭程度，或在必要时降低负重；具体幅度由个人恢复和训练史决定。 |

休息日不写入训练 JSONL。按用户约定，没有训练记录的日期就是休息日，不创建空日志。

测试/PR 和技术练习不是本项目的核心日类型。肌肥大训练没有必要定期测试 1RM 或安排力量举式 PR 日；如果偶尔测试，应使用 `tags` 或 `notes` 记录目的。技术练习同理：若只是常规动作练习，仍是 `standard`；若同时有意降低训练压力以恢复，才标 `deload`。

## 训练压力不能压成一个数字

容量（volume）和重量（load）相关，但不是同一个变量。每次记录尽量保留以下独立字段或可计算量：

- 工作组数：排除热身组；对同一肌群按项目规则统计直接工作组。
- 总次数：用于观察在相同负重下的完成量。
- `volume_load = Σ(重量 kg × 次数)`：只在相同动作、变体、器械和计重方式下比较。不同品牌器械、滑轮倍率、角度或单侧/双侧不得直接合并成 PR。
- 负荷强度：有 1RM、百分比或稳定的重量区间时记录；没有就保留未知，不猜测。
- 努力程度：RIR/RPE。接近力竭会显著影响疲劳，即使重量和次数不变。
- 密度：相同工作量所用时间或组间休息；没有时间数据时不要推断密度变化。
- 动作质量：只记录用户明确报告的动作优化、技术变化或质量评价；当前没有独立数值字段时保存在 `notes`，不得从重量变化自动推断。

因此，“重量增加但次数和组数下降”不一定是训练压力增加；“重量不变但完成更多次数或组数”也可能是清晰的超负荷。分析时至少同时查看工作组、次数、负重/相对负荷和 RIR。

### 用户个人质量优先规则

用户确认的项目优先级为 **动作质量 > 完成数量 > 工作重量**。这是个人训练策略，不是 ACSM 的通用结论。动作质量是进步判定的首要维度：如果用户明确报告为了优化动作而降低工作重量，并确认质量明显提高，该动作在叙述性评估中判为大的进步，而不是 `regressed`。重量、次数和 `volume_load` 仍按客观数据计算，不因质量评价而改写。

质量提升本身不等于机械训练压力增加，也不是现有 `overload_lever`（`load`/`reps`/`sets`/`density`）之一。因此，仅发生质量优化时，训练日仍可标为 `standard`；动作级评估则记录为“因质量提升而取得大的进步”。优化后的做法和当前重量构成新的质量基线，旧的较高重量不直接与其合并判定 PR 或退步。

## 动作级优先于训练日级

渐进超负荷首先属于“某个动作在可比条件下的变化”，其次才是训练日的汇总标签。一个训练日可以这样安排：

- 1 个优先动作：明确追求增加次数或最小负重档；
- 其余动作：保持基线、完成目标区间，或只有状态良好时再增加次数；
- 辅助动作：优先保证动作质量和目标肌群的有效工作组，不强迫每次加重。

因此，如果只有 FORWARD 推胸增加了 1 次，而划船和下拉维持基线，这仍然是有效的动作级渐进；如果训练日事先确实把推胸作为本次超负荷目标，日标签可以是 `overload`。后续分析应分别判断每个动作是 `progressed`、`maintained`、`regressed` 还是 `not_comparable`，不能用日标签替代动作级判断。

### 证据边界

目前没有高质量研究直接比较“每个动作都必须同时渐进”与“只让一个或少数动作渐进”对肌肉肥大的差异。因此，不能把选择其中一种写成 ACSM 结论。

现有间接证据是：ACSM 2026 证据汇总中，固定动作与变化动作对肌肥大没有稳定差异；在总训练量相等时，周期化与非周期化对肌肥大也没有稳定差异。相关研究更常把训练量（尤其工作组）和周频率作为剂量变量，而不是要求每个动作在每次训练都增加。故本项目“优先动作推进、其他动作维持或按状态推进”是个体化实施启发式，不是已被直接验证的唯一方案。

## 本项目的判定流程

1. 先看训练意图：用户说“渐进”“加重”或“这周减量”，优先记录为相应类型；用户说“冲 PR”或“技术练习”时，用 `tags`/`notes` 记录训练目的，不自动创建新的 `day_type`；计划标签和实际完成数据分开保存。
2. 选择可比基线：同一 `exercise_id + variant + equipment`，并匹配胸背日的顺序角色。优先使用最近两次可比记录的中位水平，而不是只与上一次偶然表现比较。
3. 先判定动作质量：只有用户明确报告动作优化或质量变化时才使用该信息。若因优化而降重且质量显著提高，记为大的动作级进步，并从本次建立新质量基线；不能仅凭降重自动推断质量改善。
4. 判定 `overload`：至少一个变量有计划地提高，同时没有用另一个变量的大幅下降抵消；在记录中写明 `day_type_basis`（如 `planned`、`user_reported` 或 `agent_comparison`）和 `overload_lever`（`load`、`reps`、`sets`、`density`）。没有足够基线时只记录计划意图，不宣称已经实现超负荷。
5. 判定 `deload`：必须有明确的减载意图或周期安排，并观察到整体压力下降。项目可用“工作组减少约 30–50%、或明显远离力竭、必要时再降低负重”作为起始规划启发式；这不是 ACSM 的硬阈值，需按恢复反应调整。
6. 若只是当天状态差、少做了一组或重量下降，且没有质量改善或减载意图，仍标 `standard` 并在 `notes` 记录实际情况；不要自行判为动作优化，也不要事后把偶然低表现改称减载。

## 与记录格式的关系

每个训练动作记录都带同一训练日的 `day_type` 和 `day_type_basis`。同一天不得混用不同 `day_type`；旧日志缺少该字段时视为 `unclassified`，不擅自回填历史事实。示例：

```json
{
  "day_type": "overload",
  "day_type_basis": "planned",
  "notes": "overload_lever=reps; matched baseline=2026-08-05 back-first"
}
```

CLI 示例：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\fitness.ps1 add `
  -Date 2026-08-08 -Exercise "FORWARD推胸" -ResolveAs "器械推胸" `
  -Sets "10x110","9x110","8x110" -Sequence 1 `
  -DayType overload -DayTypeBasis planned `
  -Notes "overload_lever=reps"
```

## 证据边界

- ACSM 2026：持续性、个体化和足够训练量优先；不要求复杂周期化，也没有统一的“超负荷日”百分比。
- ACSM 2009：提供了在目标次数上限被连续达到后逐步增加负荷等操作建议，适合作为项目的双重渐进启发式，不应理解为每次都必须加重。
- Delphi 减载共识：减载的关键是“有意降低训练压力并改善后续准备度”，而不是某个固定重量或周数。
- 训练量负荷（`weight × reps`）可用于同条件下的趋势观察，但不能替代长期适应、恢复和动作可比性判断。
- ACSM 2026 补充证据表：[Position Stand supplementary evidence PDF](https://cdn-links.lww.com/permalink/mss/d/mss_1_1_2025_11_13_phillips_msse-d-25-00141_sdc1.pdf)，其中列出动作选择、周期化和训练量对肌肥大的汇总结果。
- Moesgaard L et al. [Effects of Periodization on Strength and Muscle Hypertrophy in Volume-Equated Resistance Training Programs](https://pubmed.ncbi.nlm.nih.gov/35044672/), 2022。
- Baz-Valle E et al. [Total Number of Sets as a Training Volume Quantification Method for Muscle Hypertrophy](https://pubmed.ncbi.nlm.nih.gov/30063555/), 2021。

## 版本记录

- 2026-08-05：新增训练日类型、容量/重量分离记录和计划意图与实际表现的判定边界；采用 ACSM 2026、ACSM 2009、Delphi 减载共识及相关综述作为依据。
- 2026-08-05：根据肌肥大目标收窄核心日类型为 `standard`、`overload`、`deload`；测试/PR 和技术练习改为可选的 `tags`/`notes`，不作为必需训练阶段。
- 2026-08-05：补充证据边界：尚无直接试验证明同一训练日所有动作必须同时渐进；“优先动作推进、其余动作维持或按状态推进”保留为项目启发式。
- 2026-08-24：加入用户确认的个人规则“动作质量 > 完成数量 > 工作重量”；动作优化导致主动降重且质量显著提高时，动作级判为大的进步，但不改写客观负荷数据，也不自动标为 `overload`。

## 来源

- American College of Sports Medicine. [ACSM Publishes Updated Resistance Training Guidelines](https://acsm.org/resistance-training-guidelines-update-2026/), 2026。
- American College of Sports Medicine. [Progression Models in Resistance Training for Healthy Adults](https://chapters.acsm.org/docs/default-source/science/translated-position-stands/simplified-chinese/cs_progression.pdf?sfvrsn=d5894b8b_2), 2009。
- James LP et al. [Delphi consensus on deloading in resistance training](https://pubmed.ncbi.nlm.nih.gov/37730925/), 2023。
- [Volume-load tracking in resistance training](https://pmc.ncbi.nlm.nih.gov/articles/PMC6316164/), 2018。
