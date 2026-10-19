from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from rosetta.capsule import bundle, contract, read_capsule, replay
from rosetta.common import Invalid, canonical, digest, save_json
from rosetta.control import targets


class CapsuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = next(t for t in targets() if t['id'] == 'calibration-c5')
        graph = {'vertices': 5, 'edges': [[0,1],[1,2],[2,3],[3,4],[4,0]]}
        self.code = 'import json\nprint(json.dumps(' + repr({'status':'candidate','certificate':graph}) + '))\n'
        packet = {'target':self.target,'sources':[]}
        proposal = {'python':self.code}
        report = {'target_id':self.target['id'],'target_kind':'calibration',
                  'method_id':'construct-an-odd-cycle','run_id':'fixture',
                  'outcome':{'status':'calibration_passed'},'agent':{'id':'fixture','model':'fixture'},
                  'experiment':{'image_id':'sha256:fixture'},'controller_sha256':'fixture',
                  'proposal_sha256':digest(proposal),'packet_sha256':digest(packet),
                  'artifact_uri':'file:///private/path/not-for-contribution',
                  'agent_summary':'private diagnostic omitted from capsule'}
        self.run = self.root/'run'
        self.run.mkdir()
        for name, value in [('run.json',report),('packet.json',packet),('proposal.json',proposal),
                            ('pre-execution.json',{'program_sha256':hashlib.sha256(self.code.encode()).hexdigest()})]:
            save_json(self.run/name,value)
        (self.run/'experiment.py').write_text(self.code)
        self.path = self.root/'contribution.zip'
        bundle(self.run,self.path)

    def rewrite(self, update=None, extra=None):
        with zipfile.ZipFile(self.path) as archive:
            files = {n:archive.read(n) for n in archive.namelist()}
        if update:
            update(files)
        with zipfile.ZipFile(self.path,'w') as archive:
            for name, data in files.items():
                archive.writestr(name,data)
            if extra:
                archive.writestr(*extra)

    def test_portable_minimum_evidence_excludes_host_diagnostics(self):
        manifest, files, target, sha = read_capsule(self.path)
        self.assertEqual(set(files),{'manifest.json','experiment.py','sources.json'})
        self.assertEqual(target['id'],self.target['id'])
        self.assertEqual(manifest['claim_status'],'contributor_report_unverified')
        self.assertEqual(sha,hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertNotIn(b'private/path',b''.join(files.values()))
        self.assertNotIn(b'private diagnostic',b''.join(files.values()))
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode),0o600)

    def test_changed_program_rejected_before_execution(self):
        self.rewrite(lambda f:f.update({'experiment.py':b'print("forged")'}))
        with patch('rosetta.capsule.experiment') as execute, self.assertRaisesRegex(Invalid,'hash mismatch'):
            replay(self.path,'unused')
        execute.assert_not_called()

    def test_changed_local_run_not_packaged(self):
        (self.run/'experiment.py').write_text('print("changed")')
        with self.assertRaisesRegex(Invalid,'artifacts changed'):
            bundle(self.run,self.root/'changed.zip')

    def test_traversal_and_duplicate_members_rejected(self):
        original = self.path.read_bytes()
        for extra in [('../outside.py',b'bad'),('experiment.py',b'duplicate')]:
            self.path.write_bytes(original)
            with self.subTest(extra=extra[0]):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore',UserWarning)
                    self.rewrite(extra=extra)
                with self.assertRaises(Invalid):
                    read_capsule(self.path)
        self.assertFalse((self.root/'outside.py').exists())

    def test_symlink_member_rejected(self):
        with zipfile.ZipFile(self.path) as archive:
            files = {n:archive.read(n) for n in archive.namelist()}
        with zipfile.ZipFile(self.path,'w') as archive:
            for name,data in files.items():
                info = zipfile.ZipInfo(name)
                if name == 'experiment.py':
                    info.create_system=3
                    info.external_attr=(stat.S_IFLNK|0o777)<<16
                archive.writestr(info,data)
        with self.assertRaisesRegex(Invalid,'symlink'):
            read_capsule(self.path)

    def test_decompression_limit_rejected(self):
        with zipfile.ZipFile(self.path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json',b'{}')
            archive.writestr('experiment.py',b'x'*2_000_001)
            archive.writestr('sources.json',b'[]')
        self.assertLess(self.path.stat().st_size,2_000_000)
        with self.assertRaisesRegex(Invalid,'oversized'):
            read_capsule(self.path)

    def test_contributor_cannot_replace_reviewed_contract(self):
        def changed(files):
            manifest=json.loads(files['manifest.json'])
            manifest['target_contract_sha256']=contract({**self.target,'minimum_degree':0})
            files['manifest.json']=canonical(manifest)
        self.rewrite(changed)
        with self.assertRaisesRegex(Invalid,'local reviewed verifier'):
            read_capsule(self.path)

    def test_invalid_manifest_type_rejected(self):
        self.rewrite(lambda f:f.update({'manifest.json':b'[]'}))
        with self.assertRaises(Invalid):
            read_capsule(self.path)

    def test_claim_does_not_override_independent_checker(self):
        receipt={'failure':None,'exit_code':0,'stdout':json.dumps({'status':'candidate',
                 'certificate':{'vertices':4,'edges':[[0,1],[1,2],[2,3],[3,0]]}})}
        with patch('rosetta.capsule.experiment',return_value=receipt):
            result=replay(self.path,'fixture')
        self.assertEqual(result['outcome']['status'],'rejected')
        self.assertFalse(result['discovery_confirmed'])
        self.assertFalse(result['payout_earned'])

    def test_invalid_replay_output_is_rejected(self):
        with patch('rosetta.capsule.experiment',return_value={'failure':None,'exit_code':0,'stdout':'not JSON'}):
            self.assertEqual(replay(self.path,'fixture')['outcome']['status'],'rejected')

    @unittest.skipUnless(os.environ.get('ROSETTA_DOCKER_TESTS')=='1','opt-in real Docker replay')
    def test_actual_offline_replay(self):
        result=replay(self.path,os.environ['ROSETTA_TEST_IMAGE'])
        self.assertEqual(result['outcome']['status'],'calibration_passed',result)
        self.assertEqual(result['contributor_claim_status'],'unverified')
        self.assertEqual(result['execution']['network'],'none')
        self.assertFalse(result['discovery_confirmed'])

    def test_cli_hash_failure_has_stable_code_without_invoking_docker(self):
        from rosetta import cli
        import io
        self.rewrite(lambda f:f.update({'experiment.py':b'changed'}))
        for message in ('capsule artifact hash mismatch', 'human wording changed'):
            from rosetta.common import CapsuleIntegrityError
            with patch('sys.argv',['rosetta','replay',str(self.path),'--image','unused']), \
                 patch('rosetta.capsule.read_capsule',side_effect=CapsuleIntegrityError(message)), \
                 patch('rosetta.capsule.experiment') as execute, patch('sys.stderr',new_callable=io.StringIO) as error:
                with self.assertRaises(SystemExit) as stopped:cli.main()
            self.assertEqual(stopped.exception.code,3)
            self.assertEqual(json.loads(error.getvalue())['error']['code'],'CAPSULE_HASH_MISMATCH')
            execute.assert_not_called()
        with patch('sys.argv',['rosetta','replay',str(self.path),'--image','unused']), \
             patch('rosetta.capsule.experiment') as execute, patch('sys.stderr',new_callable=io.StringIO) as error:
            with self.assertRaises(SystemExit) as stopped:cli.main()
        self.assertEqual(stopped.exception.code,3)
        self.assertEqual(json.loads(error.getvalue())['error']['code'],'CAPSULE_HASH_MISMATCH')
        execute.assert_not_called()


if __name__=='__main__':
    unittest.main()
