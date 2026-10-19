from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

from .common import Invalid, bounded_process, canonical, digest, now, read_json, save_json
from .sandbox import experiment
from .intake import live_status
from .verify import check_result, validate_plan
from .witness import export

CODE_ROOT = Path(__file__).resolve().parent
ROOT = CODE_ROOT.parent
if not (ROOT / "PROMPT.md").is_file() or not (ROOT / "catalog/targets.json").is_file():
    ROOT = Path(sys.prefix) / "share/rosetta"


def controller_fingerprint():
    return digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(CODE_ROOT.glob("*.py"))})


def adapter_fingerprint(config):
    files = {}
    for item in config["agent_command"]:
        path = Path(item)
        if path.is_file() and path.suffix in {".py", ".json", ".sh"}:
            if path.stat().st_size > 1024 * 1024:
                raise Invalid("adapter configuration/code file is too large")
            files[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest({"command": config["agent_command"], "files": files})


def source_packet(target):
    sources = []
    for spec in target["sources"]:
        relative = Path(spec["path"])
        path = (ROOT / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(ROOT / "sources"):
            raise Invalid("source path escapes the source directory")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != spec["sha256"]:
            raise Invalid("source hash mismatch")
        checked = dt.datetime.fromisoformat(spec["checked_at"].replace("Z", "+00:00"))
        if checked.tzinfo is None:
            raise Invalid("source review requires a timezone")
        age = dt.datetime.now(dt.timezone.utc) - checked
        if age.total_seconds() < -300 or age.days >= 7:
            raise Invalid("source review expired or invalid; refresh target status and reward terms")
        sources.append({"uri": spec["uri"], "sha256": spec["sha256"], "content": data.decode()})
    if not sources:
        raise Invalid("target requires a preserved, reviewed source packet")
    return sources


def targets():
    return read_json(ROOT / "catalog/targets.json")["targets"]


def run(config, *, target_id, date=None, proposal=None, retry_export=True,
        retry_of=None, attempt_id=None, retry_reason=None):
    state = Path(config["state_dir"]).expanduser().resolve()
    state.mkdir(parents=True, exist_ok=True)
    state.chmod(0o700)
    lock_file = state / "controller.lock"
    with lock_file.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Invalid("another Rosetta run is active") from None
        if retry_export and config.get("witness"):
            for pending in sorted((state / "runs").glob("*/run.json")):
                try:
                    export(pending.parent, **config["witness"])
                except (Invalid, OSError, subprocess.SubprocessError):
                    # Still record today's run even if Witness is temporarily unavailable.
                    pass
        target = next((t for t in targets() if t["id"] == target_id), None)
        if not target or target.get("enabled") is not True:
            raise Invalid("unknown or disabled target")
        day = date or dt.datetime.now(ZoneInfo(config.get("timezone", "America/Chicago"))).date().isoformat()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise Invalid("invalid run date")
        dt.date.fromisoformat(day)
        retry = None
        if any(x is not None for x in [retry_of, attempt_id, retry_reason]):
            if (not isinstance(retry_of, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", retry_of)
                    or not isinstance(attempt_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", attempt_id)
                    or not isinstance(retry_reason, str) or not 1 <= len(retry_reason.strip()) <= 500):
                raise Invalid("retry requires a safe original run ID, stable attempt ID and review reason")
            original_path = state / "runs" / retry_of / "run.json"
            original = read_json(original_path)
            if (original["run_id"] != retry_of or original["target_id"] != target_id
                    or original["outcome"]["status"] != "failed" or original.get("experiment") is not None):
                raise Invalid("retry is limited to a failed proposal stage for the same target")
            if original["method_id"] not in target["methods"]:
                raise Invalid("original method is no longer approved")
            retry = {"run_id": retry_of, "run_sha256": digest(original), "reason": retry_reason,
                     "method_id": original["method_id"], "prior_provider_outcome": "unknown"}
        run_id = retry_of + "-retry-" + attempt_id if retry else day + "-" + target_id
        directory = state / "runs" / run_id
        if (directory / "run.json").exists():
            existing = read_json(directory / "run.json")
            if retry and existing.get("retry") != retry:
                raise Invalid("retry attempt ID conflicts with a different prior run or review")
            return existing  # same explicit attempt key is idempotent
        if directory.exists():
            raise Invalid("interrupted run requires explicit recovery; artifacts have been preserved")
        sources = source_packet(target) + [live_status(target)] if target["kind"] != "calibration" else []
        history = [read_json(p) for p in sorted((state / "runs").glob("*/run.json"))
                   if p.parent != directory]
        used = {r["method_id"] for r in history if r["target_id"] == target_id}
        methods = [retry["method_id"]] if retry else [m for m in target["methods"] if m not in used]
        if not methods:
            raise Invalid("reviewed methods exhausted; no automatic rerun of a recorded dead end")
        directory.mkdir(parents=True, mode=0o700)
        method = methods[0]
        packet = {"protocol_version": 1, "run_id": run_id, "target": target, "method_id": method,
                  "retry": retry,
                  "sources": sources, "previous_outcomes": [{"method_id": x["method_id"], "outcome": x["outcome"]}
                  for x in history if x["target_id"] == target_id],
                  "instructions": (ROOT / "PROMPT.md").read_text()}
        save_json(directory / "packet.json", packet)
        started = now()
        receipt = None
        raw_summary = "No agent response was obtained."
        outcome = {"status": "failed", "reason": "not started"}
        agent_receipt = {"exit_code": None, "failure": None}
        plan = None
        try:
            if proposal:
                plan = read_json(proposal)
                raw_summary = canonical(plan).decode()
            else:
                if not config.get("agent_command"):
                    raise Invalid("no agent adapter configured")
                agent_receipt = bounded_process(config["agent_command"], cwd=directory,
                    env={**os.environ, "ROSETTA_PACKET": str(directory / "packet.json"),
                         "ROSETTA_AGENT_RECEIPT": str(directory / "agent-receipt.json")},
                    stdin=canonical(packet), seconds=180, output_limit=131072)
                # Keep diagnostics private, never in the public source tree.
                save_json(directory / "agent-execution.json", agent_receipt)
                if agent_receipt["failure"] or agent_receipt["exit_code"]:
                    failure = agent_receipt["failure"] or "nonzero_exit"
                    raise Invalid(f"agent adapter {failure}; provider completion and charge status unknown")
                raw_summary = agent_receipt["stdout"]
                plan = json.loads(raw_summary)
            validate_plan(plan, packet)
            save_json(directory / "proposal.json", plan)
            code_file = directory / "experiment.py"
            code_file.write_text(plan["python"])
            code_file.chmod(0o644)  # the unprivileged container user must be able to read this one file
            save_json(directory / "pre-execution.json", {"at": now(), "proposal_sha256": digest(plan),
                "program_sha256": hashlib.sha256(code_file.read_bytes()).hexdigest(), "method_id": method})
            receipt = experiment(code_file, image=config["image"], seconds=30)
            save_json(directory / "experiment-execution.json", receipt)
            if receipt["failure"] or receipt["exit_code"]:
                outcome = {"status": "inconclusive", "reason": "experiment failed, timed out or exceeded output limit"}
            else:
                outcome = check_result(json.loads(receipt["stdout"]), target)
        except (Invalid, ValueError, OSError, subprocess.SubprocessError) as error:
            outcome = {"status": "failed", "reason": str(error)[:500]}
        head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True).stdout)
        report = {"schema_version": 1, "run_id": run_id, "target_id": target_id, "target_kind": target["kind"],
            "retry": retry,
            "method_id": method, "started_at": started, "finished_at": now(), "code_commit": head,
            "working_tree_dirty": dirty, "controller_sha256": controller_fingerprint(),
            "prompt_sha256": hashlib.sha256(packet["instructions"].encode()).hexdigest(),
            "packet_sha256": digest(packet), "proposal_sha256": digest(plan) if plan else None,
            "agent": {"id": "proposal-file", "model": "unknown-unverified"} if proposal else config["agent_identity"],
            "agent_summary": raw_summary[:131072],
            "agent_usage": read_json(directory / "agent-receipt.json") if (directory / "agent-receipt.json").exists() else None,
            "artifact_uri": directory.as_uri(), "outcome": outcome,
            "experiment": receipt, "reward": target.get("reward"),
            "discovery_confirmed": False, "payout_earned": False}
        save_json(directory / "run.json", report)
        witness_status = "not_configured"
        if config.get("witness"):
            try:
                export(directory, **config["witness"])
                witness_status = "verified"
            except (Invalid, OSError, subprocess.SubprocessError):
                witness_status = "queued"
        save_json(directory / "status.json", {"witness": witness_status,
            "requires_review": outcome["status"] in {"failed", "candidate_needs_review"},
            "notification_sent": False})
        return report


def validate_calibration(config):
    from .sandbox import resolve_image
    state = Path(config["state_dir"]).expanduser()
    gate = read_json(state / "calibration.json")
    expected = {"controller_sha256": controller_fingerprint(), "agent": config["agent_identity"],
                "adapter_sha256": adapter_fingerprint(config), "image_id": resolve_image(config["image"]),
                "prompt_sha256": hashlib.sha256((ROOT / "PROMPT.md").read_bytes()).hexdigest()}
    if (any(gate.get(key) != value for key, value in expected.items()) or gate.get("passed") is not True
            or gate.get("live_adapter_tested") is not True):
        raise Invalid("calibration gate does not match this controller, adapter, prompt or image")
    if (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(gate["at"])).days >= 7:
        raise Invalid("agent calibration expired; repeat the bounded controls")
    from urllib.parse import unquote, urlparse
    proof = urlparse(gate["run_uri"])
    if proof.scheme != "file" or proof.netloc:
        raise Invalid("calibration proof must be a local artifact")
    proof_path = Path(unquote(proof.path)).resolve()
    if not proof_path.is_relative_to((state / "calibrations").resolve()):
        raise Invalid("calibration proof escapes private calibration state")
    report = read_json(proof_path / "run.json")
    if digest(report) != gate["run_sha256"] or report["agent"] != config["agent_identity"]:
        raise Invalid("calibration proof changed or identifies another agent")
    return gate


def daily(config):
    validate_calibration(config)
    return run(config, target_id=config["daily_target"])


def retry(config, *, retry_of, attempt_id, reason):
    """Explicit operator-reviewed recovery, never called by the daily scheduler."""
    validate_calibration(config)
    return run(config, target_id=config["daily_target"], retry_of=retry_of,
               attempt_id=attempt_id, retry_reason=reason)


def calibrate(config, proposal=None):
    import uuid
    from .verify import graph_certificate, validate_cipher
    state = Path(config["state_dir"]).expanduser()
    trial = {**config, "state_dir": str(state / "calibrations" / uuid.uuid4().hex), "witness": None}
    report = run(trial, target_id="calibration-c5", proposal=proposal)
    bad = graph_certificate({"vertices": 4, "edges": [[0,1],[1,2],[2,3],[3,0]]},
                            minimum_degree=2, forbidden_lengths=[4])
    if bad["status"] != "rejected":
        raise Invalid("positive cycle control failed")
    try:
        validate_cipher({"ciphertext_lines": [[0,1],[1]], "total_length": 2, "unique_glyphs": 2})
    except Invalid:
        pass
    else:
        raise Invalid("malformed input control failed")
    if report["outcome"]["status"] != "calibration_passed":
        raise Invalid("agent calibration did not produce a valid independently checked counterexample")
    gate = {"passed": True, "at": now(), "controller_sha256": controller_fingerprint(),
            "agent": config["agent_identity"], "adapter_sha256": adapter_fingerprint(config),
            "image_id": report["experiment"]["image_id"], "prompt_sha256": report["prompt_sha256"],
            "run_uri": report["artifact_uri"], "run_sha256": digest(report), "live_adapter_tested": proposal is None,
            "controls": ["agent-counterexample", "reject-four-cycle", "reject-malformed-input"]}
    save_json(state / "calibration.json", gate)
    return gate
