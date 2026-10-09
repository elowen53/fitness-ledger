#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
train_logbook.py - train-logbook 的 macOS CLI，使用 Python 3。

Commands: resolve, add, resequence, recent, stats, report, list, validate

Example (macOS):
    ./scripts/train-logbook.sh add --exercise "上斜器械推胸" \
        --sets "12x40@2","10x45@1" --equipment "Life Fitness Insignia" \
        --notes "座椅 4 档" --sequence 1

"""

import argparse
import json
import os
import re
import sys
import uuid
import tempfile
from contextlib import contextmanager
from datetime import datetime
from analysis import build_report, context_errors, QUALITY_CHANGES, record_date, weight_basis
from validation import record_errors, WEIGHT_BASES, number, valid_date, valid_timestamp


# ---------------------------------------------------------------------------
# Paths / project root
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_PATH = os.path.join(PROJECT_ROOT, "catalog", "exercises.json")
WORKOUT_ROOT = os.path.join(PROJECT_ROOT, "data", "workouts")


# ---------------------------------------------------------------------------
# Case-insensitive variant words extracted from reported exercise names.
# ---------------------------------------------------------------------------

VARIANT_WORDS = [
    ("angle", "incline", r"坐姿仰卧|上斜|上倾|incline|inclined"),
    ("angle", "decline", r"下斜|下倾|decline|declined"),
    ("angle", "flat", r"平板|水平|flat"),
    ("angle", "vertical", r"垂直|vertical"),
    ("posture", "seated", r"坐姿|坐式|seated"),
    ("posture", "standing", r"站姿|站式|standing"),
    ("posture", "lying", r"仰卧|俯卧|lying"),
    ("posture", "kneeling", r"跪姿|kneeling"),
    ("laterality", "unilateral", r"单侧|单臂|单腿|unilateral|single[- ]arm|single[- ]leg"),
    ("laterality", "alternating", r"交替|alternating"),
    ("laterality", "bilateral", r"双侧|双臂|双腿|bilateral"),
    ("grip", "narrow_neutral", r"窄距对握|窄握对握|窄距中立握|narrow neutral"),
    ("grip", "wide", r"宽距|宽握|wide grip"),
    ("grip", "narrow", r"窄距|窄握|narrow grip"),
    ("grip", "neutral", r"对握|中立握|neutral grip"),
]

_VARIANT_PATTERNS = [(field, value, re.compile(pattern, re.IGNORECASE))
                     for field, value, pattern in VARIANT_WORDS]


def normalize_name(name):
    if name is None:
        return ""
    text = name.lower()
    return re.sub(r"[\s\-_—–·,，。()（）/\\]+", "", text)


def get_variant(name):
    result = {"angle": None, "posture": None, "laterality": None, "grip": None}
    text = name or ""
    for field, value, pattern in _VARIANT_PATTERNS:
        if result[field] is None and pattern.search(text):
            result[field] = value
    return result


def get_equipment_type(name, catalog_type):
    text = name or ""
    if re.search(r"哑铃|dumbbell", text, re.IGNORECASE):
        return "dumbbell"
    if re.search(r"杠铃|barbell", text, re.IGNORECASE):
        return "barbell"
    if re.search(r"绳索|钢线|龙门架|拉力器|cable", text, re.IGNORECASE):
        return "cable"
    if re.search(r"豪斯特|hoist", text, re.IGNORECASE):
        return "machine"
    if re.search(r"器械|机器|推胸机|腿举机|machine", text, re.IGNORECASE):
        return "machine"
    if re.search(r"自重|bodyweight", text, re.IGNORECASE):
        return "bodyweight"
    if catalog_type in ("machine", "barbell", "dumbbell", "cable"):
        return catalog_type
    return None


def remove_variant_words(name):
    result = name or ""
    for _, _, pattern in _VARIANT_PATTERNS:
        result = pattern.sub("", result)
    return result


# ---------------------------------------------------------------------------
# Catalog / history access
# ---------------------------------------------------------------------------

def read_catalog(catalog_path=CATALOG_PATH):
    if not os.path.exists(catalog_path):
        raise SystemExit("动作词典不存在: %s" % catalog_path)
    with open(catalog_path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def read_workout_records(workout_root=WORKOUT_ROOT):
    records = []
    if not os.path.isdir(workout_root):
        return records
    for dirpath, _, filenames in os.walk(workout_root):
        for filename in sorted(filenames):
            if not filename.endswith(".jsonl"):
                continue
            path = os.path.join(dirpath, filename)
            with open(path, "r", encoding="utf-8-sig") as f:
                for line_no, line in enumerate(f, start=1):
                    if not line.strip():
                        continue
                    try:
                        records.append(json.loads(line))
                    except ValueError:
                        raise SystemExit("无效 JSONL: %s:%d" % (path, line_no))
    return records


def collect_history_names(records):
    historical = {}
    for record in records:
        hid = record.get("exercise_id")
        hname = record.get("reported_name")
        if not hid or not hname:
            continue
        historical.setdefault(hid, [])
        if hname not in historical[hid]:
            historical[hid].append(hname)
    return historical


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def resolve_exercise(name, records=None, catalog=None, catalog_path=CATALOG_PATH,
                     workout_root=WORKOUT_ROOT):
    if not name or not name.strip():
        raise SystemExit("需要 --exercise。")
    if catalog is None:
        catalog = read_catalog(catalog_path)
    if records is None:
        records = read_workout_records(workout_root)
    normalized = normalize_name(name)
    base_normalized = normalize_name(remove_variant_words(name))
    historical_names = collect_history_names(records)

    candidates = []
    for item in catalog["exercises"]:
        best = 0
        matched_alias = None
        matched_source = None
        names = []
        for catalog_name in ([item.get("canonical_name")] + list(item.get("aliases") or [])):
            names.append({"name": catalog_name, "source": "catalog"})
        if item.get("id") in historical_names:
            for history_name in historical_names[item["id"]]:
                names.append({"name": history_name, "source": "history"})
        for entry in names:
            alias = entry["name"] or ""
            a = normalize_name(alias)
            score = 0
            if normalized == a:
                score = 100
            elif base_normalized == a:
                score = 96
            elif len(a) >= 2 and normalized.find(a) != -1:
                score = 72 + min(18, len(a) * 2)
            elif len(a) >= 2 and base_normalized.find(a) != -1:
                score = 68 + min(18, len(a) * 2)
            elif len(normalized) >= 2 and a.find(normalized) != -1:
                score = 65 + min(15, len(normalized) * 2)
            if (score > best or
                    (score == best and entry["source"] == "catalog" and matched_source == "history")):
                best = score
                matched_alias = alias
                matched_source = entry["source"]
        if best >= 65:
            candidates.append({
                "id": item.get("id"),
                "canonical_name": item.get("canonical_name"),
                "score": best,
                "matched_alias": matched_alias,
                "matched_source": matched_source,
            })

    candidates.sort(key=lambda c: (-c["score"], c["id"] or ""))
    status = "unknown"
    selected = None
    if candidates:
        margin = candidates[0]["score"] - candidates[1]["score"] if len(candidates) > 1 else 100
        if candidates[0]["score"] >= 75 and margin >= 8:
            status = "resolved"
            selected = candidates[0]
        else:
            status = "ambiguous"

    return {
        "status": status,
        "input": name,
        "exercise": selected,
        "variant": get_variant(name),
        "candidates": candidates[:5],
    }


# ---------------------------------------------------------------------------
# Set parsing
# ---------------------------------------------------------------------------

def parse_set(spec, warmup):
    text = spec.strip().lower()
    text = re.sub(r"公斤|千克", "kg", text)
    text = text.replace("次", "")
    side = None
    m = re.match(r"^(右手|右|right|r|左手|左|left|l)\s*[:：]\s*(.+)$", text)
    if m:
        side = "right" if m.group(1) in ("右手", "右", "right", "r") else "left"
        text = m.group(2)

    parsed = {
        "reps": None,
        "weight_kg": None,
        "rir": None,
        "duration_sec": None,
        "bodyweight": False,
        "warmup": warmup,
        "side": side,
        "round": None,
    }

    m = re.match(r"^(\d+)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*(?:kg)?(?:\s*@\s*(\d+(?:\.\d+)?))?$", text)
    if m:
        parsed["reps"] = int(m.group(1))
        parsed["weight_kg"] = float(m.group(2))
        if m.group(3):
            parsed["rir"] = float(m.group(3))
        return parsed

    m = re.match(r"^(\d+)\s*[x×*]\s*(?:bw|bodyweight|自重)(?:\s*@\s*(\d+(?:\.\d+)?))?$", text)
    if m:
        parsed["reps"] = int(m.group(1))
        parsed["bodyweight"] = True
        if m.group(2):
            parsed["rir"] = float(m.group(2))
        return parsed

    m = re.match(r"^(\d+(?:\.\d+)?)\s*(?:s|秒)$", text)
    if m:
        parsed["duration_sec"] = float(m.group(1))
        return parsed

    raise SystemExit("无法解析组 '%s'。使用 12x40@2、12xbw 或 30s。" % spec)


# ---------------------------------------------------------------------------
# Date / id helpers
# ---------------------------------------------------------------------------

def iso7(dt):
    """Format a timezone-aware ISO timestamp with 7 fractional digits."""
    return dt.strftime('%Y-%m-%dT%H:%M:%S.') + ('%06d0' % dt.microsecond) + dt.strftime('%z')[:3] + ':' + dt.strftime('%z')[3:]


def now_local():
    return datetime.now().astimezone()


def new_record_id(performed):
    return performed.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


# ---------------------------------------------------------------------------
# Variant validation
# ---------------------------------------------------------------------------

def assert_variant_allowed(catalog_item, field, value):
    if not value:
        return
    allowed = (catalog_item.get("supported_variants") or {}).get(field) or []
    if value not in allowed:
        raise SystemExit(
            "动作 %s 不支持 %s=%s；允许值: %s" % (catalog_item.get("id"), field, value, ", ".join(allowed)))


# ---------------------------------------------------------------------------
# Command: add
# ---------------------------------------------------------------------------

def command_add(args):
    context = {key: value for key, value in (
        ('session_template', args.session_template), ('execution_standard', args.execution_standard),
        ('quality_change', args.quality_change), ('rest_sec', args.rest_sec)) if value is not None}
    errors = context_errors(context)
    if errors:
        raise SystemExit('; '.join(errors))
    sets = []
    for set_value in args.sets or []:
        for piece in re.split(r"[,，]", set_value):
            if piece.strip():
                sets.append(piece.strip())
    if not sets:
        raise SystemExit("需要至少一个 --sets 值。")
    if args.warmup_count < 0 or args.warmup_count > len(sets):
        raise SystemExit("WarmupCount 必须在 0 到组数之间。")

    resolution_input = args.resolve_as if args.resolve_as else args.exercise
    resolution = resolve_exercise(resolution_input, catalog_path=args.catalog_path,
                                  workout_root=args.workout_root)
    if resolution["status"] != "resolved":
        sys.stderr.write("动作名称未唯一解析（%s）。先运行 resolve 并确认动作。\n" % resolution["status"])
        sys.exit(1)

    catalog = read_catalog(args.catalog_path)
    catalog_item = next((i for i in catalog["exercises"] if i.get("id") == resolution["exercise"]["id"]), None)
    if catalog_item is None:
        raise SystemExit("词典中找不到动作 %s" % resolution["exercise"]["id"])

    # ResolveAs chooses identity only; the user's name remains the variant source.
    variant = get_variant(args.exercise)
    final_angle = args.angle or variant['angle']
    final_posture = args.posture or variant['posture']
    final_grip = args.grip or variant['grip']
    parsed_sets = [parse_set(spec, i < args.warmup_count) for i, spec in enumerate(sets)]
    sided = any(s['side'] for s in parsed_sets)
    final_laterality = args.laterality or variant['laterality'] or ('unilateral' if sided else 'bilateral')
    for field, value in (('angle', final_angle), ('posture', final_posture), ('laterality', final_laterality)):
        assert_variant_allowed(catalog_item, field, value)
    now = now_local()
    training_date = args.date or (args.performed_at[:10] if args.performed_at else now.strftime('%Y-%m-%d'))
    if not valid_date(training_date):
        raise SystemExit('Date 必须是 yyyy-MM-dd。')
    if args.performed_at and (not valid_timestamp(args.performed_at) or args.performed_at[:10] != training_date):
        raise SystemExit('PerformedAt 必须包含时区且与 Date 一致。')
    if args.sequence < 1:
        raise SystemExit('需要大于 0 的 --sequence。')

    default = None
    profile_path = os.path.join(args.project_root, 'profile', 'training-preferences.json')
    if os.path.exists(profile_path):
        with open(profile_path, encoding='utf-8-sig') as f:
            default = json.load(f).get('recording_preferences', {}).get('rir_default')
        if default is not None and (not isinstance(default, dict) or default.get('status') != 'user_confirmed'
                                    or not number(default.get('missing_means'))):
            raise SystemExit('无效的已确认 RIR 默认偏好。')
    used_default = False
    side_rounds = {}
    for parsed_set in parsed_sets:
        if parsed_set['side']:
            key = (parsed_set['warmup'], parsed_set['side'])
            side_rounds[key] = side_rounds.get(key, 0) + 1
            parsed_set['round'] = side_rounds[key]
        parsed_set['rir_source'] = 'reported' if parsed_set['rir'] is not None else 'unknown'
        if parsed_set['rir'] is None and not parsed_set['warmup'] and default is not None:
            parsed_set['rir'] = default['missing_means']
            parsed_set['rir_source'] = 'profile_default'
            used_default = True

    record = {
        "schema_version": 2,
        "id": new_record_id(now),
        "training_date": training_date,
        "recorded_at": iso7(now),
        "performed_at": args.performed_at,
        "weight_basis": args.weight_basis,
        "day_type": args.day_type,
        "day_type_basis": args.day_type_basis,
        "sequence": args.sequence if args.sequence and args.sequence > 0 else None,
        "exercise_id": resolution["exercise"]["id"],
        "reported_name": args.exercise,
        "variant": {
            "angle": final_angle,
            "posture": final_posture,
            "laterality": final_laterality,
            "grip": final_grip,
        },
        "equipment": {
            "type": get_equipment_type(args.exercise, catalog_item.get("equipment_type")),
            "name": args.equipment if args.equipment else None,
        },
        "sets": parsed_sets,
        "notes": args.notes if args.notes else None,
        "tags": [t for t in (args.tags or []) if t.strip()],
    }

    if used_default:
        record['rir_default'] = default
    if context:
        record['analysis_context'] = context
    errors = record_errors(read_workout_records(args.workout_root) + [record], catalog)
    if errors:
        raise SystemExit('\n'.join(errors))

    directory = os.path.join(args.workout_root, training_date[:4], training_date[5:7])
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, training_date + ".jsonl")
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

    if args.json:
        print(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    else:
        print("已记录: %s [%s]" % (catalog_item.get("canonical_name"), catalog_item.get("id")))
        print("日期: %s；顺序: %s；组数: %d；文件: %s" % (
            training_date, record["sequence"], len(parsed_sets), path))
        print("变体: angle=%s, posture=%s, laterality=%s, grip=%s；器械类型: %s；器械: %s" % (
            final_angle, final_posture, final_laterality, final_grip,
            record["equipment"]["type"], args.equipment or ""))


# ---------------------------------------------------------------------------
# Command: resolve
# ---------------------------------------------------------------------------

def command_resolve(args):
    result = resolve_exercise(args.exercise, catalog_path=args.catalog_path,
                              workout_root=args.workout_root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return
    print("状态: %s" % result["status"])
    if result["exercise"]:
        ex = result["exercise"]
        print("动作: %s [%s]" % (ex["canonical_name"], ex["id"]))
        print("命中: %s；来源: %s；置信分: %s" % (ex["matched_alias"], ex["matched_source"], ex["score"]))
    v = result["variant"]
    print("变体: angle=%s, posture=%s, laterality=%s" % (v["angle"], v["posture"], v["laterality"]))
    if result["status"] != "resolved":
        print("候选:")
        print("id\tcanonical_name\tscore\tmatched_alias\tmatched_source")
        for c in result["candidates"]:
            print("%s\t%s\t%s\t%s\t%s" % (c["id"], c["canonical_name"], c["score"],
                                          c["matched_alias"], c["matched_source"]))
        sys.exit(2)


# ---------------------------------------------------------------------------
# Command: recent
# ---------------------------------------------------------------------------

def command_recent(args):
    catalog = read_catalog(args.catalog_path)
    name_map = {item["id"]: item.get("canonical_name") for item in catalog["exercises"]}
    records = read_workout_records(args.workout_root)
    records.sort(key=lambda r: (r.get("sequence") is None, r.get("sequence") or 0, r.get("id") or ""))
    records.sort(key=record_date, reverse=True)
    rows = []
    for record in records[:args.limit]:
        variant = "/".join(v for v in [
            record.get("variant", {}).get("angle"),
            record.get("variant", {}).get("posture"),
            record.get("variant", {}).get("laterality"),
            record.get("variant", {}).get("grip"),
        ] if v)
        equipment = "/".join(v for v in [
            (record.get("equipment") or {}).get("type"),
            (record.get("equipment") or {}).get("name"),
        ] if v)
        rows.append({
            "date": record_date(record),
            "day_type": record.get("day_type") or "unclassified",
            "sequence": record.get("sequence"),
            "exercise": name_map.get(record.get("exercise_id")),
            "variant": variant,
            "equipment": equipment,
            "sets": len(record.get("sets") or []),
            "id": record.get("id"),
        })
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
    else:
        print("date\tday_type\tsequence\texercise\tvariant\tequipment\tsets\tid")
        for r in rows:
            print("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % (
                r["date"], r["day_type"], r["sequence"], r["exercise"],
                r["variant"], r["equipment"], r["sets"], r["id"]))


# ---------------------------------------------------------------------------
# Command: resequence
# ---------------------------------------------------------------------------

def command_resequence(args):
    if not args.id:
        raise SystemExit("需要 --id。")
    if args.sequence < 1:
        raise SystemExit("需要大于 0 的 --sequence。")
    records = read_workout_records(args.workout_root)
    matches = [r for r in records if r.get('id') == args.id]
    if len(matches) != 1:
        raise SystemExit('记录 ID 不存在或重复: %s' % args.id)
    matches[0]['sequence'] = args.sequence
    errors = record_errors(records, read_catalog(args.catalog_path))
    if errors:
        raise SystemExit('\n'.join(errors))
    for dirpath, _, filenames in os.walk(args.workout_root):
        for filename in sorted(filenames):
            if not filename.endswith('.jsonl'):
                continue
            path = os.path.join(dirpath, filename)
            with open(path, encoding='utf-8-sig') as f:
                lines = f.read().splitlines()
            for i, line in enumerate(lines):
                if line.strip() and json.loads(line).get('id') == args.id:
                    lines[i] = json.dumps(matches[0], ensure_ascii=False, separators=(',', ':'))
                    fd, temporary = tempfile.mkstemp(dir=dirpath, prefix='.resequence-')
                    try:
                        with os.fdopen(fd, 'w', encoding='utf-8') as f:
                            f.write('\n'.join(lines) + '\n')
                            f.flush()
                            os.fsync(f.fileno())
                        os.replace(temporary, path)
                    finally:
                        if os.path.exists(temporary):
                            os.unlink(temporary)
                    print('已更新动作顺序: %s -> %d' % (args.id, args.sequence))
                    return


# ---------------------------------------------------------------------------
# Command: stats
# ---------------------------------------------------------------------------

def command_stats(args):
    records = read_workout_records(args.workout_root)
    if args.exercise:
        resolution = resolve_exercise(args.exercise, records=records,
                                      catalog_path=args.catalog_path,
                                      workout_root=args.workout_root)
        if resolution["status"] != "resolved":
            raise SystemExit("统计筛选动作未唯一解析。")
        exercise_id = resolution["exercise"]["id"]
        records = [r for r in records if r.get("exercise_id") == exercise_id]

    expanded = []
    for record in records:
        working_sets = [s for s in (record.get("sets") or []) if not s.get("warmup")]
        reps = sum(s["reps"] for s in working_sets if s.get("reps") is not None)
        volume = 0.0
        for s in working_sets:
            if s.get("reps") is not None and s.get("weight_kg") is not None:
                volume += float(s["reps"]) * float(s["weight_kg"])
        variant = record.get("variant") or {}
        variant_key = "/".join(variant.get(k) or "-" for k in ("angle", "posture", "laterality", "grip"))
        equipment_name = "/".join(v for v in [
            (record.get("equipment") or {}).get("type"),
            (record.get("equipment") or {}).get("name"),
        ] if v) or "-"
        expanded.append({
            "exercise_id": record.get("exercise_id"),
            "variant": variant_key,
            "equipment": equipment_name,
            "sequence": record.get("sequence"),
            "weight_basis": weight_basis(record),
            "sessions": 1,
            "sets": len(working_sets),
            "reps": reps,
            "volume_kg": volume,
        })

    groups = {}
    for row in expanded:
        key = (row["exercise_id"], row["variant"], row["equipment"], row["sequence"], row["weight_basis"])
        if key not in groups:
            groups[key] = {
                "exercise_id": row["exercise_id"],
                "variant": row["variant"],
                "equipment": row["equipment"],
                "sequence": row["sequence"],
                "weight_basis": row["weight_basis"],
                "entries": 0,
                "sets": 0,
                "reps": 0,
                "volume_kg": 0.0,
            }
        g = groups[key]
        g["entries"] += row["sessions"]
        g["sets"] += row["sets"]
        g["reps"] += row["reps"]
        g["volume_kg"] += row["volume_kg"]

    rows = list(groups.values())
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
    else:
        rows.sort(key=lambda r: (r["exercise_id"] or "", r["variant"], r["equipment"],
                                 r["sequence"] is None, r["sequence"]))
        print("exercise_id\tvariant\tequipment\tsequence\tweight_basis\tentries\tsets\treps\tvolume_kg")
        for r in rows:
            print("%s\t%s\t%s\t%s\t%s\t%d\t%d\t%d\t%s" % (
                r["exercise_id"], r["variant"], r["equipment"], r["sequence"], r["weight_basis"],
                r["entries"], r["sets"], r["reps"], r["volume_kg"]))


# ---------------------------------------------------------------------------
# Command: list
# ---------------------------------------------------------------------------

def command_list(args):
    catalog = read_catalog(args.catalog_path)
    rows = [{
        "id": item.get("id"),
        "name": item.get("canonical_name"),
        "pattern": item.get("movement_pattern"),
        "aliases": len(item.get("aliases") or []),
    } for item in catalog["exercises"]]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
    else:
        print("id\tname\tpattern\taliases")
        for r in rows:
            print("%s\t%s\t%s\t%d" % (r["id"], r["name"], r["pattern"], r["aliases"]))


# ---------------------------------------------------------------------------
# Command: validate
# ---------------------------------------------------------------------------

def command_validate(args):
    catalog = read_catalog(args.catalog_path)
    errors = []
    ids = {}
    aliases = {}
    for item in catalog["exercises"]:
        item_id = item.get("id") or ""
        if not item_id or not re.fullmatch(r"[a-z0-9_]+", item_id, re.IGNORECASE):
            errors.append("无效 ID: %s" % item_id)
        if item_id in ids:
            errors.append("重复 ID: %s" % item_id)
        else:
            ids[item_id] = True
        if item.get("naming_status") == "user_defined":
            if not item.get("definition"):
                errors.append("自定义动作 %s 缺少 definition" % item_id)
            if not item.get("primary_muscles"):
                errors.append("自定义动作 %s 缺少 primary_muscles" % item_id)
            if item.get("target_basis") != "user_confirmed":
                errors.append("自定义动作 %s 的 target_basis 必须是 user_confirmed" % item_id)
        for name in ([item.get("canonical_name")] + list(item.get("aliases") or [])):
            normalized = normalize_name(name)
            if normalized in aliases and aliases[normalized] != item_id:
                errors.append("别名冲突 '%s': %s / %s" % (name, aliases[normalized], item_id))
            else:
                aliases[normalized] = item_id

    records = read_workout_records(args.workout_root)
    errors.extend(record_errors(records, catalog))

    if errors:
        for e in errors:
            sys.stderr.write("%s\n" % e)
        sys.exit(1)

    result = {
        "status": "ok",
        "exercises": len(catalog["exercises"]),
        "workout_records": len(records),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    else:
        print("校验通过: %d 个动作，%d 条训练记录。" % (result["exercises"], result["workout_records"]))


# ---------------------------------------------------------------------------
# Argument handling
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="train-logbook",
        description="train-logbook macOS CLI（Python 3）。",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    def add_common(p):
        p.add_argument("--exercise", dest="exercise", default=None, help="动作原始叫法")
        p.add_argument("--resolve-as", dest="resolve_as", default=None, help="归一化到规范动作名")
        p.add_argument("--sets", dest="sets", nargs="+", default=None, help="组,如 12x40@2")
        p.add_argument("--date", dest="date", default=None, help="训练日期 yyyy-MM-dd")
        p.add_argument('--performed-at', dest='performed_at', default=None, help='用户报告的实际训练时间（带时区，可选）')
        p.add_argument('--weight-basis', dest='weight_basis', choices=WEIGHT_BASES, default='unknown', help='已确认重量口径')
        p.add_argument("--equipment", dest="equipment", default=None, help="具体器械")
        p.add_argument("--angle", dest="angle", default=None, help="flat/incline/decline/vertical")
        p.add_argument("--posture", dest="posture", default=None, help="seated/standing/lying/kneeling")
        p.add_argument("--laterality", dest="laterality", default=None, help="bilateral/unilateral/alternating")
        p.add_argument("--grip", dest="grip", default=None, help="narrow/wide/neutral/narrow_neutral")
        p.add_argument("--notes", dest="notes", default=None, help="备注")
        p.add_argument("--session-template", dest="session_template", default=None, help="已确认的训练模板标识（可选）")
        p.add_argument("--execution-standard", dest="execution_standard", default=None, help="已确认的执行标准版本（可选）")
        p.add_argument("--quality-change", dest="quality_change", choices=QUALITY_CHANGES, default=None, help="用户明确报告的质量状态（可选）")
        p.add_argument("--rest-sec", dest="rest_sec", type=float, default=None, help="当次实际统一组间休息秒数（可选）")
        p.add_argument("--tags", dest="tags", nargs="+", default=None, help="标签")
        p.add_argument("--day-type", dest="day_type", default="standard",
                       choices=("standard", "overload", "deload"), help="standard/overload/deload")
        p.add_argument("--day-type-basis", dest="day_type_basis", default="default", help="day_type 依据")
        p.add_argument("--sequence", dest="sequence", type=int, default=0, help="训练内动作顺序(1 起)")
        p.add_argument("--warmup-count", dest="warmup_count", type=int, default=0, help="前 N 组为热身")
        p.add_argument("--limit", dest="limit", type=int, default=10, help="recent 条数")
        p.add_argument("--json", dest="json", action="store_true", help="输出 JSON")
        p.add_argument("--id", dest="id", default=None, help="记录 ID(resequence 用)")
        p.add_argument("--project-root", dest="project_root", default=PROJECT_ROOT,
                       help="仓库根目录(默认脚本上级目录)")

    for name in ("resolve", "add", "resequence", "recent", "stats", "report", "validate", "list"):
        p = sub.add_parser(name, help="train-logbook %s" % name)
        add_common(p)
    return parser


@contextmanager
def write_lock(root):
    """Serialize ledger writes with an exclusive file; never steal a stale lock."""
    path = os.path.join(root, '.train-logbook-write.lock')
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise SystemExit('账本正在写入，或存在遗留 .train-logbook-write.lock；确认没有写入进程后重试。')
    try:
        os.close(fd)
        yield
    finally:
        os.unlink(path)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        sys.exit(2)

    args.catalog_path = os.path.join(args.project_root, "catalog", "exercises.json")
    args.workout_root = os.path.join(args.project_root, "data", "workouts")

    if args.command == "resolve":
        command_resolve(args)
    elif args.command == "add":
        with write_lock(args.project_root):
            command_add(args)
    elif args.command == "recent":
        command_recent(args)
    elif args.command == "resequence":
        with write_lock(args.project_root):
            command_resequence(args)
    elif args.command == "stats":
        command_stats(args)
    elif args.command == "report":
        try:
            result = build_report(read_workout_records(args.workout_root), read_catalog(args.catalog_path),
                                  args.date or now_local().strftime('%Y-%m-%d'))
        except ValueError as error:
            raise SystemExit(str(error))
        print(json.dumps(result, ensure_ascii=False, indent=None if args.json else 2))
    elif args.command == "list":
        command_list(args)
    elif args.command == "validate":
        command_validate(args)


if __name__ == "__main__":
    main()
