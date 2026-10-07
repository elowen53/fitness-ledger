"""Ledger invariants shared by pre-write checks and validate."""
import math
import re
from datetime import datetime
from analysis import context_errors, record_date

WEIGHT_BASES = ('unknown', 'per_implement', 'per_side', 'total', 'machine_display')


def number(value, minimum=0, integer=False):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value >= minimum
            and (not integer or isinstance(value, int)))


def valid_date(value):
    try:
        return isinstance(value, str) and datetime.strptime(value, '%Y-%m-%d').strftime('%Y-%m-%d') == value
    except ValueError:
        return False


def valid_timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,7})?(?:Z|[+-]\d{2}:\d{2})', value):
        return False
    try:
        offset = datetime.fromisoformat(re.sub(r'(\.\d{6})\d', r'\1', value).replace('Z', '+00:00')).utcoffset()
        return offset is not None and abs(offset.total_seconds()) <= 14 * 3600
    except ValueError:
        return False


def record_errors(records, catalog):
    errors, ids, sequences, days = [], set(), set(), {}
    items = {i['id']: i for i in catalog['exercises']}
    for r in records:
        if not isinstance(r, dict):
            errors.append('record must be an object')
            continue
        rid = r.get('id')
        def fail(message):
            errors.append('%s: %s' % (rid, message))
        if not isinstance(rid, str) or not rid.strip():
            fail('id must be nonempty text')
        elif rid in ids:
            fail('duplicate record id')
        else:
            ids.add(rid)
        version = r.get('schema_version')
        if type(version) is not int or version not in (1, 2):
            fail('unsupported schema_version')
        if not isinstance(r.get('reported_name'), str) or not r['reported_name'].strip():
            fail('reported_name must be nonempty text')
        eid = r.get('exercise_id')
        item = items.get(eid) if isinstance(eid, str) else None
        if item is None:
            fail('unknown exercise_id')
        errors.extend('%s: %s' % (rid, e) for e in context_errors(r.get('analysis_context')))
        performed = r.get('performed_at')
        if version == 2:
            if not valid_date(r.get('training_date')):
                fail('invalid training_date')
            if not valid_timestamp(r.get('recorded_at')):
                fail('invalid recorded_at')
            if performed is not None and (not valid_timestamp(performed) or performed[:10] != r.get('training_date')):
                fail('performed_at must match training_date and include timezone')
        elif not valid_timestamp(performed):
            fail('invalid performed_at')
        date = record_date(r)
        seq = r.get('sequence')
        if seq is None and version == 1:
            pass  # Legacy unknown order is preserved, never invented.
        elif not number(seq, 1, integer=True):
            fail('sequence must be a positive integer')
        else:
            key = (date, seq)
            if key in sequences:
                fail('duplicate date/sequence')
            sequences.add(key)
        day = r.get('day_type')
        if day is not None or version == 2:
            if day not in ('standard', 'overload', 'deload'):
                fail('invalid day_type')
            elif date in days and days[date] != day:
                fail('mixed day_type on same date')
            else:
                days[date] = day
        if version == 2 and (not isinstance(r.get('day_type_basis'), str) or not r['day_type_basis'].strip()):
            fail('day_type_basis must be nonempty text')
        if r.get('weight_basis') is not None and r['weight_basis'] not in WEIGHT_BASES:
            fail('invalid weight_basis')
        if version == 2 and r.get('weight_basis') is None:
            fail('weight_basis required')
        v = r.get('variant')
        if not isinstance(v, dict):
            fail('variant must be an object')
            v = {}
        for field, allowed in (
            ('angle', ('flat', 'incline', 'decline', 'vertical')),
            ('posture', ('standing', 'seated', 'lying', 'kneeling')),
            ('laterality', ('bilateral', 'unilateral', 'alternating'))):
            value = v.get(field)
            if value is not None and (value not in allowed or (item and value not in item.get('supported_variants', {}).get(field, []))):
                fail('unsupported variant.' + field)
        if v.get('grip') is not None and (not isinstance(v['grip'], str) or not v['grip'].strip()):
            fail('grip must be nonempty text')
        if version == 2 and v.get('laterality') is None:
            fail('laterality required')
        if not isinstance(r.get('equipment'), dict):
            fail('equipment must be an object')
        sets = r.get('sets')
        if not isinstance(sets, list) or not sets:
            fail('sets must be a nonempty array')
            continue
        rounds = set()
        for index, s in enumerate(sets, 1):
            if not isinstance(s, dict):
                fail('set %s must be an object' % index)
                continue
            for field, minimum, integer in (('reps', 0, True), ('weight_kg', 0, False), ('rir', 0, False), ('duration_sec', 0, False)):
                value = s.get(field)
                if value is not None and (not number(value, minimum, integer) or (field == 'duration_sec' and value == 0)):
                    fail('invalid set %s %s' % (index, field))
            for field in ('warmup', 'bodyweight'):
                if not isinstance(s.get(field), bool):
                    fail('set %s %s must be boolean' % (index, field))
            if s.get('reps') is None and s.get('duration_sec') is None:
                fail('set %s needs reps or duration_sec' % index)
            side, rnd = s.get('side'), s.get('round')
            if side not in (None, 'left', 'right'):
                fail('invalid set side')
            if side is not None and v.get('laterality') not in ('unilateral', 'alternating', None):
                fail('side conflicts with laterality')
            if side is None and (rnd is not None or (version == 2 and v.get('laterality') == 'unilateral')):
                fail('unilateral sets require explicit side; unsided sets cannot have round')
            if rnd is not None and not number(rnd, 1, True):
                fail('round must be a positive integer')
            elif side in ('left', 'right') and rnd is not None:
                key = (bool(s.get('warmup')), side, rnd)
                if key in rounds:
                    fail('duplicate side/round within warmup or work sets')
                rounds.add(key)
            elif side is not None and version == 2:
                fail('sided sets require round')
            source = s.get('rir_source')
            if source is not None or version == 2:
                if source not in ('reported', 'profile_default', 'unknown'):
                    fail('invalid rir_source')
                elif (source == 'unknown') != (s.get('rir') is None):
                    fail('rir_source conflicts with rir')
                elif source == 'profile_default':
                    default = r.get('rir_default')
                    if (not isinstance(default, dict) or default.get('status') != 'user_confirmed'
                            or default.get('missing_means') != s.get('rir') or s.get('warmup')):
                        fail('profile_default requires matching confirmed snapshot and work set')
    return errors
