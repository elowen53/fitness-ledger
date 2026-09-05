#!/usr/bin/env bash
# Smoke tests for the macOS / Linux CLI (scripts/fitness.py).
# Mirrors the assertions in tests/smoke.ps1. Run from anywhere:
#   bash tests/smoke.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FITNESS="$SCRIPT_DIR/../scripts/fitness.py"

TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p "$TMP_ROOT/catalog" "$TMP_ROOT/data/workouts"
cp "$PROJECT_ROOT/catalog/exercises.json" "$TMP_ROOT/catalog/exercises.json"

run() {
    python3 "$FITNESS" "$@" --project-root "$TMP_ROOT"
}

json_get() {
    # json_get <json> <dotted path>
    python3 -c '
import json, sys
data = json.loads(sys.argv[1])
for part in sys.argv[2].split("."):
    if part.isdigit():
        data = data[int(part)]
    else:
        data = data[part]
print(data)
' "$1" "$2"
}

expect_eq() {
    local actual="$1" expected="$2" label="$3"
    if [ "$actual" != "$expected" ]; then
        echo "FAIL: $label: expected '$expected', got '$actual'" >&2
        exit 1
    fi
}

resolved="$(run resolve --exercise "上斜器械推胸" --json)"
expect_eq "$(json_get "$resolved" status)" "resolved" "上斜器械推胸 status"
expect_eq "$(json_get "$resolved" exercise.id)" "machine_chest_press" "上斜器械推胸 id"
expect_eq "$(json_get "$resolved" variant.angle)" "incline" "上斜器械推胸 angle"

branded="$(run resolve --exercise "力健上斜推胸机" --json)"
expect_eq "$(json_get "$branded" status)" "resolved" "力健上斜推胸机 status"
expect_eq "$(json_get "$branded" exercise.id)" "machine_chest_press" "力健上斜推胸机 id"

nonstandard="$(run resolve --exercise "自创飞盘动作" --json)"
expect_eq "$(json_get "$nonstandard" status)" "unknown" "自创飞盘动作 status"

run add --exercise "上斜器械推胸" --sets "12x40@2","10x45@1" --equipment "test machine" \
    --date "2026-08-05" --sequence 1 --json >/dev/null
run add --exercise "坐姿哑铃侧平举" --sets "15x5,13x5" --date "2026-08-05" --sequence 2 --json >/dev/null
run add --exercise "Y举" --sets "R:8x20,L:8x20,R:7x20,L:8x20" --laterality unilateral \
    --date "2026-08-05" --sequence 3 --json >/dev/null
run add --exercise "豪斯特推胸" --resolve-as "器械推胸" --sets "9x80" --equipment "HOIST" \
    --laterality bilateral --date "2026-08-05" --sequence 4 --json >/dev/null
run add --exercise "临时编号推胸" --resolve-as "器械推胸" --sets "10x50" --equipment "alignment test machine" \
    --laterality bilateral --date "2026-08-06" --sequence 1 --json >/dev/null
run add --exercise "上斜器械推胸" --sets "10x50" --equipment "test machine" \
    --date "2026-08-06" --sequence 2 --json >/dev/null

history_resolved="$(run resolve --exercise "临时编号推胸" --json)"
expect_eq "$(json_get "$history_resolved" status)" "resolved" "历史叫法 status"
expect_eq "$(json_get "$history_resolved" exercise.id)" "machine_chest_press" "历史叫法 id"
expect_eq "$(json_get "$history_resolved" exercise.matched_source)" "history" "历史叫法 source"

validation="$(run validate --json)"
expect_eq "$(json_get "$validation" status)" "ok" "validate status"
expect_eq "$(json_get "$validation" workout_records)" "6" "validate record count"

unilateral_log="$(python3 -c '
import json, sys
path = sys.argv[1] + "/data/workouts/2026/08/2026-08-05.jsonl"
with open(path, encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r.get("exercise_id") == "user_y_raise":
            print(json.dumps(r, ensure_ascii=False))
            break
' "$TMP_ROOT")"
expect_eq "$(json_get "$unilateral_log" sets.0.side)" "right" "单侧 set0 side"
expect_eq "$(json_get "$unilateral_log" sets.2.round)" "2" "单侧 set2 round"

stats="$(run stats --exercise "器械推胸" --json)"
test_machine_stats="$(python3 -c '
import json, sys
rows = json.loads(sys.argv[1])
print(json.dumps([r for r in rows if r.get("equipment") == "machine/test machine"], ensure_ascii=False))
' "$stats")"
count="$(python3 -c 'import json,sys; print(len(json.loads(sys.argv[1])))' "$test_machine_stats")"
expect_eq "$count" "2" "stats 顺序角色分组数"
seq_one_volume="$(python3 -c '
import json, sys
rows = json.loads(sys.argv[1])
print([r["volume_kg"] for r in rows if r.get("sequence") == 1][0])
' "$test_machine_stats")"
expect_eq "$seq_one_volume" "930.0" "stats 顺序1训练量"

report="$(run report --date 2026-08-06 --json)"
expect_eq "$(json_get "$report" windows.0.working_set_entries)" "11" "report 工作组条数"
expect_eq "$(json_get "$report" last_workout_date)" "2026-08-06" "report 截止日期"
side_rounds="$(python3 -c 'import json,sys; print(next(m["working_rounds"] for m in json.loads(sys.argv[1])["windows"][0]["muscles"] if m["muscle"] == "side_delts"))' "$report")"
expect_eq "$side_rounds" "4" "report 单侧工作轮次"
expect_eq "$(json_get "$(run validate --json)" workout_records)" "6" "report 不写训练事实"

echo "smoke tests passed"
