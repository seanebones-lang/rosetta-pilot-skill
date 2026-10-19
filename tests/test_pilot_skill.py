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


if __name__ == '__main__': unittest.main()
