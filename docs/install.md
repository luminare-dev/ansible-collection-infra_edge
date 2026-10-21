# Installation

The collection is installed from this repository: from a release tag with git, or from the
collection tarball attached to the GitHub release.

What was tested, on 2026-10-21 with ansible-core 2.21.5 and Python 3.12 in an `ubuntu:24.04`
container, before any release existed: the install from a tag with git and the install from
`requirements.yml`, both against a local clone of the repository with a test tag `v0.1.0` (a
`file://` URL in place of the GitHub URL), and `ansible-galaxy collection install` of a tarball
built locally with `ansible-galaxy collection build`. `gh release download`, `sha256sum -c` and
`gh attestation verify` were not run, because there is no release to download yet. Repeated the
same day for the version with the `base` role: both installs also pulled the dependencies from
Ansible Galaxy (devsec.hardening 11.0.0, community.general 13.5.0, ansible.posix 2.2.2 and the
collections that devsec.hardening needs, community.crypto and community.mysql); one download
failed once with a read timeout and passed when the command was run again. On 2026-10-22, for
the version with the `mariadb` role, the install from a tag (ansible-core 2.21.5, Python 3.14,
empty collections path) also pulled ansible.mariadb 6.0.2 from Ansible Galaxy.

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
ansible-galaxy collection install git+https://github.com/luminare-dev/ansible-collection-infra_edge.git,v0.1.0
```

In a project, pin the tag in `requirements.yml` and install it with
`ansible-galaxy collection install -r requirements.yml`:

```yaml
collections:
  - name: https://github.com/luminare-dev/ansible-collection-infra_edge.git
    type: git
    version: v0.1.0
```

From the release tarball (needs the GitHub CLI for the download and the attestation check):

```bash
gh release download v0.1.0 --repo luminare-dev/ansible-collection-infra_edge
sha256sum -c SHA256SUMS
ansible-galaxy collection install luminare-infra_edge-0.1.0.tar.gz
```
<!-- x-release-please-end -->

## Verify the release download

Every release has a `SHA256SUMS` file for both archives (the source archive and the collection
tarball) and a build provenance attestation:

```bash
sha256sum -c --ignore-missing SHA256SUMS
gh attestation verify <archive>.tar.gz --repo luminare-dev/ansible-collection-infra_edge
```

## Check that it works

```bash
ansible-galaxy collection list luminare.infra_edge
```

The output names the folder the collection was installed into and its version, for example:

```text
# /home/user/.ansible/collections/ansible_collections
Collection          Version
------------------- -------
luminare.infra_edge 0.1.0
```

## Uninstall

`ansible-galaxy` has no remove command. Delete the collection folder from the path that
`ansible-galaxy collection list` printed:

```bash
rm -rf ~/.ansible/collections/ansible_collections/luminare/infra_edge
```
