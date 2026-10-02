const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const C=require('../shared/obsidian_ui/plugin-src/core.js');
const cfg=JSON.parse(fs.readFileSync('config/obsidian_ui.en.yaml.example'));
const ru=JSON.parse(fs.readFileSync('config/obsidian_ui.ru.yaml.example'));
cfg.locale='en';
assert.ok(cfg.labels.last7&&ru.labels.last7,'the preset has labels in both locales');

assert.deepEqual(C.range('7','2026-01-01'),['2025-12-26','2026-01-01'],'year boundary');
assert.deepEqual(C.range('7','2026-03-01'),['2026-02-23','2026-03-01'],'month boundary');
assert.deepEqual(C.range('7','2024-03-01'),['2024-02-24','2024-03-01'],'leap-year boundary');
assert.deepEqual(C.comparison([],'2025-12-26','2026-01-01','day','sum',0,'7').period,
 ['2025-12-19','2025-12-25'],'the previous seven days do not overlap');

class Element {
 constructor(tag,opts={}){this.tag=tag;this.textContent=opts.text;this.children=[];}
 createEl(tag,opts){const e=new Element(tag,opts);this.children.push(e);return e;}
 createDiv(opts){return this.createEl('div',opts);}
 setAttribute(){}
 empty(){this.children=[];}
 all(tag){return this.children.flatMap(e=>[...(e.tag===tag?[e]:[]),...e.all(tag)]);}
}
let day='2026-01-01';
let saved=JSON.stringify({
 page:{preset:'custom',from:'2025-12-20',to:'2026-01-01',filters:{}},
 cards:{x:{own:true,from:'2025-12-30',to:'2026-01-01',grain:'day'}},
});
const charts=[{id:'x',title:'Steps',type:'line',method:'sum',rows:[{date:'2025-12-30',value:1,series:'Steps'}]}];
function open(kind='health',data={charts}){
 const core={...C,range:preset=>C.range(preset,day)};
 const sandbox={chartCore:core,Intl,console,app:{vault:{getName:()=> 'Test'}},
  localStorage:{getItem:()=>saved,setItem:(key,value)=>saved=value},
  getComputedStyle:()=>({getPropertyValue:()=> '#000'}),
  ResizeObserver:class{observe(){}disconnect(){}},
  echarts:{init:()=>({setOption(){},on(){},resize(){},dispose(){}})}};
 vm.createContext(sandbox);
 vm.runInContext(fs.readFileSync('shared/obsidian_ui/plugin-src/dashboard.js','utf8'),sandbox);
 const root=new Element('div');
 const close=sandbox.renderInteractive({container:root,component:{register(){}}},cfg,kind,data);
 return {root,close};
}
let view=open();
const period=view.root.all('select')[0];
assert.ok(period.children.some(option=>option.value==='7'&&option.textContent===cfg.labels.last7));
period.value='7';period.onchange();
let state=JSON.parse(saved);
assert.deepEqual([state.page.from,state.page.to],['2025-12-26','2026-01-01']);
assert.equal(state.cards.x.own,true);
assert.deepEqual([state.cards.x.from,state.cards.x.to],['2025-12-30','2026-01-01']);
view.close();

day='2026-01-02';view=open();state=JSON.parse(saved);
assert.deepEqual([state.page.from,state.page.to],['2025-12-27','2026-01-02'],'reopening recalculates a relative preset');
assert.deepEqual([state.cards.x.from,state.cards.x.to],['2025-12-30','2026-01-01'],'chart-specific dates remain fixed');
view.close();

saved=JSON.stringify({page:{preset:'custom',from:'2025-12-20',to:'2026-01-01',filters:{}}});
view=open('health',{charts:[]});state=JSON.parse(saved);
assert.deepEqual([state.page.from,state.page.to],['2025-12-20','2026-01-01'],'custom dates stay fixed');
view.close();

saved='{}';view=open('calendar',{charts:[]});state=JSON.parse(saved);
assert.equal(state.page.preset,'upcoming','calendar retains its existing default');
assert.deepEqual([state.page.from,state.page.to],['2026-01-02','2026-01-15']);
view.close();
console.log('Last 7 days: boundaries, comparison, reopening, custom dates and calendar default passed');
