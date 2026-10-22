# Roles

Each role of the collection lives in its own folder here and is used by its fully qualified name,
`luminare.infra_edge.<role>`. A role folder holds:

- `defaults/main.yml`: every variable, prefixed with the role name;
- `meta/argument_specs.yml`: type, default and description of every variable, checked when the
  role starts;
- `README.md`: what the role does and its variable table, generated from
  `meta/argument_specs.yml` with `python3 tests/role_docs.py --write` (a unit test fails when
  the table is out of date);
- `molecule/default/`: the role's Molecule scenario (`molecule.yml`, `converge.yml`,
  `verify.yml`, and where needed `prepare.yml`, a `requirements.yml` for the collections the
  role uses, or extra steps such as `side_effect.yml`). The driver, the two test platforms and
  the test sequence come from the shared
  [`.config/molecule/config.yml`](../.config/molecule/config.yml); a scenario with extra steps
  repeats the sequence with them in its own `molecule.yml`. CI finds every
  `roles/*/molecule/default/molecule.yml` and runs it in one job per platform (Debian 13,
  Ubuntu 24.04). Every role needs this scenario: a unit test fails for a role folder without it.

| Role | README |
|---|---|
| `luminare.infra_edge.base` | [base/README.md](base/README.md) |
| `luminare.infra_edge.cloudflared` | [cloudflared/README.md](cloudflared/README.md) |
| `luminare.infra_edge.nginx` | [nginx/README.md](nginx/README.md) |
| `luminare.infra_edge.mariadb` | [mariadb/README.md](mariadb/README.md) |
| `luminare.infra_edge.restic_backup` | [restic_backup/README.md](restic_backup/README.md) |

The playbook [`luminare.infra_edge.edge`](../playbooks/edge.yml) runs the roles together on one
host (`restic_backup` when `edge_restic_backup_enabled` is true), with the example inventory in [`examples/edge/`](../examples/edge/); its Molecule
scenario is [`extensions/molecule/edge/`](../extensions/molecule/edge/molecule.yml).
