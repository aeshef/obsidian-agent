from pathlib import Path
import json
import shutil
from copy import deepcopy
from shared.obsidian_ui.config import ui_config
from shared.vault_paths_config import folder, vault_file, finance_sub, dashboards_sub
from shared.capabilities.profile import get_capabilities
from shared.vault_layout import knowledge_subdir
from shared.locale import agent_locale
from shared.constants import goals_year


def install_assets(vault: Path):
    config = deepcopy(ui_config())
    root = f"{folder('dashboards')}/{dashboards_sub('data')}/{config['layout']['view_root']}"
    source = Path(__file__).parent / "assets"
    target = vault / root
    target.mkdir(parents=True, exist_ok=True)
    for asset in source.glob("*"):
        if asset.is_file():
            dest = target / asset.name
            body = asset.read_text().replace("Assistant UI/", root+"/").encode()
            if not dest.exists() or dest.read_bytes() != body:
                dest.write_bytes(body)
    dash = folder("dashboards")
    paths = {"main": f"{dash}/{vault_file('main_dashboard_md')}",
             "progress": f"{dash}/{vault_file('progress_year_dashboard_md', year=goals_year())}",
             "finance": f"{dash}/{finance_sub('dashboard_md')}",
             "health": f"{dash}/{vault_file('health_dashboard_md')}",
             "calendar": f"{dash}/{vault_file('calendar_dashboard_md')}",
             "analytics": f"{dash}/{vault_file('analytics_dashboard_md')}",
             "system": f"{dash}/{vault_file('system_hub_md')}",
             "library": f"{dash}/{config['layout']['library_file']}"}
    prof=get_capabilities()
    modules={"finance":prof.module("finance"), "planning":prof.module("planning"), "knowledge":prof.module("knowledge")}
    paths={k:v for k,v in paths.items() if (k!='finance' or modules['finance']) and (k!='library' or modules['knowledge']) and (k not in ('progress','health','analytics','calendar') or modules['planning'])}
    config.update({"locale":agent_locale(),"view_root":root,"paths":paths,"knowledge_folder":knowledge_subdir(),"dashboards_folder":dash})
    config['home_sources'] = {}
    if modules['planning']:
        config['home_sources']['calendar'] = f"{dash}/{dashboards_sub('data')}/{vault_file('calendar_json')}"
    (target/'config.json').write_text(json.dumps(config,ensure_ascii=False),encoding='utf-8')
    snippet=vault/'.obsidian/snippets/assistant-ui.css'
    snippet.parent.mkdir(parents=True,exist_ok=True)
    css=(source/'view.css').read_text()
    if not snippet.exists() or snippet.read_text()!=css:snippet.write_text(css)
    plugin_source=Path(__file__).parent/'plugin'
    plugin_target=vault/'.obsidian/plugins/assistant-dashboard-ux'
    plugin_target.mkdir(parents=True,exist_ok=True)
    for asset in plugin_source.iterdir():
        if asset.is_file():shutil.copy2(asset,plugin_target/asset.name)
    source_status=vault/'.sync/pipeline_health.json'
    if source_status.is_file():
        (target/'status.json').write_bytes(source_status.read_bytes())
    return root
