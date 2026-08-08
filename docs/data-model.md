# 数据模型

每条 JSONL 记录代表一次训练中的一个动作，包含若干组。`schema_version` 用于将来迁移。

```json
{
  "schema_version": 1,
  "id": "20260805-193012-a1b2c3",
  "performed_at": "2026-08-05T19:30:12.0000000+08:00",
  "day_type": "standard",
  "day_type_basis": "default",
  "sequence": 1,
  "exercise_id": "machine_chest_press",
  "reported_name": "力健上斜推胸机",
  "variant": {
    "angle": "incline",
    "posture": null,
    "laterality": null,
    "grip": null
  },
  "equipment": {
    "type": "machine",
    "name": "Life Fitness Insignia"
  },
  "sets": [
    {"reps": 12, "weight_kg": 40, "rir": 2, "duration_sec": null, "bodyweight": false, "warmup": false, "side": null, "round": null}
  ],
  "notes": "座椅 4 档",
  "tags": ["push"]
}
```

设计规则：

- `reported_name` 永远保留原始叫法，便于发现误归一化。
- `sequence` 是用户实际训练顺序，从 1 开始；分析和展示训练日时优先按它排序，不能用落盘时间代替。
- 未知值用 `null`，不使用空字符串或臆测值。
- kg 是唯一外部负重单位；自重动作使用 `bodyweight=true`，不把体重伪装成外部负重。
- 默认训练量只计算非热身且同时有 `reps`、`weight_kg` 的组。
- 单侧动作的 `side` 使用 `left | right`，`round` 表示该侧的第几轮。双侧动作两者均为 `null`。
- 会影响动作可比性的握法保存在 `variant.grip`。例如窄距对握为 `narrow_neutral`，宽距为 `wide`。
- `equipment.type` 保存 `machine / cable / barbell / dumbbell / bodyweight` 等可比较的器械大类。
- `equipment.name` 不做全局枚举，因为同一器械在不同健身房可能有不同标识。

## 动作身份与长期对齐

- `exercise_id` 是同一基本动作跨日期、跨叫法保持不变的唯一身份；`reported_name` 是用户当次原话，不承担唯一性。
- 新记录写入前，解析器同时匹配词典规范名/别名和历史 `reported_name`。命中历史叫法时仍返回原 `exercise_id`，但不会因此自动污染全局别名。
- 名称不同但存在合理的同动作候选时，需要用户确认对齐；确认无法归入已有动作后才创建新 ID。
- 默认趋势键为 `exercise_id + variant.angle + variant.posture + variant.laterality + variant.grip + equipment.type + equipment.name + sequence`。其中 `sequence` 表示本次训练内的顺序角色；不同趋势键不直接比较重量或 PR。
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
