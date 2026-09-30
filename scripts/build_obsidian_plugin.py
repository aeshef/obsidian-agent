"""Bundle local chart code for desktop and mobile (no Node APIs at runtime)."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'shared/obsidian_ui'
def module(path):
 return '(function(){const module={exports:{}};const exports=module.exports;\n'+path.read_text()+'\nreturn module.exports;})()'
parts=['const echarts='+module(root/'vendor/echarts.js')+';', 'const chartCore='+module(root/'plugin-src/core.js')+';', (root/'plugin-src/dashboard.js').read_text(), (root/'plugin-src/main.js').read_text()]
(root/'plugin/main.js').write_text('\n'.join(parts))
