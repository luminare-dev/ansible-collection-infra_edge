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

## The cloudflared role stops with "Set cloudflared_token"

**Cause:** `cloudflared_token` is empty (by default it is read from the environment variable
`TUNNEL_TOKEN` of the control node, and that variable is not set in the shell that runs
`ansible-playbook`), or the value is not a tunnel token. A tunnel token is base64-encoded JSON and
starts with `eyJ`; the tunnel ID or an API token does not work.

**Fix:** copy the token of the remotely managed tunnel from the Cloudflare dashboard (it is part
of the install command shown for the tunnel) and export it without echo in the same shell:

```bash
read -rs TUNNEL_TOKEN && export TUNNEL_TOKEN
```

## The cloudflared role fails at "Download the package file and check its SHA-256"

**Cause:** `cloudflared_version` was changed without `cloudflared_deb_sha256` (the checksum does
not match the new file), or the version does not exist in Cloudflare's repository pool.

**Fix:** take both SHA-256 values (`cloudflared-linux-amd64.deb`, `cloudflared-linux-arm64.deb`)
from the checksum list of the same GitHub release and set them together with the version (see
"Upgrading cloudflared" in the [role README](../roles/cloudflared/README.md#upgrading-cloudflared)).

## The cloudflared role fails at "Enable and start the connector" or "Restart cloudflared"

**Cause:** the unit has `Type=notify`, so systemd waits for the tunnel's first connection to
Cloudflare's edge and gives up after 30 seconds: the token is wrong or was rotated, or outbound
port 7844 is blocked.

**Fix:** read the reason with `journalctl -u cloudflared -n 50` on the host, then follow
"Tunnel connector down or not connected" in the [runbook](runbook.md).

## The nginx role stops with "Every item of nginx_sites needs a unique name"

**Cause:** an item of `nginx_sites` breaks a rule that the role checks before it changes
anything: the `listen` address is not on the loopback interface (only `127.0.0.1:<port>` or
`[::1]:<port>`; the tunnel connector on the same host is the only client), the `upstream` is not
an `http://` URL, the name is used twice or is `default`, or a value contains a space, quote,
semicolon or brace. The message lists the site names it read.

**Fix:** correct the item. A site for another host needs that host's own nginx and connector.

## The nginx role fails at "Check the configuration with nginx -t"

**Cause:** the role wrote the files, but nginx refuses the configuration, for example because the
host name in an `upstream` does not resolve on the host (nginx resolves it when it loads the
configuration: `host not found in upstream`), or because of a file in `/etc/nginx/conf.d/` that
the role does not manage. nginx keeps serving the configuration it had before; the role does not
reload it.

**Fix:** read the message of the failed task (nginx names the file and line), correct the
inventory or the other file, and run the playbook again. Until then every run fails at this
check.

## A relay port of the nginx role is not reachable from other hosts

**Cause:** the firewall of the base role has no rule for it: `/etc/nftables.d` did not exist
when the role ran (and `nginx_firewall_manage` is false), nftables was not running, so the role
did not restart it, or `nginx_firewall_sources` does not cover the client. A firewall in front of
the host (for example at the hosting provider) can also block it.

**Fix:** check the rules with `cat /etc/nftables.d/20-nginx.nft` and
`nft list chain inet filter input`, and the listener with `ss -tulnp | grep nginx`. Apply the
base role before the nginx role (or set `nginx_firewall_manage: true`), correct
`nginx_firewall_sources`, and run the playbook again.

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
