"""Fill unstated variant/equipment fields from the user's own history (user rule, 2026-10-11).

Only null fields are filled. A value is used when the nearest evidence tier agrees on it:
same reported name (most frequent wins) -> same equipment name -> same exercise (only when
history knows a single value). Anything else is returned as ambiguous for the agent to ask.
"""
from collections import Counter
import re

FILL_FIELDS = (('equipment', 'name'), ('equipment', 'type'), ('variant', 'angle'),
               ('variant', 'posture'), ('variant', 'grip'))
# A known target value must match a known peer value exactly; unknown peers do not qualify.
STRICT = (('equipment', 'name'), ('equipment', 'type'), ('variant', 'angle'), ('variant', 'grip'))
METHODS = ('history_reported_name', 'history_equipment', 'history_exercise', 'name_unified', 'convention')


def norm(text):
    return re.sub(r"[\s\-_—–·,，。()（）/\\]+", "", (text or '').lower())


def get(record, path):
    if len(path) == 1:
        return record.get(path[0])
    return (record.get(path[0]) or {}).get(path[1])


def set_field(record, key, value):
    path = key.split('.')
    if len(path) == 1:
        record[key] = value
    else:
        record.setdefault(path[0], {})[path[1]] = value


def default_weight_basis(record, preference, catalog_type=None):
    """User rule (2026-10-11): basis follows the equipment type, whatever the laterality.

    machines (plate- or pin-loaded), cables and barbells are totals; dumbbells are per dumbbell.
    A record without a type uses the catalog type when every listed option maps to one basis.
    """
    if not isinstance(preference, dict) or preference.get('status') != 'user_confirmed':
        return None
    if record.get('weight_basis') not in (None, 'unknown'):
        return None
    if not any(s.get('weight_kg') is not None for s in record.get('sets') or []):
        return None
    mapping = preference.get('by_equipment_type') or {}
    etype = get(record, ('equipment', 'type'))
    if etype is not None:
        return mapping.get(etype)
    options = {mapping.get(t) for t in (catalog_type or '').split('_or_')} if catalog_type else {None}
    return options.pop() if len(options) == 1 else None


def compatible(target, peer):
    for path in STRICT:
        if get(target, path) is not None and get(peer, path) != get(target, path):
            return False
    for path in (('variant', 'posture'), ('variant', 'laterality')):
        if get(target, path) is not None and get(peer, path) not in (None, get(target, path)):
            return False
    return True


def decide(values, plurality):
    """Return (value, support) when confident, (None, counts) when ambiguous, None when no evidence."""
    counts = Counter(v for v in values if v is not None)
    if not counts:
        return None
    ranked = counts.most_common()
    if len(ranked) == 1 or (plurality and ranked[0][1] > ranked[1][1]):
        return ranked[0][0], ranked[0][1]
    return None, dict(counts)


def unify_name(name, exercise_id, history):
    """A stated name contained in exactly one more frequent historical name (less specific -> known).

    A more specific stated name is kept: it may be a different machine of the same brand.
    """
    counts = Counter(get(r, ('equipment', 'name')) for r in history
                     if r.get('exercise_id') == exercise_id and get(r, ('equipment', 'name')))
    if not name or name in counts:
        return None
    candidates = [h for h in counts if norm(name) and norm(name) in norm(h)]
    if len(candidates) == 1 and counts[candidates[0]] > counts.get(name, 0):
        return candidates[0], counts[candidates[0]]
    return None


def infer(target, history):
    """Return (fills, ambiguous); history must exclude the target. The target is not mutated."""
    target = {k: dict(target.get(k) or {}) if k in ('variant', 'equipment') else target.get(k) for k in target}
    eid = target.get('exercise_id')
    pool = [r for r in history if r.get('exercise_id') == eid]
    fills, ambiguous = {}, {}
    unified = unify_name(get(target, ('equipment', 'name')), eid, pool)
    if unified:
        fills['equipment.name'] = dict(value=unified[0], method='name_unified', support=unified[1],
                                       original=target['equipment']['name'])
        target['equipment']['name'] = unified[0]
    for path in FILL_FIELDS:
        if get(target, path) is not None:
            continue
        peers = [r for r in pool if compatible(target, r)]
        same_name = [r for r in peers if norm(r.get('reported_name')) == norm(target.get('reported_name'))]
        tiers = [('history_reported_name', same_name, True)]
        if get(target, ('equipment', 'name')) is not None:
            tiers.append(('history_equipment', peers, False))
        tiers.append(('history_exercise', peers, False))
        for method, rows, plurality in tiers:
            result = decide([get(r, path) for r in rows], plurality)
            if result is None:
                continue
            value, support = result
            key = '.'.join(path)
            if value is None:
                ambiguous[key] = support
            else:
                fills[key] = dict(value=value, method=method, support=support, original=None)
                target[path[0]][path[1]] = value
            break
    return fills, ambiguous


def inferred_errors(record):
    """Provenance must describe the record's current values."""
    data = record.get('inferred_fields')
    if data is None:
        return []
    if not isinstance(data, dict) or not data:
        return ['inferred_fields must be a nonempty object']
    errors = []
    allowed = {'.'.join(p) for p in FILL_FIELDS} | {'variant.laterality', 'weight_basis'}
    for key, item in data.items():
        if key not in allowed or not isinstance(item, dict):
            errors.append('invalid inferred_fields.' + str(key))
        elif item.get('method') not in METHODS:
            errors.append('invalid inferred_fields.%s.method' % key)
        elif get(record, tuple(key.split('.'))) != item.get('value'):
            errors.append('inferred_fields.%s does not match the record' % key)
    return errors
