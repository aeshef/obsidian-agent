#!/bin/zsh
# Одностороннее зеркало vault для Obsidian на iPhone (read-mostly).
# Исключено: 700_, 800_, 600_, 300_Дашборды/Данные/Действия/
#
# По умолчанию — iCloud Obsidian (только телефон; Mac только пишет файлы через rsync):
#   ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault — Mobile
#
# Локальный тест без iCloud:
#   MOBILE_VAULT="$HOME/Documents/Obsidian Vault — Mobile" ./export_mobile_vault.sh
#
# Пример:
#   ./export_mobile_vault.sh
#
# Автозапуск: obsidian_sync.sh шаг 5e (каждый цикл LaunchAgent, ~5 мин).
# Отключить: SKIP_MOBILE_VAULT=1 ~/bin/obsidian_sync.sh

set -euo pipefail

if [[ -n "${0:A}" && -f "${0:A}" ]]; then
  P="$(cd "$(dirname "${0:A}")/../.." && pwd)"
  [[ -d "$P/800_Автоматизация" ]] && SRC="$P"
fi
SRC="${SRC:-/Users/example/Documents/Obsidian Vault}"
MOBILE="${MOBILE_VAULT:-$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault — Mobile}"

RSYNC=(rsync -a --delete --exclude='.DS_Store')

echo "export_mobile_vault: $SRC → $MOBILE"

mkdir -p "$MOBILE"

"${RSYNC[@]}" "$SRC/100_Задачи/" "$MOBILE/100_Задачи/"
"${RSYNC[@]}" "$SRC/200_Цели/" "$MOBILE/200_Цели/"
"${RSYNC[@]}" --exclude='Данные/Действия/' "$SRC/300_Дашборды/" "$MOBILE/300_Дашборды/"
"${RSYNC[@]}" "$SRC/400_Рутины/" "$MOBILE/400_Рутины/"

mkdir -p "$MOBILE/.obsidian/plugins"
for f in app.json appearance.json community-plugins.json core-plugins.json templates.json daily-notes.json; do
  [[ -f "$SRC/.obsidian/$f" ]] && cp "$SRC/.obsidian/$f" "$MOBILE/.obsidian/$f"
done
for p in dataview templater-obsidian obsidian-kanban; do
  [[ -d "$SRC/.obsidian/plugins/$p" ]] && rsync -a "$SRC/.obsidian/plugins/$p/" "$MOBILE/.obsidian/plugins/$p/"
done
[[ -d "$SRC/.obsidian/snippets" ]] && rsync -a "$SRC/.obsidian/snippets/" "$MOBILE/.obsidian/snippets/"

echo "OK: $(du -sh "$MOBILE" | awk '{print $1}') → $MOBILE"
