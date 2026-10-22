# 0018. restic from the distribution with an optional pinned release instead of always the newest release

- **Status:** accepted
- **Date:** 2026-10-22

## Context

The `restic_backup` role needs restic on every edge host. Debian 13 ships restic 0.18.0 and
Ubuntu 24.04 0.16.4 (in `universe`, with security updates from Ubuntu); the upstream project
publishes newer releases (0.19.1 on 2026-07-05) as compressed binaries with a `SHA256SUMS` file
signed by its release key. The versions differ in ways the role must handle: 0.16 exits with 1 for
a missing repository and a wrong password, 0.17 and later with 10 and 12; 0.16 and 0.18 skip a
missing backup path without an error, 0.19 exits with 3.

## Considered options

1. The distribution's package by default; the pinned upstream release as an option
   (`restic_backup_install_method: binary`), checked against its SHA-256.
2. Always the upstream release, pinned and checked.
3. The newest upstream release at every run.

## Decision

Option 1. The package needs no download from GitHub at converge time and gets security updates
with the rest of the host (the `base` role installs them every night). Hosts that need a newer
restic set `binary`: the role downloads `restic_<version>_linux_<arch>.bz2` of
`restic_backup_version`, checks it against `restic_backup_binary_sha256` (the defaults are the
lines of the release's `SHA256SUMS`, whose signature by the release key
`CF8F18F2844575973F79D4E191A6868BD3F7A907` was checked on 2026-10-22), installs
`/usr/local/bin/restic` and downloads nothing while that version is installed. The wrapper
`/usr/local/sbin/restic-env` names the binary of the chosen method, so every job uses it. The role
does not depend on the version: it detects a missing repository and a wrong password by exit code
or message, and the backup script fails on a missing path itself. Option 3 would change restic on
a host without a reviewed change.

Tested on 2026-10-22 in the Molecule scenario: the packages of Debian 13 (0.18.0) and Ubuntu
24.04 (0.16.4) create and use the repository, then the upstream 0.19.1 backs up into the same
repository and the restore test passes with it.

## Consequences

- Good: no network access to GitHub with the default, and updates come with the distribution.
- Good: one role for three restic versions, each tested.
- Bad: Ubuntu 24.04 hosts run an older restic than Debian 13 hosts unless they use `binary`.
- Bad: the pinned release is not updated by Dependabot; a new version needs its two checksums from
  the release by hand.
