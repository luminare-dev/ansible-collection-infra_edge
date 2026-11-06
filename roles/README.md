# Roles

Each role is used by its full name, `luminare.infra_edge.<role>`. Its variables are prefixed
with the role name and described in `meta/argument_specs.yml`; the table in its README is
generated from that file with `python3 tests/role_docs.py --write`. Every role has a Molecule
scenario in `molecule/default/` that CI runs on Debian 13 and Ubuntu 24.04.

| Role | README |
|---|---|
| `luminare.infra_edge.base` | [base/README.md](base/README.md) |
| `luminare.infra_edge.cloudflared` | [cloudflared/README.md](cloudflared/README.md) |
| `luminare.infra_edge.nginx` | [nginx/README.md](nginx/README.md) |
| `luminare.infra_edge.mariadb` | [mariadb/README.md](mariadb/README.md) |
| `luminare.infra_edge.restic_backup` | [restic_backup/README.md](restic_backup/README.md) |

The playbook [`luminare.infra_edge.edge`](../playbooks/edge.yml) runs them together on one host,
with the example inventory in [`examples/edge/`](../examples/edge/).
