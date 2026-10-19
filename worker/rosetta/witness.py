"""Stable JSONL records, imported by Witness's validating CLI, never direct SQL writes."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import uuid

from .common import Invalid, canonical, digest, read_json, save_json

NAMESPACE = uuid.UUID("5ad86dfa-728f-45f6-b943-073f88c31b69")


def node(run, name, epistemic_type, payload, author, parents=()):
    return {"id": str(uuid.uuid5(NAMESPACE, run["run_id"] + ":" + name)), "cid": digest(payload),
            "epistemic_type": epistemic_type, "payload": payload, "author": author,
            "timestamp": run["finished_at"], "parents": list(parents), "signature": None,
            "labels": ["rosetta", "run:" + run["run_id"], run["target_kind"], run["outcome"]["status"]],
            "domain": "agent-research", "source_uri": run["artifact_uri"]}


def records(run):
    controller = {"id": "rosetta:controller:v0.2", "name": "Rosetta execution recorder",
                  "author_type": "software", "metadata": {}}
    observation = node(run, "execution", "observed", {"measurement": {
        "quantity": "research_execution_receipt", "value": {"numeric": None, "text": canonical(run).decode(),
        "unit": None, "categorical": None}, "location": {"latitude": None, "longitude": None,
        "station_id": None, "description": "local bounded computation", "altitude_m": None},
        "measured_at": run["finished_at"], "instrument": {"id": "rosetta:controller:v0.2",
        "name": "Rosetta", "model": "0.2.0", "calibration_ref": None}, "uncertainty": None,
        "chain_of_custody": None}}, controller)
    author = {"id": "rosetta:agent:" + run["agent"]["id"], "name": run["agent"]["id"],
              "author_type": "model", "metadata": {}}
    inner = {"id": str(uuid.uuid5(NAMESPACE, run["run_id"] + ":generated-content")),
             "cid": digest(run["agent_summary"]), "epistemic_type": "generated",
             "payload": {"content": run["agent_summary"]}, "author": author,
             "timestamp": run["finished_at"], "parents": [], "signature": None,
             "labels": ["rosetta", "unreviewed-agent-output"], "domain": "agent-research",
             "source_uri": run["artifact_uri"]}
    generation = node(run, "agent-summary", "generated", {"node": inner,
        "model": {"id": run["agent"]["id"], "version": run["agent"]["model"],
                  "hash": None, "training_data_ref": None}, "prompt": run["prompt_sha256"],
        "parameters": {}, "human_reviewed": False}, author, [observation["id"]])
    return [observation, generation]


def existing_record(database, expected):
    if not Path(database).exists():
        return False
    with sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM nodes WHERE id=?", (expected["id"],)).fetchone()
        if row is None:
            return False
        for field in ["payload", "author", "parents", "labels"]:
            if json.loads(row[field]) != expected[field]:
                raise Invalid(f"Witness record conflict for {expected['id']}: {field}")
        for field in ["cid", "epistemic_type", "domain", "source_uri", "signature"]:
            if row[field] != expected[field]:
                raise Invalid(f"Witness record conflict for {expected['id']}: {field}")
        if dt.datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")) != dt.datetime.fromisoformat(expected["timestamp"]):
            raise Invalid("Witness record timestamp conflict")
        return True


def export(run_dir, database, executable):
    run_dir, database = Path(run_dir), Path(database)
    run = read_json(run_dir / "run.json")
    envelope = run_dir / "witness-envelope.json"
    nodes = records(run)
    if envelope.exists() and read_json(envelope) != nodes:
        raise Invalid("sealed Witness envelope changed; refusing overwrite")
    if not envelope.exists():
        save_json(envelope, nodes)
    # Resolve partial imports using deterministic IDs + exact read-back, not a POST retry
    # that creates new random IDs. Concurrent duplicate inserts fail, and remain retryable.
    missing = [item for item in nodes if not existing_record(database, item)]
    if missing:
        database.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="wb", dir=run_dir, suffix=".jsonl") as stream:
            for item in missing:
                stream.write(canonical(item) + b"\n")
            stream.flush()
            env = {k: v for k, v in os.environ.items() if k not in {"WITNESS_DB", "WITNESS_KEY"}}
            result = subprocess.run([str(executable), "--database", "sqlite://" + str(database.resolve()),
                                     "jsonl", "--file", stream.name], env=env, capture_output=True, timeout=30)
            if result.returncode:
                raise Invalid("Witness CLI import failed; envelope remains queued for retry")
        database.chmod(0o600)
    if not all(existing_record(database, item) for item in nodes):
        raise Invalid("Witness read-back verification failed")
    receipt = {"status": "verified", "node_ids": [x["id"] for x in nodes],
               "cids": [x["cid"] for x in nodes], "envelope_sha256": digest(nodes)}
    save_json(run_dir / "witness-receipt.json", receipt)
    return receipt
