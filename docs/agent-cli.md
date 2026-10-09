# train-logbook Agent CLI 参考

本文档供 Agent 执行仓库任务时使用，不是面向最终用户的操作指南。行为约束以根目录 `AGENTS.md` 为准；本文只集中保存脚本接口和调用示例。

## macOS 入口

使用 `./scripts/train-logbook.sh <command> ...`，由它调用 `scripts/train_logbook.py`。运行环境为 macOS、Bash 和 Python 3 标准库；可用 `PYTHON_BIN` 指定 Python 3 可执行文件。

命令：

- `resolve`：对齐自然语言动作名称
- `add`：追加一条训练动作记录
- `resequence`：按记录 ID 修正动作顺序
- `recent`：查看最近记录
- `stats`：按可比键汇总训练数据
- `report`：只读的滚动 7/14 天肌群训练量和最近候选表现报告
- `list`：列出动作词典
- `validate`：校验词典和全部训练日志

修改实现后，运行 `bash tests/smoke.sh` 和 `python3 -m unittest discover -s tests -p 'test_*.py'`。

## 调用示例

```bash
./scripts/train-logbook.sh resolve --exercise "力健上斜推胸机" --json

./scripts/train-logbook.sh add \
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

./scripts/train-logbook.sh recent --limit 10 --json
./scripts/train-logbook.sh stats --exercise "器械推胸" --json
./scripts/train-logbook.sh list --json
./scripts/train-logbook.sh validate --json

./scripts/train-logbook.sh resequence \
  --id "20260827-120000-abcdef" \
  --sequence 2
```

## 组格式

- `12x40@2`：40 kg，12 次，RIR 2
- `12xbw`：自重 12 次
- `30s`：30 秒计时组
- `R:8x20` / `L:8x20`：右侧 / 左侧；脚本按同侧出现顺序保存 `round`
- 使用 `--warmup-count 2`，将最前两组标记为热身组

未报告 RIR 时，组格式不加 `@`；脚本读取 `profile/training-preferences.json` 已确认的默认偏好，只补工作组并保存 `rir_source=profile_default` 与偏好快照。用户当次明确报告 RIR 才使用 `@RIR`，保存为 `reported`。热身组不补默认值；没有已确认默认偏好时保持未知。不要把 Agent 自行补入的 `@0` 冒充当次报告。

## 常用参数

| 含义 | 参数 |
|---|---|
| 用户原始叫法 | `--exercise` |
| 已确认的规范动作 | `--resolve-as` |
| 训练组 | `--sets` |
| 实际训练日期 | `--date` |
| 实际训练时刻（可选，带时区） | `--performed-at` |
| 重量口径 | `--weight-basis` |
| 动作顺序 | `--sequence` |
| 具体器械 | `--equipment` |
| 角度 | `--angle` |
| 姿势 | `--posture` |
| 单双侧 | `--laterality` |
| 握法 | `--grip` |
| 热身组数 | `--warmup-count` |
| 训练日类型 | `--day-type` |
| 类型依据 | `--day-type-basis` |
| 备注 | `--notes` |
| 标签 | `--tags` |
| 实际训练模板（可选） | `--session-template` |
| 已确认执行标准版本（可选） | `--execution-standard` |
| 用户报告的质量变化（可选） | `--quality-change` |
| 实际统一组间休息秒数（可选） | `--rest-sec` |
| JSON 输出 | `--json` |

`--day-type` 允许 `standard`、`overload`、`deload`。训练日类型的判定规则与 `overload_lever` 记录方式见 `knowledge/training-day-types.md`。

## 使用约束

- `resolve` 只有返回 `resolved` 且语义合理时才允许继续写入；`ambiguous` 或 `unknown` 必须先确认。
- 品牌、机型或临时描述不应污染动作别名；含义已确认时用 `--resolve-as` 保留原话并归一。
- `add` 必须显式保存真实训练顺序，遗漏或重复时在写入前拒绝。多条记录全部写入后运行一次 `validate` 即可。
- `resequence` 会重写包含目标记录的 JSONL 文件，只用于用户明确要求的最小纠错。
- `stats` 默认按 `exercise_id + variant + equipment + sequence + weight_basis` 分组，跨组结果不能直接判定 PR 或退步。
- 不要把训练计划写入 `data/workouts/`，也不要自行提交 Git；是否提交或推送由用户明确授权。

## 训练分析

```bash
./scripts/train-logbook.sh report --date 2026-09-05 --json
# 默认以今天为截止日，完整账本只读分析
./scripts/train-logbook.sh report --json
```

`report` 支持截止日期、项目根目录和 JSON 输出，分析所有肌群。它不使用 `--exercise` 筛选，避免误把单动作组数当成整个肌群周剂量。默认两个窗口均包含截止日；候选趋势详见 `docs/data-model.md`。非 JSON 模式也输出缩进 JSON，供 Agent 读取后向用户用自然语言总结。

在现有 `add` 调用上，可选择增加 `--session-template "推日-A" --execution-standard "座椅4-全幅-v2" --quality-change maintained --rest-sec 180`。只保存已确认的实际信息，不将处方填成完成事实。质量状态完整枚举见数据模型。

Agent 读取报告后仍须检查原始 `notes`、当前 profile 与相关 `data/day-notes/`，按照 `knowledge/training-analysis.md` 做判断。报告既不从备注关键词自动判质量，也不重新询问已确认的默认 RIR；写入工作组时由脚本应用当前偏好，组格式只填写用户明确报告的 RIR。原 `stats` 接口和所有记录原则保持不变。

## 分析回归测试

```bash
bash tests/smoke.sh
python3 -m unittest discover -s tests -p 'test_*.py'
```

测试只在临时目录写入模拟记录，不改真实账本；同时验证 shell 入口与直接调用 Python 的结果一致。

## 版本 2 写入补充

新记录自动保存 `training_date`、`recorded_at`；未知实际时刻的 `performed_at` 为 `null`。只在用户明确报告时传 `--performed-at '2026-10-07T19:30:00+08:00'`，其日期必须与 `--date` 一致。不传 `--date` 时，优先采用显式训练时刻的日期，否则采用本机今天；Agent 应根据用户时区显式传实际日期。

`--weight-basis` 接受 `per_implement`（单只）、`per_side`（每侧）、`total`（合计）、`machine_display`（器械标示）和默认 `unknown`。例如用户明确说「双手各持 20kg 哑铃」时可传 `--sets '8x20' --weight-basis per_implement --laterality bilateral`；数值保持原报的 20，不自动翻倍。重量口径有歧义时仍须按原规则询问。

`--resolve-as` 只确定基本动作身份，角度、姿势、单双侧和握法均从 `--exercise` 原话提取，显式变体参数优先覆盖。热身与工作组分别计算同侧轮次。

`tests/test_train_logbook.py` 在临时目录验证拒绝写入不改文件、旧版兼容、日期/顺序、重量口径、默认来源、热身轮次、纠错和 shell/Python 入口一致性。
