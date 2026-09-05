# Training Analysis Implementation Plan

**Goal:** 在不改变动作记录原则的前提下，增加执行上下文、保守的可比性分析和滚动训练量报告。

**Architecture:** 保留所有现有命令行为与历史 schema；add 仅接受可选 analysis_context。report 只读日志，按原有动作/变体/器械/实际 sequence 建立候选，再检查执行标准、前序训练与努力程度，不自动改写计划、轮换、偏好、日类型或 PR。Python 与 PowerShell 各自原生实现，无新增运行依赖。

**Tech Stack:** Python 标准库、PowerShell、JSONL、临时目录中的跨平台回归测试。

## 已确认的约束

- 同步远程后基线为 0da4923；保留远程新增的质量优先策略与全部事实。
- 不修改 data/、catalog/、profile/、AGENTS.md 的记录原则，不追溯填充未知元数据。
- 原话、动作消歧、左右分组、实际顺序、默认力竭、无日志休息日、质量改善降重为大进步全部保留。
- 不自动提交或推送本轮优化。

## 实现步骤

1. 增加 tests/test_analysis.py：临时账本覆盖单侧轮次、自重/热身、日期窗口、旧日志兼容、跨器械/顺序隔离、质量改善降重、前序工作量变化、未知信息不判 PR；可选比较两平台 JSON。
2. 修改 scripts/fitness.py 与 scripts/fitness.ps1；新增原生 analysis.py / analysis.ps1 模块。增加可选执行标准、模板、明确质量变化、休息秒数；旧 add 输出保持不变。validate 检查新增元数据。
3. report 输出滚动 7/14 天直接组数、每侧数据、频率、休息日期和最近三次候选历史；已知不一致建立新基线，缺失上下文仅提供有限比较；负重吨位只描述外部负荷。
4. 更新 docs/data-model.md、docs/agent-cli.md、README.md 与带来源的 knowledge/training-analysis.md；区分教练经验、科学原则与用户事实。将旧计划保留为历史，当前流程指向最新偏好。
5. 运行原有两个 smoke 脚本、新分析回归与两平台一致性检查；真实账本只读 validate/report；用同步后的 Git 基线验证数据、词典、偏好及记录合同未变。

## 完成与验证

- 已完成原生 Python/PowerShell 分析模块、可选上下文参数、校验、报告及文档；既有 stats 接口未更改。
- `tests/smoke.sh` 与 `tests/smoke.ps1` 均通过，包含新增 report 检查。
- 8 项分析回归通过，覆盖可选字段不改变原记录语义、左右轮次、自重/热身、质量降重、执行/休息/前序门槛、无数据窗口和两端 JSON 一致性；包含跨时区日期边界及整数/浮点等值条件。
- PowerShell 使用临时目录中的微软官方 7.6.5 macOS ARM64 运行时测试，未安装系统软件；未在 Windows PowerShell 5.1 主机实测。
- 真实账本的 2026-08-24 与 2026-09-05 报告已核对两端一致；25 个动作、78 条训练记录校验通过。
- 相对同步后基线 `0da4923`，`data/`、`catalog/`、`profile/`、`AGENTS.md` 无任何改动。未提交或推送本轮代码修改。
