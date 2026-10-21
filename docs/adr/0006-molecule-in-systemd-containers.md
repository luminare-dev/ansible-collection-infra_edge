# 0006. Molecule in systemd containers instead of virtual machines

- **Status:** accepted
- **Date:** 2026-10-21

## Context

Every role must prove on every pull request that it converges on Debian 13 and Ubuntu 24.04 and
that a second run reports `changed=0`. The roles manage services, so the test hosts need systemd
as PID 1. CI runs on GitHub-hosted `ubuntu-24.04` runners, which have Docker but no nested
virtualization by default. Several projects may run Molecule on one Docker daemon at the same
time.

## Considered options

1. Molecule with the Docker driver and privileged systemd containers built from a repository-local
   Dockerfile on digest-pinned `debian:trixie` and `ubuntu:24.04` images.
2. Molecule with prebuilt community images (for example the `docker-*-ansible` images).
3. Molecule with virtual machines (Vagrant or a cloud driver).

## Decision

Option 1. The shared pieces live in one place, `.config/molecule/`: `config.yml` (driver, both
platforms, provisioner, verifier and the test sequence `dependency, destroy, syntax, create,
prepare, converge, idempotence, verify, destroy`) and `Dockerfile.j2` (systemd, Python 3,
python3-apt, sudo, CA certificates; kernel module loading masked). Molecule merges each role's
`roles/<role>/molecule/default/molecule.yml` on top of `config.yml`. Containers run privileged
with the host cgroup namespace, `/sys/fs/cgroup` mounted read-write and tmpfs on `/run` and
`/run/lock`. Instance names are `ie-<role>-debian13` and `ie-<role>-ubuntu2404` (from
`MOLECULE_ROLE`), so they never clash with other projects or other roles on a shared daemon.

In CI a plan job lists `roles/*/molecule/default/molecule.yml` as JSON, and a role × platform
matrix (`debian13`, `ubuntu2404`) runs `molecule test --platform-name ie-<role>-<platform>` once
per pair (45-minute timeout), so a Debian failure and an Ubuntu failure show as separate checks
named `molecule-scenario (<role>, <platform>)`. An aggregate job named `molecule` reports one
result and passes when no role has a scenario. A unit test keeps the matrix platforms equal to
the platforms of `config.yml` and fails when a role folder has no scenario. The scenarios run on
pull requests, on demand and weekly, not on pushes to `main`. Dependabot updates the base image
digests (digests only for `ubuntu:24.04`, never the tag).

## Consequences

- Good: no third-party image; every base layer is pinned and reviewed through Dependabot.
- Good: the same command runs locally and in CI, and adding a role needs only its scenario.
- Bad: containers share the runner's kernel, so firewall rules loaded into the kernel, sysctl
  values and kernel modules cannot be proven; such tasks are tagged `molecule-notest` and their
  checks are listed as limitations until they run on a virtual machine.
- Bad: the `molecule` check is not one of the required checks of the `main` ruleset, so a
  failing scenario does not block a merge by itself; reviewers have to look at it.
