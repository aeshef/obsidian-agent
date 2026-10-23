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

Finance, health, task progress, calendar and cross-domain analytics expose shared controls. Each chart can inherit the page range or use its own dates and grain; comparisons for the month, quarter, and year presets use the same dates shifted back by one month, quarter, or year (days are clamped to the end of shorter months); other ranges, including a chart's own custom dates, use the immediately preceding interval of equal length, aligned by day offset. Event counts and expenses sum, health averages observed daily values, and workload takes the last observed snapshot. Missing observations remain null. Calendar hours split overnight events and exclude cancelled/all-day entries; overlapping appointments remain separate booked hours.

View preferences live in device-local storage, namespaced by vault and dashboard. They are not inserted into generated Markdown or synchronized over iCloud. The mobile mirror receives the bundled plugin and datasets. On progress and health pages, sections that embed fixed chart images from the dashboards charts folder are removed from the generated page, and no appendix of fixed reports is added. Use the interactive charts and tables instead. The page toolbar sets the page-wide period (preset or custom dates, with Previous and Next shifting by the current range length). Each chart has a Show/Hide table button; tables open below the chart without replacing it and paginate locally, and clicking a point shows the underlying observations. Reset restores the default page range and filters and clears every chart's own settings. Table visibility and fullscreen state reset on reopening, while ranges and filters persist. Current task-goal mapping and fallback priorities are labelled as current metadata rather than historical facts.

## Developer notes

### Where to edit

| Kind | Path | Edit by hand? |
|---|---|---|
| Source | `shared/obsidian_ui/plugin-src/` (`core.js`, `dashboard.js`, `main.js`), `shared/obsidian_ui/layout.py`, `shared/obsidian_ui/reports.py` | Yes |
| Vendored library | `shared/obsidian_ui/vendor/echarts.js` | No |
| Generated bundle | `shared/obsidian_ui/plugin/main.js` | No, rebuild it |
| Generated vault files | Dashboard pages and extracted view files such as `section-<kind>-<n>.js` in the vault | No, overwritten on refresh |

### Tests

Run from the repository root:

    node tests/test_analytics_interactive.cjs
    node tests/test_echarts_heatmap.cjs
    node tests/test_interactive_charts.cjs
    node tests/test_interactive_display.cjs
    node tests/test_period_comparison.cjs
    node tests/test_wip_completion_boundaries.cjs

### Rebuilding the plugin

After editing anything in `plugin-src/`, rebuild the bundle:

    python scripts/build_obsidian_plugin.py

On Windows, run `python -X utf8 scripts/build_obsidian_plugin.py` if you get a decoding error.
