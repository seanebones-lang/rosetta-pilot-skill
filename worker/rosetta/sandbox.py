from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import uuid

from .common import Invalid, bounded_process


def resolve_image(image):
    result = subprocess.run(["docker", "image", "inspect", image, "--format", "{{.Id}}"],
                            capture_output=True, text=True, timeout=15)
    image_id = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise Invalid("sandbox image must already be installed; Rosetta never pulls images unattended")
    return image_id


def experiment(code_file, *, image, seconds=30):
    code_file = Path(code_file).resolve(strict=True)
    if not code_file.is_file() or code_file.stat().st_size > 24000:
        raise Invalid("invalid experiment file")
    image_id = resolve_image(image)
    name = "rosetta-" + uuid.uuid4().hex
    command = ["docker", "run", "--name", name, "--pull=never", "--rm", "--network=none",
               "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=65534:65534",
               "--memory=256m", "--memory-swap=256m", "--cpus=1", "--pids-limit=32",
               "--ulimit=nofile=64:64", "--ulimit=fsize=1048576:1048576", "--log-driver=none",
               "--tmpfs=/tmp:rw,noexec,nosuid,size=16m", "--workdir=/tmp",
               "--mount", f"type=bind,src={code_file},dst=/experiment.py,readonly",
               "--entrypoint=python3", image_id, "-I", "-B", "/experiment.py"]
    try:
        result = bounded_process(command, seconds=seconds, output_limit=32768)
    finally:
        # Named cleanup is required even when the Docker client times out or is interrupted.
        subprocess.run(["docker", "rm", "--force", name], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=10)
    return {**result, "image_id": image_id, "network": "none", "memory_mb": 256,
            "cpu_limit": 1, "wall_limit_seconds": seconds}
