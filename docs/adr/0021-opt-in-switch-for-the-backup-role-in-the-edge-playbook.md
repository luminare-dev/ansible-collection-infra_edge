# 0021. An opt-in switch for the backup role in the edge playbook instead of a fifth fixed role

- **Status:** accepted; amends [ADR 0017](0017-edge-playbook-with-example-inventory.md) (the
  playbook gets one switch)
- **Date:** 2026-10-22

## Context

The playbook `luminare.infra_edge.edge` ([ADR 0017](0017-edge-playbook-with-example-inventory.md))
runs four roles and has no switches. The `restic_backup` role needs a repository off the host and
its password, which an existing inventory does not have; as a fixed fifth role it would stop
every such inventory at its input checks after an upgrade.

## Considered options

1. `restic_backup` as the fifth role with `when: edge_restic_backup_enabled | default(false)`;
   the example inventory switches it on.
2. `restic_backup` as a fixed fifth role.
3. A second playbook for the edge host with backups.

## Decision

Option 1. An inventory of the previous release sets up the same host; the example inventory, which
the `edge` scenario tests, switches the backups on with an S3-compatible bucket, and the scenario
replaces only the bucket by a local folder. The scenario checks the composition: the dumps of
`mariadb` and the backup started together run in order, the snapshot holds the dumps, the
default retention is applied, and the restore test passes. Option 3 would duplicate the playbook.
The other roles keep `--skip-tags` as their way out.

## Consequences

- Good: no breaking change for existing inventories, and the documented example backs up its
  database.
- Bad: the switch only decides whether the role runs; switching it off later leaves the installed
  timers running until `restic_backup_timers_enabled: false` is applied once.
