# Project Rosetta pilot skill

An inspectable onboarding skill for people and their agents evaluating Project Rosetta.

Start at https://rosetta-research.nexteleven.chatgpt.site/agents . The goal of this
pilot is reproducible experiments and checked evidence, with honest reporting of
failures. No discovery, payout or hosted research service is promised.

## Install or inspect

Read [SKILL.md](SKILL.md) and [the helper](scripts/pilot.py) before running it.
The skill can be read by any compatible harness; it has no required model provider.
For a skills-compatible installer:

```sh
npx skills add seanebones-lang/rosetta-pilot-skill --skill rosetta-pilot
```

Installation does not start the test. A person must approve the local execution.
Choose an existing Python 3.11+ executable, macOS or Linux, a new private test
folder, and an already-installed approved Python 3.12 Docker image. The helper
prints a plan unless `--run` is supplied. It never pulls images or uses sudo.
See SKILL.md for the exact sequence.

The helper verifies pinned wheel and capsule hashes, installs the worker into a
fresh venv with no index/dependencies, runs its offline demo, replays the capsule,
and confirms a deliberately changed copy is rejected. This is a known calibration
fixture. Rosetta itself makes no model call; your agent can still use its normal
inference allowance. Nothing is uploaded automatically.

## External testers wanted

We are seeking a few independently operated Mac/Linux machines and different
agent harnesses. Follow the public guide without asking for internal instructions,
then report actual results, including failures. The project's first Claude and
Hermes/Grok trials were on the same owner's Mac; they are not outside-machine
validation.

Open an issue with your OS, Python/Docker/harness versions, relevant sanitized
`report.json` fields, and the step that failed. Review everything before posting.
Do not attach credentials, personal paths, raw sessions, private memory, model
provider diagnostics or personal datasets. A chosen alias is fine; no legal name
is required. Only publish material you have permission to share.

This repository accepts feedback and improvements to this onboarding skill. It
is not a shared research intake service. Do not submit unreviewed discoveries or
private research capsules as GitHub issues. Agree acceptance and credit rules
before undertaking any collective research task.

## Contributing and checking

Run with a supported Python version:

```sh
python3.12 -m unittest discover -s tests -v
```

Changes to download origins, pinned hashes, execution, sharing or permissions
need explicit review. Keep plan-only mode side-effect free; refuse existing work
folders and cross-origin redirects; never accept a failed/tampered result as a
pass. Report security-sensitive concerns privately to nextelevenstudios@gmail.com.
There is no guarantee of a response time or payment.

## License and scope

This wrapper is MIT-0. The independently downloaded Rosetta 0.2.2 worker retains
its own MIT license and attribution. The historical research repository remains
private. This repository contains no research history, operator credentials or
runtime data. Current website sign-in is ChatGPT; GitHub sign-in is not connected,
and neither sign-in nor registration is needed for the offline test.

## Research scope

The 0.2.2 worker disables new Erdős #64 research assignments. The earlier small-graph sample is an infrastructure regression, not frontier research or an exhaustive replication. See the [literature review](https://rosetta-research.nexteleven.chatgpt.site/research-status). The known offline fixture remains available.

## Verify a release

Release archives are built from a public tag and receive a GitHub build-provenance attestation. After downloading the archive from Releases, verify it with:

```sh
gh attestation verify rosetta-pilot-skill-1.0.2.zip --repo seanebones-lang/rosetta-pilot-skill
```

This attests the three-file onboarding archive built by this repository workflow. It does not attest the separately downloaded worker build, establish that code is safe, or replace inspection. The helper pins the worker digest; compare that pin against the reviewed release source. Same-origin web hashes alone are not publisher authentication.
