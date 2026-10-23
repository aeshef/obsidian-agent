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

Assistant Dashboards 1.1 bundles Apache ECharts 6.1 locally (Apache-2.0). `shared/obsidian_ui/plugin-src/` contains the modular sources; run `python scripts/build_obsidian_plugin.py` after edits. Vendor integrity and license information are in `shared/obsidian_ui/vendor/`. No CDN calls or data uploads are made.

Finance, health, task progress, calendar and cross-domain analytics expose shared controls. The page Period selector, custom From/To fields, Previous/Next buttons, and page filters set the default date range and rows for its charts. A chart's Period control can inherit that range or use its own From/To dates; its Grain control selects the bucket size independently. A chart's own dates and grain do not change the page range or another chart. Reset restores the page defaults and clears chart preferences. Comparisons use the immediately preceding equal-length interval, aligned by day offset. Event counts and expenses sum, health averages observed daily values, and workload takes the last observed snapshot. Missing observations remain null. Calendar hours split overnight events and exclude cancelled/all-day entries; overlapping appointments remain separate booked hours.

View preferences live in device-local storage, namespaced by vault and dashboard. They are not inserted into generated Markdown or synchronized over iCloud. The mobile mirror receives the bundled plugin and datasets. On health and progress pages, fixed-report blocks that reference the configured charts folder are removed from the generated page; there is no collapsed export appendix. Other pages can retain their existing images. Table visibility and expanded chart state reset on reopening, while page ranges, filters, and chart settings persist. Show table opens a paginated detail table below its chart without replacing the chart; Hide table closes it. Clicking a chart point opens its underlying observations. Current task-goal mapping and fallback priorities are labelled as current metadata rather than historical facts.

### Developer checks

- Edit `shared/obsidian_ui/plugin-src/*.js` for interactive behavior and `config/obsidian_ui.{en,ru}.yaml.example` for labels. `shared/obsidian_ui/plugin/main.js` is a generated bundle; rebuild it after source edits with `python scripts/build_obsidian_plugin.py` and inspect the diff.
- Run `node tests/test_interactive_display.cjs`, `node tests/test_period_comparison.cjs`, `node tests/test_interactive_charts.cjs`, and `node tests/test_echarts_heatmap.cjs` from the repository root. For the Python layout check, set `AGENT_LOCALE=ru` (the fixture uses an RU vault path), then run `pytest tests/test_dashboard_report_layout.py -q`.
- Dashboard Markdown, extracted Dataview view files, and datasets in the vault are generated by the dashboard/scaffold code. Edit their source generators and packaged assets in this repository; a refresh overwrites generated vault files.
