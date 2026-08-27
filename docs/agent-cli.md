# Fitness Ledger Agent CLI Reference

本文档供 Agent 执行仓库任务时使用，不是面向最终用户的操作指南。行为约束以根目录 `AGENTS.md` 为准；本文只集中保存脚本接口和调用示例。

## 平台入口

- Windows：`& .\scripts\fitness.ps1 <command> ...`
- macOS / Linux：`./scripts/fitness.sh <command> ...`
- `scripts/fitness.py` 是跨平台实现，由 `fitness.sh` 调用。

Windows 与 macOS / Linux 实现共享动作词典和数据格式，命令保持一致：

- `resolve`：对齐自然语言动作名称
- `add`：追加一条训练动作记录
- `resequence`：按记录 ID 修正动作顺序
- `recent`：查看最近记录
- `stats`：按可比键汇总训练数据
- `list`：列出动作词典
- `validate`：校验词典和全部训练日志

修改任一实现后，必须同步另一实现，并运行 `tests/smoke.ps1` 与 `tests/smoke.sh`。

## Windows 示例

```powershell
# 解析动作；Agent 应优先读取 JSON 状态与候选
& .\scripts\fitness.ps1 resolve -Exercise "力健上斜推胸机" -Json

# 追加训练记录；reported_name 保留 -Exercise 的原话
& .\scripts\fitness.ps1 add `
  -Date "2026-08-27" `
  -Sequence 1 `
  -Exercise "力健上斜推胸机" `
  -ResolveAs "器械推胸" `
  -Sets "12x40@2","10x45@1","10x45@1" `
  -Equipment "Life Fitness Insignia" `
  -Angle incline `
  -Posture seated `
  -Laterality bilateral `
  -DayType standard

# 查询与校验
& .\scripts\fitness.ps1 recent -Limit 10 -Json
& .\scripts\fitness.ps1 stats -Exercise "器械推胸" -Json
& .\scripts\fitness.ps1 list -Json
& .\scripts\fitness.ps1 validate -Json

# 仅在用户明确纠正顺序并已定位记录 ID 后使用
& .\scripts\fitness.ps1 resequence -Id "20260827-120000-abcdef" -Sequence 2
```

## macOS / Linux 示例

```bash
./scripts/fitness.sh resolve --exercise "力健上斜推胸机" --json

./scripts/fitness.sh add \
  --date "2026-08-27" \
  --sequence 1 \
  --exercise "力健上斜推胸机" \
  --resolve-as "器械推胸" \
  --sets "12x40@2" "10x45@1" "10x45@1" \
  --equipment "Life Fitness Insignia" \
  --angle incline \
  --posture seated \
  --laterality bilateral \
  --day-type standard

./scripts/fitness.sh recent --limit 10 --json
./scripts/fitness.sh stats --exercise "器械推胸" --json
./scripts/fitness.sh list --json
./scripts/fitness.sh validate --json

./scripts/fitness.sh resequence \
  --id "20260827-120000-abcdef" \
  --sequence 2
```

## 组格式

- `12x40@2`：40 kg，12 次，RIR 2
- `12xbw`：自重 12 次
- `30s`：30 秒计时组
- `R:8x20` / `L:8x20`：右侧 / 左侧；脚本按同侧出现顺序保存 `round`
- Windows 使用 `-WarmupCount 2`、macOS / Linux 使用 `--warmup-count 2`，将最前两组标记为热身组

未报告 RIR 时，按 `profile/training-preferences.json` 的当前记录偏好处理。不要在脚本文档中硬编码可能变化的用户偏好。

## 常用参数

| 含义 | Windows | macOS / Linux |
|---|---|---|
| 用户原始叫法 | `-Exercise` | `--exercise` |
| 已确认的规范动作 | `-ResolveAs` | `--resolve-as` |
| 训练组 | `-Sets` | `--sets` |
| 日期 | `-Date` | `--date` |
| 动作顺序 | `-Sequence` | `--sequence` |
| 具体器械 | `-Equipment` | `--equipment` |
| 角度 | `-Angle` | `--angle` |
| 姿势 | `-Posture` | `--posture` |
| 单双侧 | `-Laterality` | `--laterality` |
| 握法 | `-Grip` | `--grip` |
| 热身组数 | `-WarmupCount` | `--warmup-count` |
| 训练日类型 | `-DayType` | `--day-type` |
| 类型依据 | `-DayTypeBasis` | `--day-type-basis` |
| 备注 | `-Notes` | `--notes` |
| 标签 | `-Tags` | `--tags` |
| JSON 输出 | `-Json` | `--json` |

`DayType` 允许 `standard`、`overload`、`deload`。训练日类型的判定规则与 `overload_lever` 记录方式见 `knowledge/training-day-types.md`。

## 使用约束

- `resolve` 只有返回 `resolved` 且语义合理时才允许继续写入；`ambiguous` 或 `unknown` 必须先确认。
- 品牌、机型或临时描述不应污染动作别名；含义已确认时用 `ResolveAs` 保留原话并归一。
- `add` 必须显式保存真实训练顺序。多条记录全部写入后运行一次 `validate` 即可。
- `resequence` 会重写包含目标记录的 JSONL 文件，只用于用户明确要求的最小纠错。
- `stats` 默认按 `exercise_id + variant + equipment + sequence` 分组，跨组结果不能直接判定 PR 或退步。
- 不要把训练计划写入 `data/workouts/`，也不要自行提交 Git；是否提交或推送由用户明确授权。
