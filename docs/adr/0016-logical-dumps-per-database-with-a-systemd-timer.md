# 0016. Logical dumps per database with a systemd timer instead of physical backups or cron

- **Status:** accepted
- **Date:** 2026-10-22

## Context

An edge host keeps a few small databases next to its applications. Each night the data must end
up in files that a backup tool can copy off the host later in the night, that can be restored
one database at a time, and whose creation shows a failure clearly. MariaDB offers logical dumps
(`mariadb-dump`) and physical backups (`mariadb-backup`). The root account logs in with
`unix_socket`, so a job that runs as root needs no password file.

## Considered options

1. A script that dumps every database into its own zstd file plus one file with the accounts
   (`mariadb-dump --system=users`), run by a sandboxed oneshot service and a timer, with a
   retention in days.
2. One `mariadb-dump --all-databases` file per night.
3. `mariadb-backup` (physical backup of the data directory).
4. A cron job.

## Decision

Option 1. The script (`/usr/local/sbin/mariadb-dump-all`) lists the databases, skips the system
databases and dumps each one with `--single-transaction --routines --events --triggers
--databases` into `<database>-<UTC time>.sql.zst`, then the accounts and grants with
`--system=users --insert-ignore` into `system-users-<UTC time>.sql.zst`. Each file is written as
`.partial` and renamed when the dump and the compression succeeded (`set -o pipefail`); files older
than `mariadb_dump_retention_days` are deleted only after a run in which every dump succeeded.
`mariadb-dump.service` runs it as root with `UMask=0077`, no capabilities, no network
(`PrivateNetwork`; the socket is a file) and a read-only system except the dump folder;
`mariadb-dump.timer` starts it at `mariadb_dump_oncalendar` with `Persistent=true`.

Option 2 restores everything or nothing. Option 3 needs the same server version for the restore
and a prepare step, and its files are larger than compressed SQL for small databases. Option 4
has no sandbox, loses a run missed while the host was off, and reports a failure only by e-mail;
a failed systemd unit shows in `systemctl --failed` and the journal.

Tested on 2026-10-22 in the Molecule scenario on Debian 13 (MariaDB 11.8) and Ubuntu 24.04
(MariaDB 10.11): a run of the service writes one file per database and the accounts file
(mode 0600, folder 0700), deletes a planted dump that is three days old and keeps one from the
day before; a dropped table comes back from its dump and a dropped account from the accounts
dump. A unit test runs the script with stand-ins for the MariaDB tools and checks that a failed
dump keeps the old files and leaves no `.partial` file.

## Consequences

- Good: one database can be restored with `zstd -dc <file> | mariadb`, on another MariaDB version
  too.
- Good: no password file on the host; the dumps are readable by root only.
- Bad: a logical dump and its restore take longer than a physical backup for large databases, and
  tables of other engines than InnoDB are not part of the consistent snapshot.
- Bad: the dumps stay on the host until a backup tool copies them; two days of dumps need disk
  space for two compressed copies of every database.
