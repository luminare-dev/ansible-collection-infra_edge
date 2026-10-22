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
