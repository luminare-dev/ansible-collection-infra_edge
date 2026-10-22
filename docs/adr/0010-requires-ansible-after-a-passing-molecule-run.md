# 0010. requires_ansible 2.20 after a passing Molecule run instead of the CI version only

- **Status:** accepted; amends [ADR 0007](0007-one-hash-pinned-test-toolchain.md)
- **Date:** 2026-10-21

## Context

[ADR 0007](0007-one-hash-pinned-test-toolchain.md) set `requires_ansible: ">=2.21.0"`, the only
ansible-core version CI runs, and allowed a lower value only after a Molecule converge with an
older ansible-core passes. With `">=2.21.0"`, a control node with ansible-core 2.20 cannot use
the collection, even where the roles do not need anything from 2.21. ansible-lint 26.10.1 knows
ansible-core 2.15 to 2.19 only, so every newer version has to be listed in
`supported_ansible_also` of `.ansible-lint`.

## Considered options

1. Keep `">=2.21.0"`.
2. `">=2.20.0"` once the scenario of every role has passed with an ansible-core 2.20 release;
   CI keeps running 2.21 only.
3. `">=2.20.0"` and a second Molecule matrix with ansible-core 2.20 in CI.

## Decision

Option 2. On 2026-10-21 the `base` scenario (converge, idempotence `changed=0`, verify) passed
on Debian 13 and Ubuntu 24.04 with ansible-core 2.20.10, Molecule 26.10.0 and the collections
of the `ansible` 14.5.0 package, in a separate virtual environment (the README lists the
measured run). `meta/runtime.yml` declares `requires_ansible: ">=2.20.0"`, and `.ansible-lint`
lists `2.20.` and `2.21.` in `supported_ansible_also`. A role added later is run the same way
with ansible-core 2.20 before the release that contains it; if it fails, the value goes back to
`">=2.21.0"`. Option 3 would double the Molecule jobs of every pull request and need a second
hash-pinned requirements file, because the `ansible` 14.5.0 package requires ansible-core 2.21.

## Consequences

- Good: control nodes with ansible-core 2.20 can install and use the collection.
- Bad: CI does not run ansible-core 2.20, so a change that needs 2.21 shows only in the manual
  run; the README lists this under Limitations.
- Bad: the manual run installs the `ansible` 14.5.0 package with `pip --no-deps` (it requires
  ansible-core 2.21), so its collections are not hash-checked against `requirements-test.txt`.
