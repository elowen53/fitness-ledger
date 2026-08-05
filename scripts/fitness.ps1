[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("resolve", "add", "resequence", "recent", "stats", "validate", "list")]
    [string]$Command,

    [string]$Exercise,
    [string]$Id,
    [string]$ResolveAs,
    [string[]]$Sets,
    [string]$Date,
    [string]$Equipment,
    [string]$Angle,
    [string]$Posture,
    [string]$Laterality,
    [string]$Grip,
    [string]$Notes,
    [string[]]$Tags,
    [int]$Sequence = 0,
    [int]$WarmupCount = 0,
    [int]$Limit = 10,
    [switch]$Json,
    [string]$ProjectRoot
)

$ErrorActionPreference = "Stop"

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

    foreach ($item in $catalog.exercises) {
        $best = 0
        $matchedAlias = $null
        $names = @($item.canonical_name) + @($item.aliases)
        foreach ($alias in $names) {
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
            if ($score -gt $best) {
                $best = $score
                $matchedAlias = $alias
            }
        }
        if ($best -ge 65) {
            $candidates += [pscustomobject]@{
                id = $item.id
                canonical_name = $item.canonical_name
                score = $best
                matched_alias = $matchedAlias
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

function Read-WorkoutRecords {
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
        $Object | ConvertTo-Json -Depth 12
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

switch ($Command) {
    "resolve" {
        $result = Resolve-Exercise $Exercise
        if ($Json) { Write-OutputObject $result; break }
        Write-Host "状态: $($result.status)"
        if ($result.exercise) {
            Write-Host "动作: $($result.exercise.canonical_name) [$($result.exercise.id)]"
            Write-Host "命中: $($result.exercise.matched_alias)；置信分: $($result.exercise.score)"
        }
        Write-Host "变体: angle=$($result.variant.angle), posture=$($result.variant.posture), laterality=$($result.variant.laterality)"
        if ($result.status -ne "resolved") {
            $result.candidates | Format-Table id, canonical_name, score, matched_alias -AutoSize
            exit 2
        }
        break
    }

    "add" {
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
        $finalAngle = if ($Angle) { $Angle } else { $resolution.variant.angle }
        $finalPosture = if ($Posture) { $Posture } else { $resolution.variant.posture }
        $finalLaterality = if ($Laterality) { $Laterality } else { $resolution.variant.laterality }
        $finalGrip = if ($Grip) { $Grip } elseif ($ResolveAs) { (Get-Variant $Exercise).grip } else { $resolution.variant.grip }
        Assert-VariantAllowed $catalogItem "angle" $finalAngle
        Assert-VariantAllowed $catalogItem "posture" $finalPosture
        Assert-VariantAllowed $catalogItem "laterality" $finalLaterality

        if ($Date) {
            $parsedDate = [datetime]::MinValue
            if (-not [datetime]::TryParseExact($Date, "yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::None, [ref]$parsedDate)) {
                throw "Date 必须是 yyyy-MM-dd。"
            }
            $now = [datetimeoffset]::Now
            $performed = [datetimeoffset]::new($parsedDate.Year, $parsedDate.Month, $parsedDate.Day, $now.Hour, $now.Minute, $now.Second, $now.Offset)
        } else {
            $performed = [datetimeoffset]::Now
        }

        $parsedSets = @()
        $sideRounds = @{ left = 0; right = 0 }
        for ($i = 0; $i -lt $Sets.Count; $i++) {
            $parsedSet = Parse-Set $Sets[$i] ($i -lt $WarmupCount)
            if ($parsedSet.side) {
                $sideRounds[$parsedSet.side]++
                $parsedSet["round"] = $sideRounds[$parsedSet.side]
            }
            $parsedSets += $parsedSet
        }
        $shortId = [guid]::NewGuid().ToString("N").Substring(0, 6)
        $record = [ordered]@{
            schema_version = 1
            id = $performed.ToString("yyyyMMdd-HHmmss") + "-" + $shortId
            performed_at = $performed.ToString("o")
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

        $directory = Join-Path (Join-Path $WorkoutRoot $performed.ToString("yyyy")) $performed.ToString("MM")
        [void][IO.Directory]::CreateDirectory($directory)
        $path = Join-Path $directory ($performed.ToString("yyyy-MM-dd") + ".jsonl")
        $line = $record | ConvertTo-Json -Compress -Depth 12
        [IO.File]::AppendAllText($path, $line + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
        if ($Json) { Write-OutputObject $record }
        else {
            Write-Host "已记录: $($catalogItem.canonical_name) [$($catalogItem.id)]"
            Write-Host "日期: $($performed.ToString('yyyy-MM-dd'))；顺序: $($record.sequence)；组数: $($parsedSets.Count)；文件: $path"
            Write-Host "变体: angle=$finalAngle, posture=$finalPosture, laterality=$finalLaterality, grip=$finalGrip；器械类型: $($record.equipment.type)；器械: $Equipment"
        }
        break
    }

    "recent" {
        $catalog = Read-Catalog
        $nameMap = @{}
        foreach ($item in $catalog.exercises) { $nameMap[$item.id] = $item.canonical_name }
        $rows = Read-WorkoutRecords | Sort-Object performed_at -Descending | Select-Object -First $Limit | ForEach-Object {
            [pscustomobject]@{
                date = ([datetimeoffset]$_.performed_at).ToString("yyyy-MM-dd")
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
        $found = $false
        $files = Get-ChildItem -LiteralPath $WorkoutRoot -Recurse -File -Filter "*.jsonl"
        foreach ($file in $files) {
            $updatedLines = @()
            $changed = $false
            foreach ($line in (Get-Content -LiteralPath $file.FullName -Encoding UTF8)) {
                if ([string]::IsNullOrWhiteSpace($line)) { continue }
                $record = $line | ConvertFrom-Json
                if ($record.id -eq $Id) {
                    if ($found) { throw "记录 ID 重复: $Id" }
                    $record | Add-Member -NotePropertyName sequence -NotePropertyValue $Sequence -Force
                    $updatedLines += ($record | ConvertTo-Json -Compress -Depth 12)
                    $changed = $true
                    $found = $true
                } else {
                    $updatedLines += $line
                }
            }
            if ($changed) {
                [IO.File]::WriteAllLines($file.FullName, $updatedLines, [Text.UTF8Encoding]::new($false))
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
                sessions = 1
                sets = $workingSets.Count
                reps = if ($reps) { $reps } else { 0 }
                volume_kg = $volume
            }
        }
        $rows = $expanded | Group-Object exercise_id, variant, equipment | ForEach-Object {
            $first = $_.Group[0]
            [pscustomobject]@{
                exercise_id = $first.exercise_id
                variant = $first.variant
                equipment = $first.equipment
                entries = ($_.Group | Measure-Object -Property sessions -Sum).Sum
                sets = ($_.Group | Measure-Object -Property sets -Sum).Sum
                reps = ($_.Group | Measure-Object -Property reps -Sum).Sum
                volume_kg = ($_.Group | Measure-Object -Property volume_kg -Sum).Sum
            }
        }
        if ($Json) { Write-OutputObject @($rows) } else { $rows | Sort-Object exercise_id, variant, equipment | Format-Table -AutoSize }
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
        $sequenceByDate = @{}
        foreach ($record in $records) {
            if ($record.schema_version -ne 1) { $errors += "记录 $($record.id) schema_version 不是 1" }
            if (-not $ids.ContainsKey([string]$record.exercise_id)) { $errors += "记录 $($record.id) 引用了未知动作 $($record.exercise_id)" }
            if (@($record.sets).Count -eq 0) { $errors += "记录 $($record.id) 没有训练组" }
            if ($null -ne $record.sequence) {
                if ([int]$record.sequence -lt 1) { $errors += "记录 $($record.id) 的 sequence 必须大于 0" }
                $recordDate = ([datetimeoffset]$record.performed_at).ToString("yyyy-MM-dd")
                $sequenceKey = "$recordDate|$($record.sequence)"
                if ($sequenceByDate.ContainsKey($sequenceKey)) {
                    $errors += "动作顺序冲突 $sequenceKey：$($sequenceByDate[$sequenceKey]) / $($record.id)"
                } else { $sequenceByDate[$sequenceKey] = $record.id }
            }
        }
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
