# 0017. A collection playbook with a tested example inventory instead of an all-in-one role

- **Status:** accepted; amended by [ADR 0021](0021-opt-in-switch-for-the-backup-role-in-the-edge-playbook.md)
  (one switch, for the backup role)
- **Date:** 2026-10-22

## Context

Most users want the whole edge host, not four separate roles: hardening and the firewall, the
tunnel connector, the sites and the database, in the right order and with values that fit
together (the sites on the loopback address the connector forwards to, port 3306 only for the
application hosts). Each role has its own Molecule scenario, but none of them shows that the
roles work together: that the drop-in of `mariadb` loads with the ruleset of `base`, that the
handlers of one role do not undo another, and that a second run of all four is still idempotent.

## Considered options

1. A playbook in the collection, `playbooks/edge.yml` (run as `luminare.infra_edge.edge`), that
   lists the four roles and nothing else; every value lives in the inventory, with a complete
   example in `examples/edge/`. A collection-level Molecule scenario runs that playbook with the
   example's `group_vars`.
2. A role `edge` with the four roles as dependencies in `meta/main.yml`.
3. An example playbook in the README only.

## Decision

Option 1. A collection playbook is installed with the collection (from a tag or the release
tarball), runs by its fully qualified name and can be imported into other playbooks
(`ansible.builtin.import_playbook: luminare.infra_edge.edge`). Each role keeps its own tag, so
`--skip-tags` leaves a role out. A wrapper role would hide the order of the roles in
`meta/main.yml`, merge their variables into one role scope and could not be skipped per role.

The scenario `extensions/molecule/edge` (Molecule's layout for collection scenarios, run from the
repository root) links `examples/edge/group_vars/`, so the example and the tested values cannot
drift apart. Its `converge.yml` adds only what an operator adds to the example (SSH keys, the
vault values, the tunnel token, the host's private address from the example inventory) and then
imports the playbook. Unlike the role scenarios it runs the tasks tagged `molecule-notest`: the
base role loads its firewall and starts fail2ban, and the drop-in handlers of the other roles
restart them, as on a real host. `prepare.yml` creates a network namespace inside the instance
for the hosts outside (an application host, a management host and another host), connected by
a veth pair to the example's private address, so `verify.yml` tests the composed firewall from
other addresses. CI runs the scenario as `molecule-edge (<platform>)`, one job per platform,
and the aggregate `molecule` check needs it.

## Consequences

- Good: one command sets up a host, and the documented example is the tested one: a variable
  in the example that no role knows fails a unit test.
- Good: the scenario checks what no role scenario can: the drop-ins of the roles together, the
  listeners of the whole host, a request through nginx to an application that reads its database
  over the socket, and that a second run of all four roles changes nothing.
- Bad: the playbook has no switches; a host without a database uses `--skip-tags mariadb` or its
  own playbook with the roles it needs.
- Bad: the scenario repeats the two platforms of `.config/molecule/config.yml`, because a
  scenario's platform list replaces the shared one; a unit test keeps them equal.
- Bad: the firewall is tested inside the network namespace of a container, from addresses in a
  second namespace, not on the real interfaces of a virtual machine and not after a reboot.
