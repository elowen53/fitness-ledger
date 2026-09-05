# Read-only training analysis, mirrored by analysis.py. PowerShell 5.1 compatible.
function Get-ContextErrors($Context) {
    if ($null -eq $Context) { return }
    if ($Context -isnot [System.Collections.IDictionary] -and $Context -isnot [pscustomobject]) {
        return 'analysis_context must be an object'
    }
    $keys = if ($Context -is [System.Collections.IDictionary]) { @($Context.Keys) } else { @($Context.PSObject.Properties.Name) }
    foreach ($key in @('session_template', 'execution_standard')) {
        if ($key -in $keys -and ($Context.$key -isnot [string] -or [string]::IsNullOrWhiteSpace($Context.$key))) {
            "$key must be nonempty text"
        }
    }
    if ('quality_change' -in $keys -and $Context.quality_change -cnotin @('maintained', 'improved', 'improved_with_load_reduction', 'degraded')) {
        'invalid quality_change'
    }
    if ('rest_sec' -in $keys) {
        $n = $Context.rest_sec
        if (($n -isnot [int] -and $n -isnot [long] -and $n -isnot [double] -and $n -isnot [decimal]) -or [double]::IsNaN([double]$n) -or [double]::IsInfinity([double]$n) -or $n -le 0) {
            'rest_sec must be a positive finite number'
        }
    }
}

function Get-RecordDate($Record) {
    return ([datetimeoffset]$Record.performed_at).ToString('yyyy-MM-dd')
}

function Get-WorkSets($Record) { @($Record.sets | Where-Object { -not $_.warmup }) }

function Get-BaseKey($Record) {
    return ,@($Record.exercise_id, $Record.variant.angle, $Record.variant.posture,
        $Record.variant.laterality, $Record.variant.grip, $Record.equipment.type,
        $Record.equipment.name, $Record.sequence)
}

function Get-SetMetrics($Record) {
    $sets = @(Get-WorkSets $Record)
    $left = @($sets | Where-Object { $_.side -eq 'left' })
    $right = @($sets | Where-Object { $_.side -eq 'right' })
    $lr = @($left | Where-Object { $null -ne $_.round } | ForEach-Object { $_.round } | Sort-Object -Unique)
    $rr = @($right | Where-Object { $null -ne $_.round } | ForEach-Object { $_.round } | Sort-Object -Unique)
    $paired = @($lr | Where-Object { $_ -in $rr }).Count
    $union = @(@($lr + $rr) | Sort-Object -Unique).Count
    $bilateral = @($sets | Where-Object { -not $_.side }).Count
    $reps = 0; $volume = 0.0
    foreach ($s in $sets) {
        $reps += $s.reps
        if ($null -ne $s.weight_kg -and $null -ne $s.reps) { $volume += $s.weight_kg * $s.reps }
    }
    return [ordered]@{
        working_set_entries = $sets.Count; working_rounds = $bilateral + $union
        bilateral_sets = $bilateral; left_sets = $left.Count; right_sets = $right.Count
        paired_rounds = $paired; unpaired_rounds = $union - $paired
        unknown_round_entries = @($sets | Where-Object { $_.side -and $null -eq $_.round }).Count
        reps = $reps; external_volume_kg = $volume
    }
}

function Get-Snapshot($Record) {
    $r = [ordered]@{
        id = $Record.id; date = Get-RecordDate $Record; sequence = $Record.sequence
        reported_name = $Record.reported_name; notes = $Record.notes
        analysis_context = $Record.analysis_context; sets = @(Get-WorkSets $Record)
    }
    $metrics = Get-SetMetrics $Record
    foreach ($key in $metrics.Keys) { $r[$key] = $metrics[$key] }
    return $r
}

function Get-Preceding($Record, $Records) {
    $sameDay = @($Records | Where-Object { (Get-RecordDate $_) -eq (Get-RecordDate $Record) })
    if ($null -eq $Record.sequence -or @($sameDay | Where-Object { $null -eq $_.sequence }).Count -gt 0) { return $null }
    $earlier = @($sameDay | Where-Object { $_.sequence -lt $Record.sequence } | Sort-Object sequence)
    $items = @($earlier | ForEach-Object {
        [ordered]@{ key = Get-BaseKey $_; sets = @(Get-WorkSets $_); context = $_.analysis_context; notes = $_.notes }
    })
    return ,$items
}

function ConvertTo-AnalysisJson($Value) { ConvertTo-Json -InputObject $Value -Depth 30 -Compress }

function Test-AnalysisEqual($A, $B) {
    if ($null -eq $A -or $null -eq $B) { return ($null -eq $A -and $null -eq $B) }
    if ($A -is [System.Collections.IDictionary] -or $A -is [pscustomobject]) {
        if ($B -isnot [System.Collections.IDictionary] -and $B -isnot [pscustomobject]) { return $false }
        $ak = if ($A -is [System.Collections.IDictionary]) { @($A.Keys) } else { @($A.PSObject.Properties.Name) }
        $bk = if ($B -is [System.Collections.IDictionary]) { @($B.Keys) } else { @($B.PSObject.Properties.Name) }
        if ($ak.Count -ne $bk.Count) { return $false }
        foreach ($k in $ak) {
            if ($k -cnotin $bk -or -not (Test-AnalysisEqual $A.$k $B.$k)) { return $false }
        }
        return $true
    }
    if ($A -is [array]) {
        if ($B -isnot [array] -or $A.Count -ne $B.Count) { return $false }
        for ($i=0; $i -lt $A.Count; $i++) { if (-not (Test-AnalysisEqual $A[$i] $B[$i])) { return $false } }
        return $true
    }
    if ($A -is [string]) { return ($B -is [string] -and $A -ceq $B) }
    return ($A -eq $B)
}

function Compare-Training($Latest, $Previous, $Records) {
    $c = $Latest.analysis_context; $p = $Previous.analysis_context
    $quality = $c.quality_change
    $reasons = @(); $status = 'comparable'; $delta = $null
    if ($null -eq $Previous) {
        $status = 'new_baseline'; $reasons = @('no_previous_base_match')
    } else {
        foreach ($key in @('execution_standard', 'session_template')) {
            if ($null -ne $c.$key -and $null -ne $p.$key -and $c.$key -cne $p.$key) {
                $status = 'new_baseline'; $reasons += $key + '_changed'
            } elseif (-not $c.$key -or -not $p.$key) { $reasons += $key + '_unknown' }
        }
        if ($null -eq $Latest.sequence) { $reasons += 'sequence_unknown' }
        $e = $Latest.equipment
        if (-not $e.type -or ($e.type -in @('machine', 'cable') -and -not $e.name)) { $reasons += 'equipment_identity_unknown' }
        if (-not $Latest.variant.laterality) { $reasons += 'laterality_unknown' }
        $before = Get-Preceding $Previous $Records
        $after = Get-Preceding $Latest $Records
        if ($null -eq $before -or $null -eq $after) { $reasons += 'preceding_work_unknown' }
        elseif (-not (Test-AnalysisEqual $before $after)) { $reasons += 'preceding_work_changed' }
        if (-not $c.rest_sec -or -not $p.rest_sec) { $reasons += 'rest_unknown' }
        elseif ($c.rest_sec -ne $p.rest_sec) { $reasons += 'rest_changed' }
        if (-not $quality -or -not $p.quality_change) { $reasons += 'quality_unknown' }
        if ($p.quality_change -eq 'degraded') { $reasons += 'previous_quality_declined' }
        if ($Latest.notes -or $Previous.notes) { $reasons += 'notes_require_review' }
        $a = @(Get-WorkSets $Latest); $b = @(Get-WorkSets $Previous)
        $both = @($a + $b)
        if ($a.Count -eq 0 -or $b.Count -eq 0 -or @($both | Where-Object { $null -eq $_.rir }).Count -gt 0) { $reasons += 'effort_unknown' }
        if (@($both | Where-Object { $null -eq $_.reps }).Count -gt 0) { $reasons += 'rep_measurement_unavailable' }
        if (@($both | Where-Object { $null -eq $_.weight_kg -and -not $_.bodyweight }).Count -gt 0) { $reasons += 'load_unknown' }
        if (@($both | Where-Object { $_.bodyweight }).Count -gt 0) { $reasons += 'bodyweight_load_untracked' }
        $aa = @($a | ForEach-Object { ,@($_.side, $_.round, $_.weight_kg, $_.bodyweight, $_.duration_sec, $_.rir) })
        $bb = @($b | ForEach-Object { ,@($_.side, $_.round, $_.weight_kg, $_.bodyweight, $_.duration_sec, $_.rir) })
        if (-not (Test-AnalysisEqual $aa $bb)) { $reasons += 'set_conditions_changed' }
        if ($status -eq 'comparable' -and $reasons.Count -gt 0) { $status = 'limited' }
    }
    if ($quality -in @('improved', 'improved_with_load_reduction')) {
        $status = 'new_baseline'; $reasons += 'reported_quality_improvement'
        $assessment = if ($quality -eq 'improved_with_load_reduction') { 'major_quality_progress' } else { 'quality_progress' }
    } elseif ($quality -eq 'degraded') {
        $status = 'limited'; $reasons += 'reported_quality_decline'; $assessment = 'quality_declined'
    } elseif ($status -eq 'comparable') {
        $delta = (Get-SetMetrics $Latest).reps - (Get-SetMetrics $Previous).reps
        $assessment = if ($delta -gt 0) { 'reps_increased' } elseif ($delta -eq 0) { 'reps_unchanged' } else { 'reps_decreased' }
    } else {
        $assessment = if ($status -eq 'new_baseline') { 'establish_baseline' } else { 'review_context' }
    }
    return [ordered]@{ comparability = $status; reasons = @($reasons); assessment = $assessment; reps_delta = $delta }
}

function Build-TrainingReport($Records, $Catalog, [string]$AsOf) {
    $end = [datetime]::MinValue
    if (-not [datetime]::TryParseExact($AsOf, 'yyyy-MM-dd', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::None, [ref]$end)) { throw 'Date must be yyyy-MM-dd' }
    foreach ($r in $Records) {
        $errors = @(Get-ContextErrors $r.analysis_context)
        if ($errors.Count -gt 0) { throw "$($r.id): $($errors -join '; ')" }
    }
    $eligible = @($Records | Where-Object { (Get-RecordDate $_) -le $AsOf } | Sort-Object @{Expression={Get-RecordDate $_}}, sequence, id)
    $catalogMap = [System.Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
    foreach ($i in $Catalog.exercises) { $catalogMap[$i.id] = $i }
    $windows = @()
    foreach ($days in @(7, 14)) {
        $start = $end.AddDays(-$days+1).ToString('yyyy-MM-dd')
        $selected = @($eligible | Where-Object { (Get-RecordDate $_) -ge $start })
        $dates = @($selected | ForEach-Object { Get-RecordDate $_ } | Sort-Object -Unique)
        $muscles = [System.Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
        $entries = 0
        foreach ($r in $selected) {
            $metrics = Get-SetMetrics $r
            $entries += $metrics.working_set_entries
            if ($metrics.working_set_entries -eq 0) { continue }
            if (-not $catalogMap.ContainsKey($r.exercise_id)) { continue }
            foreach ($muscle in @($catalogMap[$r.exercise_id].primary_muscles | Sort-Object -Unique)) {
                if (-not $muscles.ContainsKey($muscle)) {
                    $m = [ordered]@{ muscle = $muscle; dates = @() }
                    foreach ($k in $metrics.Keys) { if ($k -notin @('reps', 'external_volume_kg')) { $m[$k] = 0 } }
                    $muscles[$muscle] = $m
                }
                $m = $muscles[$muscle]
                $m.dates += Get-RecordDate $r
                foreach ($k in $metrics.Keys) { if ($m.Contains($k)) { $m[$k] += $metrics[$k] } }
            }
        }
        $muscleRows = @()
        foreach ($key in @($muscles.Keys | Sort-Object)) {
            $m = $muscles[$key]
            $m['training_dates'] = @($m.dates | Sort-Object -Unique)
            $m.Remove('dates'); $m['frequency'] = $m.training_dates.Count
            $muscleRows += $m
        }
        $rest = @(for ($n=0; $n -lt $days; $n++) {
            $d = $end.AddDays(-$n).ToString('yyyy-MM-dd')
            if ($d -notin $dates) { $d }
        })
        $windows += [ordered]@{ days=$days; start=$start; end=$AsOf; training_dates=@($dates)
            rest_dates=@($rest | Sort-Object); working_set_entries=$entries; muscles=@($muscleRows) }
    }
    $groups = [System.Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
    foreach ($r in $eligible) {
        $key = ConvertTo-AnalysisJson (Get-BaseKey $r)
        if (-not $groups.ContainsKey($key)) { $groups[$key] = @() }
        $groups[$key] += $r
    }
    $trends = @()
    foreach ($rs in $groups.Values) {
        $latest = $rs[-1]
        if ((Get-RecordDate $latest) -lt $windows[1].start) { continue }
        $previous = if ($rs.Count -gt 1) { $rs[-2] } else { $null }
        $history = @(for ($n=$rs.Count-1; $n -ge [Math]::Max(0,$rs.Count-3); $n--) { Get-Snapshot $rs[$n] })
        $t = [ordered]@{ exercise_id=$latest.exercise_id; base_key=Get-BaseKey $latest; history=@($history) }
        $comparison = Compare-Training $latest $previous $eligible
        foreach ($key in $comparison.Keys) { $t[$key] = $comparison[$key] }
        $trends += [pscustomobject]$t
    }
    $lastDate = if ($eligible.Count -gt 0) { Get-RecordDate $eligible[-1] } else { $null }
    return [ordered]@{
        as_of=$AsOf; last_workout_date=$lastDate
        days_since_last_workout=if ($lastDate) { ($end-[datetime]::ParseExact($lastDate,'yyyy-MM-dd',[Globalization.CultureInfo]::InvariantCulture)).Days } else { $null }
        windows=@($windows); trends=@($trends | Sort-Object exercise_id, @{Expression={$_.history[0].id}})
        guidance='Descriptive only; review quality, recovery and historical notes before changing the plan. No automatic PR, overload or deload.'
        counting_basis='Catalog primary_muscles only; overlapping muscles are not additive. Unpaired rounds remain visible; unknown rounds are not imputed.'
    }
}
