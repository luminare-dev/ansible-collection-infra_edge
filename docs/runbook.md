# Runbook

The collection runs nothing by itself; this page covers the failures of its CI and release
automation. Each role that installs a service or a timer adds its own sections here.

## Check failed: molecule

| | |
|---|---|
| **Meaning** | The aggregate `molecule` job failed: the `molecule-plan` job or at least one `molecule-scenario (<role>, <platform>)` job did not pass. `<platform>` is `debian13` or `ubuntu2404`. |
| **Impact** | The pull request should not be merged; the role may not converge, may not be idempotent or may fail its checks on Debian 13 or Ubuntu 24.04. |
| **Diagnosis** | Open the failed `molecule-scenario (<role>, <platform>)` job. The summary at the end of the log names the Molecule action that failed (`converge`, `idempotence`, `verify`); the instance is `ie-<role>-<platform>`. Reproduce it locally in one shell: `cd roles/<role> && export MOLECULE_ROLE=<role>`, then `molecule test --platform-name ie-<role>-<platform> --destroy never`, then `molecule login --host ie-<role>-<platform>`. Every Molecule command needs `MOLECULE_ROLE` set, otherwise the instance names do not match. |
| **Mitigation** | If the log shows a download or package mirror error, re-run the failed jobs once. |
| **Fix** | Fix the role or its scenario in the same pull request. Run `molecule destroy` in the same shell (with `MOLECULE_ROLE` still set) afterwards to remove the containers. |

## Scheduled CI run failed without a code change

| | |
|---|---|
| **Meaning** | The weekly `ci` run (Tuesdays 03:41 UTC) failed although `main` did not change. |
| **Impact** | None for users yet; a role no longer converges or is no longer idempotent with the current Debian or Ubuntu packages, or a lint or tool update changed a result. |
| **Diagnosis** | Compare the failing job with the last passing run of the same job: look for package versions in the converge output and for a recently merged Dependabot pull request (base image digests, Python tools). |
| **Mitigation** | Open an issue with the failing job link, so that pull requests are not blamed for the failure. |
| **Fix** | Adapt the role to the new package version, or pin the package in the role with a comment and a follow-up issue. |

## Release build failed: galaxy.yml has a different version than the tag

| | |
|---|---|
| **Meaning** | The `build` job of the release stopped with `galaxy.yml has version …, the tag is v…`: the release pull request did not update `galaxy.yml`. |
| **Impact** | The GitHub release stays a draft without files, so nothing reaches users. |
| **Diagnosis** | `git show vX.Y.Z:galaxy.yml \| grep '^version'` shows the old version. Check that the `version:` line still ends with `# x-release-please-version` and that `release-please-config.json` lists `galaxy.yml` under `extra-files`. |
| **Mitigation** | None needed; the previous release stays the latest one. |
| **Fix** | Restore the annotation or the `extra-files` entry in a pull request with a `fix:` title, delete the empty draft release, and let release-please prepare the next version. |

## The release pull request shows no checks

| | |
|---|---|
| **Meaning** | release-please opens its pull request with the workflow token, and such pull requests do not start workflows. |
| **Impact** | The required checks never report, so the pull request cannot be merged. |
| **Diagnosis** | The pull request `chore(main): release X.Y.Z` has no `ci / lint-test` check. |
| **Mitigation** | Close the pull request and reopen it once; the checks then run. |
| **Fix** | None; this is how GitHub treats the workflow token (see [ADR 0004](adr/0004-draft-releases-with-checksums-and-provenance.md)). |
