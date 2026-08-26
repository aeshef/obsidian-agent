# config/agent

В git только `*.example.yaml` и `prompts/*.example.txt` (**только комментарии `#`** у personalized, generic_en — рабочий EN-текст). Локальные `prompts/*.txt` — gitignore.

```bash
../../scripts/setup_agent_config.sh
```

Создаёт при отсутствии: `platform.yaml`, `memory/models/routing/tools.yaml`, `prompts/*.txt`, `user_profile.md`. **`capabilities.yaml`:** `setup_agent_config.sh` копирует starter, если нет `OBSIDIAN_AGENT_FULL_INSTALL=1`; иначе omit = full. Present YAML is fail-closed — [CAPABILITIES.md](../../docs/CAPABILITIES.md).

См. [docs/AGENT_CONFIG.md](../../docs/AGENT_CONFIG.md).

**Профиль:** `user_profile.md.example` — шаблон; реальный `user_profile.md` в gitignore.
