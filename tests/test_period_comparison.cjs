const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const C=require('../shared/obsidian_ui/plugin-src/core.js');
let q=C.comparison([{date:'2026-08-01',value:2},{date:'2026-08-28',value:4},{date:'2026-08-29',value:100}],'2026-09-01','2026-09-28','month','sum',0,'month');
assert.deepEqual(q.period,['2026-08-01','2026-08-28']);assert.equal(q.points[0].value,6);
assert.deepEqual(C.comparison([],'2026-07-01','2026-09-28','day','sum',0,'quarter').period,['2026-04-01','2026-06-28']);
assert.deepEqual(C.comparison([],'2026-01-01','2026-09-28','day','sum',0,'year').period,['2025-01-01','2025-09-28']);
assert.deepEqual(C.comparison([],'2026-09-10','2026-09-12','day').period,['2026-09-07','2026-09-09']);
q=C.comparison([{date:'2026-09-05',value:10},{date:'2026-09-06',value:20},{date:'2026-09-07',value:30}],'2026-09-10','2026-09-12','day','mean',3);
assert.equal(q.points[0].value,20,'rolling lookback must include observations before the previous interval');
assert.equal(q.rows[0].sourceValue,30,'drilldown must retain the raw observation');
assert.equal(q.points[0].sourceFrom,'2026-09-07');
q=C.comparison([{date:'2026-02-28',value:4}],'2026-03-01','2026-03-31','day','sum',0,'month');
assert.equal(q.points[27].value,4);assert.equal(q.points[28].value,null,'short prior month must not fabricate observations');
const cfg=JSON.parse(fs.readFileSync('config/obsidian_ui.en.yaml.example'));cfg.locale='en';
class E{constructor(tag,o={}){this.tag=tag;this.textContent=o.text;this.children=[];}createEl(t,o){const e=new E(t,o);this.children.push(e);return e;}createDiv(o){return this.createEl('div',o);}setAttribute(){}empty(){this.children=[];}all(t){return this.children.flatMap(e=>[...(e.tag===t?[e]:[]),...e.all(t)]);}}
function render(rows,{compare=false,preset='month',grain='month'}={}){
 let saved=JSON.stringify({page:{preset,from:'2026-09-01',to:'2026-09-28',filters:{}},cards:{x:{compare,grain}}}),option,click;
 const core={...C,range:()=>['2026-09-01','2026-09-28']};
 const sandbox={chartCore:core,Intl,console,app:{vault:{getName:()=> 'test'}},localStorage:{getItem:()=>saved,setItem:(k,v)=>saved=v},getComputedStyle:()=>({getPropertyValue:()=> '#000'}),ResizeObserver:class{observe(){}disconnect(){}},echarts:{init:()=>({setOption:o=>option=o,on:(n,f)=>click=f,resize(){},dispose(){}})}};
 vm.createContext(sandbox);vm.runInContext(fs.readFileSync('shared/obsidian_ui/plugin-src/dashboard.js','utf8'),sandbox);
 const root=new E('div');sandbox.renderInteractive({container:root,component:{register(){}}},cfg,'test',{charts:[{id:'x',title:'x',type:'bar',method:'sum',rows}]});
 return {root,option:()=>option,click:e=>click(e),toggle:()=>{const label=root.all('label').find(l=>l.children.some(c=>c.textContent===cfg.labels.compare));const box=label.children.find(c=>c.tag==='input');box.checked=true;box.onchange();}};
}
const row=(date,value)=>({date,value,series:'a',description:date});
let view=render([row('2026-08-03',8),row('2026-09-03',3)]);
view.toggle();let option=view.option();assert.equal(option.series.length,2);assert.equal(option.series[1].data[0],8);assert.equal(option.series[1].type,'bar');assert.equal(option.series[1].stack,'previous');
view.click({name:'2026-09-01',seriesIndex:1});assert.ok(view.root.all('td').some(e=>e.textContent==='2026-08-03'),'previous chart click must show previous records');assert.ok(!view.root.all('td').some(e=>e.textContent==='2026-09-03'));
assert.match(option.tooltip.formatter([{seriesIndex:1,dataIndex:0,seriesName:'a',value:8}]),/2026-08-03/);
view=render([row('2026-08-03',8)],{compare:true});assert.ok(view.option(),'previous data must remain visible when current interval is empty');assert.equal(view.option().series[1].data[0],8);
view=render([row('2026-09-03',3)],{compare:true});assert.ok(view.root.all('div').some(e=>e.textContent===cfg.labels.compare_missing));
console.log('Period comparison: calendar, equal ranges, rolling, month gaps, checkbox, chart, drilldown and empty intervals passed');
