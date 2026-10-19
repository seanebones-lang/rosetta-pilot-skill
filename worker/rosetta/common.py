from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time


class Invalid(ValueError):
    pass


class CapsuleIntegrityError(Invalid):
    """Stable CLI classification; message text is only for humans."""
    code = "CAPSULE_HASH_MISMATCH"
    exit_code = 3


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def bounded_process(command, *, cwd=None, env=None, stdin=b"", seconds=60, output_limit=131072):
    """Bound wall time AND captured output; terminate the entire child process group."""
    start = time.monotonic()
    proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    streams = {"stdout": bytearray(), "stderr": bytearray()}
    reason = None
    selector = selectors.DefaultSelector()
    try:
        # Packets are capped by the caller; ordinary pipe capacity is not assumed.
        os.set_blocking(proc.stdin.fileno(), False)
        selector.register(proc.stdin, selectors.EVENT_WRITE, "stdin")
        for name in streams:
            stream = getattr(proc, name)
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        offset = 0
        while selector.get_map():
            if time.monotonic() - start > seconds:
                reason = "timeout"
                break
            for key, _ in selector.select(timeout=0.05):
                if key.data == "stdin":
                    try:
                        offset += os.write(key.fd, stdin[offset:offset + 4096]) if offset < len(stdin) else 0
                    except BrokenPipeError:
                        offset = len(stdin)
                    if offset >= len(stdin):
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                else:
                    block = os.read(key.fd, 4096)
                    if not block:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                    else:
                        streams[key.data].extend(block)
                        if sum(map(len, streams.values())) > output_limit:
                            reason = "output_limit"
                            break
            if reason:
                break
        if reason:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        proc.wait(timeout=5)
    finally:
        selector.close()
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
        for name in ["stdin", "stdout", "stderr"]:
            stream = getattr(proc, name)
            if not stream.closed:
                stream.close()
    return {"exit_code": proc.returncode, "failure": reason,
            "elapsed_ms": round((time.monotonic() - start) * 1000),
            **{k: bytes(v[:output_limit]).decode("utf-8", "replace") for k, v in streams.items()}}
