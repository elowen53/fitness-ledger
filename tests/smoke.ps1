$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Script = Join-Path $ProjectRoot "scripts\fitness.ps1"
$TempRoot = Join-Path ([IO.Path]::GetTempPath()) ("fitness-ledger-test-" + [guid]::NewGuid().ToString("N"))

try {
    New-Item -ItemType Directory -Path (Join-Path $TempRoot "catalog") -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $TempRoot "data\workouts") -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "catalog\exercises.json") -Destination (Join-Path $TempRoot "catalog\exercises.json")

    $resolved = & $Script resolve -Exercise "上斜器械推胸" -ProjectRoot $TempRoot -Json | ConvertFrom-Json
    if ($resolved.status -ne "resolved") { throw "上斜器械推胸未解析" }
    if ($resolved.exercise.id -ne "machine_chest_press") { throw "动作 ID 错误" }
    if ($resolved.variant.angle -ne "incline") { throw "角度解析错误" }

    $branded = & $Script resolve -Exercise "力健上斜推胸机" -ProjectRoot $TempRoot -Json | ConvertFrom-Json
    if ($branded.status -ne "resolved" -or $branded.exercise.id -ne "machine_chest_press") { throw "带品牌动作名未解析" }

    $nonstandard = & $Script resolve -Exercise "自创飞盘动作" -ProjectRoot $TempRoot -Json 2>$null | ConvertFrom-Json
    if ($nonstandard.status -ne "unknown") { throw "未定义的非传统动作应要求用户确认" }

    & $Script add -Exercise "上斜器械推胸" -Sets "12x40@2", "10x45@1" -Equipment "test machine" -Date "2026-08-05" -Sequence 1 -ProjectRoot $TempRoot | Out-Null
    & $Script add -Exercise "坐姿哑铃侧平举" -Sets "15x5,13x5" -Date "2026-08-05" -Sequence 2 -ProjectRoot $TempRoot | Out-Null
    & $Script add -Exercise "Y举" -Sets "R:8x20,L:8x20,R:7x20,L:8x20" -Laterality "unilateral" -Date "2026-08-05" -Sequence 3 -ProjectRoot $TempRoot | Out-Null
    & $Script add -Exercise "豪斯特推胸" -ResolveAs "器械推胸" -Sets "9x80" -Equipment "HOIST" -Laterality "bilateral" -Date "2026-08-05" -Sequence 4 -ProjectRoot $TempRoot | Out-Null
    & $Script add -Exercise "临时编号推胸" -ResolveAs "器械推胸" -Sets "10x50" -Equipment "alignment test machine" -Laterality "bilateral" -Date "2026-08-06" -Sequence 1 -ProjectRoot $TempRoot | Out-Null
    & $Script add -Exercise "上斜器械推胸" -Sets "10x50" -Equipment "test machine" -Date "2026-08-06" -Sequence 2 -ProjectRoot $TempRoot | Out-Null

    $historyResolved = & $Script resolve -Exercise "临时编号推胸" -ProjectRoot $TempRoot -Json | ConvertFrom-Json
    if ($historyResolved.status -ne "resolved" -or $historyResolved.exercise.id -ne "machine_chest_press") { throw "历史叫法未对齐到原动作 ID" }
    if ($historyResolved.exercise.matched_source -ne "history") { throw "历史叫法未标记 history 来源" }

    $validation = & $Script validate -ProjectRoot $TempRoot -Json | ConvertFrom-Json
    if ($validation.status -ne "ok" -or $validation.workout_records -ne 6) { throw "记录校验失败" }

    $unilateralLog = Get-Content -LiteralPath (Join-Path $TempRoot "data\workouts\2026\08\2026-08-05.jsonl") -Encoding UTF8 | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.exercise_id -eq "user_y_raise" } | Select-Object -First 1
    if ($unilateralLog.sets[0].side -ne "right" -or $unilateralLog.sets[2].round -ne 2) { throw "单侧与轮次解析错误" }
    $expectedLog = Join-Path $TempRoot "data\workouts\2026\08\2026-08-05.jsonl"
    if (-not (Test-Path -LiteralPath $expectedLog)) { throw "日志未写入按年月分层的路径" }

    $stats = & $Script stats -Exercise "器械推胸" -ProjectRoot $TempRoot -Json | ConvertFrom-Json
    $testMachineStats = @($stats | Where-Object { $_.equipment -eq "machine/test machine" })
    if ($testMachineStats.Count -ne 2) { throw "不同顺序角色未分开统计" }
    $sequenceOne = @($testMachineStats | Where-Object { $_.sequence -eq 1 })
    $sequenceTwo = @($testMachineStats | Where-Object { $_.sequence -eq 2 })
    if ($sequenceOne.Count -ne 1 -or $sequenceOne[0].volume_kg -ne 930) { throw "顺序1训练量计算错误" }
    if ($sequenceTwo.Count -ne 1 -or $sequenceTwo[0].volume_kg -ne 500) { throw "顺序2训练量计算错误" }

    $report = & $Script report -Date "2026-08-06" -ProjectRoot $TempRoot -Json | ConvertFrom-Json
    if ($report.windows[0].working_set_entries -ne 11) { throw "report 工作组条数错误" }
    if ($report.last_workout_date -ne "2026-08-06") { throw "report 截止日期错误" }
    $sideRounds = @($report.windows[0].muscles | Where-Object { $_.muscle -eq "side_delts" })
    if ($sideRounds[0].working_rounds -ne 4) { throw "report 单侧轮次错误" }
    $afterReport = & $Script validate -ProjectRoot $TempRoot -Json | ConvertFrom-Json
    if ($afterReport.workout_records -ne 6) { throw "report 不应写训练事实" }

    Write-Host "smoke tests passed"
} finally {
    if (Test-Path -LiteralPath $TempRoot) {
        Remove-Item -LiteralPath $TempRoot -Recurse -Force
    }
}
