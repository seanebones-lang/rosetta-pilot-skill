# Contributions from other agents and machines

An agent on another machine can use Rosetta with its own credentials, compute and
chosen compatible harness. The core format, controller and certificate checks
remain the same. Contributors own their execution costs and must not share keys,
personal memory or private datasets. Public code does not grant access to Sean's
machines, accounts, Witness database or provider credits.

The implemented portable handoff is a contribution capsule:

```sh
rosetta bundle --run /path/to/sealed/run --output contribution.zip
rosetta replay contribution.zip --image your-existing-python-image
```

The capsule contains an exact program, preserved sources and a bounded manifest.
It omits local state paths, provider diagnostics, credentials and personal memory.
It is created locally; nothing is uploaded. Review all material before sharing.
Every received report is explicitly contributor_report_unverified, even if the
sender claims success. Hash checks establish byte consistency, not honest execution.

Replay checks member names/size/types/hashes, never extracts arbitrary paths,
requires a matching local target/verifier contract, and runs the code again in the
bounded offline container. The contributor's outcome and graph parameters cannot
replace the local checker. A successful replay establishes that particular local
execution/check, not novelty, an independent mathematical review or prize acceptance.

Mothership can later provide reviewed task discovery, optional expiring work
claims, submission queues and per-principal artifact access. There is no public
coordinator or contribution-ingestion service yet. Witness should first retain a
received submission as unverified generated material, then record our actual
independent replay separately with the source capsule hash. Never import a remote
author's self-reported receipt as a measurement made by our own controller.

Deduplicate exact target/input/method/version/parameter/search-range combinations.
A negative result with independently checked coverage narrows that documented
coverage; the current generic no_candidate output does not certify search
completeness. Merely replaying a program that prints no_candidate does not prove
that it searched anything. A negative result does not ban a whole
method family or establish impossibility. A changed seed is not novelty. Preserve
contradictory reports, correction links, missing evidence and failed replays.

Start with a few known contributors and calibration tasks. Public registration,
malicious-worker isolation, quotas, privacy review, author identity, moderation,
queue abuse and deployment are separate work before opening the coordinator.

The first acceptance milestone is two independently configured machines: one
creates a capsule and the other replays it, rejects an altered copy, and retains
separate submission and replay records. A clean installed package on the same Mac
tests packaging independence but does not establish that cross-machine milestone.
Remote record IDs must include an authenticated contributor namespace and a
content/task identity. The local controller's date/target run IDs are not a global
namespace and must not be imported unchanged from arbitrary contributors.

Contributors should receive attribution for accepted reproducible artifacts,
corrections and useful coverage. Do not rank contribution quality by token usage,
claimed hours, quantity of agents or unverified breakthrough claims. Reward and
ownership terms need to be explicit before assigning a task with a monetary award.
Rosetta's owner has chosen fair, balanced allocation and equal prominence for named
credit. Equal shares are the starting proposal; documented adjustments require the
agreed review process. See [the contribution policy](../CONTRIBUTING.md#fair-credit-and-collective-awards).
The shared registry must link a stable party ID and consenting public credit name
to individual agent/work records. Contributor registration and payout handling
are not implemented in the current portable worker.
