"""Read-only training analysis; no inferred facts."""
from datetime import datetime, timedelta
import json
import math

QUALITY_CHANGES = ('maintained', 'improved', 'improved_with_load_reduction', 'degraded')
SET_TYPES = ('straight', 'top', 'backoff', 'drop', 'rest_pause', 'myo')
# Legacy sets have no set_type and are read as straight sets.
PRIMARY_SET_TYPES = (None, 'straight', 'top')
FAILURE_MODES = ('technical', 'absolute', 'extended')
PARTIAL_POSITIONS = ('lengthened', 'shortened')
SETUP_SOURCES = ('reported', 'same_as_previous')
# Project heuristic: muscles that share a region count as "already trained" for sequence roles.
MUSCLE_REGIONS = {'lats': 'back', 'back': 'back', 'traps': 'back',
                  'front_delts': 'shoulders', 'side_delts': 'shoulders', 'rear_delts': 'shoulders', 'shoulders': 'shoulders'}
LONG_GAP_DAYS = 21
# Project heuristic: the first two weeks after a layoff re-establish baselines.
RETURN_PHASE_DAYS = 14
# Missing or differing context that makes a numeric verdict unsafe; other reasons are caveats.
BLOCKING_REASONS = ('rest_changed', 'previous_quality_declined', 'effort_unknown', 'effort_changed',
                    'failure_mode_changed', 'rep_measurement_unavailable', 'load_unknown')


def context_errors(context):
    if context is None:
        return []
    if not isinstance(context, dict):
        return ['analysis_context must be an object']
    errors = []
    for key in ('session_template', 'execution_standard'):
        if key in context and (not isinstance(context[key], str) or not context[key].strip()):
            errors.append(key + ' must be nonempty text')
    if 'quality_change' in context and context['quality_change'] not in QUALITY_CHANGES:
        errors.append('invalid quality_change')
    if 'rest_sec' in context:
        n = context['rest_sec']
        if isinstance(n, bool) or not isinstance(n, (float, int)) or not math.isfinite(n) or n <= 0:
            errors.append('rest_sec must be a positive finite number')
    return errors


def record_date(record):
    # Version 1 timestamps are retained only as a legacy date source.
    return record.get('training_date') or (record.get('performed_at') or '')[:10]


def weight_basis(record):
    return record.get('weight_basis') or 'unknown'


def work_sets(record):
    return [s for s in record.get('sets', []) if not s.get('warmup')]


def primary_sets(record):
    return [s for s in work_sets(record) if s.get('set_type') in PRIMARY_SET_TYPES]


def setup_values(record):
    return ((record.get('setup') or {}).get('values')) or None


def identity_key(record):
    v, e = record.get('variant') or {}, record.get('equipment') or {}
    return [record.get('exercise_id')] + [v.get(k) for k in ('angle', 'posture', 'laterality', 'grip')] + [e.get('type'), e.get('name')]


def regions(record, catalog_map):
    muscles = catalog_map.get(record.get('exercise_id'), {}).get('primary_muscles', [])
    return {MUSCLE_REGIONS.get(m, m) for m in muscles}


def sequence_role(record, records, catalog_map):
    """opener / muscle_first / muscle_after / unknown, from the actual same-day order."""
    seq = record.get('sequence')
    if seq is None:
        return 'unknown'
    if seq == 1:
        return 'opener'
    same_day = [r for r in records if r is not record and record_date(r) == record_date(record)]
    if any(r.get('sequence') is None for r in same_day):
        return 'unknown'
    mine = regions(record, catalog_map)
    earlier = [r for r in same_day if r['sequence'] < seq]
    return 'muscle_after' if any(regions(r, catalog_map) & mine for r in earlier) else 'muscle_first'


def base_key(record, role):
    return identity_key(record) + [role, weight_basis(record)]


def set_metrics(record):
    sets = work_sets(record)
    sides = {side: [s for s in sets if s.get('side') == side] for side in ('left', 'right')}
    rounds = {side: {s['round'] for s in ss if s.get('round') is not None} for side, ss in sides.items()}
    paired = len(rounds['left'] & rounds['right'])
    union = len(rounds['left'] | rounds['right'])
    missing = sum(s.get('side') is not None and s.get('round') is None for s in sets)
    bilateral = sum(not s.get('side') for s in sets)
    return dict(working_set_entries=len(sets), working_rounds=bilateral + union,
                bilateral_sets=bilateral, left_sets=len(sides['left']), right_sets=len(sides['right']),
                paired_rounds=paired, unpaired_rounds=union-paired, unknown_round_entries=missing,
                primary_set_entries=sum(s.get('set_type') in PRIMARY_SET_TYPES for s in sets),
                reps=sum(s.get('reps') or 0 for s in sets),
                external_volume_kg=sum((s.get('weight_kg') or 0)*(s.get('reps') or 0) for s in sets))


def snapshot(record):
    return dict(id=record.get('id'), date=record_date(record),
                sequence=record.get('sequence'), weight_basis=weight_basis(record), reported_name=record.get('reported_name'),
                notes=record.get('notes'), analysis_context=record.get('analysis_context'), setup=record.get('setup'),
                sets=work_sets(record), **set_metrics(record))


def preceding(record, records):
    seq = record.get('sequence')
    same_day = [r for r in records if record_date(r) == record_date(record)]
    if seq is None or any(r.get('sequence') is None for r in same_day):
        return None
    earlier = sorted([r for r in same_day if r['sequence'] < seq], key=lambda r: r['sequence'])
    return [dict(key=identity_key(r), sets=work_sets(r), context=r.get('analysis_context'), notes=r.get('notes')) for r in earlier]


def load_of(s):
    return 'bw' if s.get('bodyweight') else s.get('weight_kg')


def top_sets(record):
    """First primary set at the heaviest load, per side (None for bilateral)."""
    result = {}
    for side in sorted({s.get('side') for s in primary_sets(record)}, key=str):
        sets = [s for s in primary_sets(record) if s.get('side') == side and s.get('reps') is not None]
        loads = [s.get('weight_kg') for s in sets if s.get('weight_kg') is not None]
        if not sets:
            continue
        top = max(loads) if loads else None
        result[side] = next(s for s in sets if s.get('weight_kg') == top)
    return result


def performance(latest, previous):
    a, b = primary_sets(latest), primary_sets(previous)
    profile = lambda sets: [(s.get('side'), load_of(s)) for s in sets]
    if profile(a) == profile(b):
        delta = sum(s.get('reps') or 0 for s in a) - sum(s.get('reps') or 0 for s in b)
        return dict(reps_delta=delta, top_load_delta=0, top_set_reps_delta=None,
                    assessment='reps_increased' if delta > 0 else ('reps_unchanged' if delta == 0 else 'reps_decreased'))
    ta, tb = top_sets(latest), top_sets(previous)
    sides = sorted(set(ta) & set(tb), key=str)
    if not sides:
        return dict(reps_delta=None, top_load_delta=None, top_set_reps_delta=None, assessment='review_context')
    load_deltas = [load_of(ta[k]) - load_of(tb[k]) for k in sides
                   if isinstance(load_of(ta[k]), (int, float)) and isinstance(load_of(tb[k]), (int, float))]
    if len(load_deltas) != len(sides) and any(load_of(ta[k]) != load_of(tb[k]) for k in sides):
        return dict(reps_delta=None, top_load_delta=None, top_set_reps_delta=None, assessment='review_context')
    load_delta = load_deltas[0] if load_deltas and len(set(load_deltas)) == 1 else (0 if not load_deltas else None)
    reps = {k: ta[k]['reps'] - tb[k]['reps'] for k in sides}
    reps_out = reps[None] if list(reps) == [None] else {k: v for k, v in reps.items()}
    if load_delta is None:
        assessment = 'review_context'
    elif load_delta > 0:
        assessment = 'load_increased'
    elif load_delta < 0:
        assessment = 'load_decreased'
    elif all(v > 0 for v in reps.values()):
        assessment = 'top_set_reps_increased'
    elif all(v == 0 for v in reps.values()):
        assessment = 'top_set_reps_unchanged'
    elif all(v < 0 for v in reps.values()):
        assessment = 'top_set_reps_decreased'
    else:
        assessment = 'top_set_reps_mixed'
    return dict(reps_delta=None, top_load_delta=load_delta, top_set_reps_delta=reps_out, assessment=assessment)


def best_reps_by_load(group, periods=()):
    """Best single primary-set reps per side and load within one comparable key; not a PR claim."""
    best = {}
    for r in group:
        for s in primary_sets(r):
            if s.get('reps') is None or (s.get('weight_kg') is None and not s.get('bodyweight')):
                continue
            key = (s.get('side'), load_of(s))
            if key not in best or s['reps'] > best[key]['reps']:
                best[key] = dict(side=s.get('side'), load=load_of(s), reps=s['reps'], date=record_date(r), record_id=r.get('id'),
                                 before_last_layoff=bool(periods) and record_date(r) < periods[-1]['start'])
    return sorted(best.values(), key=lambda b: (str(b['side']), b['load'] == 'bw', -(b['load'] if b['load'] != 'bw' else 0)))


def layoff_periods(records, day_notes, date):
    """Paused ranges from day notes plus training gaps over LONG_GAP_DAYS, merged; only up to date."""
    periods = []
    for note in day_notes or []:
        if note.get('training_status') == 'paused' and note.get('date') and note['date'] <= date:
            periods.append([note['date'], min(note.get('applies_through') or note['date'], date), 'day_note'])
    dates = sorted({record_date(r) for r in records if record_date(r) <= date})
    day = lambda s: datetime.strptime(s, '%Y-%m-%d').date()
    for a, b in zip(dates, dates[1:]):
        if (day(b) - day(a)).days > LONG_GAP_DAYS:
            periods.append([(day(a)+timedelta(days=1)).isoformat(), (day(b)-timedelta(days=1)).isoformat(), 'training_gap'])
    periods.sort()
    merged = []
    for start, end, source in periods:
        if merged and day(start) <= day(merged[-1]['end']) + timedelta(days=1):
            last = merged[-1]
            last['end'] = max(last['end'], end)
            last['sources'] = sorted(set(last['sources']) | {source})
        else:
            merged.append(dict(start=start, end=end, sources=[source]))
    for p in merged:
        p['days'] = (day(p['end']) - day(p['start'])).days + 1
    return merged


def crossed_layoff(previous, latest, periods):
    return next((p for p in periods if record_date(previous) < p['start'] and p['end'] < record_date(latest)), None)


def return_phase(records, periods, date):
    if not periods:
        return None
    p = periods[-1]
    after = sorted({record_date(r) for r in records if p['end'] < record_date(r) <= date})
    days = (datetime.strptime(date, '%Y-%m-%d') - datetime.strptime(p['end'], '%Y-%m-%d')).days
    return dict(layoff=p, first_session=after[0] if after else None, sessions_since_return=len(after),
                days_since_return=days, active=bool(after) and days <= RETURN_PHASE_DAYS)


def compare(latest, previous, records, periods=()):
    c, p = latest.get('analysis_context') or {}, (previous or {}).get('analysis_context') or {}
    quality = c.get('quality_change')
    reasons, status = [], 'comparable'
    result = dict(reps_delta=None, top_load_delta=None, top_set_reps_delta=None, days_since_previous=None)
    if previous is None:
        status, reasons = 'new_baseline', ['no_previous_base_match']
    else:
        gap = (datetime.strptime(record_date(latest), '%Y-%m-%d') - datetime.strptime(record_date(previous), '%Y-%m-%d')).days
        result['days_since_previous'] = gap
        layoff = crossed_layoff(previous, latest, periods)
        if layoff:
            # Re-establish the baseline after a layoff; pre-layoff numbers stay as reference only.
            status = 'new_baseline'
            reasons.append('crosses_layoff')
            reference = performance(latest, previous)
            result['pre_layoff_reference'] = dict(previous_date=record_date(previous), layoff=layoff,
                                                  top_load_delta=reference['top_load_delta'],
                                                  top_set_reps_delta=reference['top_set_reps_delta'],
                                                  reps_delta=reference['reps_delta'])
        elif gap > LONG_GAP_DAYS:
            reasons.append('long_gap')
        for key in ('execution_standard', 'session_template'):
            if c.get(key) is not None and p.get(key) is not None and c[key] != p[key]:
                status = 'new_baseline'
                reasons.append(key + '_changed')
            elif not c.get(key) or not p.get(key):
                reasons.append(key + '_unknown')
        e = latest.get('equipment') or {}
        su, sp = setup_values(latest), setup_values(previous)
        if su is not None and sp is not None and su != sp:
            status = 'new_baseline'
            reasons.append('setup_changed')
        elif (su is None or sp is None) and e.get('type') in ('machine', 'cable'):
            reasons.append('setup_unknown')
        if latest.get('sequence') is None:
            reasons.append('sequence_unknown')
        if not e.get('type') or (e.get('type') in ('machine', 'cable') and not e.get('name')):
            reasons.append('equipment_identity_unknown')
        if not (latest.get('variant') or {}).get('laterality'):
            reasons.append('laterality_unknown')
        before, after = preceding(previous, records), preceding(latest, records)
        if before is None or after is None:
            reasons.append('preceding_work_unknown')
        elif before != after:
            reasons.append('preceding_work_changed')
        if not c.get('rest_sec') or not p.get('rest_sec'):
            reasons.append('rest_unknown')
        elif c['rest_sec'] != p['rest_sec']:
            reasons.append('rest_changed')
        if quality is None or p.get('quality_change') is None:
            reasons.append('quality_unknown')
        if p.get('quality_change') == 'degraded':
            reasons.append('previous_quality_declined')
        # Free text is evidence for the agent, not a safe automatic classifier.
        if latest.get('notes') or previous.get('notes'):
            reasons.append('notes_require_review')
        a, b = primary_sets(latest), primary_sets(previous)
        if not a or not b or any(s.get('rir') is None for s in a+b):
            reasons.append('effort_unknown')
        elif sorted(s['rir'] for s in a) != sorted(s['rir'] for s in b) and len(a) == len(b):
            reasons.append('effort_changed')
        ta, tb = top_sets(latest), top_sets(previous)
        if any(ta[k].get('failure_mode') and tb[k].get('failure_mode') and ta[k]['failure_mode'] != tb[k]['failure_mode']
               for k in set(ta) & set(tb)):
            reasons.append('failure_mode_changed')
        if any(s.get('reps') is None for s in a+b):
            reasons.append('rep_measurement_unavailable')
        if any(s.get('weight_kg') is None and not s.get('bodyweight') for s in a+b):
            reasons.append('load_unknown')
        if any(s.get('weight_kg') is not None for s in a+b) and (weight_basis(latest) == 'unknown' or weight_basis(previous) == 'unknown'):
            reasons.append('weight_basis_unknown')
        if any(s.get('bodyweight') for s in a+b):
            reasons.append('bodyweight_load_untracked')
        if [(s.get('side'), load_of(s)) for s in a] != [(s.get('side'), load_of(s)) for s in b]:
            reasons.append('set_structure_changed')
        if status == 'comparable' and reasons:
            status = 'limited'
    blocking = [r for r in reasons if r in BLOCKING_REASONS]
    if quality in ('improved', 'improved_with_load_reduction'):
        status = 'new_baseline'
        reasons.append('reported_quality_improvement')
        assessment = 'major_quality_progress' if quality == 'improved_with_load_reduction' else 'quality_progress'
    elif quality == 'degraded':
        status = 'limited'
        reasons.append('reported_quality_decline')
        assessment = 'quality_declined'
    elif status == 'new_baseline':
        assessment = 'establish_baseline'
    elif blocking:
        assessment = 'review_context'
    else:
        result.update(performance(latest, previous))
        assessment = result.pop('assessment')
        # A lower number may be an unrecorded technique change; never present it as regression without explicit quality.
        if quality != 'maintained' and (assessment == 'load_decreased' or
                                        ('notes_require_review' in reasons and assessment.endswith('decreased'))):
            assessment = 'review_context'
    return dict(comparability=status, reasons=reasons, blocking_reasons=blocking, assessment=assessment, **result)


def build_report(records, catalog, date, day_notes=None):
    end = datetime.strptime(date, '%Y-%m-%d').date()
    if end.isoformat() != date:
        raise ValueError('Date must be yyyy-MM-dd')
    for r in records:
        errors = context_errors(r.get('analysis_context'))
        if errors:
            raise ValueError('%s: %s' % (r.get('id'), '; '.join(errors)))
    eligible = [r for r in records if record_date(r) <= date]
    eligible.sort(key=lambda r: (record_date(r), r.get('sequence') or 0, r.get('id') or ''))
    catalog_map = {i['id']: i for i in catalog['exercises']}
    periods = layoff_periods(eligible, day_notes, date)
    windows = []
    for days in (7, 14):
        start = (end-timedelta(days=days-1)).isoformat()
        selected = [r for r in eligible if record_date(r) >= start]
        dates = sorted({record_date(r) for r in selected})
        muscles = {}
        for r in selected:
            metrics = set_metrics(r)
            if not metrics['working_set_entries']:
                continue
            for muscle in sorted(set(catalog_map.get(r['exercise_id'], {}).get('primary_muscles', []))):
                if muscle not in muscles:
                    muscles[muscle] = dict(muscle=muscle, dates=set(), **{k: 0 for k in metrics if k not in ('reps', 'external_volume_kg')})
                m = muscles[muscle]
                m['dates'].add(record_date(r))
                for k in metrics:
                    if k in m:
                        m[k] += metrics[k]
        muscle_rows = []
        for key in sorted(muscles):
            m = muscles[key]
            m['training_dates'] = sorted(m.pop('dates'))
            m['frequency'] = len(m['training_dates'])
            muscle_rows.append(m)
        windows.append(dict(days=days, start=start, end=date, training_dates=dates,
                            rest_dates=sorted((end-timedelta(days=i)).isoformat() for i in range(days) if (end-timedelta(days=i)).isoformat() not in dates),
                            working_set_entries=sum(set_metrics(r)['working_set_entries'] for r in selected),
                            muscles=muscle_rows))
    groups = {}
    for r in eligible:
        key = json.dumps(base_key(r, sequence_role(r, eligible, catalog_map)), ensure_ascii=False)
        groups.setdefault(key, []).append(r)
    trends = []
    for key, rs in groups.items():
        latest = rs[-1]
        if record_date(latest) < windows[1]['start']:
            continue
        previous = rs[-2] if len(rs) > 1 else None
        trends.append(dict(exercise_id=latest['exercise_id'], base_key=json.loads(key),
                           history=[snapshot(r) for r in rs[-3:][::-1]],
                           best_reps_by_load=best_reps_by_load(rs, periods),
                           **compare(latest, previous, eligible, periods)))
    trends.sort(key=lambda t: (t['exercise_id'], str(t['history'][0]['id'])))
    last_date = record_date(eligible[-1]) if eligible else None
    return dict(as_of=date, last_workout_date=last_date,
                days_since_last_workout=(end-datetime.strptime(last_date, '%Y-%m-%d').date()).days if last_date else None,
                layoffs=periods, return_phase=return_phase(eligible, periods, date),
                windows=windows, trends=trends,
                guidance='Descriptive only; review quality, recovery and historical notes before changing the plan. No automatic PR, overload or deload. '
                         'Limited comparisons still show numbers; read every reason as a caveat. '
                'After a layoff, compare post-return sessions with each other; pre-layoff numbers are reference only.',
                counting_basis='Catalog primary_muscles only; overlapping muscles are not additive. Unpaired rounds remain visible; unknown rounds are not imputed. '
                               'Back-off, drop, rest-pause and myo sets count as working set entries; trends use straight/top sets only.')
