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
- `report`：只读的滚动 7/14 天肌群训练量和最近候选表现报告
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
| 实际训练模板（可选） | `-SessionTemplate` | `--session-template` |
| 已确认执行标准版本（可选） | `-ExecutionStandard` | `--execution-standard` |
| 用户报告的质量变化（可选） | `-QualityChange` | `--quality-change` |
| 实际统一组间休息秒数（可选） | `-RestSec` | `--rest-sec` |
| JSON 输出 | `-Json` | `--json` |

`DayType` 允许 `standard`、`overload`、`deload`。训练日类型的判定规则与 `overload_lever` 记录方式见 `knowledge/training-day-types.md`。

## 使用约束

- `resolve` 只有返回 `resolved` 且语义合理时才允许继续写入；`ambiguous` 或 `unknown` 必须先确认。
- 品牌、机型或临时描述不应污染动作别名；含义已确认时用 `ResolveAs` 保留原话并归一。
- `add` 必须显式保存真实训练顺序。多条记录全部写入后运行一次 `validate` 即可。
- `resequence` 会重写包含目标记录的 JSONL 文件，只用于用户明确要求的最小纠错。
- `stats` 默认按 `exercise_id + variant + equipment + sequence` 分组，跨组结果不能直接判定 PR 或退步。
- 不要把训练计划写入 `data/workouts/`，也不要自行提交 Git；是否提交或推送由用户明确授权。

## 训练分析

```bash
./scripts/fitness.sh report --date 2026-09-05 --json
# 默认以今天为截止日，完整账本只读分析
./scripts/fitness.sh report --json
```

```powershell
& .\scripts\fitness.ps1 report -Date "2026-09-05" -Json
```

`report` 支持截止日期、项目根目录和 JSON 输出，分析所有肌群。它不使用 `Exercise` 筛选，避免误把单动作组数当成整个肌群周剂量。默认两个窗口均包含截止日；候选趋势详见 `docs/data-model.md`。两端非 JSON 模式也输出缩进 JSON，供 Agent 读取后向用户用自然语言总结。

在现有 `add` 调用上，可选择增加 `--session-template "推日-A" --execution-standard "座椅4-全幅-v2" --quality-change maintained --rest-sec 180`；PowerShell 等价为 `-SessionTemplate "推日-A" -ExecutionStandard "座椅4-全幅-v2" -QualityChange maintained -RestSec 180`。只保存已确认的实际信息，不将处方填成完成事实。质量状态完整枚举见数据模型。

Agent 读取报告后仍须检查原始 `notes`、当前 profile 与相关 `data/day-notes/`，按照 `knowledge/training-analysis.md` 做判断。报告既不从备注关键词自动判质量，也不重新询问已确认的默认 RIR；写入工作组时继续按当前偏好准备组格式。原 `stats` 接口和所有记录原则保持不变。

## 分析回归测试

```bash
bash tests/smoke.sh
python3 -m unittest discover -s tests -p test_analysis.py
# 已有 PowerShell 时启用两端 JSON 和记录兼容性比较
PWSH=/path/to/pwsh python3 -m unittest discover -s tests -p test_analysis.py
pwsh -NoProfile -File tests/smoke.ps1
```

测试只在临时目录写入模拟记录，不改真实账本。未设置 `PWSH` 时，跨平台对比用例明确标为跳过；Python 测试仍执行。
