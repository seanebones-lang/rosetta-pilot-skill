"""Safety boundaries of the distributable no-key onboarding wrapper."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/pilot.py'
spec = importlib.util.spec_from_file_location('pilot_skill', SCRIPT)
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class PilotSkillTests(unittest.TestCase):
    def test_plan_neither_creates_directory_nor_fetches_or_executes(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / 'not-created'
            with patch('sys.argv', ['pilot', '--work', str(work), '--image', 'approved']), \
                 patch.object(pilot, 'fetch') as fetch, patch.object(pilot, 'invoke') as invoke, \
                 patch('sys.stdout', new_callable=io.StringIO) as output:
                self.assertEqual(pilot.main(), 0)
                self.assertFalse(json.loads(output.getvalue())['changes_made'])
            fetch.assert_not_called()
            invoke.assert_not_called()
            self.assertFalse(work.exists())

    def test_existing_work_and_symlink_are_refused_without_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / 'precious'; work.mkdir()
            (work / 'keep').write_text('keep')
            link = Path(temp) / 'link'; link.symlink_to(work)
            for selected in (work, link):
                with patch('sys.argv', ['pilot', '--work', str(selected), '--image', 'approved', '--run']), \
                     patch.object(pilot, 'run') as run, patch('sys.stderr', new_callable=io.StringIO):
                    with self.assertRaises(SystemExit): pilot.main()
                    run.assert_not_called()
            self.assertEqual((work / 'keep').read_text(), 'keep')

    def test_mismatched_download_is_not_saved_or_executed(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(pilot.urllib.request, 'build_opener') as opener:
                opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'tampered'
                with self.assertRaisesRegex(pilot.Stopped, 'size/hash mismatch'):
                    pilot.fetch(pilot.WHEEL, Path(temp))
            self.assertFalse((Path(temp) / pilot.WHEEL).exists())

    def test_redirect_is_rejected_instead_of_forwarding(self):
        with self.assertRaises(pilot.Stopped):
            pilot.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://unrelated.example/payload')

    def test_blocked_download_stops_before_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(pilot, 'fetch', side_effect=urllib.error.HTTPError(pilot.ORIGIN, 403, 'blocked', {}, None)), \
                 patch.object(pilot, 'invoke') as invoke:
                result = pilot.run(Path(temp), 'approved')
            invoke.assert_not_called()
            self.assertEqual(result['status'], 'stopped')
            self.assertNotIn('rosetta_provider_calls', result)

    def test_missing_prerequisite_never_runs_fixture_or_pulls(self):
        with tempfile.TemporaryDirectory() as temp:
            called = []
            def invoke(args, folder, name, **kw):
                called.append([str(x) for x in args])
                return subprocess.CompletedProcess(args, 0, json.dumps({'status': 'needs_setup'}), '')
            with patch.object(pilot, 'fetch', return_value='fixturehash'), patch.object(pilot, 'invoke', side_effect=invoke):
                result = pilot.run(Path(temp), 'approved')
            self.assertEqual(result['status'], 'stopped')
            self.assertFalse(any('demo' in command or 'replay' in command or 'pull' in command for command in called))

    def test_failed_command_diagnostic_redacts_own_private_path(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with patch.object(pilot, 'fetch', return_value='fixturehash'), \
                 patch.object(pilot, 'invoke', side_effect=OSError('failed at ' + str(folder))):
                result = pilot.run(folder, 'approved')
            self.assertNotIn(str(folder), json.dumps(result))
            self.assertFalse(result['uploaded'])


class HostBoundaryTests(unittest.TestCase):
    def test_subprocess_does_not_inherit_unlisted_credentials_or_injection_hooks(self):
        with tempfile.TemporaryDirectory() as temp:
            poison = {name: 'fictional-secret' for name in (
                'SSH_AUTH_SOCK', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
                'GOOGLE_APPLICATION_CREDENTIALS', 'DATABASE_URL', 'SERVICE_PAT',
                'PYTHONPATH', 'PYTHONSTARTUP', 'LD_PRELOAD', 'DYLD_INSERT_LIBRARIES')}
            env = {'PATH': '/usr/bin:/bin', 'HOME': temp, 'LANG': 'C',
                   'DOCKER_CONTEXT': 'desktop-linux', 'DOCKER_CONFIG': temp, **poison}
            with patch.dict(pilot.os.environ, env, clear=True), patch.object(pilot.subprocess, 'run') as run:
                run.return_value = subprocess.CompletedProcess([], 0, '{}', '')
                pilot.invoke(['trusted-tool'], Path(temp), 'env-test')
                received = run.call_args.kwargs['env']
            self.assertTrue(set(poison).isdisjoint(received))
            self.assertEqual(received['DOCKER_CONTEXT'], 'desktop-linux')
            self.assertEqual(received['HOME'], temp)
            self.assertEqual(received['PIP_DISABLE_PIP_VERSION_CHECK'], '1')

    def test_real_child_only_sees_approved_runtime_settings(self):
        import sys
        with tempfile.TemporaryDirectory() as temp, patch.dict(pilot.os.environ, {
                'SERVICE_PAT': 'fictional-pat', 'SSH_AUTH_SOCK': '/fictional/socket',
                'DATABASE_URL': 'postgres://fiction:password@invalid/db'}):
            code = 'import os,json; print(json.dumps({k:os.environ.get(k) for k in ["SERVICE_PAT","SSH_AUTH_SOCK","DATABASE_URL","PATH"]}))'
            result = pilot.invoke([sys.executable, '-I', '-c', code], Path(temp), 'real-child')
            actual = json.loads(result.stdout)
            self.assertIsNone(actual['SERVICE_PAT'])
            self.assertIsNone(actual['SSH_AUTH_SOCK'])
            self.assertIsNone(actual['DATABASE_URL'])
            self.assertTrue(actual['PATH'])

    def test_malformed_json_shapes_stop_with_receipt_and_no_later_stage(self):
        valid_doctor = {'status': 'demo_ready', 'image_id': 'sha256:' + 'a'*64}
        valid_demo = {'status':'passed','provider_calls':0,'test_kind':'offline_fixture','live_research_unlocked':False}
        for stage in ('doctor', 'demo', 'replay'):
            for bad in ([], None, 'invalid-shape', 4):
                with self.subTest(stage=stage, bad=bad), tempfile.TemporaryDirectory() as temp:
                    calls = []
                    def invoke(args, folder, name, **kw):
                        calls.append(name)
                        obj = bad if name == stage else (valid_doctor if name == 'doctor' else valid_demo)
                        return subprocess.CompletedProcess(args, 0, json.dumps(obj), '')
                    with patch.object(pilot, 'fetch', return_value='known'), patch.object(pilot, 'invoke', side_effect=invoke):
                        result = pilot.run(Path(temp), 'approved')
                    self.assertEqual(result['status'], 'stopped')
                    self.assertEqual(json.loads((Path(temp)/'report.json').read_text()), result)
                    self.assertEqual(calls[-1], stage)
                    self.assertFalse(result['uploaded'])

    def test_replay_nested_types_and_unexpected_errors_preserve_stopped_report(self):
        valid_doctor = {'status':'demo_ready','image_id':'sha256:'+'a'*64}
        valid_demo = {'status':'passed','provider_calls':0,'test_kind':'offline_fixture','live_research_unlocked':False}
        for nested in ({'outcome': [],'execution': {}}, {'outcome': {},'execution': None}):
            with tempfile.TemporaryDirectory() as temp:
                def invoke(args, folder, name, **kw):
                    obj = valid_doctor if name=='doctor' else valid_demo if name=='demo' else nested
                    return subprocess.CompletedProcess(args,0,json.dumps(obj),'')
                with patch.object(pilot,'fetch',return_value='known'),patch.object(pilot,'invoke',side_effect=invoke):
                    self.assertEqual(pilot.run(Path(temp),'approved')['status'],'stopped')
                self.assertTrue((Path(temp)/'report.json').exists())
        with tempfile.TemporaryDirectory() as temp, patch.object(pilot,'fetch',side_effect=AttributeError('fictional-secret')):
            result = pilot.run(Path(temp),'approved')
            self.assertEqual(result['status'],'stopped')
            self.assertNotIn('fictional-secret',json.dumps(result))

    def test_integrity_control_uses_exit_and_code_instead_of_human_wording(self):
        import zipfile
        cases = [(3, {'error':{'code':'CAPSULE_HASH_MISMATCH','message':'wording changed'}}, 'passed'),
                 (1, {'error':{'code':'CAPSULE_HASH_MISMATCH'}}, 'stopped'),
                 (3, {'error':{'code':'OTHER_FAILURE'}}, 'stopped')]
        for code, error, expected in cases:
            with self.subTest(code=code,error=error), tempfile.TemporaryDirectory() as temp:
                folder=Path(temp)
                def fetch(name, target):
                    if name==pilot.CAPSULE:
                        with zipfile.ZipFile(target/name,'x') as z:
                            for member in ('manifest.json','experiment.py','sources.json'):z.writestr(member,b'{}')
                    return 'known'
                def invoke(args, target, name, **kw):
                    values={'doctor':{'status':'demo_ready','image_id':'sha256:'+'a'*64},
                            'demo':{'status':'passed','provider_calls':0,'test_kind':'offline_fixture','live_research_unlocked':False},
                            'replay':{'outcome':{'status':'calibration_passed'},'execution':{'exit_code':0,'network':'none'},'discovery_confirmed':False}}
                    if name=='tampered-replay':return subprocess.CompletedProcess(args,code,'',json.dumps(error))
                    return subprocess.CompletedProcess(args,0,json.dumps(values.get(name,{})),'')
                with patch.object(pilot,'fetch',side_effect=fetch),patch.object(pilot,'invoke',side_effect=invoke):
                    result=pilot.run(folder,'approved')
                self.assertEqual(result['status'],expected)


    def test_invalid_json_syntax_preserves_a_stopped_report(self):
        with tempfile.TemporaryDirectory() as temp:
            calls=[]
            def invoke(args, folder, name, **kw):
                calls.append(name)
                return subprocess.CompletedProcess(args,0,'not json','')
            with patch.object(pilot,'fetch',return_value='known'),patch.object(pilot,'invoke',side_effect=invoke):
                result=pilot.run(Path(temp),'approved')
            self.assertEqual(result['status'],'stopped')
            self.assertEqual(calls[-1],'doctor')
            self.assertTrue((Path(temp)/'report.json').exists())


if __name__ == '__main__': unittest.main()
