# VPS deploy (24/7 bot)

Telegram bots should run on a small always-on server. Running only on your laptop works for testing, but the bot stops when the computer sleeps.

## Minimum server

| Resource | Recommendation |
|----------|----------------|
| CPU | 1 vCPU |
| RAM | 1 GB (2 GB if knowledge + vision ingest) |
| Disk | 20 GB SSD |
| OS | Ubuntu 22.04 or 24.04 LTS |

Any provider with SSH root access is fine (Hetzner, DigitalOcean, Linode, Vultr, Timeweb, Selectel, etc.). Pick a region close to you.

## 1. Create the VPS

1. Create a VM with Ubuntu LTS.
2. Note the public IPv4 address.
3. Optional: add an SSH key in the provider panel (recommended).

## 2. SSH access (keys only)

On your Mac/Linux **local machine**:

```bash
# if you don't have a key yet
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""

# copy key to the server (replace user and IP)
ssh-copy-id root@YOUR_SERVER_IP

# test — should login without password
ssh root@YOUR_SERVER_IP
```

Optional `~/.ssh/config` entry:

```
Host my-obsidian-agent
  HostName YOUR_SERVER_IP
  User root
  IdentityFile ~/.ssh/id_ed25519
```

Then use `my-obsidian-agent` as `SERVER` in `.env`.

**Never paste root passwords into chat or commit them to git.**

## 3. Configure `.env` locally

In the obsidian-agent repo:

```bash
./scripts/oa-python.sh scripts/setup/env_tools.py set SERVER 'root@YOUR_SERVER_IP'
# or: set SERVER 'my-obsidian-agent'
```

Also set `SERVER_BOTS=/root/bots` and `SERVER_VAULT=/root/obsidian-vault` (defaults in `.env.example`).

## 4. Deploy code

From the repo root on your Mac:

```bash
./scripts/deploy.sh --prod --install-deps
```

This rsyncs the monorepo to the server, patches server `.env` (tokens are **not** overwritten), and restarts `unified_bot`.

Verify on the server:

```bash
ssh root@YOUR_SERVER_IP 'pgrep -af unified_bot'
ssh root@YOUR_SERVER_IP 'tail -20 /root/bots/logs/unified_bot.log'
```

## 5. Sync Obsidian vault (optional)

If the bot reads/writes your vault on the server:

```bash
./scripts/install_mac_sync.sh   # LaunchAgent: Mac ↔ VPS
./scripts/obsidian_sync.sh      # manual run
```

See `docs/SETUP.md` § Mac ↔ VPS sync.

## 6. After deploy

- Telegram → `/start` on the **same** bot token
- Test one message (expense, task, etc.)
- Local bot: stop `./scripts/run_unified_bot.sh` if you only want the server instance

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `Permission denied (publickey)` | Run `ssh-copy-id`, check `SERVER` user@host |
| `deploy.sh: SERVER not set` | `env_tools.py set SERVER ...` |
| Bot works locally, not on VPS | Check `unified_bot.log`, `VAULT_PATH` on server `.env` |
| Vault empty on server | Run `obsidian_sync.sh` or set `SERVER_VAULT` |

More: `docs/SETUP.md` §7.
