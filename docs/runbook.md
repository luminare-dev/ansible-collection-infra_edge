# Runbook

The collection runs nothing by itself. This page covers the services and timers that its roles
install on a host, and the failures of its CI and release automation.

## SSH login refused after the base role ran

| | |
|---|---|
| **Meaning** | `ssh` to a host that `luminare.infra_edge.base` configured ends with `Permission denied (publickey)` or a timeout. |
| **Impact** | Nobody can administer the host over SSH, and playbook runs against it fail as unreachable. |
| **Diagnosis** | A timeout points to the firewall (`base_mgmt_cidrs`, `base_ssh_allow_mode`) or a fail2ban ban; `Permission denied` points to the key, the user or the group: only members of `sshusers` with a listed key may log in, root never. From the host console: `nft list ruleset`, `fail2ban-client status sshd`, `journalctl -u ssh`, `sshd -T`. |
| **Mitigation** | Follow the [lock-out recovery](../roles/base/README.md#lock-out-recovery) steps on the console: stop nftables, unban the address, or add the key. |
| **Fix** | Correct the key lists, `base_mgmt_cidrs` or the group membership in the inventory and run the playbook again. |

## nftables did not load

| | |
|---|---|
| **Meaning** | `systemctl status nftables` shows `failed` after a change to `/etc/nftables.conf` or a file in `/etc/nftables.d/`. |
| **Impact** | The kernel keeps no ruleset from this file: with a failed start after a reboot the host has no firewall at all. |
| **Diagnosis** | `nft -c -f /etc/nftables.conf` names the file and line with the error; `journalctl -u nftables` shows the failed start. A drop-in must hold only `add rule inet filter input … accept` lines. |
| **Mitigation** | Move the broken drop-in out of `/etc/nftables.d/`, then `systemctl restart nftables` and `systemctl restart fail2ban`. |
| **Fix** | Correct the template of the role that wrote the drop-in; the roles check the ruleset with `nft -c` before they restart nftables. |

## Security updates are not installed

| | |
|---|---|
| **Meaning** | Security updates stay pending (`apt list --upgradable` lists packages from the security archive for more than a day). |
| **Impact** | Known vulnerabilities stay open on the host. |
| **Diagnosis** | `systemctl list-timers 'apt-daily*'` shows the daily timers; `/var/log/unattended-upgrades/unattended-upgrades.log` shows the last run; `apt-config dump Unattended-Upgrade::Origins-Pattern APT::Periodic` shows the allowed origins and whether the daily run is on. A held package or a dpkg error stops the run. |
| **Mitigation** | Run `unattended-upgrade -d` once and read its output; install an urgent update by hand with `apt-get install --only-upgrade <package>`. |
| **Fix** | Remove the cause (held package, broken dpkg state) and check that `base_unattended_upgrades_enabled` is true. If `/var/run/reboot-required` exists, reboot in a maintenance window or set `base_unattended_reboot`. |

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
