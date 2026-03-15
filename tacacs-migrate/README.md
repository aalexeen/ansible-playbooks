# tacacs-migrate

Ansible playbook for migrating Cisco IOS / IOS XE switches from local authentication to TACACS+.

Supports classic IOS (12.x) and IOS XE (16.x/17.x). Works with one or two TACACS+ servers.

---

## What it does

Migrates AAA on each switch in five phases plus automatic rollback:

1. **Broker open** — opens a persistent SSH safety session to the switch via netdev-broker using local credentials; this session is independent of Ansible's connection and survives any AAA changes
2. **Preflight** — validates variables, checks IOS version, ensures the local admin user has privilege 15
3. **Configure** — adds TACACS+ server(s), tests reachability; supports legacy IOS 12 syntax (`tacacs-server host`) and modern IOS XE 16+ named objects (`tacacs server`)
4. **Safeguard** — applies interim command authorization via local auth (safe state before switching)
5. **Switch** — enables TACACS+ authentication and exec authorization, verifies login via test user
6. **Finalize** — switches command authorization to TACACS+, enables accounting, final verification, saves config
7. **Rollback** (rescue, automatic) — if any phase fails, sends rollback commands through the broker safety session to revert all AAA changes and remove TACACS+ server config, then saves

Config is **never saved** until phase 6 is fully verified. If anything goes wrong before that, rollback fires automatically and the switch is left exactly as it was.

---

## Requirements

**Controller:**
- Ansible >= 2.9
- `cisco.ios` collection: `ansible-galaxy collection install cisco.ios`
- `community.general` collection: `ansible-galaxy collection install community.general`
- `ansible-vault` (included with Ansible)
- **netdev-broker** running on the controller (provides the safety session for rollback)

**Switches:**
- Cisco IOS 12.x or IOS XE 16.x / 17.x
- SSH or Telnet access with a local admin user
- `aaa new-model` already configured (or will be applied during migration)
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
./tacacs-migrate.sh configure-broker  # reconfigure netdev-broker URL and token
./tacacs-migrate.sh configure-hosts   # edit switch inventory
./tacacs-migrate.sh status            # show current config and vault state
./tacacs-migrate.sh vault-rekey       # change vault password
```

Runtime overrides:

```bash
./tacacs-migrate.sh run -e serial=5                    # 5 switches in parallel
./tacacs-migrate.sh run -e broker_session_timeout=900  # broker idle timeout (default: 600s)
./tacacs-migrate.sh run -l SW01 -e connection_mode=telnet  # force Telnet for a host
```

---

## Secrets (vault.yml)

All sensitive values are stored encrypted with `ansible-vault`. The vault contains:

| Variable | Description |
|---|---|
| `broker_url` | netdev-broker URL (e.g. `http://127.0.0.1:8765`) |
| `broker_token` | netdev-broker API token |
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

- **Work session** — Ansible's normal `network_cli` SSH connection (or a Telnet broker session for Telnet-only devices)
- **Safety session** — a persistent SSH session opened via netdev-broker before any AAA changes, using local credentials; completely independent of Ansible's connection and survives AAA reconfiguration

If migration fails at any point before `write memory`, the rescue block sends rollback commands directly through the broker safety session:
1. Reverts `aaa authentication` and `aaa authorization` to local
2. Removes TACACS+ server configuration from the switch
3. Saves the config

The switch is left exactly as it was before the playbook ran.

Per-host log files are written to `../logs/<hostname>_<timestamp>.log` on the controller regardless of success or failure.

### IOS version branching

| Branch | Versions | TACACS+ syntax |
|---|---|---|
| `legacy` | IOS 12.x – 15.x | `tacacs-server host <IP> key <key>` |
| `modern` | IOS XE 16.x / 17.x | `tacacs server <name>` (named object) |

On legacy devices the playbook first tries the per-host key syntax (`tacacs-server host <IP> key <key>`); if the device rejects it, it falls back to the separate global key syntax (`tacacs-server key <key>`) automatically.
