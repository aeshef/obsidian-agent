# Obsidian presentation

Generated dashboards share the presentation in `shared/obsidian_ui`. Styling and labels live in `config/obsidian_ui.{en,ru}.yaml.example`; personal overrides use the corresponding `.yaml` files. Sources and records remain in their existing domain stores.

- Minimal and Style Settings provide the theme and adjustable dashboard width/radius.
- Finance has calendar month/quarter/year filters and a category drilldown. Export uses the spending exclusions and base currency. A gap means unrecorded data, not a verified zero.
- Long planning histories aggregate event counts by week; workload uses the last snapshot per week.
- Bases supplies library cards, a catalog, and project views.
- QuickAdd supplies ideas, materials, project notes, and linking an open note to a project. Meta Bind library buttons call those commands. No task-status or transaction-write buttons are generated.
- Workspaces can retain separate planning, finance, and reading layouts.
- Assistant Dashboards opens generated pages (`assistant-ui: true`) in reading mode after Obsidian restores the tab state. This keeps the first Dataview block rendered and callout clicks out of the editor. Explicit Edit mode remains available; ordinary notes are unaffected.

The dashboard scaffold also refreshes the library and its templates. Domain generators install shared assets into the configured dashboards/data folder. Edit the generators or packaged assets; generated pages are overwritten on refresh. JavaScript views are extracted from generated Markdown into stable files rather than copied into every page.

The existing iCloud mobile export is one way. Its presentation config is explicitly read-only, QuickAdd write commands are omitted, and library capture buttons are hidden on mobile. Capture through the bot or the primary Mac vault. This does not change iPhone Health shortcut automations.

A status report older than the configured age is shown as unknown. Page generation time and measurement freshness are separate. Source-status commands show the last saved report and do not claim to run a synchronization.

Verification covers aggregation semantics, export exclusions, HTML escaping, generated view references, locale scaffolding, and chart catalogs. User data must not be included in fixtures or release archives.

## Interactive exploration

Assistant Dashboards 1.1 bundles Apache ECharts 6.1 locally (Apache-2.0). `plugin-src/` contains the modular sources; run `python scripts/build_obsidian_plugin.py` after edits. Vendor integrity and license information are in `shared/obsidian_ui/vendor/`. No CDN calls or data uploads are made.

To verify that the generated bundle is current without changing files, run `python scripts/build_obsidian_plugin.py --check`. It exits non-zero when `shared/obsidian_ui/plugin/main.js` is missing or stale; rerun the build command above to update it.

Finance, health, task progress, calendar and cross-domain analytics expose shared controls. Each chart can inherit the page range or use its own dates and grain; comparisons use the immediately preceding equal-length interval, aligned by day offset. Event counts and expenses sum, health averages observed daily values, and workload takes the last observed snapshot. Missing observations remain null. Calendar hours split overnight events and exclude cancelled/all-day entries; overlapping appointments remain separate booked hours.

View preferences live in device-local storage, namespaced by vault and dashboard. They are not inserted into generated Markdown or synchronized over iCloud. The mobile mirror receives the bundled plugin and datasets. Fixed reports are linked in a collapsed appendix with an explicit independent-date-range notice; images are not embedded a second time. Table visibility and fullscreen state reset on reopening, while ranges and filters persist. Tables open below the chart without replacing it and paginate locally; clicking a point shows the underlying observations. Current task-goal mapping and fallback priorities are labelled as current metadata rather than historical facts.
