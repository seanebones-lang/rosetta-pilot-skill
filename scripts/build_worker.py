"""Build the public MIT worker snapshot with fixed wheel timestamps."""
from pathlib import Path
import os
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
out = root / 'dist'
out.mkdir(exist_ok=True)
env = dict(os.environ, SOURCE_DATE_EPOCH='1792368000')
subprocess.run([sys.executable, '-m', 'pip', 'wheel', '.', '--no-deps', '--no-index',
                '--no-build-isolation', '--wheel-dir', str(out)],
               cwd=root/'worker', env=env, check=True)
# Fail the release if the built wheel differs from the independently pinned helper.
import ast
import hashlib
import zipfile
pins = {}
for node in ast.parse((root/'scripts/pilot.py').read_text()).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        if node.targets[0].id == 'WHEEL': pins['name'] = ast.literal_eval(node.value)
        if node.targets[0].id == 'ARTIFACTS':
            entry = node.value.values[0]
            pins['hash'] = ast.literal_eval(entry.elts[1])
            pins['bytes'] = ast.literal_eval(entry.elts[2])
wheel = out/pins['name']
assert wheel.stat().st_size == pins['bytes']
assert hashlib.sha256(wheel.read_bytes()).hexdigest() == pins['hash']
with zipfile.ZipFile(wheel) as z:
    for name in z.namelist():
        if name.startswith('rosetta/') and name.endswith('.py'):
            assert z.read(name) == (root/'worker'/name).read_bytes()
print('Worker artifact matches the reviewed helper pin and source bytes.')
