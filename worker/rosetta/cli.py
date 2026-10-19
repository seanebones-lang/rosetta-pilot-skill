from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import Invalid, CapsuleIntegrityError, read_json
from .control import calibrate, daily as daily_run, retry as retry_run, run, targets
from .verify import validate_cipher
from .witness import export


def main():
    parser = argparse.ArgumentParser(description="Agent-independent, evidence-preserving research")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("targets")
    sub.add_parser("protocol", help="Print the machine-readable agent contract and connection status")
    health = sub.add_parser("doctor", help="Read-only local readiness checks; no model call")
    health.add_argument("--config")
    health.add_argument("--image")
    demonstration = sub.add_parser("demo", help="Run known offline fixtures; no provider key or research unlock")
    demonstration.add_argument("--state", required=True)
    demonstration.add_argument("--image", default="python:3.12-slim-bookworm")
    check = sub.add_parser("check-cipher")
    check.add_argument("path")
    daily = sub.add_parser("run")
    daily.add_argument("--config", required=True)
    daily.add_argument("--target", required=True)
    daily.add_argument("--date")
    daily.add_argument("--proposal", help="Adapter-free mode: validate an existing proposal JSON")
    scheduled = sub.add_parser("daily")
    scheduled.add_argument("--config", required=True)
    recovery = sub.add_parser("retry", help="Explicitly retry a failed proposal; preserve/link original evidence")
    recovery.add_argument("--config", required=True)
    recovery.add_argument("--retry-of", required=True)
    recovery.add_argument("--attempt-id", required=True)
    recovery.add_argument("--reason", required=True)
    calibration = sub.add_parser("calibrate")
    calibration.add_argument("--config", required=True)
    calibration.add_argument("--proposal")
    flush = sub.add_parser("flush")
    flush.add_argument("--config", required=True)
    contribution = sub.add_parser("bundle", help="Create a portable, unverified contribution capsule; no upload")
    contribution.add_argument("--run", required=True)
    contribution.add_argument("--output", required=True)
    replay = sub.add_parser("replay", help="Independently execute and check an untrusted capsule in Docker")
    replay.add_argument("path")
    replay.add_argument("--image", required=True)
    args = parser.parse_args()
    try:
        if args.command == "targets":
            print(json.dumps(targets(), indent=2))
        elif args.command == "protocol":
            from .onboarding import protocol
            print(json.dumps(protocol(), indent=2))
        elif args.command == "doctor":
            from .onboarding import doctor
            print(json.dumps(doctor(args.config, args.image), indent=2))
        elif args.command == "demo":
            from .onboarding import demo
            print(json.dumps(demo(args.state, args.image), indent=2))
        elif args.command == "check-cipher":
            print(json.dumps({"status": "valid", "symbols": len(validate_cipher(read_json(args.path)))}))
        elif args.command == "run":
            result = run(read_json(args.config), target_id=args.target, date=args.date, proposal=args.proposal)
            print(json.dumps({"run_id": result["run_id"], "outcome": result["outcome"],
                              "discovery_confirmed": False, "payout_earned": False}))
        elif args.command == "daily":
            result = daily_run(read_json(args.config))
            print(json.dumps({"run_id": result["run_id"], "outcome": result["outcome"]}))
        elif args.command == "retry":
            result = retry_run(read_json(args.config), retry_of=args.retry_of,
                               attempt_id=args.attempt_id, reason=args.reason)
            print(json.dumps({"run_id": result["run_id"], "outcome": result["outcome"], "retry": result["retry"]}))
        elif args.command == "calibrate":
            print(json.dumps(calibrate(read_json(args.config), proposal=args.proposal)))
        elif args.command == "flush":
            config = read_json(args.config)
            runs = sorted((Path(config["state_dir"]).expanduser() / "runs").glob("*/run.json"))
            for path in runs:
                export(path.parent, **config["witness"])
            print(json.dumps({"verified_runs": len(runs)}))
        elif args.command == "bundle":
            from .capsule import bundle
            print(json.dumps(bundle(args.run, args.output)))
        elif args.command == "replay":
            from .capsule import replay as replay_capsule
            print(json.dumps(replay_capsule(args.path, args.image)))
    except CapsuleIntegrityError as error:
        parser.exit(error.exit_code, json.dumps({"error": {"code": error.code,
                    "message": str(error)}}) + "\n")
    except (Invalid, OSError, ValueError) as error:
        parser.exit(1, f"Rosetta stopped safely: {error}\n")


if __name__ == "__main__":
    main()
