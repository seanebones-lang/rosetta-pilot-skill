# Agent and harness adapters

The controller is provider-neutral. An adapter is a trusted executable configured
by the operator, not a shell command supplied by a model. It receives one packet
JSON on stdin and writes one proposal JSON on stdout. Diagnostics belong on stderr.
See PROMPT.md for the protocol. Exit nonzero on any provider or parsing failure.
The controller bounds the adapter to 180 seconds and 128 KiB output.

`--proposal file.json` accepts the same format without invoking any agent. This is
also the interoperability and offline-testing entry point. A harness can prepare
that file without changing Rosetta. There is no hard dependency on Claude, Hermes,
Harness, an SDK or a model provider.

`hermes_sdk.py` is the first live adapter. It uses an existing Hermes installation
and an existing NVIDIA or xAI credential. It verifies an empty tool surface before any
model call, disables memory/context/background review, requests one bounded reply,
and refuses a different provider/endpoint. It does not copy credentials to disk.
Its isolated agent home prevents personal memory or SOUL entering the research
prompt. Configuration paths and model identity are supplied explicitly.
The Rosetta-specific configuration does not change Hermes's global model. xAI
API calls are paid usage; bounded output and time limits are not a hard dollar cap.
For xAI, reasoning_effort defaults explicitly to low and is recorded. A guard at
the actual SDK request path checks the model, endpoint, output limit and empty
tool surface, and blocks a second request. Automatic retries and recovery are
disabled. A timeout still leaves upstream completion/charge status unknown.

Other harnesses can implement the stdin/stdout contract. They have not been
individually validated yet. A trusted host adapter can access host resources;
only generated experiment code receives the Docker restrictions.
