# 0007. One hash-pinned test toolchain instead of separate installs

- **Status:** accepted
- **Date:** 2026-10-21

## Context

CI needs ansible-core, ansible-lint, Molecule with its Docker driver and, at run time, the
community collections that the Docker driver and the roles use (`community.docker`,
`ansible.posix` and others). Installed one by one, these tools resolve to whatever is newest on
the day of the run, and `ansible-galaxy` pulls collections without a hash check against a
reviewed value. The lint-test job of the template already installs `requirements-dev.txt` with
`pip --require-hashes`.

## Considered options

1. One `requirements-test.txt`, compiled by `pip-compile --generate-hashes` from
   `requirements-test.in`, that also pins the `ansible` community package for the collections.
2. Pinned Python tools plus a collections `requirements.yml` installed from Galaxy at run time.
3. Unpinned installs (`pip install ansible-lint molecule`).

## Decision

Option 1. `requirements-test.in` pins ansible-core 2.21.5, ansible-lint 26.10.1, Molecule
26.10.0, molecule-plugins[docker] 26.10.12, yamllint 1.38.0 and the `ansible` package 14.5.0
(built for ansible-core 2.21.5; it contains `community.docker`, `ansible.posix`,
`ansible.mariadb` and `community.general`). It is compiled with Python 3.12 on Ubuntu 24.04,
the Python of the GitHub `ubuntu-24.04` runner, and constrained by `requirements-dev.txt` so that
shared packages keep one version. Every job installs it with
`pip install --require-hashes --only-binary=:all:`; Dependabot proposes updates.

The lint-test job runs the unit tests and `ansible-lint` with the `production` profile from this
toolchain. `meta/runtime.yml` declares `requires_ansible: ">=2.21.0"`, the only ansible-core
version CI runs; it is lowered only after a Molecule converge with an older ansible-core passes.
ansible-lint 26.10.1 lists ansible-core 2.15 to 2.19 as supported, so `.ansible-lint` adds 2.21
through `supported_ansible_also`.

## Consequences

- Good: every Python package and every collection used in CI is pinned and hash-checked; a
  changed file on the package index fails the install.
- Good: the same file works for a local virtual environment (also tested with Python 3.14).
- Bad: the `ansible` package is large (about 51 MB, about one minute to install per job), and
  its collection versions move together with the package version.
