# Troubleshooting

## Could not find git executable to extract the collection from the Git repository

```text
[ERROR]: Could not find git executable to extract the collection from the Git repository
`https://github.com/luminare-dev/ansible-collection-infra_edge.git`: Failed to find required
executable "git" in paths: ...
```

**Cause:** `ansible-galaxy` clones the repository to install from a tag, and git is not
installed on the control node.

**Fix:** install git, or install the collection tarball from the GitHub release instead (see
[Installation](install.md)).

```bash
sudo apt-get install git
```

## The role 'luminare.infra_edge.…' was not found

```text
[ERROR]: The role 'luminare.infra_edge.<role>' was not found in: ...
```

**Cause:** the collection is not installed in a path that `ansible-playbook` searches, or it is
installed in another virtual environment or user account.

**Fix:** check where the collection is, and install it again in the same environment that runs
the playbook.

```bash
ansible-galaxy collection list luminare.infra_edge
ansible-config dump | grep COLLECTIONS_PATHS
```

## The base role stops with "Set base_admin_ssh_keys and base_automation_ssh_keys"

**Cause:** one of the two key lists is empty, or both users have the same name. The SSH server
accepts keys only, so a user without a key could not log in; the role stops before it changes
anything.

**Fix:** set at least one public key for each user in the inventory (`base_admin_ssh_keys`,
`base_automation_ssh_keys`), and give the users different names.

## The base role stops with "base_mgmt_cidrs is empty"

**Cause:** `base_ssh_allow_mode` is `mgmt_cidrs` (the default), but no management network is
listed, so the firewall would refuse SSH from every address.

**Fix:** list the networks you administer the host from (for example `192.0.2.0/24`), or set
`base_ssh_allow_mode: any` (SSH open to everyone, protected by keys and fail2ban) or `loopback`
(only local or tunnelled access).

## The base role stops with "is not a valid host name"

**Cause:** `base_hostname` defaults to the inventory name of the host. If the inventory names
the host by its IP address (for example `203.0.113.10`) or the name contains characters a host
name may not have (such as `_`), the role refuses it before it changes anything, because the name
would end up in `/etc/hosts` or make `hostnamectl` fail.

**Fix:** set `base_hostname` for the host to a valid name (for example `edge-1` or
`edge-1.example.com`), or to `""` to leave the host name and `/etc/hosts` unchanged.

## The role 'devsec.hardening.ssh_hardening' was not found

```text
[ERROR]: The role 'devsec.hardening.ssh_hardening' was not found in: ...
```

**Cause:** the collection was installed with `--no-deps` or from a copy, so its dependencies
(`devsec.hardening`, `community.general`, `ansible.posix`) are missing.

**Fix:** install them, or install the collection again without `--no-deps`.

```bash
ansible-galaxy collection install "devsec.hardening:>=11.0.0,<12.0.0" "community.general:>=13.0.0,<14.0.0" "ansible.posix:>=2.2.0,<3.0.0"
```

## Molecule: docker command not found in PATH

```text
[ERROR]: Task failed: docker command not found in PATH: Failed to find required executable
"docker" in paths: ...
```

**Cause:** the instances are created through the Docker API, but Ansible connects to them with
the `community.docker.docker` connection plugin, which calls the Docker command-line client.

**Fix:** install the Docker client on the machine that runs Molecule (the GitHub runners have it).

```bash
sudo apt-get install docker.io
```

## Still stuck?

Search the issues, then ask in the project's
[Discussions](https://github.com/luminare-dev/ansible-collection-infra_edge/discussions). Never
post secrets, keys, IP addresses, hostnames or player data; redact logs before you paste them.
