"""Write-safety and v1/v2 regressions for the macOS CLI."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from analysis import set_metrics
from train_logbook import iso7
from datetime import datetime, timezone, timedelta


class TrainLogbookTests(unittest.TestCase):
    def fixture(self, directory, runtime=None):
        runtime = runtime or [sys.executable, str(ROOT/'scripts/train_logbook.py')]
        root = Path(directory)
        (root/'catalog').mkdir()
        (root/'profile').mkdir()
        shutil.copyfile(ROOT/'catalog/exercises.json', root/'catalog/exercises.json')
        shutil.copyfile(ROOT/'profile/training-preferences.json', root/'profile/training-preferences.json')
        def invoke(*args, ok=True):
            args = list(args)+['--project-root', directory, '--json']
            result = subprocess.run(runtime+args, capture_output=True, text=True)
            if ok:
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout) if result.stdout.strip().startswith(('{', '[')) else result.stdout
            self.assertNotEqual(result.returncode, 0, result.stdout)
            return result
        return root, invoke

    def add(self, invoke, sequence='1', date='2026-09-05', **options):
        args = ['add', '--exercise', options.pop('exercise', '器械推胸'), '--sets', options.pop('sets', '10x40'), '--date', date]
        if sequence is not None:
            args += ['--sequence', sequence]
        for k, v in options.items():
            args += ['--'+k.replace('_','-'), v]
        return invoke(*args)

    def files(self, root):
        return {str(f.relative_to(root)): f.read_bytes() for f in root.rglob('*') if f.is_file()}

    def test_variants_defaults_and_rir_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            root, run = self.fixture(d)
            r = self.add(run, exercise='力健坐姿上斜推胸机', resolve_as='器械推胸', sets='8x20,10x40,9x40@1', warmup_count='1')
            self.assertEqual(r['variant'], dict(angle='incline',posture='seated',laterality='bilateral',grip=None))
            self.assertEqual([s['rir'] for s in r['sets']], [None,0,1])
            self.assertEqual([s['rir_source'] for s in r['sets']], ['unknown','profile_default','reported'])
            self.assertEqual(r['rir_default']['missing_means'], 0)
            r2 = self.add(run, sequence='2', exercise='上斜器械推胸', resolve_as='器械推胸', angle='flat')
            self.assertEqual(r2['variant']['angle'], 'flat')
            self.assertEqual(run('validate')['status'], 'ok')

    def test_rejected_writes_do_not_touch_files(self):
        with tempfile.TemporaryDirectory() as d:
            root, run = self.fixture(d)
            self.add(run)
            before = self.files(root)
            common = ['add','--exercise','器械推胸','--sets','10x40','--date','2026-09-05']
            for extra in [[], ['--sequence','0'], ['--sequence','-1'], ['--sequence','1'],
                          ['--sequence','2','--day-type','deload'],
                          ['--sequence','2','--performed-at','2026-09-06T12:00:00+08:00'],
                          ['--sequence','2','--performed-at','2026-09-05T12:00:00']]:
                run(*(common+extra), ok=False)
                self.assertEqual(before, self.files(root))
            run('add','--exercise','Y举','--sets','R:8x20','--sequence','2','--date','2026-09-05','--laterality','bilateral',ok=False)
            run('add','--exercise','Y举','--sets','8x20','--sequence','2','--date','2026-09-05','--laterality','unilateral',ok=False)
            run('add','--exercise','器械推胸','--sets','0s','--sequence','2','--date','2026-09-05',ok=False)
            self.assertEqual(before, self.files(root))

    def test_validation_rejects_corrupt_records(self):
        with tempfile.TemporaryDirectory() as d:
            root, run = self.fixture(d)
            good = self.add(run)
            path = next(root.rglob('*.jsonl'))
            for field, value in [('reps',-1),('reps',1.5),('reps',True),('weight_kg',-2),('rir',-1),
                                 ('duration_sec',0),('warmup','false'),('side','right'),('round',1)]:
                bad = copy.deepcopy(good); bad['sets'][0][field] = value
                path.write_text(json.dumps(bad)+'\n')
                run('validate',ok=False)
            for field, value in [('sequence',None),('sequence',1.5),('sequence',True),('sets',{}),
                                 ('sets',[None]),('training_date','2026-02-30'),('recorded_at','garbage'),
                                 ('performed_at','2026-09-06T12:00:00+08:00'),('weight_basis','made_up')]:
                bad=copy.deepcopy(good); bad[field]=value
                path.write_text(json.dumps(bad)+'\n'); run('validate',ok=False)
            bad=copy.deepcopy(good); bad['sequence']=2
            path.write_text(json.dumps(good)+'\n'+json.dumps(bad)+'\n')
            run('validate',ok=False)
            path.write_text(json.dumps(good)+'\n'); self.assertEqual(run('validate')['status'],'ok')

    def test_warmups_do_not_shift_work_rounds(self):
        with tempfile.TemporaryDirectory() as d:
            root, run = self.fixture(d)
            r = self.add(run, exercise='Y举', sets='R:8x5,L:8x20,R:8x20', warmup_count='1')
            self.assertEqual(r['variant']['laterality'],'unilateral')
            self.assertEqual([s['round'] for s in r['sets']],[1,1,1])
            m=set_metrics(r)
            self.assertEqual((m['paired_rounds'],m['working_rounds'],m['unpaired_rounds']),(1,1,0))
            report=run('report','--date','2026-09-05')
            self.assertEqual(report['windows'][0]['muscles'][0]['paired_rounds'],1)
            self.assertEqual(run('validate')['status'],'ok')

    def test_dates_recent_and_backfilled_order(self):
        with tempfile.TemporaryDirectory() as d:
            root, run = self.fixture(d)
            r=self.add(run,sequence='2',performed_at='2026-09-05T00:30:00-07:00')
            self.assertEqual(r['schema_version'],2)
            self.assertEqual(r['training_date'],'2026-09-05')
            self.assertTrue(r['recorded_at'])
            self.assertEqual(r['performed_at'],'2026-09-05T00:30:00-07:00')
            r2=self.add(run)
            self.assertIsNone(r2['performed_at'])
            self.add(run,date='2026-09-04')
            self.add(run,date='2026-09-06')
            rows=run('recent')
            self.assertEqual([(r['date'],r['sequence']) for r in rows], [('2026-09-06',1),('2026-09-05',1),('2026-09-05',2),('2026-09-04',1)])
            self.assertEqual(run('report','--date','2026-09-05')['last_workout_date'],'2026-09-05')
            self.assertEqual(run('validate')['status'],'ok')

    def test_weight_basis_separates_stats_and_trends(self):
        with tempfile.TemporaryDirectory() as d:
            root, run = self.fixture(d)
            self.add(run,date='2026-09-03',weight_basis='per_implement')
            self.add(run,date='2026-09-04',weight_basis='total')
            self.add(run,date='2026-09-05',exercise='侧平举')
            rows=run('stats')
            self.assertEqual({r['weight_basis'] for r in rows},{'per_implement','total','unknown'})
            self.assertTrue(all(r['volume_kg']==400 for r in rows))
            self.assertEqual(len(run('report','--date','2026-09-05')['trends']),3)
            self.assertEqual(len([r for r in rows if r['exercise_id']=='machine_chest_press']),2)

    def test_legacy_compatibility_and_failed_correction(self):
        with tempfile.TemporaryDirectory() as d:
            root, run=self.fixture(d)
            legacy=json.loads((ROOT/'data/workouts/2026/08/2026-08-24.jsonl').read_text().splitlines()[0])
            legacy.pop('sequence'); legacy.pop('day_type')
            path=root/'data/workouts/legacy.jsonl';path.parent.mkdir(parents=True)
            path.write_text(json.dumps(legacy,ensure_ascii=False)+'\n')
            original=path.read_bytes()
            self.assertEqual(run('validate')['status'],'ok')
            a=self.add(run); b=self.add(run,sequence='2')
            run('report','--date','2026-09-05');run('recent');run('stats')
            self.assertEqual(path.read_bytes(),original)
            before=self.files(root)
            run('resequence','--id',a['id'],'--sequence','2',ok=False)
            self.assertEqual(before,self.files(root))
            run('resequence','--id',a['id'],'--sequence','3')
            self.assertEqual(run('validate')['status'],'ok')
            self.assertEqual([r['sequence'] for r in run('recent')][:2],[2,3])
            self.assertEqual(path.read_bytes(),original)

    def test_set_notation_and_failure_modes(self):
        with tempfile.TemporaryDirectory() as d:
            root, run = self.fixture(d)
            r = self.add(run, sets='9x81!t,bo:11x65,12xbw+2sp')
            u = self.add(run, sequence='3', exercise='Y举', sets='R:drop:8x20+3lp@0,drop:l:8x20+1p!e')
            got = [(s['set_type'], s['side'], s['weight_kg'], s['partial_reps'], s['partial_position'], s['failure_mode'], s['rir'])
                   for s in r['sets'] + u['sets']]
            self.assertEqual(got, [('straight', None, 81.0, None, None, 'technical', 0),
                                   ('backoff', None, 65.0, None, None, None, 0),
                                   ('straight', None, None, 2, 'shortened', None, 0),
                                   ('drop', 'right', 20.0, 3, 'lengthened', None, 0),
                                   ('drop', 'left', 20.0, 1, None, 'extended', 0)])
            before = self.files(root)
            for bad in ['10x40@1!a', 'zz:10x40', '30s!t', 'bo:bo:10x40']:
                run('add', '--exercise', '器械推胸', '--sets', bad, '--sequence', '2', '--date', '2026-09-05', ok=False)
            run('add', '--exercise', '器械推胸', '--sets', 'bo:8x20,10x40', '--warmup-count', '1', '--sequence', '2', '--date', '2026-09-05', ok=False)
            self.assertEqual(before, self.files(root))
            self.assertEqual(run('validate')['status'], 'ok')

    def test_setup_reported_and_carried_forward(self):
        with tempfile.TemporaryDirectory() as d:
            root, run = self.fixture(d)
            run('add', '--exercise', '器械推胸', '--sets', '10x40', '--sequence', '1', '--date', '2026-09-04',
                '--equipment', 'FORWARD', '--setup-same-as-last', ok=False)
            first = run('add', '--exercise', '器械推胸', '--sets', '10x40', '--sequence', '1', '--date', '2026-09-04',
                        '--equipment', 'FORWARD', '--setup', '座椅=4', '靠垫=2')
            self.assertEqual(first['setup'], dict(values={'座椅': '4', '靠垫': '2'}, source='reported', from_record=None))
            found = run('setup', '--exercise', '器械推胸', '--equipment', 'FORWARD')
            self.assertEqual((found['status'], found['setup']['座椅']), ('found', '4'))
            self.assertEqual(run('setup', '--exercise', '器械推胸', '--equipment', 'HOIST')['status'], 'none')
            second = run('add', '--exercise', '器械推胸', '--sets', '11x40', '--sequence', '1', '--date', '2026-09-05',
                         '--equipment', 'FORWARD', '--setup-same-as-last')
            self.assertEqual(second['setup']['from_record'], first['id'])
            run('add', '--exercise', '器械推胸', '--sets', '11x40', '--sequence', '2', '--date', '2026-09-05',
                '--equipment', 'FORWARD', '--setup', '座椅', ok=False)
            self.assertEqual(run('validate')['status'], 'ok')
            path = next(root.rglob('2026-09-05.jsonl'))
            bad = dict(second, setup=dict(second['setup'], values={'座椅': '5'}))
            path.write_text(json.dumps(bad, ensure_ascii=False) + '\n')
            run('validate', ok=False)

    def test_unstated_equipment_follows_history(self):
        with tempfile.TemporaryDirectory() as d:
            root, run = self.fixture(d)
            for day in ('01', '02'):
                run('add', '--exercise', '蝴蝶机夹胸', '--sets', '10x59', '--sequence', '1', '--date', '2026-09-' + day,
                    '--equipment', '蝴蝶机', '--posture', 'seated')
            r = run('add', '--exercise', '蝴蝶机夹胸', '--sets', '10x59', '--sequence', '1', '--date', '2026-09-03')
            self.assertEqual((r['equipment']['name'], r['variant']['posture']), ('蝴蝶机', 'seated'))
            self.assertEqual(r['inferred_fields']['equipment.name']['method'], 'history_reported_name')
            r = run('add', '--exercise', '蝴蝶机夹胸', '--sets', '10x59', '--sequence', '1', '--date', '2026-09-04', '--no-infer')
            self.assertIsNone(r['equipment']['name'])
            self.assertNotIn('equipment.name', r.get('inferred_fields', {}))
            # A stated name contained in one more frequent historical name is unified.
            r = run('add', '--exercise', '夹胸', '--sets', '10x59', '--sequence', '1', '--date', '2026-09-05', '--equipment', '蝴蝶')
            self.assertEqual(r['inferred_fields']['equipment.name'], dict(value='蝴蝶机', method='name_unified', support=3, original='蝴蝶'))
            # Several machines for the same exercise and an unseen name: ask, do not guess.
            run('add', '--exercise', '器械推胸', '--sets', '10x80', '--sequence', '2', '--date', '2026-09-01', '--equipment', 'FORWARD')
            run('add', '--exercise', '器械推胸', '--sets', '10x80', '--sequence', '2', '--date', '2026-09-02', '--equipment', 'HOIST')
            # A more specific name is kept, not collapsed into the brand.
            r = run('add', '--exercise', '器械推胸', '--sets', '10x80', '--sequence', '2', '--date', '2026-09-03', '--equipment', 'HOIST 上斜')
            self.assertEqual(r['equipment']['name'], 'HOIST 上斜')
            before = self.files(root)
            result = run('add', '--exercise', '坐姿推胸机', '--sets', '10x80', '--sequence', '2', '--date', '2026-09-05', ok=False)
            self.assertIn('equipment.name', result.stderr)
            self.assertEqual(before, self.files(root))
            r = run('add', '--exercise', '器械推胸', '--sets', '10x80', '--sequence', '2', '--date', '2026-09-05', '--equipment', '诺德士')
            self.assertEqual(r['equipment']['name'], '诺德士')
            self.assertEqual(run('validate')['status'], 'ok')

    def test_weight_basis_follows_equipment_type(self):
        with tempfile.TemporaryDirectory() as d:
            root, run = self.fixture(d)
            r = self.add(run, sequence='1')
            self.assertEqual((r['weight_basis'], r['inferred_fields']['weight_basis']['method']), ('total', 'convention'))
            self.assertEqual(self.add(run, sequence='2', weight_basis='unknown')['weight_basis'], 'total')
            self.assertEqual(self.add(run, sequence='3', weight_basis='per_side')['weight_basis'], 'per_side')
            self.assertEqual(self.add(run, sequence='4', exercise='哑铃侧平举', sets='10x8')['weight_basis'], 'per_implement')
            # Unilateral loads follow the equipment too: shared-plate machines and cables are totals.
            self.assertEqual(self.add(run, sequence='5', exercise='Y举', sets='R:8x20,L:8x20')['weight_basis'], 'total')
            self.assertEqual(self.add(run, sequence='7', exercise='豪斯特二头弯举', resolve_as='肱二头弯举', sets='R:10x80,L:10x80')['weight_basis'], 'total')
            self.assertEqual(self.add(run, sequence='8', exercise='单臂哑铃划船', sets='R:10x30,L:10x30')['weight_basis'], 'per_implement')
            self.assertEqual(self.add(run, sequence='6', exercise='引体向上', sets='10xbw')['weight_basis'], 'unknown')
            # Without a type in history, the name, or an unambiguous catalog type: left unknown.
            self.assertEqual(self.add(run, sequence='9', exercise='肩推', sets='10x40')['weight_basis'], 'unknown')
            # History-inferred type drives the basis: the earlier dumbbell lateral raise makes this per dumbbell.
            self.assertEqual(self.add(run, sequence='11', exercise='侧平举', sets='10x8')['weight_basis'], 'per_implement')
            # Catalog type cable_or_machine maps to a single basis.
            self.assertEqual(self.add(run, sequence='10', exercise='高位下拉', sets='10x60')['weight_basis'], 'total')
            # align applies the same rule to history, but never overrides a stated basis.
            path = next(root.rglob('*.jsonl'))
            rows = [json.loads(l) for l in path.read_text().splitlines()]
            rows[0]['weight_basis'] = 'unknown'
            rows[0].pop('inferred_fields')
            path.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in rows))
            plans = run('align')['plans']
            self.assertEqual([(p['id'], set(p['fills'])) for p in plans], [(r['id'], {'weight_basis'})])
            self.assertEqual(run('align', '--apply')['applied'], 1)
            self.assertEqual(json.loads(path.read_text().splitlines()[0])['weight_basis'], 'total')
            self.assertEqual(run('validate')['status'], 'ok')

    def test_align_backfills_history_with_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            root, run = self.fixture(d)
            a = run('add', '--exercise', '蝴蝶机夹胸', '--sets', '10x59', '--sequence', '1', '--date', '2026-09-01', '--no-infer')
            run('add', '--exercise', '蝴蝶机夹胸', '--sets', '10x59', '--sequence', '1', '--date', '2026-09-02', '--equipment', '蝴蝶机')
            path = next(root.rglob('2026-09-01.jsonl'))
            legacy = dict(a, schema_version=1, performed_at='2026-09-01T12:00:00+08:00', variant=dict(a['variant'], laterality=None))
            for key in ('training_date', 'recorded_at'):
                legacy.pop(key)
            path.write_text(json.dumps(legacy, ensure_ascii=False) + '\n')
            before = self.files(root)
            plan = run('align')
            self.assertEqual(before, self.files(root))
            self.assertEqual(set(plan['plans'][0]['fills']), {'equipment.name', 'variant.laterality'})
            self.assertEqual(run('align', '--apply', '--skip-id', a['id'])['applied'], 0)
            self.assertEqual(run('align', '--apply')['applied'], 1)
            fixed = json.loads(path.read_text())
            self.assertEqual((fixed['equipment']['name'], fixed['variant']['laterality']), ('蝴蝶机', 'bilateral'))
            self.assertEqual(fixed['sets'], a['sets'])
            self.assertEqual(run('align')['plans'], [])
            self.assertEqual(run('validate')['status'], 'ok')
            path.write_text(json.dumps(dict(fixed, equipment=dict(fixed['equipment'], name='其他')), ensure_ascii=False) + '\n')
            run('validate', ok=False)

    def test_focus_marks_overload_day(self):
        with tempfile.TemporaryDirectory() as d:
            root, run = self.fixture(d)
            before = self.files(root)
            run('add', '--exercise', '器械推胸', '--sets', '10x80', '--sequence', '1', '--date', '2026-09-05', '--focus', ok=False)
            run('add', '--exercise', '器械推胸', '--sets', '10x80', '--sequence', '1', '--date', '2026-09-05', '--overload-lever', 'reps', ok=False)
            run('add', '--exercise', '器械推胸', '--sets', '10x80', '--sequence', '1', '--date', '2026-09-05',
                '--focus', '--overload-lever', 'reps', '--day-type', 'standard', ok=False)
            self.assertEqual(before, self.files(root))
            r = run('add', '--exercise', '器械推胸', '--sets', '11x80', '--sequence', '1', '--date', '2026-09-05',
                    '--focus', '--overload-lever', 'reps', '--target', '最重组多一次')
            self.assertEqual(r['progression_target'], dict(lever='reps', target='最重组多一次', basis='user_reported'))
            self.assertEqual(r['day_type'], 'overload')
            other = run('add', '--exercise', '蝴蝶机夹胸', '--sets', '10x59', '--sequence', '2', '--date', '2026-09-05')
            self.assertEqual((other['day_type'], 'progression_target' in other), ('overload', False))
            self.assertEqual(run('add', '--exercise', '器械推胸', '--sets', '10x80', '--sequence', '1', '--date', '2026-09-06')['day_type'], 'standard')
            self.assertEqual(run('validate')['status'], 'ok')
            path = next(root.rglob('2026-09-06.jsonl'))
            bad = json.loads(path.read_text())
            bad['progression_target'] = dict(lever='reps', target=None, basis='user_reported')
            path.write_text(json.dumps(bad, ensure_ascii=False) + '\n')
            run('validate', ok=False)

    def test_setup_list_reports_machines_without_setup(self):
        with tempfile.TemporaryDirectory() as d:
            root, run = self.fixture(d)
            run('add', '--exercise', '器械推胸', '--sets', '10x80', '--sequence', '1', '--date', '2026-09-04', '--equipment', 'FORWARD', '--setup', '座椅=4')
            run('add', '--exercise', '蝴蝶机夹胸', '--sets', '10x59', '--sequence', '2', '--date', '2026-09-04', '--equipment', '蝴蝶机')
            run('add', '--exercise', '哑铃侧平举', '--sets', '10x8', '--sequence', '3', '--date', '2026-09-04')
            rows = run('setup')
            self.assertEqual([(x['exercise_id'], x['status'], x['setup']) for x in rows],
                             [('machine_chest_press', 'found', {'座椅': '4'}), ('pec_deck_fly', 'none', None)])
            # The lookup ignores a type the name alone cannot reveal.
            self.assertEqual(run('setup', '--exercise', 'FORWARD推胸', '--resolve-as', '器械推胸', '--equipment', 'FORWARD')['status'], 'found')
            # Same brand, different machine (angle): no carry-over.
            self.assertEqual(run('setup', '--exercise', '上斜推胸', '--resolve-as', '器械推胸', '--equipment', 'FORWARD')['status'], 'none')
            run('add', '--exercise', '上斜推胸', '--resolve-as', '器械推胸', '--sets', '10x60', '--sequence', '4', '--date', '2026-09-04',
                '--equipment', 'FORWARD', '--setup-same-as-last', ok=False)

    def test_setup_carries_over_from_record_without_type(self):
        with tempfile.TemporaryDirectory() as d:
            root, run = self.fixture(d)
            old = run('add', '--exercise', 'Y举', '--sets', 'R:8x20,L:8x20', '--sequence', '1', '--date', '2026-09-04',
                      '--equipment', '龙门架钢线', '--setup', '滑轮=最低', '--no-infer')
            path = next(root.rglob('2026-09-04.jsonl'))
            path.write_text(json.dumps(dict(old, equipment=dict(old['equipment'], type=None)), ensure_ascii=False) + '\n')
            self.assertEqual(run('setup', '--exercise', 'Y举', '--equipment', '龙门架钢线')['status'], 'found')
            new = run('add', '--exercise', 'Y举', '--sets', 'R:8x20,L:8x20', '--sequence', '1', '--date', '2026-09-05',
                      '--equipment', '龙门架钢线', '--setup-same-as-last')
            self.assertEqual(new['setup']['from_record'], old['id'])
            self.assertEqual(run('validate')['status'], 'ok')

    def test_shared_lock_does_not_get_stolen(self):
        with tempfile.TemporaryDirectory() as d:
            root,run=self.fixture(d)
            (root/'.train-logbook-write.lock').write_text('held')
            before=self.files(root)
            run('add','--exercise','器械推胸','--sets','10x40','--sequence','1',ok=False)
            self.assertEqual(before,self.files(root))

    def test_negative_timezone_formatter(self):
        stamp=iso7(datetime(2026,9,5,12,0,tzinfo=timezone(timedelta(hours=-7))))
        self.assertEqual(stamp,'2026-09-05T12:00:00.0000000-07:00')

    def test_shell_entry_point_matches_python_outputs(self):
        results=[]
        for runtime in ([sys.executable, str(ROOT/'scripts/train_logbook.py')], [shutil.which('bash') or 'bash', (ROOT/'scripts/train-logbook.sh').as_posix()]):
            with tempfile.TemporaryDirectory() as d:
                root,run=self.fixture(d,runtime)
                r=self.add(run,exercise='坐姿上斜器械推胸',resolve_as='器械推胸',weight_basis='machine_display')
                r['id']='stable-id';r['recorded_at']='2026-10-07T12:00:00.0000000+08:00'
                next(root.rglob('*.jsonl')).write_text(json.dumps(r,ensure_ascii=False)+'\n')
                results.append([r,run('recent'),run('stats'),run('report','--date','2026-09-05')])
        self.assertEqual(results[0],results[1])


if __name__=='__main__':
    unittest.main()
