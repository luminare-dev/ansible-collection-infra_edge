# Example inventory for the edge playbook

A complete inventory for [`luminare.infra_edge.edge`](../../playbooks/edge.yml), with the backups
switched on. The Molecule scenario `extensions/molecule/edge` runs the playbook with these
`group_vars`, so the example stays working. Names use `example.com` and addresses the
documentation ranges.

| File | What it holds |
|---|---|
| `inventory.yml` | The host `edge-01.example.com` in the group `edge`: its SSH address, the login user of the first run, the private address the database listens on and its backup repository |
| `group_vars/edge/main.yml` | The values of every edge host: the SSH keys and management networks (`base`), the nginx site, the database with its two accounts and the application host that may reach port 3306, and the backups (`restic_backup`, switched on with `edge_restic_backup_enabled`) |
| `group_vars/edge/vault.yml` | Not included: create it encrypted with the six secrets below |

## Use it

1. Copy the folder (after an install from a tag it is in the collection, for example
   `~/.ansible/collections/ansible_collections/luminare/infra_edge/examples/edge`).
2. In `inventory.yml`, set the host name, `ansible_host`, the private address
   `mariadb_bind_address` (or remove that line to keep the database on `127.0.0.1`, together
   with `mariadb_allowed_app_hosts` and the second account in `group_vars/edge/main.yml`) and the
   host's backup repository `restic_backup_repository` in your S3-compatible bucket (or set
   `edge_restic_backup_enabled: false` in `group_vars/edge/main.yml` to leave the backups out).
3. In `group_vars/edge/main.yml`, put your public SSH keys, your management networks, the site of
   your application and its database.
4. Create the vault file with `ansible-vault create group_vars/edge/vault.yml`:

   ```yaml
   vault_base_admin_password_hash: "<output of openssl passwd -6>"
   vault_edge_app_db_password: "<a new password>"
   vault_edge_app_reader_db_password: "<another new password>"
   vault_edge_backup_password: "<a long new password for the restic repository>"
   vault_edge_backup_s3_key_id: "<access key ID of the bucket>"
   vault_edge_backup_s3_secret: "<secret access key of the bucket>"
   ```

   Keep a copy of `vault_edge_backup_password` outside the host and the bucket: without it the
   snapshots cannot be read.

5. Export the tunnel token without echo, then run the playbook:

   ```bash
   read -rs TUNNEL_TOKEN && export TUNNEL_TOKEN
   ansible-playbook -i inventory.yml luminare.infra_edge.edge --ask-vault-pass
   ```

After the first night, `restic-env snapshots` (as root on the host) lists the first snapshot,
and `restic-restore-test` restores it into a temporary folder and compares it with the snapshot.

The first run logs in as root. The `base` role then refuses SSH logins as root, so set
`ansible_user: ansible` (the automation user) in `inventory.yml` for every later run. The public
hostname of the tunnel (`app.example.com` here) points to `http://127.0.0.1:8080` in the
Cloudflare dashboard or API; the playbook does not create tunnels or routes.

All variables are described in [docs/configuration.md](../../docs/configuration.md).
