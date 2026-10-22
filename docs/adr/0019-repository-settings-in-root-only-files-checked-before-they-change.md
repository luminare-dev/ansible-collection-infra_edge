# 0019. Repository settings in root-only files, checked before they change, instead of Environment= lines in the unit

- **Status:** accepted
- **Date:** 2026-10-22

## Context

A restic run needs the repository address, its password and often backend credentials (an S3
access key). Roles often write them as `Environment=` lines into the unit file (readable by every
local user) or pass them to Ansible tasks through `environment:`, which puts them on the remote
command line, where `ps` and verbose Ansible output show them. A wrong password in the inventory
must not break a backup that works, and a failing or unreachable backend must never lead to a
second repository being initialised.

## Considered options

1. Root-only files under `/etc/restic` (`env` with the repository and the credentials, every value
   shell-quoted; `password`; `excludes`), read by a wrapper `/usr/local/sbin/restic-env` for every
   restic run; the new settings are first tried against the repository through a helper that
   gets them on standard input.
2. `Environment=` and `RESTIC_PASSWORD` in the unit files, `snapshots || init` before each backup.
3. systemd credentials (`LoadCredentialEncrypted=`).

## Decision

Option 1. The services, the restore test, the role and an operator all run restic through the
wrapper, so there is one way to reach the repository, and it reads the settings as root. The
settings are written by tasks with `no_log` and no diff. Before they replace the old files, the
role runs `files/repository_state.py` with the new settings on standard input; it hands them to
restic as environment variables of the restic process (readable by root only) and reports
whether the repository exists, is missing, rejects the password or fails. Only "missing" leads to
`restic init`, and restic refuses to initialise a location that holds a repository. Option 2
shows the password to every local user and runs `init` after any failed `snapshots`, also a
network error. Option 3 needs a credential key per host and does not cover runs by hand.

Tested on 2026-10-22 in the Molecule scenario: a value with a quote, a dollar sign, backquotes, a
backslash and spaces reaches restic unchanged; a run with a wrong password stops with its
message and leaves the settings files, the repository's configuration and its keys unchanged; the
password appears nowhere in the journal of the instance or in the output of a converge with
`-vvv`.

## Consequences

- Good: no secret on a command line, in a unit file or in Ansible's output.
- Good: a typo in the password or the credentials cannot stop a working backup.
- Bad: every run of the role opens the repository once, so an unreachable backend fails the play.
- Bad: the files hold the secrets in plain text for root; disk encryption of the host is out of
  scope.
