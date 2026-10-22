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

Ansible collection for edge hosts: base hardening, an outbound tunnel, a web server and a database.

[![ci](https://github.com/luminare-dev/ansible-collection-infra_edge/actions/workflows/ci.yml/badge.svg)](https://github.com/luminare-dev/ansible-collection-infra_edge/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/luminare-dev/ansible-collection-infra_edge?sort=semver)](https://github.com/luminare-dev/ansible-collection-infra_edge/releases)
[![licence](https://img.shields.io/github/license/luminare-dev/ansible-collection-infra_edge)](LICENSE)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/luminare-dev/ansible-collection-infra_edge/badge)](https://scorecard.dev/viewer/?uri=github.com/luminare-dev/ansible-collection-infra_edge)

## Why

An edge host is a small Linux server that reaches the internet through an outbound tunnel, serves
a few sites with a web server and keeps a database next to them. Set up by hand, it needs the same
hardening and service steps every time, and the result drifts. This collection holds those steps
as Ansible roles. On every pull request, CI runs each role's Molecule scenario in Debian 13 and
Ubuntu 24.04 containers with systemd and expects `changed=0` on the second run, and each release
ships the collection tarball with checksums and build provenance.

## Quickstart

Needs Python 3.12 or later and git. Install the collection from a release tag:

<!-- x-release-please-start-version -->
```bash
python3 -m venv ~/.venvs/edge && . ~/.venvs/edge/bin/activate
pip install "ansible-core>=2.21,<2.22"
ansible-galaxy collection install git+https://github.com/luminare-dev/ansible-collection-infra_edge.git,v0.1.0
ansible-galaxy collection list luminare.infra_edge
```
<!-- x-release-please-end -->

[docs/install.md](docs/install.md) also covers the release tarball and how to verify it.

## How it works

Every pull request runs the template checks, the unit tests (they also build and install the
collection tarball) and ansible-lint with the production profile; a unit test fails when a role
has no Molecule scenario. A plan job lists the roles with a scenario, and the matrix starts one
job per role and platform: each job tests one role in a Debian 13 or an Ubuntu 24.04 container
with systemd. An aggregate job named `molecule` reports one result for all of them. After a
merge to `main`, release-please prepares the next version; the release attaches the source
archive and the collection tarball with `SHA256SUMS`.

```mermaid
flowchart LR
    pr(["Pull request"]) --> lint["ci / lint-test: unit tests, collection build, ansible-lint"]
    pr --> plan["molecule-plan: roles with a scenario"]
    plan --> scenario["molecule-scenario: one job per role and platform (Debian 13, Ubuntu 24.04)"]
    scenario --> gate["molecule: one result for all jobs"]
    merge(["Merge to main"]) --> rp["release-please: tag vX.Y.Z"]
    rp --> release["GitHub release: source archive, collection tarball, SHA256SUMS"]
    release --> operator(["Operator installs from the tag"])
```

## Design decisions

The decisions behind this project are recorded as short ADRs in [docs/adr/](docs/adr/):

- [ADR 0001: Record architecture decisions](docs/adr/0001-record-architecture-decisions.md)
- [ADR 0002: Pin every action and downloaded tool](docs/adr/0002-pin-actions-and-downloaded-tools.md)
- [ADR 0003: Secret scanning with the gitleaks binary](docs/adr/0003-secret-scanning-with-the-gitleaks-binary.md)
- [ADR 0004: Draft releases with checksums and provenance](docs/adr/0004-draft-releases-with-checksums-and-provenance.md)
- [ADR 0005: Why git tags and release tarballs instead of a package index upload](docs/adr/0005-git-tags-and-release-tarballs.md)
- [ADR 0006: Why Molecule in systemd containers instead of virtual machines](docs/adr/0006-molecule-in-systemd-containers.md)
- [ADR 0007: Why one hash-pinned test toolchain instead of separate installs](docs/adr/0007-one-hash-pinned-test-toolchain.md)

## Supported versions

| Component | Tested with | Supported |
|---|---|---|
| ansible-core (control node) | 2.21.5 | 2.21 and later (`requires_ansible: ">=2.21.0"`) |
| Python (control node) | 3.12 (Ubuntu 24.04) and 3.14 | 3.12 and later (required by ansible-core 2.21) |
| Debian (managed host) | 13 "trixie" Molecule image | 13 |
| Ubuntu (managed host) | 24.04 "noble" Molecule image | 24.04 LTS |

Fixes go into the latest minor release only. See the
[security policy](https://github.com/luminare-dev/.github/blob/main/SECURITY.md) for reporting.

## Limitations

- This version contains no role yet: it is the collection skeleton with its Molecule harness, CI
  and release automation, so nothing has been applied to a managed host.
- The `molecule` check is not yet a required check of the `main` ruleset (the required checks
  are `ci / lint-test`, `secrets / gitleaks`, `pr / pr-title` and `DCO`), so a failing scenario
  shows on the pull request but does not block the merge by itself.
- Molecule runs in privileged containers, not virtual machines. Kernel-level behaviour (firewall
  rules loaded into the kernel, sysctl values, kernel modules) cannot be proven there.
- Only ansible-core 2.21 is tested; `requires_ansible` is lowered only after an older
  ansible-core passes a Molecule converge.
- Only x86-64 is tested (the GitHub `ubuntu-24.04` runner and the local test machine).
- `ansible-test sanity` is not run: the collection has no plugins or modules, and ansible-lint
  checks the roles and the metadata.
- The collection is not on Ansible Galaxy yet: it is installed from the git tags and the
  tarballs of the GitHub releases only, and the namespace `luminare` has not been requested yet
  ([ADR 0005](docs/adr/0005-git-tags-and-release-tarballs.md)).

## Results

| What | Value | How it was measured |
|---|---|---|
| Unit tests | 114 run: 112 passed, 2 skipped (markdownlint-cli2 not on the PATH; a template-only check) | `python3 -m unittest discover -s tests -v` with Python 3.14, 2026-10-21 |
| ansible-lint | 0 failures, 0 warnings in 18 files, production profile | `ansible-lint` 26.10.1 from the repository root, 2026-10-21 |
| Collection tarball | 21 files, 19 KB; installs into an empty collections path | `ansible-galaxy collection build`, then `ansible-galaxy collection install --no-deps` (ansible-core 2.21.5), 2026-10-21 |
| Test tools install | 47 packages in 51 s, every file checked against its sha256 | `pip install --require-hashes --only-binary=:all:` of `requirements-dev.txt` and `requirements-test.txt` with Python 3.12 in an `ubuntu:24.04` container, 2026-10-21 |

## Documentation and links

- [Installation](docs/install.md) · [Configuration](docs/configuration.md) ·
  [Upgrade](docs/upgrade.md) · [Troubleshooting](docs/troubleshooting.md) ·
  [Runbook](docs/runbook.md) · [ADRs](docs/adr/) · [Roles](roles/README.md)
- [Changelog](CHANGELOG.md) and [releases](https://github.com/luminare-dev/ansible-collection-infra_edge/releases)
  (each release has `SHA256SUMS` and a build provenance attestation)
- [Contributing](https://github.com/luminare-dev/.github/blob/main/CONTRIBUTING.md) ·
  [Code of conduct](https://github.com/luminare-dev/.github/blob/main/CODE_OF_CONDUCT.md) ·
  [Security](https://github.com/luminare-dev/.github/blob/main/SECURITY.md) ·
  [Support](https://github.com/luminare-dev/.github/blob/main/SUPPORT.md)
- Project page: <https://luminare.tech/open-source/ansible-collection-infra_edge/>

## Licence

[Apache-2.0](LICENSE). The licence covers the code only: the project name, logo, header images
and `docs/brand/` are not licensed (see [NOTICE](NOTICE)).

<!-- byline:studio -->
*a [Luminare Development](https://luminare.tech/open-source/ansible-collection-infra_edge/) open-source project*
<!-- /byline:studio -->
<!-- byline:personal
*by [ItsPaulAT](https://github.com/ItsPaulAT) · [project page](https://luminare.tech/open-source/ansible-collection-infra_edge/)*
/byline:personal -->
