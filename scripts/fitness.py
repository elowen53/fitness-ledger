#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fitness.py - cross-platform CLI for the fitness ledger (macOS / Linux).

Mirrors scripts/fitness.ps1 command-for-command, so the ledger can be
maintained identically from Windows (PowerShell) and macOS (Python 3).

Commands: resolve, add, resequence, recent, stats, list, validate

Example (macOS):
    ./scripts/fitness.sh add --exercise "上斜器械推胸" \
        --sets "12x40@2","10x45@1" --equipment "Life Fitness Insignia" \
        --notes "座椅 4 档" --sequence 1

PowerShell-style flags (-Exercise, -Sets ...) are accepted too.
"""

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime


# ---------------------------------------------------------------------------
# Paths / project root
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_PATH = os.path.join(PROJECT_ROOT, "catalog", "exercises.json")
WORKOUT_ROOT = os.path.join(PROJECT_ROOT, "data", "workouts")


# ---------------------------------------------------------------------------
# Variant words (mirrors $VariantWords in fitness.ps1; PowerShell -match is
# case-insensitive, so we use re.IGNORECASE)
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
    """Format a tz-aware datetime like PowerShell's 'o' (7 fractional digits)."""
    s = dt.isoformat(timespec="microseconds")
    if "." in s:
        base, rest = s.split(".", 1)
        frac, _, tz = rest.partition("+")
        tz = "+" + tz
        return "%s.%s0%s" % (base, frac[:6].ljust(6, "0"), tz)
    return s


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

    final_angle = args.angle if args.angle else resolution["variant"]["angle"]
    final_posture = args.posture if args.posture else resolution["variant"]["posture"]
    final_laterality = args.laterality if args.laterality else resolution["variant"]["laterality"]
    if args.grip:
        final_grip = args.grip
    elif args.resolve_as:
        final_grip = get_variant(args.exercise)["grip"]
    else:
        final_grip = resolution["variant"]["grip"]

    assert_variant_allowed(catalog_item, "angle", final_angle)
    assert_variant_allowed(catalog_item, "posture", final_posture)
    assert_variant_allowed(catalog_item, "laterality", final_laterality)

    if args.date:
        try:
            parsed_date = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            raise SystemExit("Date 必须是 yyyy-MM-dd。")
        now = now_local()
        performed = parsed_date.replace(hour=now.hour, minute=now.minute,
                                        second=now.second, microsecond=now.microsecond,
                                        tzinfo=now.tzinfo)
    else:
        performed = now_local()

    parsed_sets = []
    side_rounds = {"left": 0, "right": 0}
    for i, spec in enumerate(sets):
        parsed_set = parse_set(spec, i < args.warmup_count)
        if parsed_set["side"]:
            side_rounds[parsed_set["side"]] += 1
            parsed_set["round"] = side_rounds[parsed_set["side"]]
        parsed_sets.append(parsed_set)

    record = {
        "schema_version": 1,
        "id": new_record_id(performed),
        "performed_at": iso7(performed),
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

    directory = os.path.join(args.workout_root, performed.strftime("%Y"), performed.strftime("%m"))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, performed.strftime("%Y-%m-%d") + ".jsonl")
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

    if args.json:
        print(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    else:
        print("已记录: %s [%s]" % (catalog_item.get("canonical_name"), catalog_item.get("id")))
        print("日期: %s；顺序: %s；组数: %d；文件: %s" % (
            performed.strftime("%Y-%m-%d"), record["sequence"], len(parsed_sets), path))
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
    records.sort(key=lambda r: r.get("performed_at") or "", reverse=True)
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
            "date": (record.get("performed_at") or "")[:10],
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
    found = False
    for dirpath, _, filenames in os.walk(args.workout_root):
        for filename in sorted(filenames):
            if not filename.endswith(".jsonl"):
                continue
            path = os.path.join(dirpath, filename)
            with open(path, "r", encoding="utf-8-sig") as f:
                lines = f.read().splitlines()
            updated_lines = []
            changed = False
            for line in lines:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("id") == args.id:
                    if found:
                        raise SystemExit("记录 ID 重复: %s" % args.id)
                    record["sequence"] = args.sequence
                    updated_lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                    changed = True
                    found = True
                else:
                    updated_lines.append(line)
            if changed:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(updated_lines) + "\n")
    if not found:
        raise SystemExit("找不到记录: %s" % args.id)
    print("已更新动作顺序: %s -> %d" % (args.id, args.sequence))


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
            "sessions": 1,
            "sets": len(working_sets),
            "reps": reps,
            "volume_kg": volume,
        })

    groups = {}
    for row in expanded:
        key = (row["exercise_id"], row["variant"], row["equipment"], row["sequence"])
        if key not in groups:
            groups[key] = {
                "exercise_id": row["exercise_id"],
                "variant": row["variant"],
                "equipment": row["equipment"],
                "sequence": row["sequence"],
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
        print("exercise_id\tvariant\tequipment\tsequence\tentries\tsets\treps\tvolume_kg")
        for r in rows:
            print("%s\t%s\t%s\t%s\t%d\t%d\t%d\t%s" % (
                r["exercise_id"], r["variant"], r["equipment"], r["sequence"],
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
    sequence_by_date = {}
    day_type_by_date = {}
    allowed_day_types = ("standard", "overload", "deload")
    for record in records:
        record_id = record.get("id")
        if record.get("schema_version") != 1:
            errors.append("记录 %s schema_version 不是 1" % record_id)
        if record.get("exercise_id") not in ids:
            errors.append("记录 %s 引用了未知动作 %s" % (record_id, record.get("exercise_id")))
        if not record.get("sets"):
            errors.append("记录 %s 没有训练组" % record_id)
        if record.get("day_type") is not None and record.get("day_type") not in allowed_day_types:
            errors.append("记录 %s 的 day_type 无效: %s" % (record_id, record.get("day_type")))
        if record.get("day_type") is not None:
            record_date = (record.get("performed_at") or "")[:10]
            if record_date in day_type_by_date and day_type_by_date[record_date] != record.get("day_type"):
                errors.append("同一天混用 day_type %s：%s / %s" % (
                    record_date, day_type_by_date[record_date], record.get("day_type")))
            else:
                day_type_by_date[record_date] = record.get("day_type")
        if record.get("sequence") is not None:
            if int(record.get("sequence")) < 1:
                errors.append("记录 %s 的 sequence 必须大于 0" % record_id)
            record_date = (record.get("performed_at") or "")[:10]
            sequence_key = "%s|%s" % (record_date, record.get("sequence"))
            if sequence_key in sequence_by_date:
                errors.append("动作顺序冲突 %s：%s / %s" % (
                    sequence_key, sequence_by_date[sequence_key], record_id))
            else:
                sequence_by_date[sequence_key] = record_id

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
        prog="fitness",
        description="fitness-ledger 跨平台 CLI(macOS/Linux 版;Windows 请用 fitness.ps1)。",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    def add_common(p):
        p.add_argument("--exercise", "--Exercise", dest="exercise", default=None, help="动作原始叫法")
        p.add_argument("--resolve-as", "--ResolveAs", dest="resolve_as", default=None, help="归一化到规范动作名")
        p.add_argument("--sets", "--Sets", dest="sets", nargs="+", default=None, help="组,如 12x40@2")
        p.add_argument("--date", "--Date", dest="date", default=None, help="训练日期 yyyy-MM-dd")
        p.add_argument("--equipment", "--Equipment", dest="equipment", default=None, help="具体器械")
        p.add_argument("--angle", "--Angle", dest="angle", default=None, help="flat/incline/decline/vertical")
        p.add_argument("--posture", "--Posture", dest="posture", default=None, help="seated/standing/lying/kneeling")
        p.add_argument("--laterality", "--Laterality", dest="laterality", default=None, help="bilateral/unilateral/alternating")
        p.add_argument("--grip", "--Grip", dest="grip", default=None, help="narrow/wide/neutral/narrow_neutral")
        p.add_argument("--notes", "--Notes", dest="notes", default=None, help="备注")
        p.add_argument("--tags", "--Tags", dest="tags", nargs="+", default=None, help="标签")
        p.add_argument("--day-type", "--DayType", dest="day_type", default="standard",
                       choices=("standard", "overload", "deload"), help="standard/overload/deload")
        p.add_argument("--day-type-basis", "--DayTypeBasis", dest="day_type_basis", default="default", help="day_type 依据")
        p.add_argument("--sequence", "--Sequence", dest="sequence", type=int, default=0, help="训练内动作顺序(1 起)")
        p.add_argument("--warmup-count", "--WarmupCount", dest="warmup_count", type=int, default=0, help="前 N 组为热身")
        p.add_argument("--limit", "--Limit", dest="limit", type=int, default=10, help="recent 条数")
        p.add_argument("--json", "--Json", dest="json", action="store_true", help="输出 JSON")
        p.add_argument("--id", "--Id", dest="id", default=None, help="记录 ID(resequence 用)")
        p.add_argument("--project-root", "--ProjectRoot", dest="project_root", default=PROJECT_ROOT,
                       help="仓库根目录(默认脚本上级目录)")

    for name in ("resolve", "add", "resequence", "recent", "stats", "validate", "list"):
        p = sub.add_parser(name, help="fitness %s" % name)
        add_common(p)
    return parser


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
        command_add(args)
    elif args.command == "recent":
        command_recent(args)
    elif args.command == "resequence":
        command_resequence(args)
    elif args.command == "stats":
        command_stats(args)
    elif args.command == "list":
        command_list(args)
    elif args.command == "validate":
        command_validate(args)


if __name__ == "__main__":
    main()
