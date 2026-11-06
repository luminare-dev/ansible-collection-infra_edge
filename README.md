<!-- header:begin: brand-repos 0.1.0, variant studio, files in https://raw.githubusercontent.com/luminare-dev/ansible-collection-infra_edge/main/docs/brand/; the project-page sync drops this block -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/luminare-dev/ansible-collection-infra_edge/main/docs/brand/readme-header-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/luminare-dev/ansible-collection-infra_edge/main/docs/brand/readme-header-light.svg">
  <img alt="luminare.infra_edge" src="https://raw.githubusercontent.com/luminare-dev/ansible-collection-infra_edge/main/docs/brand/readme-header-light.svg">
</picture>

<!-- byline:studio -->
*a [Luminare Development](https://luminare.tech/open-source/ansible-collection-infra_edge/) open-source project*
<!-- /byline:studio -->
<!-- byline:personal
*by [ItsPaulAT](https://github.com/ItsPaulAT) · [project page](https://luminare.tech/open-source/ansible-collection-infra_edge/)*
/byline:personal -->
<!-- header:end -->

# luminare.infra_edge

Ansible collection for edge hosts: base hardening, an outbound tunnel, a web server, a database and backups.

[![ci](https://github.com/luminare-dev/ansible-collection-infra_edge/actions/workflows/ci.yml/badge.svg)](https://github.com/luminare-dev/ansible-collection-infra_edge/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/luminare-dev/ansible-collection-infra_edge?sort=semver)](https://github.com/luminare-dev/ansible-collection-infra_edge/releases)
[![licence](https://img.shields.io/github/license/luminare-dev/ansible-collection-infra_edge)](LICENSE)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/luminare-dev/ansible-collection-infra_edge/badge)](https://scorecard.dev/viewer/?uri=github.com/luminare-dev/ansible-collection-infra_edge)

## Roles

| Role | What it does |
|---|---|
| [`base`](roles/base/README.md) | SSH with keys only (through `devsec.hardening.ssh_hardening`), admin and automation users, unattended security upgrades, a default-drop nftables firewall with a drop-in folder for the other roles, fail2ban, journal limits |
| [`cloudflared`](roles/cloudflared/README.md) | Connector of a remotely managed Cloudflare Tunnel: pinned version with a checked SHA-256, token in a file only the service user can read, sandboxed unit |
| [`nginx`](roles/nginx/README.md) | Reverse proxy behind the tunnel: one site per application on a loopback listener, client address from `CF-Connecting-IP` (trusted from `127.0.0.1` only), JSON access log, optional TCP/UDP relays |
| [`mariadb`](roles/mariadb/README.md) | MariaDB from the distribution on `127.0.0.1` by default, root via `unix_socket`, databases and accounts from a list, nightly zstd dumps per database |
| [`restic_backup`](roles/restic_backup/README.md) | Nightly restic backups to a repository off the host, settings in root-only files, monthly check, status file/metric and a restore test |

The playbook [`luminare.infra_edge.edge`](playbooks/edge.yml) runs them in that order on the
group `edge`; `restic_backup` only when `edge_restic_backup_enabled` is true. Visitors reach the
host only through the tunnel, and the firewall drops every port no role opened.

## Quickstart

Needs Python 3.12+ and git on the control node, and a Debian 13 or Ubuntu 24.04 host you reach
over SSH as root. Put your values into the copied example inventory first (see
[its README](examples/edge/README.md)):

<!-- x-release-please-start-version -->
```bash
python3 -m venv ~/.venvs/edge && . ~/.venvs/edge/bin/activate && pip install "ansible-core>=2.21,<2.22"
ansible-galaxy collection install git+https://github.com/luminare-dev/ansible-collection-infra_edge.git,v0.2.1
cp -r ~/.ansible/collections/ansible_collections/luminare/infra_edge/examples/edge edge
ansible-vault create edge/group_vars/edge/vault.yml   # the six vault_* values of the example
read -rs TUNNEL_TOKEN && export TUNNEL_TOKEN && ansible-playbook -i edge/inventory.yml luminare.infra_edge.edge --ask-vault-pass
```
<!-- x-release-please-end -->

Each role also works on its own; its README has an example playbook. [docs/install.md](docs/install.md)
covers the release tarball and how to verify it.

## Supported versions

| Component | Supported |
|---|---|
| ansible-core (control node) | 2.20 and later (CI runs 2.21) |
| Python (control node) | 3.12 and later |
| Managed hosts | Debian 13, Ubuntu 24.04 (x86-64 tested) |
| cloudflared (managed host) | 2026.10.2, pinned by the role |
| nginx, MariaDB, restic | the distribution's package (restic optionally a pinned release) |

Each role and the playbook are tested with Molecule in systemd containers on both
distributions. A real Cloudflare tunnel and off-host backup backends are not part of the tests
yet; the role READMEs list their limitations. Fixes go into the latest minor release only.

## Documentation

- [Installation](docs/install.md) · [Configuration](docs/configuration.md) ·
  [Upgrade](docs/upgrade.md) · [Troubleshooting](docs/troubleshooting.md) ·
  [Runbook](docs/runbook.md) · [Roles](roles/README.md)
- [Changelog](CHANGELOG.md) and [releases](https://github.com/luminare-dev/ansible-collection-infra_edge/releases)
  (each with `SHA256SUMS` and a build provenance attestation)
- [Contributing](https://github.com/luminare-dev/.github/blob/main/CONTRIBUTING.md) ·
  [Code of conduct](https://github.com/luminare-dev/.github/blob/main/CODE_OF_CONDUCT.md) ·
  [Security](https://github.com/luminare-dev/.github/blob/main/SECURITY.md) ·
  [Support](https://github.com/luminare-dev/.github/blob/main/SUPPORT.md)

## Licence

[Apache-2.0](LICENSE). The licence covers the code only: the project name, logo, header images
and `docs/brand/` are not licensed (see [NOTICE](NOTICE)).

<!-- byline:studio -->
*a [Luminare Development](https://luminare.tech/open-source/ansible-collection-infra_edge/) open-source project*
<!-- /byline:studio -->
<!-- byline:personal
*by [ItsPaulAT](https://github.com/ItsPaulAT) · [project page](https://luminare.tech/open-source/ansible-collection-infra_edge/)*
/byline:personal -->
