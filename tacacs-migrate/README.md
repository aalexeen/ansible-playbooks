# tacacs-migrate

Ansible playbook for migrating Cisco IOS / IOS XE switches from local authentication to TACACS+.

Supports classic IOS (12.x) and IOS XE (16.x/17.x). Works with one or two TACACS+ servers.

---

## What it does

Migrates AAA on each switch in six phases:

1. **Preflight** — validates variables, ensures the local admin user has privilege 15, verifies that a local safety session can be opened (rollback will work)
2. **Configure** — adds the TACACS+ server(s) to the switch, tests authentication against the server
3. **Safeguard** — applies command authorization via local auth (interim safe state before switching)
4. **Switch** — switches `aaa authentication login default` and `aaa authorization exec default` to TACACS+, then immediately reconnects as a TACACS+ test user to verify
5. **Finalize** — switches command authorization to TACACS+, enables accounting, does a final reconnect verification, saves config
6. **Rollback** (rescue) — if any phase fails, automatically reconnects via local credentials and reverts all AAA changes, then removes TACACS+ server config and saves

Config is **never saved** until phase 5 is fully verified. If anything goes wrong before that, rollback fires and the switch is left unchanged.

---

## Requirements

**Controller:**
- Ansible >= 2.9
- `cisco.ios` collection: `ansible-galaxy collection install cisco.ios`
- `community.general` collection: `ansible-galaxy collection install community.general`
- `ansible-vault` (included with Ansible)

**Switches:**
- Cisco IOS 12.x or IOS XE 16.x / 17.x
- SSH access with a local admin user
- `aaa new-model` already configured
- TACACS+ server reachable from the switch

---

## Quick start

### 1. Install

Run the installer from the source directory:

```bash
./install.sh
```

The installer will:
- Copy playbook files to `/etc/ansible/playbooks/tacacs-migrate/` (or a custom path)
- Prompt for all secrets and encrypt them into `vault.yml`
- Write the inventory file
- Install a management script at the install location

### 2. Add switches to inventory

```bash
./tacacs-migrate.sh configure-hosts
```

Or edit the inventory file directly:

```
# /etc/ansible/playbooks/tacacs-migrate/inventory/hosts

[switches]
SW01 ansible_host=10.0.0.1
SW02 ansible_host=10.0.0.2
```

### 3. Run migration

```bash
./tacacs-migrate.sh run
```

Migrate a single switch:

```bash
./tacacs-migrate.sh run -l SW01
```

Run on multiple switches in parallel (default is 1 at a time):

```bash
./tacacs-migrate.sh run -e serial=5
```

---

## Management script

After installation, use the management script at the install directory:

```bash
./tacacs-migrate.sh                   # interactive menu
./tacacs-migrate.sh run               # run migration on all switches
./tacacs-migrate.sh run -l SW01       # migrate a single switch
./tacacs-migrate.sh configure         # reconfigure all settings
./tacacs-migrate.sh configure-vault   # reconfigure secrets only
./tacacs-migrate.sh configure-hosts   # edit switch inventory
./tacacs-migrate.sh status            # show current config and vault state
./tacacs-migrate.sh vault-rekey       # change vault password
```

---

## Secrets (vault.yml)

All sensitive values are stored encrypted with `ansible-vault`. The vault contains:

| Variable | Description |
|---|---|
| `local_user` | Local admin username on switches |
| `local_pass` | Local admin password |
| `local_enable` | Enable secret (if required) |
| `local_admin_secret` | Secret for recreating admin user with privilege 15 |
| `tacacs_key` | TACACS+ shared key (must match server config) |
| `tacacs_test_user` | TACACS+ readonly user for post-migration verification |
| `tacacs_test_pass` | Password for the test user |
| `tacacs_server_primary` | Primary TACACS+ server IP |
| `tacacs_server_secondary` | Secondary TACACS+ server IP (optional) |

To view or edit the vault manually:

```bash
cd /etc/ansible/playbooks/tacacs-migrate
ansible-vault view playbook/vars/vault.yml
ansible-vault edit playbook/vars/vault.yml
```

---

## AAA configuration applied

After a successful migration each switch will have:

```
aaa authentication login default group TACACS-SERVERS local
aaa authorization exec default group TACACS-SERVERS local if-authenticated
aaa authorization config-commands
aaa authorization commands 0  default group TACACS-SERVERS if-authenticated
aaa authorization commands 1  default group TACACS-SERVERS if-authenticated
aaa authorization commands 5  default group TACACS-SERVERS none
aaa authorization commands 15 default group TACACS-SERVERS
aaa accounting exec default start-stop group TACACS-SERVERS
aaa accounting commands 0  default start-stop group TACACS-SERVERS
aaa accounting commands 1  default start-stop group TACACS-SERVERS
aaa accounting commands 5  default start-stop group TACACS-SERVERS
aaa accounting commands 15 default start-stop group TACACS-SERVERS
```

For classic IOS 12 the group name `TACACS-SERVERS` is replaced with `tacacs+`.

The fallback chain (`local`, `if-authenticated`, `none`) ensures you can still log in if the TACACS+ server is temporarily unreachable.

---

## Safety model

The playbook uses a two-session approach:

- **Work session** — Ansible's normal SSH connection used throughout migration
- **Safety session** — a separate connection opened with local credentials before any AAA changes are made; proves rollback will succeed

If migration fails at any point before `write memory`, the rescue block:
1. Opens a new connection using local credentials (bypassing any broken TACACS+ state)
2. Reverts `aaa authentication` and `aaa authorization` to local
3. Removes TACACS+ server configuration from the switch
4. Saves the config

The switch is left exactly as it was before the playbook ran.
