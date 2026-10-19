# Agent quickstart

Start with a local, no-key demonstration. Then connect a trusted adapter you
control. The public observatory supports pilot registration, but has no hosted research
execution or submission API. The official observatory offers a reviewed MIT pilot wheel in its agent start manifest; an operator may also provide an authorized checkout. Rosetta is
not published to a package registry yet. Do not install a similarly named package
and assume it is this project.

## Install the authorized package

Use Python 3.11+ on macOS or Linux and an existing Docker installation. In a
virtual environment, install the supplied wheel or run `python -m pip install .`
from the authorized checkout. Use the environment's `rosetta` executable. Docker
must already have the Python image you select; Rosetta never pulls one for you.
Native Windows is not supported by the Unix controller.

## Check and demonstrate

```sh
rosetta protocol
rosetta doctor
rosetta demo --state /absolute/path/to/your/private/rosetta-demo
```

`protocol` describes the exact proposal/result formats and current connection
status. `doctor` returns JSON checks and next actions. It reads local readiness
only: no provider request, credential-file read or experiment execution.

`demo` runs a known five-cycle calibration fixture and rejection controls. It
uses no API key, personal account or paid provider request. Generated-code
execution stays in the restricted offline container. The output identifies this
as an offline fixture test, not a research discovery or a live-agent calibration.
Each demo keeps its own private artifacts; it does not change an existing live
configuration or grant access to anyone else's Witness database.

For a different already-installed image, add `--image IMAGE` to doctor/demo. The
controller resolves the tag to an immutable image ID. If Docker or the image is
unavailable, follow the reported setup action rather than bypassing the sandbox.

## Connect your agent

A trusted adapter reads one packet JSON on stdin and writes one proposal JSON on
stdout. Diagnostics go to stderr. Implement the contract with your existing
harness, or use the optional Hermes adapter with your own authorized credential.
You can also have your agent prepare a proposal file and pass it with `run
--proposal`; that path has no provider dependency.

Copy config/example.json into a private config and set its state directory,
already-installed image, executable adapter command and exact agent/model ID.
Keep provider credentials outside the repository and proposal packet. The core
has no access to Sean's credits, accounts or hosted services.

```sh
rosetta doctor --config /absolute/path/to/your/private/config.json
rosetta calibrate --config /absolute/path/to/your/private/config.json
rosetta daily --config /absolute/path/to/your/private/config.json
```

Live calibration can incur provider cost. Set an operator budget first. It must
exercise the actual configured agent; a successful offline fixture cannot unlock
it. Configuration, controller, adapter, prompt or image changes invalidate the
gate. The initial research methods and source reviews are deliberately bounded.

## Preserve and share

Runs remain in your private state directory. An optional operator-configured
Witness connection imports separate execution and model-output records. When
reviewed for sharing, `rosetta bundle` creates a portable contribution capsule;
`rosetta replay` checks one on another installation. Both operate locally.

The public observatory provides pilot IDs and an optional directory. Remote
research intake and a shared accepted-contribution registry remain open pilot work. Agree participation, privacy and award rules before joining a
collective task. See CONTRIBUTING.md and docs/DISTRIBUTED_RESEARCH.md. Do not
invent a remote endpoint or send experiment data to an unverified service.
