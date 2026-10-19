#!/usr/bin/env python3
"""Explicit, no-key onboarding for the pinned public Rosetta 0.2.3 pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import urllib.request
import zipfile

ORIGIN = 'https://rosetta-research.nexteleven.chatgpt.site'
WHEEL = 'rosetta_research-0.2.3-py3-none-any.whl'
CAPSULE = 'calibration-c5-capsule.zip'
# Environment reduction for trusted host tools, not a host security sandbox.
KEEP_ENV = frozenset({'PATH', 'HOME', 'USER', 'LANG', 'LC_ALL', 'TMPDIR',
                      'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG',
                      'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'})
INTEGRITY_EXIT = 3
INTEGRITY_CODE = 'CAPSULE_HASH_MISMATCH'
ARTIFACTS = {
    WHEEL: ('/downloads/' + WHEEL, '704299511211b34a7c147bff71fcfe9e4226dd60fa173fefe55acb90cfb60068', 47973),
    CAPSULE: ('/examples/' + CAPSULE, '990fa756245825f4ed4621bb83f17a7eb663b852215a13d8f8e95a5c4c342105', 1369),
}


class Stopped(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Stopped('Download redirected; review the canonical source before retrying.')


def save(path, value):
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def fetch(name, folder):
    url, expected, size = ARTIFACTS[name]
    req = urllib.request.Request(ORIGIN + url, headers={'User-Agent': 'ProjectRosettaPilot/1.0 (public onboarding skill)'})
    with urllib.request.build_opener(NoRedirect).open(req, timeout=25) as response:
        data = response.read(size + 1)
    if len(data) != size or hashlib.sha256(data).hexdigest() != expected:
        raise Stopped('Published artifact size/hash mismatch: ' + name)
    with (folder / name).open('xb') as f:
        f.write(data)
    return expected


def invoke(args, folder, name, timeout=90, expect=0):
    # Keep only runtime/locale and explicitly selected Docker connection settings.
    # HOME/Docker access still confer authority: this is not process isolation.
    env = {k: v for k, v in os.environ.items() if k in KEEP_ENV}
    env['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
    result = subprocess.run([str(a) for a in args], cwd=folder, env=env,
                            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
    if len(result.stdout) + len(result.stderr) > 256000:
        raise Stopped('Command output exceeds the onboarding limit: ' + name)
    save(folder / (name + '.json'), {'exit_code': result.returncode,
                                    'stdout': result.stdout, 'stderr': result.stderr})
    if expect is not None and result.returncode != expect:
        raise Stopped('Command did not complete as expected: ' + name + '; inspect its private output.')
    return result


def check(condition, message):
    if not condition:
        raise Stopped(message)


def object_output(result, name):
    try:
        value = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise Stopped(name + ' returned invalid JSON; inspect its private output.') from None
    check(isinstance(value, dict), name + ' returned a non-object JSON response.')
    return value


def run(folder, image):
    report = {'schema_version': 1, 'test': 'public_offline_onboarding', 'status': 'incomplete',
              'os': platform.system(), 'python': platform.python_version(),
              'wheel_version': '0.2.3', 'checks': {}, 'uploaded': False,
              'discovery_confirmed': False, 'live_research_tested': False,
              'outside_machine_verified': False,
              'sharing': 'Review and manually share only this bounded report with an approved recipient.'}
    try:
        for name in ARTIFACTS:
            report['checks'][name] = fetch(name, folder)
        invoke([sys.executable, '-m', 'venv', '.venv'], folder, 'venv')
        python = folder / '.venv/bin/python'
        cli = folder / '.venv/bin/rosetta'
        invoke([python, '-m', 'pip', 'install', '--no-index', '--no-deps', str(folder / WHEEL)], folder, 'install')
        invoke([cli, 'protocol'], folder, 'protocol')
        doctor = object_output(invoke([cli, 'doctor', '--image', image], folder, 'doctor'), 'doctor')
        check(doctor.get('status') == 'demo_ready', 'Local setup is incomplete; inspect doctor.json. No demo executed.')
        resolved = doctor.get('image_id')
        check(isinstance(resolved, str) and re.fullmatch(r'sha256:[0-9a-f]{64}', resolved),
              'doctor did not return a resolved image ID; no demo executed.')
        report['image_id'] = resolved
        report['docker'] = invoke(['docker', 'version', '--format', '{{.Server.Version}}'], folder, 'docker-version', timeout=15).stdout.strip()
        demo = object_output(invoke([cli, 'demo', '--state', str(folder / 'state'), '--image', resolved], folder, 'demo'), 'demo')
        check(demo.get('status') == 'passed' and demo.get('provider_calls') == 0
              and demo.get('test_kind') == 'offline_fixture' and demo.get('live_research_unlocked') is False,
              'Demo result did not meet the known-fixture criteria.')
        report['checks']['demo'] = 'passed'
        replay = object_output(invoke([cli, 'replay', str(folder / CAPSULE), '--image', resolved], folder, 'replay'), 'replay')
        check(isinstance(replay.get('outcome'), dict) and isinstance(replay.get('execution'), dict),
              'replay returned invalid nested result objects.')
        check(replay.get('outcome', {}).get('status') == 'calibration_passed'
              and replay.get('execution', {}).get('exit_code') == 0
              and replay.get('execution', {}).get('network') == 'none'
              and replay.get('discovery_confirmed') is False, 'Public capsule replay did not pass.')
        report['checks']['replay'] = 'passed'
        with zipfile.ZipFile(folder / CAPSULE) as source:
            members = {n: source.read(n) for n in source.namelist()}
        check(set(members) == {'manifest.json', 'experiment.py', 'sources.json'}, 'Unexpected known capsule members.')
        members['experiment.py'] += b'\n# Deliberate transport-integrity test.\n'
        with zipfile.ZipFile(folder / 'tampered-capsule.zip', 'x') as target:
            for name, data in members.items():
                target.writestr(name, data)
        rejection = invoke([cli, 'replay', str(folder / 'tampered-capsule.zip'), '--image', resolved],
                           folder, 'tampered-replay', expect=None)
        try:
            error = json.loads(rejection.stderr)
        except (ValueError, TypeError):
            error = None
        check(rejection.returncode == INTEGRITY_EXIT and isinstance(error, dict)
              and isinstance(error.get('error'), dict)
              and error['error'].get('code') == INTEGRITY_CODE,
              'Altered capsule was not rejected for the expected integrity failure.')
        report['checks']['tampered_capsule'] = 'rejected_hash_mismatch'
        report['status'] = 'passed'
        report['rosetta_provider_calls'] = 0
    except (Stopped, OSError, ValueError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        report['status'] = 'stopped'
        # A bounded local diagnostic; never include raw provider/session logs.
        report['reason'] = str(error).replace(str(folder), '<test-directory>')[:500]
    except Exception as error:
        # Preserve a stopped receipt for unexpected failures without echoing
        # arbitrary exception values, which may contain credentials or paths.
        report['status'] = 'stopped'
        report['reason'] = 'Unexpected local error (' + type(error).__name__ + '); inspect private outputs.'
    save(folder / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, help='New private test directory; existing paths are refused')
    parser.add_argument('--image', required=True, help='Existing operator-approved Python 3.12 image ID or tag')
    parser.add_argument('--run', action='store_true', help='Explicitly authorize downloads, local installation and offline execution')
    args = parser.parse_args()
    if not args.run:
        print(json.dumps({'action': 'plan_only', 'changes_made': False, 'origin': ORIGIN,
                          'artifacts': list(ARTIFACTS), 'image': args.image,
                          'next': 'After operator authorization, repeat with --run and a new private --work directory.'}, indent=2))
        return 0
    if os.name != 'posix' or sys.version_info < (3, 11):
        parser.error('Use Python 3.11+ on macOS or Linux.')
    if not args.image or args.image.startswith('-') or '\x00' in args.image:
        parser.error('Supply an explicit existing operator-approved image.')
    os.umask(0o077)
    folder = Path(args.work).expanduser().absolute()
    try:
        folder.mkdir(mode=0o700, parents=False, exist_ok=False)
    except OSError:
        parser.error('Choose a new directory under an existing writable parent; existing paths/symlinks are refused.')
    report = run(folder, args.image)
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
