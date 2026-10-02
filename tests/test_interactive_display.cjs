const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const core=require('../shared/obsidian_ui/plugin-src/core.js');
const cfg=JSON.parse(fs.readFileSync('config/obsidian_ui.en.yaml.example'));cfg.locale='en';
class Element {
 constructor(tag,opts={}){this.tag=tag;this.textContent=opts.text;this.children=[];this.attrs={};}
 createEl(tag,opts){const e=new Element(tag,opts);this.children.push(e);return e;}
 createDiv(opts){return this.createEl('div',opts);}
 setAttribute(k,v){this.attrs[k]=v;}
 empty(){this.children=[];}
 all(tag){return this.children.flatMap(e=>[...(e.tag===tag?[e]:[]),...e.all(tag)]);}
}
let persisted=JSON.stringify({page:{preset:'custom',from:'2026-09-01',to:'2026-09-03',filters:{}},cards:{expense:{table:true,grain:'day'}}});
let active=0;
const sandbox={chartCore:core,Intl,console,app:{vault:{getName:()=> 'Test'}},localStorage:{getItem:()=>persisted,setItem:(k,v)=>persisted=v},getComputedStyle:()=>({getPropertyValue:()=> '#000'}),ResizeObserver:class{observe(){}disconnect(){}},echarts:{init:()=>{active++;return {setOption(){},on(){},resize(){},dispose(){active--;}}}}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync('shared/obsidian_ui/plugin-src/dashboard.js','utf8'),sandbox);
const container=new Element('div'),dv={container,component:{register(){}}};
const data={charts:[{id:'expense',title:'Expense',type:'bar',method:'sum',rows:[{date:'2026-09-01',value:10,series:'Food'}]}]};
const close=sandbox.renderInteractive(dv,cfg,'test',data);
assert.equal(active,1,'old persisted table state must not hide the chart');
assert.equal(container.all('table').length,0);
container.all('button').find(b=>b.textContent===cfg.labels.show_table).onclick();
assert.equal(active,1,'opening a table must keep the chart');
assert.equal(container.all('table').length,1);
container.all('button').find(b=>b.textContent===cfg.labels.hide_table).onclick();
assert.equal(active,1);assert.equal(container.all('table').length,0);
assert.equal(JSON.parse(persisted).cards.expense.grain,'day');
close();assert.equal(active,0,'chart listeners must be disposed');
console.log('Display regression: persisted table, table toggle and cleanup passed');
let deadlineOption,deadlineClick;
sandbox.echarts.init=()=>({setOption(o){deadlineOption=o;},on(_,fn){deadlineClick=fn;},resize(){},dispose(){}});
const deadlineContainer=new Element('div');
const stop=sandbox.renderInteractive({container:deadlineContainer,component:{register(){}}},cfg,'progress',{charts:[{id:'deadline_dates',title:'Deadlines',type:'categorical',horizontal:true,snapshot:'2026-09-03',filter_fields:['category'],rows:[{date:'2026-10-01',x:'2026-10-01',series:'Later',value:1,category:'Work',description:'Future task'}]}]});
assert.equal(deadlineOption.yAxis.inverse,true);
assert.equal(deadlineOption.yAxis.data[0],'2026-10-01','snapshot includes future deadlines outside past page range');
assert.equal(deadlineOption.xAxis.minInterval,1);
deadlineClick({name:'2026-10-01'});
assert.ok(deadlineContainer.all('td').some(e=>e.textContent==='Future task'));
stop();console.log('Deadline snapshot: future dates, horizontal axis and task drilldown passed');

persisted=JSON.stringify({page:{preset:'custom',from:'2026-09-01',to:'2026-09-03',filters:{}},cards:{chart_A:{grain:'week',compare:true},chart_B:{grain:'month'}}});
const multiContainer=new Element('div');
const stopMulti=sandbox.renderInteractive({container:multiContainer,component:{register(){}}},cfg,'test',{charts:[{id:'chart_A',title:'A',type:'bar',method:'sum',rows:[]},{id:'chart_B',title:'B',type:'bar',method:'sum',rows:[]}]});
assert.equal(JSON.parse(persisted).cards.chart_A.grain,'week');
assert.equal(JSON.parse(persisted).cards.chart_B.grain,'month');

let sectionA=multiContainer.all('section').find(s=>s.all('h3').some(h=>h.textContent==='A'));
assert.equal(sectionA.all('select').find(s=>s.attrs['aria-label']===cfg.labels.grain).value, 'week');
assert.equal(sectionA.all('input').find(i=>i.type==='checkbox').checked, true);

const resetBtnA=sectionA.all('button').find(b=>b.textContent===cfg.labels.reset_chart);
assert.ok(resetBtnA, 'Reset button should exist');
resetBtnA.onclick();

assert.equal(JSON.parse(persisted).cards.chart_A, undefined);
assert.equal(JSON.parse(persisted).cards.chart_B.grain,'month');

// Verify DOM was rebuilt with defaults
sectionA=multiContainer.all('section').find(s=>s.all('h3').some(h=>h.textContent==='A'));
assert.equal(sectionA.all('select').find(s=>s.attrs['aria-label']===cfg.labels.grain).value, 'auto');
assert.equal(sectionA.all('input').find(i=>i.type==='checkbox').checked, false);

stopMulti();
console.log('Chart reset: isolated card reset and persistence passed');
