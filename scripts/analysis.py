"""Read-only training analysis. Mirrored by analysis.ps1; no inferred facts."""
from datetime import datetime, timedelta
import json
import math

QUALITY_CHANGES = ('maintained', 'improved', 'improved_with_load_reduction', 'degraded')
SET_FIELDS = ('side', 'round', 'weight_kg', 'bodyweight', 'duration_sec', 'rir')


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


def work_sets(record):
    return [s for s in record.get('sets', []) if not s.get('warmup')]


def base_key(record):
    v, e = record.get('variant') or {}, record.get('equipment') or {}
    return [record.get('exercise_id')] + [v.get(k) for k in ('angle', 'posture', 'laterality', 'grip')] + [e.get('type'), e.get('name'), record.get('sequence')]


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
                reps=sum(s.get('reps') or 0 for s in sets),
                external_volume_kg=sum((s.get('weight_kg') or 0)*(s.get('reps') or 0) for s in sets))


def snapshot(record):
    return dict(id=record.get('id'), date=record['performed_at'][:10],
                sequence=record.get('sequence'), reported_name=record.get('reported_name'),
                notes=record.get('notes'), analysis_context=record.get('analysis_context'),
                sets=work_sets(record), **set_metrics(record))


def preceding(record, records):
    seq = record.get('sequence')
    same_day = [r for r in records if r['performed_at'][:10] == record['performed_at'][:10]]
    if seq is None or any(r.get('sequence') is None for r in same_day):
        return None
    earlier = sorted([r for r in same_day if r['sequence'] < seq], key=lambda r: r['sequence'])
    return [dict(key=base_key(r), sets=work_sets(r), context=r.get('analysis_context'), notes=r.get('notes')) for r in earlier]


def compare(latest, previous, records):
    c, p = latest.get('analysis_context') or {}, (previous or {}).get('analysis_context') or {}
    quality = c.get('quality_change')
    reasons, status, delta = [], 'comparable', None
    if previous is None:
        status, reasons = 'new_baseline', ['no_previous_base_match']
    else:
        for key in ('execution_standard', 'session_template'):
            if c.get(key) is not None and p.get(key) is not None and c[key] != p[key]:
                status = 'new_baseline'
                reasons.append(key + '_changed')
            elif not c.get(key) or not p.get(key):
                reasons.append(key + '_unknown')
        if latest.get('sequence') is None:
            reasons.append('sequence_unknown')
        e = latest.get('equipment') or {}
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
        a, b = work_sets(latest), work_sets(previous)
        if not a or not b or any(s.get('rir') is None for s in a+b):
            reasons.append('effort_unknown')
        if any(s.get('reps') is None for s in a+b):
            reasons.append('rep_measurement_unavailable')
        if any(s.get('weight_kg') is None and not s.get('bodyweight') for s in a+b):
            reasons.append('load_unknown')
        if any(s.get('bodyweight') for s in a+b):
            reasons.append('bodyweight_load_untracked')
        if [[s.get(k) for k in SET_FIELDS] for s in a] != [[s.get(k) for k in SET_FIELDS] for s in b]:
            reasons.append('set_conditions_changed')
        if status == 'comparable' and reasons:
            status = 'limited'
    if quality in ('improved', 'improved_with_load_reduction'):
        status = 'new_baseline'
        reasons.append('reported_quality_improvement')
        assessment = 'major_quality_progress' if quality == 'improved_with_load_reduction' else 'quality_progress'
    elif quality == 'degraded':
        status = 'limited'
        reasons.append('reported_quality_decline')
        assessment = 'quality_declined'
    elif status == 'comparable':
        delta = set_metrics(latest)['reps']-set_metrics(previous)['reps']
        assessment = 'reps_increased' if delta > 0 else ('reps_unchanged' if delta == 0 else 'reps_decreased')
    else:
        assessment = 'establish_baseline' if status == 'new_baseline' else 'review_context'
    return dict(comparability=status, reasons=reasons, assessment=assessment, reps_delta=delta)


def build_report(records, catalog, date):
    end = datetime.strptime(date, '%Y-%m-%d').date()
    if end.isoformat() != date:
        raise ValueError('Date must be yyyy-MM-dd')
    for r in records:
        errors = context_errors(r.get('analysis_context'))
        if errors:
            raise ValueError('%s: %s' % (r.get('id'), '; '.join(errors)))
    eligible = [r for r in records if r['performed_at'][:10] <= date]
    eligible.sort(key=lambda r: (r['performed_at'][:10], r.get('sequence') or 0, r.get('id') or ''))
    catalog_map = {i['id']: i for i in catalog['exercises']}
    windows = []
    for days in (7, 14):
        start = (end-timedelta(days=days-1)).isoformat()
        selected = [r for r in eligible if r['performed_at'][:10] >= start]
        dates = sorted({r['performed_at'][:10] for r in selected})
        muscles = {}
        for r in selected:
            metrics = set_metrics(r)
            if not metrics['working_set_entries']:
                continue
            for muscle in sorted(set(catalog_map.get(r['exercise_id'], {}).get('primary_muscles', []))):
                if muscle not in muscles:
                    muscles[muscle] = dict(muscle=muscle, dates=set(), **{k: 0 for k in metrics if k not in ('reps', 'external_volume_kg')})
                m = muscles[muscle]
                m['dates'].add(r['performed_at'][:10])
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
        key = json.dumps(base_key(r), ensure_ascii=False)
        groups.setdefault(key, []).append(r)
    trends = []
    for rs in groups.values():
        latest = rs[-1]
        if latest['performed_at'][:10] < windows[1]['start']:
            continue
        previous = rs[-2] if len(rs) > 1 else None
        trends.append(dict(exercise_id=latest['exercise_id'], base_key=base_key(latest),
                           history=[snapshot(r) for r in rs[-3:][::-1]],
                           **compare(latest, previous, eligible)))
    trends.sort(key=lambda t: (t['exercise_id'], str(t['history'][0]['id'])))
    last_date = eligible[-1]['performed_at'][:10] if eligible else None
    return dict(as_of=date, last_workout_date=last_date,
                days_since_last_workout=(end-datetime.strptime(last_date, '%Y-%m-%d').date()).days if last_date else None,
                windows=windows, trends=trends,
                guidance='Descriptive only; review quality, recovery and historical notes before changing the plan. No automatic PR, overload or deload.',
                counting_basis='Catalog primary_muscles only; overlapping muscles are not additive. Unpaired rounds remain visible; unknown rounds are not imputed.')
