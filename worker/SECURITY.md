# Security and trust boundaries

Rosetta is experimental. Source pages, proposals and result text are untrusted.
The proposing agent cannot set its own target, checker, outcome classification,
budgets, storage path or notification destination.

The operator's adapter is trusted host code, not a sandbox. The included Hermes
adapter uses an empty tool surface and private context. Generated programs run in
Docker without network, credentials or host directories (only their code file is
mounted), with read-only filesystems and bounded time/output/resources. Containers
are not a guarantee against engine/kernel flaws. Use an isolated worker machine
for hostile third-party code or public hosting.

Do not expose Witness's prototype API on a network. The exporter uses its
validating CLI; SQLite is used directly only for read-back. Imports distinguish
Generated and Observed. CIDs establish byte integrity, not truth or authorship.
Rosetta adds no authentication, custody certification or production hosting.

Use private vulnerability reporting if enabled, or contact the maintainer before
sharing exploit details publicly.

## Host authority and the public pilot

The onboarding helper, pip, Rosetta CLI and Docker client execute on the host with
ordinary user rights. They are trusted code, not sandboxed by this project. Only
the generated experiment is placed in the restricted Docker container. The
helper's environment allowlist reduces accidental inheritance of cloud tokens,
SSH-agent sockets, database URLs and Python/loader injection variables; it does
not revoke filesystem access. HOME and Docker configuration can expose on-disk
credentials, and Docker host/context/TLS settings select an authorized daemon.
On Linux, a normal rootful Docker daemon/socket grants effectively root-level
host authority. Prefer a dedicated worker or rootless Docker where appropriate;
no Docker configuration or permissions are changed automatically. SSH-agent-
dependent remote contexts may stop with the restricted environment and need an
operator decision; do not silently restore credential variables to make them work.

Unexpected ordinary exceptions produce a sanitized stopped report when the test
directory remains writable. A force-killed process, full disk or inaccessible
report destination cannot guarantee a final report. Host command output is
captured before its size is checked; that check is not a streaming memory limit.
