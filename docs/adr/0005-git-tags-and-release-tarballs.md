# 0005. Git tags and release tarballs instead of a package index upload

- **Status:** accepted
- **Date:** 2026-10-21

## Context

`luminare.infra_edge` is an Ansible collection (`galaxy.yml` at the repository root, namespace
`luminare`). Users and the organization's own projects need a version they can pin, verify and
install with standard tools. The template release (ADR 0004) builds a `git archive` of the tag,
which `ansible-galaxy` cannot install. release-please's `simple` release type updates
`version.txt` and `CHANGELOG.md`, but not `galaxy.yml`.

## Considered options

1. Install from the git tag, and attach the `ansible-galaxy collection build` tarball to the
   GitHub release next to the source archive.
2. Upload every release to Ansible Galaxy from the release workflow.
3. Both.

## Decision

Option 1. `ansible-galaxy collection install git+https://github.com/luminare-dev/ansible-collection-infra_edge.git,vX.Y.Z`
and a `requirements.yml` entry with `type: git` and `version: vX.Y.Z` install a tag directly. The
release build job also runs `ansible-galaxy collection build`, checks that the `galaxy.yml`
version equals the tag, installs the tarball once as a smoke test and writes `SHA256SUMS` over
both archives, which the existing attestation step then covers. No workflow holds a package
index token or uploads anywhere; a later upload would be a new decision.

release-please keeps `galaxy.yml` in step through an `extra-files` entry with the `generic`
updater and the `# x-release-please-version` annotation on the `version:` line. The `yaml`
updater was rejected because it rewrites the whole file and drops its comments. The same
generic updater keeps the install commands in `README.md` and `docs/install.md` on the newest
tag (lines between `x-release-please-start-version` and `x-release-please-end`).

`galaxy.yml` lists only community collections that a role really uses, each with a version
range; other `luminare` collections are never hard dependencies.

## Consequences

- Good: one tag gives the source archive, the installable tarball, checksums and provenance;
  nothing in CI needs an extra credential.
- Good: `tests/test_collection.py` builds and installs the tarball on every pull request, so a
  broken `build_ignore` or `galaxy.yml` fails before a release.
- Bad: installing from a tag needs git on the control node; the tarball route needs a download
  first.
