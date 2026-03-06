# tacacs-ng — Ansible Playbook

Deploys a TACACS+ authentication server (`tac_plus-ng`) on Ubuntu.
Source tarball is bundled in the role — **no internet access required** on either the controller or the target.

## Features

- Fully interactive installer — no Ansible knowledge required
- All secrets (TACACS+ key, password hashes, sudo password) stored in Ansible Vault — never in git
- Any number of TACACS+ users with role-based access control
- SHA-512 password hashes generated automatically during setup
- Uninstall role included (never runs unless explicitly requested)
- Single management script copied to the deployment directory — source repo not needed after install

## Quick start

```bash
git clone <repo-url>
cd tacacs-ng/
./install.sh
```

The installer guides you through everything interactively:
target host, SSH credentials, sudo password, TACACS+ users, and vault encryption.

---

## Repository structure

```
tacacs-ng/
├── install.sh                              # installer (source mode only)
├── USAGE.md                                # command reference (copied to INSTALL_DIR)
├── playbook/
│   └── deploy-tacacs.yml                  # main playbook
└── roles/
    ├── tac_plus_ng_build/                  # compile tac_plus-ng from source on target
    ├── tac_plus_ng_deploy/                 # deploy config + systemd unit
    │   ├── templates/tac_plus-ng.cfg.j2   # Jinja2 config template (no secrets)
    │   └── vars/
    │       ├── vault.yml.example           # vault structure example — safe to commit
    │       └── vault.yml                   # encrypted secrets — never committed (in .gitignore)
    ├── tac_plus_ng_test/                   # TCP check + functional auth test
    └── tac_plus_ng_uninstall/              # cleanup role (disabled by default via 'never' tag)
```

---

## How it works

### Build strategy

Source is compiled **on the target machine** to ensure compatibility with its glibc, libssl,
and libpcre2 versions. No GitHub access is needed — the tarball ships inside the role.

### Secrets management

All sensitive values are stored in `vault.yml`, encrypted with `ansible-vault`:
- TACACS+ shared key
- User password hashes
- Sudo (become) password

The config deployed to the server is generated from a Jinja2 template — no secrets appear
anywhere in the repository.

### Script modes

`install.sh` detects its context automatically:

| Mode | Condition | Available commands |
|---|---|---|
| **source** | `roles/` present next to script | `install`, `status`, `help` |
| **installed** | `.installed` marker present | `configure`, `configure-host`, `configure-users`, `configure-vault-password`, `run`, `status`, `uninstall`, `help` |

On install, the script copies itself to `INSTALL_DIR/tacacs-ng.sh`.
After that, manage everything from there — the source repo is no longer needed.

---

## installer — source mode

```bash
./install.sh              # interactive menu
./install.sh install      # full install: copy files + configure + encrypt vault
./install.sh status       # show installation status
./install.sh help         # show available commands
```

---

## tacacs-ng.sh — installed mode

See [USAGE.md](USAGE.md) for the full command reference.

```bash
./tacacs-ng.sh                           # interactive menu
./tacacs-ng.sh run                       # full deploy: build → config → service → test
./tacacs-ng.sh run --tags build          # compile from source only
./tacacs-ng.sh run --tags config,service # deploy config + start service
./tacacs-ng.sh run --tags reload         # SIGHUP — reload config without restart
./tacacs-ng.sh run --tags uninstall      # remove tac_plus-ng from target host
./tacacs-ng.sh configure                 # reconfigure host + users
./tacacs-ng.sh configure-host            # SSH / inventory only
./tacacs-ng.sh configure-users           # TACACS+ users + vault
./tacacs-ng.sh configure-vault-password  # change vault encryption password
./tacacs-ng.sh status                    # show current configuration
./tacacs-ng.sh uninstall                 # remove installed playbook from this machine
```

---

## TACACS+ roles

| Role | Priv level | Access |
|---|---|---|
| `admin` | 15 | All commands permitted |
| `engineer` | 10 | show, ping, traceroute, interface config, VLAN, STP, write/copy — no reload/delete/erase/debug |
| `readonly` | 15 | show commands only |
| `helpdesk` | 15 | L1/L2 diagnostics: show interfaces/mac/arp/cdp/vlan + ping |

---

## Playbook tags

| Tag | What it does |
|---|---|
| `deps` | Install build dependencies on target (apt) |
| `build` | Unpack source, compile, `make install` |
| `config` | Create directories, deploy config, validate with `-P` |
| `service` | Deploy systemd unit, enable, start |
| `test` | TCP check port 49 + optional functional auth test |
| `reload` | SIGHUP — reload config without restart |
| `cleanup` | Remove temporary build directory from target |
| `uninstall` | Remove tac_plus-ng from target (disabled by default via `never` tag) |

---

## Key variables

| Variable | Default | Source |
|---|---|---|
| `tacacs_server_key` | — | `vault.yml` |
| `tacacs_users` | — | `vault.yml` |
| `ansible_become_password` | — | `vault.yml` (if sudo required) |
| `tacacs_config_dir` | `/etc/tac_plus-ng` | role defaults |
| `tacacs_log_dir` | `/var/log/tac_plus-ng` | role defaults |
| `tacacs_binary` | `/usr/local/sbin/tac_plus-ng` | role defaults |
| `remote_build_dir` | `/tmp/tac-plus-ng-build` | role defaults |
| `uninstall_build_deps` | `false` | runtime `-e` override |
| `tacacs_ro_password` | `''` (test skipped) | runtime `-e` override |

---

## Controller prerequisites

- Ansible >= 2.9
- `community.general` collection — installed automatically by `install.sh`
- `python3`
- `openssl` — for password hash generation during configuration

## Build dependencies (installed automatically on target)

- `build-essential`, `clang`
- `libpcre2-dev`
- `libc-ares-dev`
- `libssl-dev`
- `pkg-config`

---

## Manual verification after deploy

```bash
# On the target machine
sudo systemctl status tac_plus-ng
sudo journalctl -u tac_plus-ng -f
sudo tail -f /var/log/tac_plus-ng/access.log

# TCP check from controller
nc -zv <target-ip> 49

# Functional TACACS+ auth test from controller
python3 roles/tac_plus_ng_test/files/tacacs_test.py \
  --host <target-ip> \
  --port 49 \
  --key '<tacacs_server_key>' \
  --user <username>
```

---

## Security notes

- `vault.yml` is in `.gitignore` — never committed to the repository
- `vars.env` (SSH settings, vault password file path) is in `.gitignore`
- All password hashes use SHA-512 (`openssl passwd -6`)
- Vault password file should be `chmod 600` and backed up securely
- The plaintext `vault.yml` is automatically removed if the script is interrupted before encryption
