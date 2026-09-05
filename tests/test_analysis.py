"""Read-only analysis regression tests; optional native PowerShell parity."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from analysis import build_report, context_errors

CATALOG = {'exercises': [{'id': 'press', 'primary_muscles': ['chest']},
                         {'id': 'raise', 'primary_muscles': ['side_delts', 'rear_delts']}]}


def record(date, reps=(10, 8), weight=40, **changes):
    r = dict(id=date, performed_at=date+'T23:00:00+08:00', exercise_id='press',
             reported_name='press', sequence=1, day_type='standard', notes=None,
             variant=dict(angle='flat', posture='seated', laterality='bilateral', grip=None),
             equipment=dict(type='machine', name='A'),
             analysis_context=dict(session_template='push', execution_standard='full-v1',
                                   quality_change='maintained', rest_sec=180),
             sets=[dict(reps=n, weight_kg=weight, rir=0, warmup=False,
                        bodyweight=False, side=None, round=None) for n in reps])
    r.update(changes)
    return r


class AnalysisTests(unittest.TestCase):
    def report(self, rows, date='2026-09-05'):
        before = copy.deepcopy(rows)
        result = build_report(rows, CATALOG, date)
        self.assertEqual(before, rows, 'analysis mutated facts')
        return result

    def test_numeric_progress_is_not_automatic_pr(self):
        r = self.report([record('2026-09-01'), record('2026-09-05', (11, 8))])
        t = r['trends'][0]
        self.assertEqual(t['comparability'], 'comparable')
        self.assertEqual(t['reps_delta'], 1)
        self.assertEqual(t['assessment'], 'reps_increased')
        self.assertNotIn('pr', t)

    def test_quality_reduction_and_missing_context(self):
        a, b = record('2026-09-01'), record('2026-09-05', weight=30)
        b['analysis_context'].update(execution_standard='full-v2', quality_change='improved_with_load_reduction')
        t = self.report([a, b])['trends'][0]
        self.assertEqual(t['assessment'], 'major_quality_progress')
        self.assertEqual(t['comparability'], 'new_baseline')
        self.assertIsNone(t['reps_delta'])
        del b['analysis_context']
        b['notes'] = '降重量，动作优化，质量显著提升。'
        t = self.report([a, b])['trends'][0]
        self.assertEqual(t['comparability'], 'limited')
        self.assertIn('notes_require_review', t['reasons'])
        self.assertEqual(t['assessment'], 'review_context')

    def test_equipment_sequence_and_preceding_work(self):
        a, b = record('2026-09-01'), record('2026-09-05')
        b['equipment']['name'] = 'B'
        self.assertEqual(len(self.report([a, b])['trends']), 2)
        b['equipment']['name'] = 'A'
        b['sequence'] = 2
        self.assertEqual(len(self.report([a, b])['trends']), 2)
        a['sequence'] = 2
        p, q = record('2026-09-01', exercise_id='raise'), record('2026-09-05', exercise_id='raise')
        q['sets'][0]['weight_kg'] = 50
        t = next(t for t in self.report([a, b, p, q])['trends'] if t['exercise_id'] == 'press')
        self.assertEqual(t['comparability'], 'limited')
        self.assertIn('preceding_work_changed', t['reasons'])

    def test_rounds_bodyweight_warmup_dates(self):
        a = record('2026-08-30', exercise_id='raise')
        a['sets'] = [dict(reps=8, weight_kg=20, rir=0, warmup=False, side=side, round=n)
                     for side, n in [('left', 1), ('right', 1), ('right', 2)]]
        b = record('2026-09-05', reps=(12,), weight=None)
        b['sets'][0]['bodyweight'] = True
        b['sets'].append(dict(reps=8, weight_kg=5, warmup=True))
        rows = [a, b, record('2026-08-29'), record('2026-08-23'), record('2026-09-06')]
        r = self.report(rows)
        w = r['windows'][0]
        muscles = {m['muscle']: m for m in w['muscles']}
        self.assertEqual(w['working_set_entries'], 4)
        self.assertEqual(muscles['side_delts']['working_rounds'], 2)
        self.assertEqual(muscles['side_delts']['paired_rounds'], 1)
        self.assertEqual(muscles['side_delts']['unpaired_rounds'], 1)
        self.assertEqual(muscles['side_delts']['left_sets'], 1)
        self.assertEqual(muscles['side_delts']['right_sets'], 2)
        self.assertEqual(muscles['chest']['working_rounds'], 1)
        self.assertEqual(len(w['rest_dates']), 5)
        self.assertEqual(r['windows'][1]['working_set_entries'], 8)
        self.assertEqual(r['last_workout_date'], '2026-09-05')

    def test_effort_quality_and_date_validation(self):
        a, b = record('2026-09-01'), record('2026-09-05', reps=(11, 8))
        b['sets'][0]['rir'] = None
        self.assertEqual(self.report([a, b])['trends'][0]['comparability'], 'limited')
        b['analysis_context']['quality_change'] = 'degraded'
        self.assertEqual(self.report([a, b])['trends'][0]['assessment'], 'quality_declined')
        self.assertTrue(context_errors({'rest_sec': -1}))
        self.assertTrue(context_errors({'rest_sec': True}))
        self.assertTrue(context_errors({'session_template': ' '}))
        with self.assertRaises(ValueError):
            self.report([], 'invalid')
        self.assertEqual(self.report([])['trends'], [])

    def test_rest_template_and_technique_gates(self):
        for field, value, status in [('rest_sec', 120, 'limited'), ('session_template', 'upper', 'new_baseline'), ('execution_standard', 'v2', 'new_baseline')]:
            a, b = record('2026-09-01'), record('2026-09-05')
            b['analysis_context'][field] = value
            self.assertEqual(self.report([a, b])['trends'][0]['comparability'], status)
        a, b = record('2026-09-01'), record('2026-09-05')
        a['analysis_context']['quality_change'] = 'degraded'
        self.assertEqual(self.report([a, b])['trends'][0]['comparability'], 'limited')

    def test_add_context_keeps_existing_recording_semantics(self):
        import shutil
        runtimes = [[sys.executable, str(ROOT/'scripts/fitness.py')]]
        if os.environ.get('PWSH'):
            runtimes.append([os.environ['PWSH'], '-NoProfile', '-File', str(ROOT/'scripts/fitness.ps1')])
        for runtime in runtimes:
            with tempfile.TemporaryDirectory() as d:
                (Path(d)/'catalog').mkdir()
                shutil.copyfile(ROOT/'catalog/exercises.json', Path(d)/'catalog/exercises.json')
                ps = runtime[0] != sys.executable
                def invoke(options):
                    if ps:
                        options = ['-'+''.join(w.title() for w in a[2:].split('-')) if a.startswith('--') else a for a in options]
                    return subprocess.run(runtime+options, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                common = ['add', '--exercise', 'Y举', '--sets', 'R:8x20@0,L:7x20@1', '--laterality', 'unilateral', '--sequence', '3', '--date', '2026-09-05', '--project-root', d, '--json']
                result = invoke(common)
                self.assertEqual(result.returncode, 0, result.stderr)
                old = json.loads(result.stdout)
                self.assertNotIn('analysis_context', old)
                result = invoke(common+['--session-template', '肩日', '--execution-standard', '座椅4-全幅-v2', '--quality-change', 'improved_with_load_reduction', '--rest-sec', '180', '--notes', '用户报告质量显著改善而降重'])
                self.assertEqual(result.returncode, 0, result.stderr)
                new = json.loads(result.stdout)
                self.assertEqual(new['sets'], old['sets'])
                for key in ['exercise_id','reported_name','sequence','variant','equipment','day_type']:
                    self.assertEqual(new[key], old[key])
                self.assertEqual(new['sets'][0]['rir'], 0)
                self.assertEqual(new['sets'][1]['rir'], 1)
                self.assertEqual(new['analysis_context']['rest_sec'], 180)
                files = {f: f.read_bytes() for f in (Path(d)/'data').rglob('*.jsonl')}
                for bad in [['--rest-sec', '-1'], ['--session-template', ' '], ['--quality-change', 'guessed']]:
                    self.assertNotEqual(invoke(common+bad).returncode, 0)
                    self.assertEqual(files, {f: f.read_bytes() for f in files})

    @unittest.skipUnless(os.environ.get('PWSH'), 'Set PWSH for native platform parity')
    def test_native_platform_parity_and_immutable_files(self):
        rows = [record('2026-09-01'), record('2026-09-05', reps=(11, 8))]
        rows += [record('2026-08-30', exercise_id='raise', analysis_context=None, notes='动作优化')]
        rows[0]['sets'][0]['weight_kg'] = 40.0
        quality = record('2026-09-04', exercise_id='raise', weight=30)
        quality['analysis_context']['quality_change'] = 'improved_with_load_reduction'
        rows.append(quality)
        unilateral = record('2026-08-31', exercise_id='raise', sequence=2)
        unilateral['sets'] = [dict(reps=8, weight_kg=20, rir=0, warmup=False, side=side, round=n)
                              for side, n in [('left', 1), ('right', 1), ('right', 2), ('left', None)]]
        rows.append(unilateral)
        warmup = record('2026-09-02', exercise_id='raise')
        warmup['sets'][0]['warmup'] = True
        warmup['sets'][1].update(weight_kg=None, bodyweight=True)
        rows.append(warmup)
        boundary = record('2026-09-05', exercise_id='raise', sequence=3)
        boundary['performed_at'] = '2026-09-05T00:30:00+14:00'
        rows.append(boundary)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'catalog').mkdir()
            (root/'data/workouts').mkdir(parents=True)
            (root/'catalog/exercises.json').write_text(json.dumps(CATALOG))
            f = root/'data/workouts/test.jsonl'
            f.write_text('\n'.join(json.dumps(r) for r in rows))
            before = f.read_bytes()
            for day in ['2026-09-05', '2026-08-01', '2026-10-01']:
                py = subprocess.check_output([sys.executable, str(ROOT/'scripts/fitness.py'), 'report', '--date', day, '--project-root', d, '--json'])
                ps = subprocess.check_output([os.environ['PWSH'], '-NoProfile', '-File', str(ROOT/'scripts/fitness.ps1'), 'report', '-Date', day, '-ProjectRoot', d, '-Json'])
                self.assertEqual(json.loads(py), json.loads(ps))
            self.assertEqual(before, f.read_bytes())


if __name__ == '__main__':
    unittest.main()
