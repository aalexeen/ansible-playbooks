# ansible-playbooks

Collection of Ansible playbooks for infrastructure automation.

## Playbooks

| Playbook | Description |
|---|---|
| [tacacs-ng](tacacs-ng/README.md) | Deploys a TACACS+ authentication server (`tac_plus-ng`) on Ubuntu. Compiles from bundled source — no internet required. Includes interactive installer, Ansible Vault secrets management, and role-based access control. |
| [tacacs-migrate](tacacs-migrate/README.md) | Migrates Cisco IOS / IOS XE switches from local authentication to TACACS+ AAA. Six-phase pipeline with automatic rollback on failure. Supports IOS 12 and IOS XE 16/17, single or dual server. |
