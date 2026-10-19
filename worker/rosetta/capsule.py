"""Portable contribution capsules. Receiving a report never establishes its truth."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import zipfile

from .common import Invalid, CapsuleIntegrityError, canonical, digest, read_json, now
from .control import targets
from .sandbox import experiment
from .verify import check_result

NAMES = {"manifest.json", "experiment.py", "sources.json"}
MAX_BYTES = 2_000_000


def contract(target):
    return digest({key: target[key] for key in ["id", "kind", "minimum_degree", "forbidden_lengths"]})


def bundle(run_dir, output):
    root = Path(run_dir)
    run = read_json(root / "run.json")
    packet = read_json(root / "packet.json")
    proposal = read_json(root / "proposal.json")
    sealed = read_json(root / "pre-execution.json")
    code = (root / "experiment.py").read_bytes()
    if (len(code) > 24000 or hashlib.sha256(code).hexdigest() != sealed["program_sha256"]
            or code.decode() != proposal["python"] or digest(proposal) != run["proposal_sha256"]
            or digest(packet) != run["packet_sha256"]):
        raise Invalid("run artifacts changed; refusing to package inconsistent evidence")
    if not run.get("experiment"):
        raise Invalid("no execution receipt to contribute")
    sources = canonical(packet["sources"])
    manifest = {"schema_version": 1, "target_id": run["target_id"], "target_kind": run["target_kind"],
        "method_id": run["method_id"], "created_at": now(), "original_run_id": run["run_id"],
        "declared_outcome": run["outcome"], "agent": run["agent"],
        "program_sha256": hashlib.sha256(code).hexdigest(), "sources_sha256": hashlib.sha256(sources).hexdigest(),
        "target_contract_sha256": contract(packet["target"]),
        "original_image_id": run["experiment"]["image_id"], "original_controller_sha256": run["controller_sha256"],
        "claim_status": "contributor_report_unverified"}
    output = Path(output)
    # Exclusive creation: never silently replace another artifact or follow an output symlink.
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, data in [("manifest.json", canonical(manifest)), ("experiment.py", code), ("sources.json", sources)]:
                archive.writestr(name, data)
    output.chmod(0o600)
    return {"capsule": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "claim_status": "contributor_report_unverified", "uploaded": False}


def read_capsule(path):
    path = Path(path)
    with path.open("rb") as stream:
        content = stream.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise Invalid("capsule exceeds the transport size limit")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) != 3 or {x.filename for x in entries} != NAMES:
                raise Invalid("unexpected/duplicate capsule members")
            if any(x.file_size > MAX_BYTES or x.flag_bits & 1 or stat.S_ISLNK(x.external_attr >> 16) for x in entries):
                raise Invalid("oversized, encrypted or symlink capsule member")
            if sum(x.file_size for x in entries) > MAX_BYTES:
                raise Invalid("decompressed capsule exceeds its limit")
            # Never extract archive paths into the host filesystem.
            data = {x.filename: archive.read(x) for x in entries}
    except (zipfile.BadZipFile, RuntimeError) as error:
        raise Invalid("invalid capsule archive") from error
    manifest = json.loads(data["manifest.json"])
    if (not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int
            or manifest["schema_version"] != 1 or manifest.get("claim_status") != "contributor_report_unverified"):
        raise Invalid("capsule schema/claim classification is unsupported")
    if not 1 <= len(data["experiment.py"]) <= 24000:
        raise Invalid("capsule program exceeds the limit")
    for name, field in [("experiment.py", "program_sha256"), ("sources.json", "sources_sha256")]:
        if hashlib.sha256(data[name]).hexdigest() != manifest.get(field):
            raise CapsuleIntegrityError("capsule artifact hash mismatch")
    target = next((t for t in targets() if t["id"] == manifest.get("target_id") and t.get("enabled")), None)
    if target is None or contract(target) != manifest.get("target_contract_sha256"):
        raise Invalid("capsule target lacks a matching local reviewed verifier contract")
    return manifest, data, target, hashlib.sha256(content).hexdigest()


def replay(path, image):
    manifest, data, target, capsule_hash = read_capsule(path)
    with tempfile.TemporaryDirectory(prefix="rosetta-replay-") as temp:
        code = Path(temp) / "experiment.py"
        code.write_bytes(data["experiment.py"])
        code.chmod(0o644)
        receipt = experiment(code, image=image, seconds=30)
    if receipt["failure"] or receipt["exit_code"]:
        outcome = {"status": "inconclusive", "reason": "independent replay did not complete successfully"}
    else:
        try:
            outcome = check_result(json.loads(receipt["stdout"]), target)
        except (Invalid, ValueError, TypeError):
            outcome = {"status": "rejected", "reason": "replayed program returned an invalid certificate/output"}
    return {"schema_version": 1, "capsule_sha256": capsule_hash,
        "contributor_claim_status": "unverified", "independent_replay": True,
        "outcome": outcome, "execution": receipt, "discovery_confirmed": False, "payout_earned": False}
