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
            self.add(run,date='2026-09-05')
            rows=run('stats')
            self.assertEqual({r['weight_basis'] for r in rows},{'per_implement','total','unknown'})
            self.assertTrue(all(r['volume_kg']==400 for r in rows))
            self.assertEqual(len(run('report','--date','2026-09-05')['trends']),3)

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
