# 数据模型

每条 JSONL 记录代表一次训练中的一个动作，包含若干组。新记录使用 `schema_version: 2`；读取和校验继续支持版本 1，不自动迁移或补写历史。

```json
{
  "schema_version": 2,
  "id": "20260805-193012-a1b2c3",
  "training_date": "2026-08-05",
  "recorded_at": "2026-10-07T19:30:12.0000000+08:00",
  "performed_at": null,
  "weight_basis": "machine_display",
  "day_type": "standard",
  "day_type_basis": "default",
  "sequence": 1,
  "exercise_id": "machine_chest_press",
  "reported_name": "力健上斜推胸机",
  "variant": {
    "angle": "incline",
    "posture": null,
    "laterality": "bilateral",
    "grip": null
  },
  "equipment": {
    "type": "machine",
    "name": "Life Fitness Insignia"
  },
  "sets": [
    {"reps": 12, "weight_kg": 40, "rir": 2, "rir_source": "reported", "duration_sec": null, "bodyweight": false, "warmup": false, "side": null, "round": null}
  ],
  "notes": "座椅 4 档",
  "tags": ["push"]
}
```

设计规则：

- `reported_name` 永远保留原始叫法，便于发现误归一化。
- `sequence` 是用户实际训练顺序，从 1 开始；分析和展示训练日时优先按它排序，不能用落盘时间代替。
- 未知数值/时间用 `null`，不使用空字符串或臆测值；重量口径与 RIR 来源用显式的 `unknown` 枚举。
- kg 是唯一外部负重单位；自重动作使用 `bodyweight=true`，不把体重伪装成外部负重。
- 外部负重总量只计算非热身且同时有 `reps`、`weight_kg` 的组。工作组条数另行计算，包含自重与计时工作组；不以缺少外部负重排除肌群训练组数。
- 单侧动作的 `side` 使用 `left | right`，`round` 表示该侧、该阶段的第几轮；新记录中热身组与工作组分别从 1 编号，不相互挤占。旧记录不自动重编号。双侧动作两者均为 `null`。
- 每组 `set_type`：`straight`（普通工作组，新记录默认）、`top`、`backoff`、`drop`、`rest_pause`、`myo`。旧记录缺少该字段，按 `straight` 读取，不回填。热身组只允许 `straight` 或缺省。
- `partial_reps`：完整次数之后额外的半程次数（正整数），不计入 `reps`；`partial_position` 为 `lengthened`、`shortened` 或 `null`（未说明）。
- `failure_mode`：`technical`、`absolute`、`extended` 或 `null`，只记录用户明确说明的力竭方式；不能用于热身组，也不能与 `rir > 0` 同时出现。
- 会影响动作可比性的握法保存在 `variant.grip`。例如窄距对握为 `narrow_neutral`，宽距为 `wide`。
- `equipment.type` 保存 `machine / cable / barbell / dumbbell / bodyweight` 等可比较的器械大类。
- `equipment.name` 不做全局枚举，因为同一器械在不同健身房可能有不同标识。

## 日期、重量口径与来源（版本 2）

- `training_date`：实际训练日期，`YYYY-MM-DD`，决定文件路径、日类型一致性、顺序唯一性、报告窗口和最近记录排序。
- `recorded_at`：脚本实际录入时刻，带时区；补录历史训练时仍是当前录入时间。
- `performed_at`：用户明确提供的实际训练时刻，带时区且本地日期必须与 `training_date` 相同；未提供则为 `null`。不再以录入时刻拼造训练时间。
- 版本 1 的日期仍取旧 `performed_at` 的原始日期部分，不按当前主机时区转换。旧时间不升级为已确认的实际训练时刻。
- `recent` 按训练日期倒序、同日 `sequence` 正序排列，最后才应用条数限制。旧记录缺少顺序时排在当日已知顺序之后；不猜测顺序。
- `weight_basis` 为整条动作记录中 `weight_kg` 的统一口径：`per_implement`（单只器械）、`per_side`（每侧）、`total`（合计外部重量）、`machine_display`（器械标示配重）、`unknown`（未确认）。只有用户已明确说明时才填写具体口径；同一记录不混用口径。不能仅凭器械名称猜测。
- `volume_kg` / `external_volume_kg` 保持原有的「记录重量 × 次数」算式，遵循本条记录的 `weight_basis`，不自动乘二，不宣称是全身承受的总重量。统计与趋势按口径分组；未知口径不能支持完全可比的负重表现结论。旧记录缺项按 `unknown` 读取，不从备注自动补写。
- 每组 `rir_source` 为 `reported`（组格式明确包含 `@RIR`）、`profile_default`（脚本应用已确认偏好）、`unknown`（无值）。默认只作用于没有显式 RIR 的工作组，热身组不补默认值。
- 应用默认 RIR 时，记录级 `rir_default` 保存所用 profile 偏好的快照，含数值、确认状态及原有确认日期/解释，保证以后偏好改变仍能追溯。原始历史没有来源字段时不反推来源。

## 写入与校验边界

- `add` 必须显式指定正整数顺序并保留非空原话。写入前使用与 `validate` 相同的记录校验，检查候选记录与完整现有账本；重复 ID、同日顺序冲突、日类型冲突、非法组数值、侧别冲突等错误均不落盘。
- 所有版本的已提供数值必须满足类型和范围约束；次数是非负整数（允许失败组 0 次），重量和 RIR 是非负有限数，计时必须大于零。版本 1 可保留缺少的顺序、日类型、单侧轮次和新增字段；版本 2 不允许以缺字段绕过新约束。
- 新单侧记录必须逐组标记左/右；带左右组但未指定单双侧时由侧别确定为单侧，没有单双侧或侧别信息时沿用双侧约定。
- `add` / `resequence` 共用排他锁 `.train-logbook-write.lock`，避免同时检查并写入相同顺序。程序异常终止遗留的锁不自动删除；先确认没有写入进程再处理。
- `resequence` 先定位唯一 ID、校验修改后的完整账本，再以同目录临时文件原子替换目标文件。冲突或重复 ID 时不修改任何记录；该命令仍只用于用户明确授权的纠错。

## 动作身份与长期对齐

- `exercise_id` 是同一基本动作跨日期、跨叫法保持不变的唯一身份；`reported_name` 是用户当次原话，不承担唯一性。
- 新记录写入前，解析器同时匹配词典规范名/别名和历史 `reported_name`。命中历史叫法时仍返回原 `exercise_id`，但不会因此自动污染全局别名。
- 名称不同但存在合理的同动作候选时，需要用户确认对齐；确认无法归入已有动作后才创建新 ID。
- 默认趋势键为 `exercise_id + variant.angle + variant.posture + variant.laterality + variant.grip + equipment.type + equipment.name + sequence_role + weight_basis`；不同趋势键不直接比较重量或 PR。
- `sequence_role` 在分析时由实际 `sequence` 推导，不写入日志：`opener`（第 1 个动作）、`muscle_first`（同日之前没有同部位动作）、`muscle_after`（同日之前已有同部位动作）、`unknown`（自身或同日记录缺少顺序）。“同部位”按词典 `primary_muscles` 判断，`lats/back/traps` 归为背部，三角肌各束归为肩部；这是项目启发式。
- `resolve` 返回的候选包含 `matched_source`：`catalog` 表示命中词典，`history` 表示命中过往日志中的原始叫法。

## 用户自定义动作

非传统动作仍存放在 `catalog/exercises.json`，不另建一套低优先级词典。示意结构：

```json
{
  "id": "user_y_raise",
  "canonical_name": "Y举",
  "naming_status": "user_defined",
  "definition": "由用户确认后的简短动作描述；未确认前不创建",
  "target_basis": "user_confirmed",
  "primary_muscles": ["side_delts", "rear_delts"]
}
```

- 文档示例本身不构成动作定义；真实定义需结合用户实际做法确认。
- `naming_status` 缺省时视为 `conventional`。
- `target_basis=user_confirmed` 表示记录的是用户的训练意图，不宣称这是医学或生物力学共识。
- 自定义动作必须有非空 `definition` 和至少一个 `primary_muscles`，词典校验会检查这一点。
- `day_type` 可为 `standard | overload | deload`，同一训练日应保持一致；`day_type_basis` 用于记录是计划、用户说明还是后续比较推定。旧记录可缺少这两个字段。
- `overload` 不是单日重量较大的同义词；需要在 `notes` 中说明 `overload_lever`（`load`/`reps`/`sets`/`density`）和可比基线。`deload` 只在有意降低训练压力时使用，不因一次低表现事后推定。完整定义见 `knowledge/training-day-types.md`。

## 可选分析上下文（向后兼容）

分析上下文同时支持版本 1 和 2。旧日志不做迁移；未提供上下文的 `add` 不新增 `analysis_context`。仅在用户明确报告或确认后，可随新记录保存：

```json
"analysis_context": {
  "session_template": "胸部优先-A",
  "execution_standard": "座椅4-全幅-不借力-v2",
  "quality_change": "improved_with_load_reduction",
  "rest_sec": 180
}
```

- `session_template`、`execution_standard`：非空文本；后者应能识别具体执行版本，细节写入原有 `notes`。都不取代动作 ID、变体、器械或真实顺序。
- `quality_change`：`maintained` / `improved` / `improved_with_load_reduction` / `degraded`，都是用户明确报告的当次质量状态。不能从数值猜测；缺少则省略。
- `improved_with_load_reduction`：编码用户确认的因优化主动降重且质量显著提高；叙述性评估为大的进步，客观重量保持原值。
- `rest_sec`：大于零的有限数值，表示本动作实际统一组间休息秒数，不是计划目标。各组不同或只有部分组已知时省略此字段，在 `notes` 保留详情，不填平均值。
- 旧记录缺少字段或值为 `null` 不补写；新上下文内部只保存已知值。`validate` 会检查新增已提供字段。

## 按历史补全的字段（inferred_fields）

```json
"inferred_fields": {
  "equipment.name": {"value": "蝴蝶机", "method": "history_reported_name", "support": 5, "original": null}
}
```

- 只出现在被补全的记录中，键为 `equipment.name`、`equipment.type`、`variant.angle`、`variant.posture`、`variant.grip`、`variant.laterality`、`weight_basis`。`weight_basis` 只按用户规则 `weight_basis_default` 补全（按器械类型：器械、钢线、杠铃记 `total`，哑铃记 `per_implement`，与单双侧无关），方法为 `convention`。`value` 必须等于记录当前值，`validate` 会检查。
- `method`：`history_reported_name`（同一叫法历史中最常用值）、`history_equipment`（同一器械历史中唯一值）、`history_exercise`（同一动作历史中唯一值）、`name_unified`（用户给出的器械名被唯一一个更常用的历史名包含；`original` 保存原名）、`convention`（未说明左右默认双侧；或按用户规则由器械类型确定重量口径）。`support` 为支持该值的历史记录数。
- 这是按用户规则得出的推定，不是用户当次原话；需要撤销时，按 `original` 恢复并删去对应键。

## 重点推进目标（可选）

```json
"progression_target": {"lever": "reps", "target": "最重组多一次", "basis": "user_reported"}
```

- 只出现在用户指定的本次重点推进动作上；`lever` 为 `load` / `reps` / `sets` / `density`，`target` 是用户原话（可为 `null`），`basis` 为 `user_reported` 或 `planned`。
- 有该字段的记录 `day_type` 必须是 `overload`。同日其他动作继承 `overload`，但没有该字段，表示维持或按状态完成。
- 它记录的是意图，不代表已经实现；是否实现由 `report` 在可比时判断。

## 器械设置（可选）

```json
"setup": {"values": {"座椅": "4", "靠垫": "2"}, "source": "reported", "from_record": null}
```

- `values`：用户报告的设置，非空的文本键值对；键名不做全局枚举。
- `source=reported`：用户本次报告；`same_as_previous`：用户确认与上次相同，`from_record` 指向被沿用的记录，该记录必须是同一动作、同一 `equipment`、同一 `variant.angle`（同品牌不同机器，如 HOIST 平推与上斜，按角度区分），日期不晚于本条，且设置值完全相同。
- 未报告时省略，不从历史自动沿用。旧记录不回填。

## report 输出

`report` 只读，不是新账本格式。`windows` 为含结束日的滚动 7/14 天；`trends` 仅列最近 14 天出现过的基础键，各含最近三次候选 `history`（新到旧，可早于窗口）。`--date` 控制截止日，默认本机今天，不自动回拨到最后训练日；晚于截止日的记录不计入。

每肌群输出工作组条数、训练轮数、左右侧组数、完整/不完整轮次、缺失 round 条数与训练频率；同一组可属于词典中的多个主要肌群，不能将各肌群组数直接相加。没有记录的日期照旧列为休息日期，不推断恢复状态。

`comparability` 为 `comparable` / `limited` / `new_baseline`，`reasons` 解释门槛，`blocking_reasons` 是其中阻止数字判断的部分（休息改变、RIR 未知或改变、力竭方式改变、上次质量下降、次数或负重缺失）。`limited` 且没有阻断原因时仍输出数字结果，其余 reasons 作为注意事项。

趋势只使用 `straight` / `top` 组：组结构和负重相同时输出 `reps_delta`；否则比较每侧“最重负荷的第一组”，输出 `top_load_delta` 和 `top_set_reps_delta`。`assessment` 可为 `reps_*`、`top_set_reps_*`、`load_increased`、`load_decreased`。负重下降且用户未明确说明质量保持，或有备注时次数下降，统一输出 `review_context`，以免把未结构化记录的质量优化当成退步。两次之间存在停训期时为 `new_baseline`（原因 `crosses_layoff`），停训前的负重和次数差值放在 `pre_layoff_reference`，仅作参考；没有停训、只是该动作相隔超过 21 天时加 `long_gap`。都会输出 `days_since_previous`。

趋势另含：`progression_target`（最新一次的推进目标）；`target_lever_moved`（可比且无阻断原因时，该变量的数字是否提高：`reps` 看次数，`load` 看最重组重量，`sets` 看普通组数；`density` 及不可比时为 `null`）；`target_effective`（按用户“质量 > 数量 > 重量”：数字提高且本次质量为保持或提高才为 `true`，质量下降为 `false`，质量未知或数字无法判断为 `null`）；`next_target`（下次建议，项目启发式，依次判断）：`restore_quality`（本次报告质量下降）、`rebuild_baseline`（跨停训或复训期内）、`confirm_baseline`（因质量、设置、执行标准或模板变化建立的新基线，先复现）、`review_context`（比较被阻断，如休息改变，复现不推进）、`add_load`（连续两次最重组达到 12 次且两次质量都确认保持或提高，加最小一档）、`confirm_quality`（达到 12 次但质量未确认，先确认）、`add_rep`（同重量最重组多 1 次）。`next_target` 是计划，不写入日志。

顶层 `layoffs` 列出停训期：日备注中 `training_status: "paused"` 的 `date`～`applies_through` 区间，与相邻训练日相隔超过 21 天的空档合并而成（`sources` 为 `day_note` / `training_gap`）。`return_phase` 描述最近一次停训后的复训：首次训练日、已练次数、距停训结束天数，`active` 表示仍在停训结束后 14 天内。`best_reps_by_load` 每项的 `before_last_layoff` 标明是否发生在最近一次停训前。`best_reps_by_load` 列出该可比键下每个负荷、每侧单组最多次数，仅作描述，不是 PR 判定。周训练量中 `primary_set_entries` 单列普通组和顶组；降重、递减、rest-pause、myo 组仍计入 `working_set_entries`。`assessment` 的次数增减只表示数字表现，不等于 PR、肌肉增长或处方；原始备注永远随候选历史返回供 Agent 阅读。详细决策与来源见 `knowledge/training-analysis.md`。
