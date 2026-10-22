# 0020. A restore test of the newest snapshot and a status file instead of trusting restic check alone

- **Status:** accepted
- **Date:** 2026-10-22

## Context

A backup that is never restored is a guess. `restic check` proves that the repository is
consistent (and with `--read-data-subset` that stored data is readable), but not that the newest
snapshot holds the files of the host, nor that the nightly job still runs. Plan 09 asks for a
restore test with a measured restore time and an alert when the last backup is older than 26
hours.

## Considered options

1. A restore test script that restores the newest snapshot of the host into a temporary folder
   with `restic restore --verify` and compares the copy with the snapshot listing; plus a status
   file and an optional node_exporter metric with the time of the last successful run.
2. `restic check --read-data` only.
3. A restore of one database dump into a scratch database.

## Decision

Option 1, next to the monthly `restic check`. `/usr/local/sbin/restic-restore-test` fails when the
newest snapshot of the host is older than `restic_backup_max_age_hours` (26), so a broken nightly
job also fails the test. `restic restore --verify` reads every restored file again and compares
it with the repository; the script then checks that every file, folder and link of the listing is
in the copy with its type, size, permissions and owner (restic's listing has no link targets), and
prints how long the restore took. The backup script writes the Unix time of every run without
errors to `/var/lib/restic-backup/last-success` and, with `restic_backup_textfile_dir`, the metric
`restic_backup_last_success_timestamp_seconds` for node_exporter, so monitoring needs no access to
the repository. Option 3 depends on the database role; a dump is restored with the steps of the
`mariadb` role.

Tested on 2026-10-22: the Molecule scenario runs the test with restic 0.18.0, 0.16.4 and 0.19.1
(passes, and fails with an age limit of 0 hours); unit tests run it against a stand-in for restic
with a missing file, a changed size and a changed mode (each fails), an old snapshot and a failed
restore.

## Consequences

- Good: one command shows that the newest backup can be restored and how long it takes.
- Good: the metric turns a silently failing timer into an alert.
- Bad: the test needs as much free space as it restores, and it does not start an application on
  the restored files.
