"""Package only the reviewed portable skill files, reproducibly."""
from pathlib import Path
import hashlib
import re
import zipfile

root = Path(__file__).resolve().parents[1]
version = re.search(r'^  version: (\d+\.\d+\.\d+)$', (root / 'SKILL.md').read_text(), re.M).group(1)
out = root / 'dist'
out.mkdir(exist_ok=True)
archive = out / f'rosetta-pilot-skill-{version}.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for name in ['SKILL.md', 'LICENSE', 'scripts/pilot.py']:
        info = zipfile.ZipInfo('rosetta-pilot/' + name, (2026, 10, 19, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        z.writestr(info, (root / name).read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
(out / 'SHA256SUMS').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')
print(archive.name)
