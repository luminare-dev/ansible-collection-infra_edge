# Example inventory for the edge playbook

A complete inventory for [`luminare.infra_edge.edge`](../../playbooks/edge.yml), the playbook
that sets up one edge host with the four roles of the collection. The Molecule scenario
`extensions/molecule/edge` runs the playbook with these `group_vars` on Debian 13 and Ubuntu 24.04
on every pull request. It adds or replaces only these values: the SSH keys (with a test key) and
the values of the vault file, the tunnel token (a synthetic one) and a test-only edge address
for the connector (`cloudflared_extra_args`), the host's private address from `inventory.yml`
(which Molecule does not read), and a small InnoDB buffer pool for the container
(`mariadb_innodb_buffer_pool_size: 128M`). Names use `example.com` and addresses the
documentation ranges, so nothing points to a real host.

| File | What it holds |
|---|---|
| `inventory.yml` | The host `edge-01.example.com` in the group `edge`: its SSH address, the login user of the first run and the private address the database listens on |
| `group_vars/edge/main.yml` | The values of every edge host: the SSH keys and management networks (`base`), the nginx site, the database with its two accounts and the application host that may reach port 3306 |
| `group_vars/edge/vault.yml` | Not included: create it encrypted with the three secrets below |

## Use it

1. Copy the folder (after an install from a tag it is in the collection, for example
   `~/.ansible/collections/ansible_collections/luminare/infra_edge/examples/edge`).
2. In `inventory.yml`, set the host name, `ansible_host` and the private address
   `mariadb_bind_address` (or remove that line to keep the database on `127.0.0.1`, together
   with `mariadb_allowed_app_hosts` and the second account in `group_vars/edge/main.yml`).
3. In `group_vars/edge/main.yml`, put your public SSH keys, your management networks, the site of
   your application and its database.
4. Create the vault file with `ansible-vault create group_vars/edge/vault.yml`:

   ```yaml
   vault_base_admin_password_hash: "<output of openssl passwd -6>"
   vault_edge_app_db_password: "<a new password>"
   vault_edge_app_reader_db_password: "<another new password>"
   ```

5. Export the tunnel token without echo, then run the playbook:

   ```bash
   read -rs TUNNEL_TOKEN && export TUNNEL_TOKEN
   ansible-playbook -i inventory.yml luminare.infra_edge.edge --ask-vault-pass
   ```

The first run logs in as root. The `base` role then refuses SSH logins as root, so set
`ansible_user: ansible` (the automation user) in `inventory.yml` for every later run. The public
hostname of the tunnel (`app.example.com` here) points to `http://127.0.0.1:8080` in the
Cloudflare dashboard or API; the playbook does not create tunnels or routes.

All variables are described in [docs/configuration.md](../../docs/configuration.md).
