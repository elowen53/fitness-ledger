# Ledger invariants shared by pre-write checks and validate; mirrored by validation.py.
$WeightBases = @('unknown', 'per_implement', 'per_side', 'total', 'machine_display')

function Test-LedgerNumber($Value, $Minimum = 0, [switch]$Integer) {
    if ($Value -isnot [int] -and $Value -isnot [long] -and $Value -isnot [double] -and $Value -isnot [decimal] -and $Value -isnot [bigint]) { return $false }
    return (-not [double]::IsNaN([double]$Value) -and -not [double]::IsInfinity([double]$Value) -and $Value -ge $Minimum -and
        (-not $Integer -or $Value -is [int] -or $Value -is [long] -or $Value -is [bigint]))
}

function Test-LedgerDate($Value) {
    $parsed = [datetime]::MinValue
    return ($Value -is [string] -and [datetime]::TryParseExact($Value, 'yyyy-MM-dd', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::None, [ref]$parsed))
}

function Test-LedgerTimestamp($Value) {
    if ($Value -isnot [string] -or $Value -cnotmatch '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,7})?(?:Z|[+-]\d{2}:\d{2})$') { return $false }
    $parsed = [datetimeoffset]::MinValue
    return [datetimeoffset]::TryParse($Value, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::None, [ref]$parsed)
}

function Test-LedgerObject($Value) { return ($Value -is [System.Collections.IDictionary] -or $Value -is [pscustomobject]) }

function Get-RecordErrors($Records, $Catalog) {
    $ids = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $sequences = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $days = @{}
    $items = [System.Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
    foreach ($i in $Catalog.exercises) { $items[$i.id] = $i }
    foreach ($r in $Records) {
        if (-not (Test-LedgerObject $r)) { 'record must be an object'; continue }
        $rid = $r.id
        if ($rid -isnot [string] -or [string]::IsNullOrWhiteSpace($rid)) { "$rid`: id must be nonempty text" }
        elseif (-not $ids.Add($rid)) { "$rid`: duplicate record id" }
        $version = $r.schema_version
        if (-not (Test-LedgerNumber $version 1 -Integer) -or $version -notin @(1,2)) { "$rid`: unsupported schema_version" }
        if ($r.reported_name -isnot [string] -or [string]::IsNullOrWhiteSpace($r.reported_name)) { "$rid`: reported_name must be nonempty text" }
        $item = $null
        if ($r.exercise_id -isnot [string] -or -not $items.ContainsKey($r.exercise_id)) { "$rid`: unknown exercise_id" }
        else { $item = $items[$r.exercise_id] }
        foreach ($errorText in @(Get-ContextErrors $r.analysis_context)) { "$rid`: $errorText" }
        $performed = $r.performed_at
        if ($version -eq 2) {
            if (-not (Test-LedgerDate $r.training_date)) { "$rid`: invalid training_date" }
            if (-not (Test-LedgerTimestamp $r.recorded_at)) { "$rid`: invalid recorded_at" }
            if ($null -ne $performed -and (-not (Test-LedgerTimestamp $performed) -or $performed.Substring(0,10) -cne $r.training_date)) { "$rid`: performed_at must match training_date and include timezone" }
        } elseif (-not (Test-LedgerTimestamp $performed)) { "$rid`: invalid performed_at" }
        $date = Get-RecordDate $r
        $seq = $r.sequence
        if ($null -eq $seq -and $version -eq 1) { } # Preserve legacy unknown order.
        elseif (-not (Test-LedgerNumber $seq 1 -Integer)) { "$rid`: sequence must be a positive integer" }
        elseif (-not $sequences.Add("$date|$seq")) { "$rid`: duplicate date/sequence" }
        $day = $r.day_type
        if ($null -ne $day -or $version -eq 2) {
            if ($day -cnotin @('standard','overload','deload')) { "$rid`: invalid day_type" }
            elseif ($days.ContainsKey($date) -and $days[$date] -cne $day) { "$rid`: mixed day_type on same date" }
            else { $days[$date] = $day }
        }
        if ($version -eq 2 -and ($r.day_type_basis -isnot [string] -or [string]::IsNullOrWhiteSpace($r.day_type_basis))) { "$rid`: day_type_basis must be nonempty text" }
        if ($null -ne $r.weight_basis -and $r.weight_basis -cnotin $WeightBases) { "$rid`: invalid weight_basis" }
        if ($version -eq 2 -and $null -eq $r.weight_basis) { "$rid`: weight_basis required" }
        $v = $r.variant
        if (-not (Test-LedgerObject $v)) { "$rid`: variant must be an object"; $v = @{} }
        foreach ($field in @('angle','posture','laterality')) {
            $allowed = switch ($field) {
                'angle' { @('flat','incline','decline','vertical') }
                'posture' { @('standing','seated','lying','kneeling') }
                'laterality' { @('bilateral','unilateral','alternating') }
            }
            $value = $v.$field
            if ($null -ne $value -and ($value -cnotin $allowed -or ($null -ne $item -and $value -cnotin @($item.supported_variants.$field)))) { "$rid`: unsupported variant.$field" }
        }
        if ($null -ne $v.grip -and ($v.grip -isnot [string] -or [string]::IsNullOrWhiteSpace($v.grip))) { "$rid`: grip must be nonempty text" }
        if ($version -eq 2 -and $null -eq $v.laterality) { "$rid`: laterality required" }
        if (-not (Test-LedgerObject $r.equipment)) { "$rid`: equipment must be an object" }
        if ($r.sets -isnot [array] -or $r.sets.Count -eq 0) { "$rid`: sets must be a nonempty array"; continue }
        $rounds = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
        $index = 0
        foreach ($s in $r.sets) {
            $index++
            if (-not (Test-LedgerObject $s)) { "$rid`: set $index must be an object"; continue }
            foreach ($field in @('reps','weight_kg','rir','duration_sec')) {
                $value = $s.$field
                if ($null -ne $value -and (-not (Test-LedgerNumber $value 0 -Integer:($field -eq 'reps')) -or ($field -eq 'duration_sec' -and $value -eq 0))) { "$rid`: invalid set $index $field" }
            }
            foreach ($field in @('warmup','bodyweight')) { if ($s.$field -isnot [bool]) { "$rid`: set $index $field must be boolean" } }
            if ($null -eq $s.reps -and $null -eq $s.duration_sec) { "$rid`: set $index needs reps or duration_sec" }
            $side = $s.side; $rnd = $s.round
            if ($null -ne $side -and $side -cnotin @('left','right')) { "$rid`: invalid set side" }
            if ($null -ne $side -and $null -ne $v.laterality -and $v.laterality -cnotin @('unilateral','alternating')) { "$rid`: side conflicts with laterality" }
            if ($null -eq $side -and ($null -ne $rnd -or ($version -eq 2 -and $v.laterality -ceq 'unilateral'))) { "$rid`: unilateral sets require explicit side; unsided sets cannot have round" }
            if ($null -ne $rnd -and -not (Test-LedgerNumber $rnd 1 -Integer)) { "$rid`: round must be a positive integer" }
            elseif ($side -cin @('left','right') -and $null -ne $rnd) {
                if (-not $rounds.Add("$([bool]$s.warmup)|$side|$rnd")) { "$rid`: duplicate side/round within warmup or work sets" }
            } elseif ($null -ne $side -and $version -eq 2) { "$rid`: sided sets require round" }
            $source = $s.rir_source
            if ($null -ne $source -or $version -eq 2) {
                if ($source -cnotin @('reported','profile_default','unknown')) { "$rid`: invalid rir_source" }
                elseif (($source -ceq 'unknown') -ne ($null -eq $s.rir)) { "$rid`: rir_source conflicts with rir" }
                elseif ($source -ceq 'profile_default') {
                    $default = $r.rir_default
                    if (-not (Test-LedgerObject $default) -or $default.status -cne 'user_confirmed' -or $default.missing_means -ne $s.rir -or $s.warmup) { "$rid`: profile_default requires matching confirmed snapshot and work set" }
                }
            }
        }
    }
}
