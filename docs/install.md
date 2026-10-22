# Installation

The collection is installed from this repository: from a release tag with git, or from the
collection tarball attached to the GitHub release.

What was tested, on 2026-10-21 with ansible-core 2.21.5 and Python 3.12 in an `ubuntu:24.04`
container, before any release existed: the install from a tag with git and the install from
`requirements.yml`, both against a local clone of the repository with a test tag `v0.1.0` (a
`file://` URL in place of the GitHub URL), and `ansible-galaxy collection install` of a tarball
built locally with `ansible-galaxy collection build`. `gh release download`, `sha256sum -c` and
`gh attestation verify` were not run then, because no release existed yet. Repeated the
same day for the version with the `base` role: both installs also pulled the dependencies from
Ansible Galaxy (devsec.hardening 11.0.0, community.general 13.5.0, ansible.posix 2.2.2 and the
collections that devsec.hardening needs, community.crypto and community.mysql); one download
failed once with a read timeout and passed when the command was run again. On 2026-10-22, for
the version with the `mariadb` role, the install from a tag (ansible-core 2.21.5, Python 3.14,
empty collections path) also pulled ansible.mariadb 6.0.2 from Ansible Galaxy. Also on
2026-10-22, for the version with the playbook `luminare.infra_edge.edge`: the install from a test
tag of a local clone (ansible-core 2.21.5, Python 3.14, empty home directory) contains
`playbooks/edge.yml` and `examples/edge/`, and `ansible-playbook -i edge/inventory.yml
luminare.infra_edge.edge --syntax-check` and `--list-hosts` with a copy of the example inventory
found the playbook by its name and listed `edge-01.example.com`. The playbook itself has not been
run against a real host; the Molecule scenario `edge` runs it in containers. After the releases
v0.1.0 and v0.2.0 were published on 2026-10-22, `gh release download`, `sha256sum -c SHA256SUMS`
(both archives OK) and `gh attestation verify` (one SLSA provenance attestation per archive)
passed for both releases, and the install from the tag `v0.2.0` with git (ansible-core 2.21.5)
contained the five roles.

## Requirements

| Requirement | Version | Notes |
|---|---|---|
| Python on the control node | 3.12 or later | required by ansible-core 2.20 and 2.21 |
| ansible-core | 2.20 or later | `requires_ansible: ">=2.20.0"` in `meta/runtime.yml`; CI tests 2.21 |
| Collections | devsec.hardening 11.x, community.general 13.x, ansible.posix 2.x, ansible.mariadb 6.x | installed with the collection as its dependencies, from Ansible Galaxy |
| git | any current version | only for the install from a tag |
| Managed hosts | Debian 13, Ubuntu 24.04 | with Python 3 |

## Install

<!-- x-release-please-start-version -->
From a release tag (needs git):

```bash
python3 -m venv ~/.venvs/edge && . ~/.venvs/edge/bin/activate
pip install "ansible-core>=2.21,<2.22"
ansible-galaxy collection install git+https://github.com/luminare-dev/ansible-collection-infra_edge.git,v0.2.1
```

In a project, pin the tag in `requirements.yml` and install it with
`ansible-galaxy collection install -r requirements.yml`:

```yaml
collections:
  - name: https://github.com/luminare-dev/ansible-collection-infra_edge.git
    type: git
    version: v0.2.1
```

From the release tarball (needs the GitHub CLI for the download and the attestation check):

```bash
gh release download v0.2.1 --repo luminare-dev/ansible-collection-infra_edge
sha256sum -c SHA256SUMS
ansible-galaxy collection install luminare-infra_edge-0.2.1.tar.gz
```
<!-- x-release-please-end -->

## Verify the release download

Every release has a `SHA256SUMS` file for both archives (the source archive and the collection
tarball) and a build provenance attestation:

```bash
sha256sum -c --ignore-missing SHA256SUMS
gh attestation verify <archive>.tar.gz --repo luminare-dev/ansible-collection-infra_edge
```

## Run the edge playbook

The collection contains a complete example inventory for its playbook in `examples/edge/` (the
same folder as in the repository). Copy it, put your values into `inventory.yml` and
`group_vars/edge/main.yml`, create `group_vars/edge/vault.yml` with the six `vault_*` values,
export the tunnel token and run the playbook by its name (details in the
[example's README](../examples/edge/README.md)):

```bash
cp -r ~/.ansible/collections/ansible_collections/luminare/infra_edge/examples/edge edge
ansible-vault create edge/group_vars/edge/vault.yml
read -rs TUNNEL_TOKEN && export TUNNEL_TOKEN
ansible-playbook -i edge/inventory.yml luminare.infra_edge.edge --ask-vault-pass
```

In your own playbooks, `ansible.builtin.import_playbook: luminare.infra_edge.edge` runs it as
one step of a longer run.

## Check that it works

```bash
ansible-galaxy collection list luminare.infra_edge
ansible-playbook -i edge/inventory.yml luminare.infra_edge.edge --list-hosts
```

The first command names the folder the collection was installed into and its version, for example:

```text
# /home/user/.ansible/collections/ansible_collections
Collection          Version
------------------- -------
luminare.infra_edge 0.1.0
```

The second one finds the playbook by its name and lists the hosts of the group `edge` in your
inventory, without connecting to them.

## Uninstall

`ansible-galaxy` has no remove command. Delete the collection folder from the path that
`ansible-galaxy collection list` printed:

```bash
rm -rf ~/.ansible/collections/ansible_collections/luminare/infra_edge
```
