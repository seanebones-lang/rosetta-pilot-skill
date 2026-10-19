# Operating Rosetta

Use Python 3.11+, Docker with an existing Python 3.12 image and your own compatible
agent adapter. Core code uses only the standard library. No image is downloaded
by a run. An image tag is resolved to its content ID before execution; pin the
ID in local configuration for reproducible daily operation.

Copy config/example.json to config/local.json (ignored by Git). Select your state
directory, exact agent command/model and image. Keep credentials outside this
repository. The supplied Hermes adapter takes a separate private JSON config:
provider=nvidia, base_url=https://integrate.api.nvidia.com/v1, model, hermes_source,
credential_env_file (existing .env with NVIDIA_API_KEY), agent_home (isolated).
For xAI use provider=xai, base_url=https://api.x.ai/v1, and the existing
XAI_API_KEY in that private environment file. Model IDs are provider-specific;
verify current availability before selecting one. The adapter never silently
changes providers when a model fails. xAI usage is paid; time/output limits do
not establish a hard monetary cap. Choose a bounded pilot and inspect usage
receipts before enabling a recurring schedule.
Run it with the Python runtime belonging to the existing Hermes installation.

The xAI adapter explicitly defaults reasoning_effort to low for bounded proposal
generation. Other supported efforts require operator configuration and a new
calibration. Grok 4.7's provider default is high; see the
[official reasoning contract](https://docs.x.ai/developers/model-capabilities/text/reasoning).
The isolated adapter disables Hermes/SDK automatic retries and recovery, and
guards the actual SDK request path: one request, the configured model/endpoint,
no tools and at most 4,096 requested output tokens. The SDK guard covers clients
cloned by Hermes. This is not a monetary cap or proof that a timed-out request was
not processed upstream. Request-start counts, effort and returned token usage
stay in the private run receipt.

```sh
python3 -m unittest discover -s tests -v
python3 -m rosetta.cli calibrate --config config/local.json
python3 -m rosetta.cli daily --config config/local.json
python3 -m rosetta.cli flush --config config/local.json
```

Calibration uses a known false graph claim. The agent must produce a program
whose certificate passes the separate checker. The controller also rejects a
known four-cycle and malformed transcription. File-only calibration cannot unlock
live scheduling. Changing controller, adapter/config, prompt, image or model
invalidates the gate. Repeat calibration at least weekly.

New Erdős #64 assignments are paused in 0.2.1 pending literature and verifier review. Only the known calibration task is currently enabled. Historical run evidence remains unchanged. The initial
Erdős #64 packet is a feasibility baseline on <=16 vertices, not a claim that this
range is novel. Four historical method families are preserved; none is currently assigned for new research. Exhausting them
requires review/new work, rather than relabeling different seeds as new methods.
More ambitious graphs, other math/cipher domains and reward classes require new
bounded verifiers and independently checked target/source packets. This is not a
general solver for every open problem.

Source reviews expire after seven days. The listed Erdős award is a documented
offer with unconfirmed prospective eligibility/funding, not guaranteed income.
Do not claim a prize without meeting its administrator's requirements. A valid
counterexample remains candidate_needs_review. Research runs cannot automatically
set discovery_confirmed or payout_earned. No automatic papers, claims or outreach.

## Witness

Set witness.database and witness.executable to an existing Witness database and
its witness-ingestion binary. The adapter creates Observed execution receipts and
Generated agent output. It never promotes agent prose to an observation of truth.
UUIDs are stable per run/record. Imports use Witness's own validating JSONL CLI;
SQLite access is read-only for exact read-back and conflict detection. A partial
import is retried with the same IDs. A conflict stops the retry; it is never
silently replaced. Copy the binary to a stable operator-owned location rather
than relying on a build-cache directory that might be cleaned.

The daily controller retries queued envelopes before each run. `flush` retries
them on demand. run.json and the envelope remain available if Witness is down.
Witness's prototype API must remain loopback-only and needs separate operational
backup/authentication work before hosting.

## Scheduling and recovery

`scripts/scheduled.py --config /absolute/config/local.json` is scheduler-neutral.
It suppresses routine no-finding outcomes and deduplicates local failure/candidate
alerts. It sends no external messages itself. The installed scheduler must choose
where output is delivered. A local machine must be awake; no cloud availability
is implied. Catch-up behavior belongs to the scheduler, not a claimed daily run.

Use one scheduler and one canonical checkout. A lock prevents overlap; one run per
target/local date prevents duplicate computation. An interrupted unsealed folder
stays intact and blocks automatic rerun. Inspect and archive it deliberately;
never delete its contents merely to make an error disappear. To pause, disable the
owning scheduler job. Do not resume the historical unbounded Claude process.

An operator can deliberately retry a sealed failure that happened before any
experiment executed. The current live calibration must pass first:

```sh
python3 -m rosetta.cli retry --config config/local.json \
  --retry-of ORIGINAL_RUN_ID --attempt-id reviewed-fix-v1 \
  --reason "Describe the reviewed correction"
```

The retry retains its parent's exact report hash and original approved method,
gets a separate run/record identity, and never overwrites the failure. Reusing
the same attempt ID for that parent returns the existing attempt even on a later
day. Reusing it with a different review reason fails. Completed experiment
outcomes cannot be rerun through this recovery shortcut. The daily scheduler
does not call retry. A timed-out provider's completion/charge status remains
unknown; this explicit recovery is a new request, not exactly-once replay.

For an offline integration test of the installed Hermes adapter, use Hermes's
Python with ROSETTA_HERMES_SOURCE set and execute tests/hermes_adapter_smoke.py.
It uses a fictional key and a synthetic SDK response, blocks network calls, and
checks the actual harness's effort/output/request-count wiring.

Runtime packets, proposals, code, execution receipts, run.json, Witness envelopes
and receipts are private and outside Git. Keep backups of runtime state and the
Witness database. Public source does not imply public release of all experiment
artifacts. Review individual datasets, provider terms and privacy before sharing.
