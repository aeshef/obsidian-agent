const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const core=require('../shared/obsidian_ui/plugin-src/core.js'),cfg=JSON.parse(fs.readFileSync('config/obsidian_ui.en.yaml.example'));cfg.locale='en';
class E{constructor(tag,o={}){this.tag=tag;this.textContent=o.text;this.children=[];}createEl(t,o){const e=new E(t,o);this.children.push(e);return e;}createDiv(o){return this.createEl('div',o);}setAttribute(){}empty(){this.children=[];}all(t){return this.children.flatMap(e=>[...(e.tag===t?[e]:[]),...e.all(t)]);}}
let persisted=JSON.stringify({page:{preset:'custom',from:'2026-09-01',to:'2026-09-10',filters:{}}}),plots=[];
const sandbox={chartCore:core,Intl,console,app:{vault:{getName:()=> 'Test'}},localStorage:{getItem:()=>persisted,setItem:(k,v)=>persisted=v},getComputedStyle:()=>({getPropertyValue:()=> '#000'}),ResizeObserver:class{observe(){}disconnect(){}},echarts:{init:()=>({setOption(o){plots.push(o);},on(){},resize(){},dispose(){}})}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync('shared/obsidian_ui/plugin-src/dashboard.js','utf8'),sandbox);
const rows=Array.from({length:10},(_,i)=>({date:'2026-09-'+String(i+1).padStart(2,'0'),a:i,b:i*2}));
const data={charts:['correlation','scatter','normalized'].map(type=>({id:type,title:type,type,method:'mean',rows,metrics:['a','b'],min_pairs:3}))};
const container=new E('div');sandbox.renderInteractive({container,component:{register(){}}},cfg,'analytics',data);
assert.equal(plots.length,3);assert.equal(plots[0].series[0].type,'heatmap');assert.equal(plots[1].series[0].data.length,10);assert.equal(plots[2].series.length,2);
const from=container.all('input').find(e=>e.type==='date');from.value='2026-09-08';from.onchange();plots=[];container.all('button').find(e=>e.textContent===cfg.labels.apply).onclick();
assert.equal(plots[1].series[0].data.length,3);assert.equal(plots[0].series[0].data[0][3],3);
console.log('Analytics UI: matrix, scatter, normalization and period changes passed');
