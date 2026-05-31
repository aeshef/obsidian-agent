# config/agent

В git только `*.example.yaml` и `prompts/*.example.txt` (**только комментарии `#`** у personalized, generic_en — рабочий EN-текст). Локальные `prompts/*.txt` — gitignore.

```bash
../../scripts/setup_agent_config.sh
```

Создаёт при отсутствии: `platform.yaml`, `memory/models/routing/tools.yaml`, `prompts/*.txt`, `user_profile.md`. **`capabilities.yaml` не создаёт** — см. [CAPABILITIES.md](../../docs/CAPABILITIES.md) (`apply_capabilities_profile.py --write` или omit file = full product).

См. [docs/AGENT_CONFIG.md](../../docs/AGENT_CONFIG.md).

**Профиль:** `user_profile.md.example` — шаблон; реальный `user_profile.md` в gitignore.
