[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("resolve", "add", "resequence", "recent", "stats", "report", "validate", "list")]
    [string]$Command,

    [string]$Exercise,
    [string]$Id,
    [string]$ResolveAs,
    [string[]]$Sets,
    [string]$Date,
    [string]$PerformedAt,
    [ValidateSet('unknown','per_implement','per_side','total','machine_display')]
    [string]$WeightBasis = 'unknown',
    [string]$Equipment,
    [string]$Angle,
    [string]$Posture,
    [string]$Laterality,
    [string]$Grip,
    [string]$Notes,
    [string]$SessionTemplate,
    [string]$ExecutionStandard,
    [ValidateSet("maintained", "improved", "improved_with_load_reduction", "degraded")]
    [string]$QualityChange,
    [Nullable[double]]$RestSec,
    [string[]]$Tags,
    [ValidateSet("standard", "overload", "deload")]
    [string]$DayType = "standard",
    [string]$DayTypeBasis = "default",
    [int]$Sequence = 0,
    [int]$WarmupCount = 0,
    [int]$Limit = 10,
    [switch]$Json,
    [string]$ProjectRoot
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "analysis.ps1")
. (Join-Path $PSScriptRoot "validation.ps1")

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
$CatalogPath = Join-Path $ProjectRoot "catalog\exercises.json"
$WorkoutRoot = Join-Path $ProjectRoot "data\workouts"

$VariantWords = @(
    @{ Field = "angle"; Value = "incline"; Pattern = "坐姿仰卧|上斜|上倾|incline|inclined" },
    @{ Field = "angle"; Value = "decline"; Pattern = "下斜|下倾|decline|declined" },
    @{ Field = "angle"; Value = "flat"; Pattern = "平板|水平|flat" },
    @{ Field = "angle"; Value = "vertical"; Pattern = "垂直|vertical" },
    @{ Field = "posture"; Value = "seated"; Pattern = "坐姿|坐式|seated" },
    @{ Field = "posture"; Value = "standing"; Pattern = "站姿|站式|standing" },
    @{ Field = "posture"; Value = "lying"; Pattern = "仰卧|俯卧|lying" },
    @{ Field = "posture"; Value = "kneeling"; Pattern = "跪姿|kneeling" },
    @{ Field = "laterality"; Value = "unilateral"; Pattern = "单侧|单臂|单腿|unilateral|single[- ]arm|single[- ]leg" },
    @{ Field = "laterality"; Value = "alternating"; Pattern = "交替|alternating" },
    @{ Field = "laterality"; Value = "bilateral"; Pattern = "双侧|双臂|双腿|bilateral" },
    @{ Field = "grip"; Value = "narrow_neutral"; Pattern = "窄距对握|窄握对握|窄距中立握|narrow neutral" },
    @{ Field = "grip"; Value = "wide"; Pattern = "宽距|宽握|wide grip" },
    @{ Field = "grip"; Value = "narrow"; Pattern = "窄距|窄握|narrow grip" },
    @{ Field = "grip"; Value = "neutral"; Pattern = "对握|中立握|neutral grip" }
)

function Read-Catalog {
    if (-not (Test-Path -LiteralPath $CatalogPath)) {
        throw "动作词典不存在: $CatalogPath"
    }
    return Get-Content -LiteralPath $CatalogPath -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Normalize-Name([string]$Name) {
    if ($null -eq $Name) { return "" }
    return ($Name.ToLowerInvariant() -replace "[\s\-_—–·,，。()（）/\\]+", "")
}

function Get-Variant([string]$Name) {
    $result = [ordered]@{ angle = $null; posture = $null; laterality = $null; grip = $null }
    foreach ($word in $VariantWords) {
        if ($null -eq $result[$word.Field] -and $Name -match $word.Pattern) {
            $result[$word.Field] = $word.Value
        }
    }
    return [pscustomobject]$result
}

function Get-EquipmentType([string]$Name, [string]$CatalogType) {
    if ($Name -match "哑铃|dumbbell") { return "dumbbell" }
    if ($Name -match "杠铃|barbell") { return "barbell" }
    if ($Name -match "绳索|钢线|龙门架|拉力器|cable") { return "cable" }
    if ($Name -match "豪斯特|hoist") { return "machine" }
    if ($Name -match "器械|机器|推胸机|腿举机|machine") { return "machine" }
    if ($Name -match "自重|bodyweight") { return "bodyweight" }
    if ($CatalogType -in @("machine", "barbell", "dumbbell", "cable")) { return $CatalogType }
    return $null
}

function Remove-VariantWords([string]$Name) {
    $result = $Name
    foreach ($word in $VariantWords) {
        $result = $result -replace $word.Pattern, ""
    }
    return $result
}

function Resolve-Exercise([string]$Name) {
    if ([string]::IsNullOrWhiteSpace($Name)) { throw "需要 -Exercise。" }
    $catalog = Read-Catalog
    $normalized = Normalize-Name $Name
    $baseNormalized = Normalize-Name (Remove-VariantWords $Name)
    $candidates = @()
    $historicalNames = @{}

    foreach ($record in @(Read-WorkoutRecords)) {
        $historyId = [string]$record.exercise_id
        $historyName = [string]$record.reported_name
        if ([string]::IsNullOrWhiteSpace($historyId) -or [string]::IsNullOrWhiteSpace($historyName)) { continue }
        if (-not $historicalNames.ContainsKey($historyId)) { $historicalNames[$historyId] = @() }
        if ($historyName -notin @($historicalNames[$historyId])) {
            $historicalNames[$historyId] = @($historicalNames[$historyId]) + $historyName
        }
    }

    foreach ($item in $catalog.exercises) {
        $best = 0
        $matchedAlias = $null
        $matchedSource = $null
        $names = @()
        foreach ($catalogName in (@($item.canonical_name) + @($item.aliases))) {
            $names += [pscustomobject]@{ name = $catalogName; source = "catalog" }
        }
        if ($historicalNames.ContainsKey([string]$item.id)) {
            foreach ($historyName in @($historicalNames[[string]$item.id])) {
                $names += [pscustomobject]@{ name = $historyName; source = "history" }
            }
        }
        foreach ($nameEntry in $names) {
            $alias = [string]$nameEntry.name
            $a = Normalize-Name $alias
            $score = 0
            if ($normalized -eq $a) { $score = 100 }
            elseif ($baseNormalized -eq $a) { $score = 96 }
            elseif ($a.Length -ge 2 -and $normalized.Contains($a)) {
                $score = 72 + [Math]::Min(18, $a.Length * 2)
            }
            elseif ($a.Length -ge 2 -and $baseNormalized.Contains($a)) {
                $score = 68 + [Math]::Min(18, $a.Length * 2)
            }
            elseif ($normalized.Length -ge 2 -and $a.Contains($normalized)) {
                $score = 65 + [Math]::Min(15, $normalized.Length * 2)
            }
            if ($score -gt $best -or ($score -eq $best -and $nameEntry.source -eq "catalog" -and $matchedSource -eq "history")) {
                $best = $score
                $matchedAlias = $alias
                $matchedSource = $nameEntry.source
            }
        }
        if ($best -ge 65) {
            $candidates += [pscustomobject]@{
                id = $item.id
                canonical_name = $item.canonical_name
                score = $best
                matched_alias = $matchedAlias
                matched_source = $matchedSource
            }
        }
    }

    $candidates = @($candidates | Sort-Object -Property @{ Expression = "score"; Descending = $true }, @{ Expression = "id"; Descending = $false })
    $status = "unknown"
    $selected = $null
    if ($candidates.Count -gt 0) {
        $margin = if ($candidates.Count -gt 1) { $candidates[0].score - $candidates[1].score } else { 100 }
        if ($candidates[0].score -ge 75 -and $margin -ge 8) {
            $status = "resolved"
            $selected = $candidates[0]
        } else {
            $status = "ambiguous"
        }
    }

    return [pscustomobject]@{
        status = $status
        input = $Name
        exercise = $selected
        variant = Get-Variant $Name
        candidates = @($candidates | Select-Object -First 5)
    }
}

function Parse-Set([string]$Spec, [bool]$Warmup) {
    $text = $Spec.Trim().ToLowerInvariant() -replace "公斤|千克", "kg" -replace "次", ""
    $side = $null
    if ($text -match "^(?<side>右手|右|right|r|左手|左|left|l)\s*[:：]\s*(?<rest>.+)$") {
        $side = if ($Matches.side -in @("右手", "右", "right", "r")) { "right" } else { "left" }
        $text = $Matches.rest
    }
    if ($text -match "^(?<reps>\d+)\s*[x×*]\s*(?<weight>\d+(?:\.\d+)?)\s*(?:kg)?(?:\s*@\s*(?<rir>\d+(?:\.\d+)?))?$") {
        return [ordered]@{
            reps = [int]$Matches.reps
            weight_kg = [double]$Matches.weight
            rir = if ($Matches.rir) { [double]$Matches.rir } else { $null }
            duration_sec = $null
            bodyweight = $false
            warmup = $Warmup
            side = $side
            round = $null
        }
    }
    if ($text -match "^(?<reps>\d+)\s*[x×*]\s*(?:bw|bodyweight|自重)(?:\s*@\s*(?<rir>\d+(?:\.\d+)?))?$") {
        return [ordered]@{
            reps = [int]$Matches.reps
            weight_kg = $null
            rir = if ($Matches.rir) { [double]$Matches.rir } else { $null }
            duration_sec = $null
            bodyweight = $true
            warmup = $Warmup
            side = $side
            round = $null
        }
    }
    if ($text -match "^(?<seconds>\d+(?:\.\d+)?)\s*(?:s|秒)$") {
        return [ordered]@{
            reps = $null
            weight_kg = $null
            rir = $null
            duration_sec = [double]$Matches.seconds
            bodyweight = $false
            warmup = $Warmup
            side = $side
            round = $null
        }
    }
    throw "无法解析组 '$Spec'。使用 12x40@2、12xbw 或 30s。"
}

function Read-WorkoutRecords([switch]$PreserveTimestamp) {
    if (-not (Test-Path -LiteralPath $WorkoutRoot)) { return @() }
    $records = @()
    $files = Get-ChildItem -LiteralPath $WorkoutRoot -Recurse -File -Filter "*.jsonl"
    foreach ($file in $files) {
        $lineNumber = 0
        foreach ($line in (Get-Content -LiteralPath $file.FullName -Encoding UTF8)) {
            $lineNumber++
            if ([string]::IsNullOrWhiteSpace($line)) { continue }
            try {
                $record = $line | ConvertFrom-Json
                # Report windows use the recorded civil date, not the host timezone.
                # Older PowerShell versions automatically convert JSON ISO timestamps.
                foreach ($field in @('performed_at','recorded_at','training_date')) {
                    if ($line -match ('"' + $field + '"\s*:\s*"([0-9T:Z.+-]+)"')) { $record.$field = $Matches[1] }
                }
                $records += $record
            } catch {
                throw "无效 JSONL: $($file.FullName):$lineNumber"
            }
        }
    }
    return $records
}

function Write-OutputObject($Object) {
    if ($Json) {
        ConvertTo-Json -InputObject $Object -Depth 12
    } else {
        $Object
    }
}

function Assert-VariantAllowed($CatalogItem, [string]$Field, [string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return }
    $allowed = @($CatalogItem.supported_variants.$Field)
    if ($Value -notin $allowed) {
        throw "动作 $($CatalogItem.id) 不支持 $Field=$Value；允许值: $($allowed -join ', ')"
    }
}

$lockStream = $null
$lockPath = Join-Path $ProjectRoot '.fitness-write.lock'
if ($Command -in @('add','resequence')) {
    try { $lockStream = [IO.File]::Open($lockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None) }
    catch { throw '账本正在写入，或存在遗留 .fitness-write.lock；确认没有写入进程后重试。' }
}
try {
switch ($Command) {
    "resolve" {
        $result = Resolve-Exercise $Exercise
        if ($Json) { Write-OutputObject $result; break }
        Write-Host "状态: $($result.status)"
        if ($result.exercise) {
            Write-Host "动作: $($result.exercise.canonical_name) [$($result.exercise.id)]"
            Write-Host "命中: $($result.exercise.matched_alias)；来源: $($result.exercise.matched_source)；置信分: $($result.exercise.score)"
        }
        Write-Host "变体: angle=$($result.variant.angle), posture=$($result.variant.posture), laterality=$($result.variant.laterality)"
        if ($result.status -ne "resolved") {
            $result.candidates | Format-Table id, canonical_name, score, matched_alias, matched_source -AutoSize
            exit 2
        }
        break
    }

    "report" {
        $asOf = if ($Date) { $Date } else { [datetime]::Now.ToString('yyyy-MM-dd') }
        $report = Build-TrainingReport @(Read-WorkoutRecords -PreserveTimestamp) (Read-Catalog) $asOf
        ConvertTo-Json -InputObject $report -Depth 30 -Compress:$Json
        break
    }
    "add" {
        $context = [ordered]@{}
        foreach ($pair in @(
            @('SessionTemplate', 'session_template'), @('ExecutionStandard', 'execution_standard'),
            @('QualityChange', 'quality_change'), @('RestSec', 'rest_sec'))) {
            if ($PSBoundParameters.ContainsKey($pair[0])) { $context[$pair[1]] = $PSBoundParameters[$pair[0]] }
        }
        $contextErrors = @(Get-ContextErrors $context)
        if ($contextErrors.Count -gt 0) { throw ($contextErrors -join '; ') }

        if (-not $Sets -or $Sets.Count -eq 0) { throw "需要至少一个 -Sets 值。" }
        # powershell.exe -File may pass comma-separated values as one string.
        # Accept both a real string array and comma-separated CLI input.
        $expandedSets = @()
        foreach ($setValue in $Sets) {
            $expandedSets += @($setValue -split "[,，]" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        }
        $Sets = $expandedSets
        if ($WarmupCount -lt 0 -or $WarmupCount -gt $Sets.Count) { throw "WarmupCount 必须在 0 到组数之间。" }
        $resolutionInput = if ($ResolveAs) { $ResolveAs } else { $Exercise }
        $resolution = Resolve-Exercise $resolutionInput
        if ($resolution.status -ne "resolved") {
            Write-Error "动作名称未唯一解析（$($resolution.status)）。先运行 resolve 并确认动作。"
        }
        $catalog = Read-Catalog
        $catalogItem = $catalog.exercises | Where-Object { $_.id -eq $resolution.exercise.id } | Select-Object -First 1
        $variant = Get-Variant $Exercise
        $finalAngle = if ($Angle) { $Angle } else { $variant.angle }
        $finalPosture = if ($Posture) { $Posture } else { $variant.posture }
        $finalGrip = if ($Grip) { $Grip } else { $variant.grip }
        $parsedSets = @(for ($i = 0; $i -lt $Sets.Count; $i++) { Parse-Set $Sets[$i] ($i -lt $WarmupCount) })
        $sided = @($parsedSets | Where-Object { $_.side }).Count -gt 0
        $finalLaterality = if ($Laterality) { $Laterality } elseif ($variant.laterality) { $variant.laterality } elseif ($sided) { 'unilateral' } else { 'bilateral' }
        Assert-VariantAllowed $catalogItem "angle" $finalAngle
        Assert-VariantAllowed $catalogItem "posture" $finalPosture
        Assert-VariantAllowed $catalogItem "laterality" $finalLaterality
        $now = [datetimeoffset]::Now
        $trainingDate = if ($Date) { $Date } elseif ($PerformedAt -and $PerformedAt.Length -ge 10) { $PerformedAt.Substring(0,10) } else { $now.ToString('yyyy-MM-dd') }
        if (-not (Test-LedgerDate $trainingDate)) { throw 'Date 必须是 yyyy-MM-dd。' }
        if ($PerformedAt -and (-not (Test-LedgerTimestamp $PerformedAt) -or $PerformedAt.Substring(0,10) -cne $trainingDate)) { throw 'PerformedAt 必须包含时区且与 Date 一致。' }
        if ($Sequence -lt 1) { throw '需要大于 0 的 -Sequence。' }
        $default = $null
        $profilePath = Join-Path $ProjectRoot 'profile/training-preferences.json'
        if (Test-Path -LiteralPath $profilePath) {
            $profile = Get-Content -LiteralPath $profilePath -Raw -Encoding UTF8 | ConvertFrom-Json
            $default = $profile.recording_preferences.rir_default
            if ($null -ne $default -and (-not (Test-LedgerObject $default) -or $default.status -cne 'user_confirmed' -or -not (Test-LedgerNumber $default.missing_means))) { throw '无效的已确认 RIR 默认偏好。' }
        }
        $usedDefault = $false
        $sideRounds = @{}
        foreach ($parsedSet in $parsedSets) {
            if ($parsedSet.side) {
                $key = "$($parsedSet.warmup)|$($parsedSet.side)"
                if (-not $sideRounds.ContainsKey($key)) { $sideRounds[$key] = 0 }
                $sideRounds[$key]++
                $parsedSet['round'] = $sideRounds[$key]
            }
            $parsedSet['rir_source'] = if ($null -ne $parsedSet.rir) { 'reported' } else { 'unknown' }
            if ($null -eq $parsedSet.rir -and -not $parsedSet.warmup -and $null -ne $default) {
                $parsedSet.rir = $default.missing_means
                $parsedSet.rir_source = 'profile_default'
                $usedDefault = $true
            }
        }
        $shortId = [guid]::NewGuid().ToString("N").Substring(0, 6)
        $record = [ordered]@{
            schema_version = 2
            id = $now.ToString("yyyyMMdd-HHmmss") + "-" + $shortId
            training_date = $trainingDate
            recorded_at = $now.ToString('o')
            performed_at = if ($PerformedAt) { $PerformedAt } else { $null }
            weight_basis = $WeightBasis
            day_type = $DayType
            day_type_basis = $DayTypeBasis
            sequence = if ($Sequence -gt 0) { $Sequence } else { $null }
            exercise_id = $resolution.exercise.id
            reported_name = $Exercise
            variant = [ordered]@{ angle = $finalAngle; posture = $finalPosture; laterality = $finalLaterality; grip = $finalGrip }
            equipment = [ordered]@{
                type = Get-EquipmentType $Exercise $catalogItem.equipment_type
                name = if ($Equipment) { $Equipment } else { $null }
            }
            sets = $parsedSets
            notes = if ($Notes) { $Notes } else { $null }
            tags = @($Tags | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
        }

        if ($usedDefault) { $record['rir_default'] = $default }
        if ($context.Count -gt 0) { $record['analysis_context'] = $context }
        $recordErrors = @(Get-RecordErrors (@(Read-WorkoutRecords) + @($record)) $catalog)
        if ($recordErrors.Count -gt 0) { throw ($recordErrors -join '; ') }

        $directory = Join-Path (Join-Path $WorkoutRoot $trainingDate.Substring(0,4)) $trainingDate.Substring(5,2)
        [void][IO.Directory]::CreateDirectory($directory)
        $path = Join-Path $directory ($trainingDate + ".jsonl")
        $line = $record | ConvertTo-Json -Compress -Depth 12
        [IO.File]::AppendAllText($path, $line + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
        if ($Json) { Write-OutputObject $record }
        else {
            Write-Host "已记录: $($catalogItem.canonical_name) [$($catalogItem.id)]"
            Write-Host "日期: $trainingDate；顺序: $($record.sequence)；组数: $($parsedSets.Count)；文件: $path"
            Write-Host "变体: angle=$finalAngle, posture=$finalPosture, laterality=$finalLaterality, grip=$finalGrip；器械类型: $($record.equipment.type)；器械: $Equipment"
        }
        break
    }

    "recent" {
        $catalog = Read-Catalog
        $nameMap = @{}
        foreach ($item in $catalog.exercises) { $nameMap[$item.id] = $item.canonical_name }
        $rows = Read-WorkoutRecords | Sort-Object @{Expression={Get-RecordDate $_}; Descending=$true}, @{Expression={$null -eq $_.sequence}}, sequence, id | Select-Object -First $Limit | ForEach-Object {
            [pscustomobject]@{
                date = Get-RecordDate $_
                day_type = if ($_.day_type) { $_.day_type } else { "unclassified" }
                sequence = $_.sequence
                exercise = $nameMap[$_.exercise_id]
                variant = (@($_.variant.angle, $_.variant.posture, $_.variant.laterality, $_.variant.grip) | Where-Object { $_ }) -join "/"
                equipment = (@($_.equipment.type, $_.equipment.name) | Where-Object { $_ }) -join "/"
                sets = @($_.sets).Count
                id = $_.id
            }
        }
        if ($Json) { Write-OutputObject @($rows) } else { $rows | Format-Table -AutoSize }
        break
    }

    "resequence" {
        if ([string]::IsNullOrWhiteSpace($Id)) { throw "需要 -Id。" }
        if ($Sequence -lt 1) { throw "需要大于 0 的 -Sequence。" }
        $records = @(Read-WorkoutRecords)
        $targets = @($records | Where-Object { $_.id -ceq $Id })
        if ($targets.Count -ne 1) { throw "记录 ID 不存在或重复: $Id" }
        $targets[0] | Add-Member -NotePropertyName sequence -NotePropertyValue $Sequence -Force
        $recordErrors = @(Get-RecordErrors $records (Read-Catalog))
        if ($recordErrors.Count -gt 0) { throw ($recordErrors -join '; ') }
        $found = $false
        $files = Get-ChildItem -LiteralPath $WorkoutRoot -Recurse -File -Filter "*.jsonl"
        foreach ($file in $files) {
            $updatedLines = @()
            $changed = $false
            foreach ($line in (Get-Content -LiteralPath $file.FullName -Encoding UTF8)) {
                if ([string]::IsNullOrWhiteSpace($line)) { continue }
                $record = $line | ConvertFrom-Json
                if ($record.id -ceq $Id) {
                    if ($found) { throw "记录 ID 重复: $Id" }
                    $record | Add-Member -NotePropertyName sequence -NotePropertyValue $Sequence -Force
                    $updatedLines += ($targets[0] | ConvertTo-Json -Compress -Depth 12)
                    $changed = $true
                    $found = $true
                } else {
                    $updatedLines += $line
                }
            }
            if ($changed) {
                $temporary = Join-Path $file.DirectoryName ('.resequence-' + [guid]::NewGuid().ToString('N'))
                try {
                    [IO.File]::WriteAllLines($temporary, $updatedLines, [Text.UTF8Encoding]::new($false))
                    [IO.File]::Replace($temporary, $file.FullName, [NullString]::Value)
                } finally {
                    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
                }
            }
        }
        if (-not $found) { throw "找不到记录: $Id" }
        Write-Host "已更新动作顺序: $Id -> $Sequence"
        break
    }

    "stats" {
        $records = @(Read-WorkoutRecords)
        $exerciseId = $null
        if ($Exercise) {
            $resolution = Resolve-Exercise $Exercise
            if ($resolution.status -ne "resolved") { throw "统计筛选动作未唯一解析。" }
            $exerciseId = $resolution.exercise.id
            $records = @($records | Where-Object { $_.exercise_id -eq $exerciseId })
        }
        $expanded = foreach ($record in $records) {
            $workingSets = @($record.sets | Where-Object { -not $_.warmup })
            $reps = ($workingSets | Where-Object { $null -ne $_.reps } | Measure-Object -Property reps -Sum).Sum
            $volume = 0.0
            foreach ($set in $workingSets) {
                if ($null -ne $set.reps -and $null -ne $set.weight_kg) { $volume += [double]$set.reps * [double]$set.weight_kg }
            }
            $variantKey = (@($record.variant.angle, $record.variant.posture, $record.variant.laterality, $record.variant.grip) | ForEach-Object { if ($_){$_}else{"-"} }) -join "/"
            $equipmentName = (@($record.equipment.type, $record.equipment.name) | Where-Object { $_ }) -join "/"
            if (-not $equipmentName) { $equipmentName = "-" }
            [pscustomobject]@{
                exercise_id = $record.exercise_id
                variant = $variantKey
                equipment = $equipmentName
                sequence = $record.sequence
                weight_basis = Get-WeightBasis $record
                sessions = 1
                sets = $workingSets.Count
                reps = if ($reps) { $reps } else { 0 }
                volume_kg = $volume
            }
        }
        $rows = $expanded | Group-Object exercise_id, variant, equipment, sequence, weight_basis | ForEach-Object {
            $first = $_.Group[0]
            [pscustomobject]@{
                exercise_id = $first.exercise_id
                variant = $first.variant
                equipment = $first.equipment
                sequence = $first.sequence
                weight_basis = $first.weight_basis
                entries = ($_.Group | Measure-Object -Property sessions -Sum).Sum
                sets = ($_.Group | Measure-Object -Property sets -Sum).Sum
                reps = ($_.Group | Measure-Object -Property reps -Sum).Sum
                volume_kg = ($_.Group | Measure-Object -Property volume_kg -Sum).Sum
            }
        }
        if ($Json) { Write-OutputObject @($rows) } else { $rows | Sort-Object exercise_id, variant, equipment, sequence | Format-Table -AutoSize }
        break
    }

    "list" {
        $catalog = Read-Catalog
        $rows = $catalog.exercises | ForEach-Object {
            [pscustomobject]@{ id = $_.id; name = $_.canonical_name; pattern = $_.movement_pattern; aliases = @($_.aliases).Count }
        }
        if ($Json) { Write-OutputObject @($rows) } else { $rows | Format-Table -AutoSize }
        break
    }

    "validate" {
        $catalog = Read-Catalog
        $errors = @()
        $ids = @{}
        $aliases = @{}
        foreach ($item in $catalog.exercises) {
            if ([string]::IsNullOrWhiteSpace($item.id) -or $item.id -notmatch "^[a-z0-9_]+$") { $errors += "无效 ID: $($item.id)" }
            if ($ids.ContainsKey($item.id)) { $errors += "重复 ID: $($item.id)" } else { $ids[$item.id] = $true }
            if ($item.naming_status -eq "user_defined") {
                if ([string]::IsNullOrWhiteSpace($item.definition)) { $errors += "自定义动作 $($item.id) 缺少 definition" }
                if (@($item.primary_muscles).Count -eq 0) { $errors += "自定义动作 $($item.id) 缺少 primary_muscles" }
                if ($item.target_basis -ne "user_confirmed") { $errors += "自定义动作 $($item.id) 的 target_basis 必须是 user_confirmed" }
            }
            foreach ($name in (@($item.canonical_name) + @($item.aliases))) {
                $normalized = Normalize-Name $name
                if ($aliases.ContainsKey($normalized) -and $aliases[$normalized] -ne $item.id) {
                    $errors += "别名冲突 '$name': $($aliases[$normalized]) / $($item.id)"
                } else { $aliases[$normalized] = $item.id }
            }
        }
        $records = @(Read-WorkoutRecords)
        $errors += @(Get-RecordErrors $records $catalog)
        if ($errors.Count -gt 0) {
            $errors | ForEach-Object { Write-Error $_ }
            exit 1
        }
        $result = [pscustomobject]@{ status = "ok"; exercises = @($catalog.exercises).Count; workout_records = $records.Count }
        if ($Json) { Write-OutputObject $result }
        else { Write-Host "校验通过: $($result.exercises) 个动作，$($result.workout_records) 条训练记录。" }
        break
    }
}

} finally {
    if ($null -ne $lockStream) { $lockStream.Dispose(); [IO.File]::Delete($lockPath) }
}
