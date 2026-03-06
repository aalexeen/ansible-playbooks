# tacacs-ng — Usage Guide

This file describes how to manage your TACACS+ deployment using `tacacs-ng.sh`.

The script is installed to your deployment directory and operates in **installed mode**,
meaning it manages the existing deployment — no source repository needed.

---

## Interactive menu

```bash
./tacacs-ng.sh
```

Launches a numbered menu with all available actions.

---

## Commands

### Run the playbook

```bash
./tacacs-ng.sh run
```

Runs the full deployment: build → config → service → test.

```bash
./tacacs-ng.sh run --tags build        # compile tac_plus-ng from source
./tacacs-ng.sh run --tags config       # deploy config file only
./tacacs-ng.sh run --tags service      # deploy systemd unit, enable, start
./tacacs-ng.sh run --tags test         # TCP check + functional auth test
./tacacs-ng.sh run --tags reload       # SIGHUP (reload config without restart)
./tacacs-ng.sh run --tags cleanup      # remove temporary build directory
./tacacs-ng.sh run --tags config,service   # config + service in one run
```

### Uninstall tac_plus-ng from the target host

```bash
./tacacs-ng.sh run --tags uninstall
```

Stops the service, removes binaries, config, logs, and systemd unit.
Build dependencies are **not** removed by default.

```bash
./tacacs-ng.sh run --tags uninstall -e uninstall_build_deps=true
```

Also removes build packages (build-essential, clang, libpcre2-dev, etc.).

---

## Configuration

### Reconfigure everything (host + users)

```bash
./tacacs-ng.sh configure
```

### Reconfigure target host only

```bash
./tacacs-ng.sh configure-host
```

Prompts for: target IP/hostname, SSH user, SSH port, SSH key, sudo (become), sudo password.

### Reconfigure TACACS+ users only

```bash
./tacacs-ng.sh configure-users
```

Prompts for: TACACS+ shared key, user list (name, role, password), vault password source.
Recreates and re-encrypts `vault.yml`. Previous vault is backed up automatically.

### Change vault encryption password

```bash
./tacacs-ng.sh configure-vault-password
```

Re-encrypts the existing vault with a new password (`ansible-vault rekey`).

---

## Status

```bash
./tacacs-ng.sh status
```

Shows current configuration: target host, SSH settings, vault state, vault password file.

---

## Uninstall the playbook itself

```bash
./tacacs-ng.sh uninstall
```

Removes the entire deployment directory from this machine (not the target host).
To remove tac_plus-ng from the **target host**, use `--tags uninstall` (see above).

---

## TACACS+ roles

| Role | Priv level | Access |
|---|---|---|
| `admin` | 15 | All commands |
| `engineer` | 10 | show, ping, traceroute, interface config, VLAN, STP, write/copy — no reload/delete/erase/debug |
| `readonly` | 15 | show commands only |
| `helpdesk` | 15 | L1/L2 diagnostics: show interfaces/mac/arp/cdp/vlan + ping |

---

## Vault

Secrets (TACACS+ shared key, password hashes, sudo password) are stored in
`roles/tac_plus_ng_deploy/vars/vault.yml`, encrypted with `ansible-vault`.

Manual vault operations:

```bash
# View decrypted contents
ansible-vault view roles/tac_plus_ng_deploy/vars/vault.yml

# Edit in place
ansible-vault edit roles/tac_plus_ng_deploy/vars/vault.yml

# Change encryption password
./tacacs-ng.sh configure-vault-password
```

---

## Files

| Path | Description |
|---|---|
| `tacacs-ng.sh` | Management script |
| `vars.env` | Local config: SSH settings, vault password file path |
| `inventory/tacacs-ng` | Ansible inventory (auto-generated) |
| `playbook/ansible.cfg` | Ansible config (auto-generated) |
| `playbook/deploy-tacacs.yml` | Main playbook |
| `roles/tac_plus_ng_deploy/vars/vault.yml` | Encrypted secrets |
| `roles/tac_plus_ng_deploy/vars/vault.yml.example` | Vault structure example |
