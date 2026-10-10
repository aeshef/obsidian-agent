const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const C=require('../shared/obsidian_ui/plugin-src/core.js');
const cfg=JSON.parse(fs.readFileSync('config/obsidian_ui.en.yaml.example'));cfg.locale='en';

let result=C.coverage([
 {date:'2026-09-01',value:0},
 {date:'2026-09-01',value:12},
 {date:'2026-09-02',value:null},
 {date:'2026-09-03',value:5},
 {date:'2026-09-04',value:NaN},
], '2026-09-01','2026-09-04');
assert.deepEqual(result,{observed:2,total:4},'zero counts, duplicate dates do not, and null/non-finite values do not');
assert.deepEqual(C.coverage([], '2026-09-01','2026-09-07'),{observed:0,total:7});
assert.deepEqual(C.coverage([], '2026-09-07','2026-09-01'),{observed:0,total:0},'invalid ranges have no denominator');

class Element {
 constructor(tag,opts={}){this.tag=tag;this.textContent=opts.text;this.children=[];this.attrs={};}
 createEl(tag,opts){const child=new Element(tag,opts);this.children.push(child);return child;}
 createDiv(opts){return this.createEl('div',opts);}
 setAttribute(key,value){this.attrs[key]=value;}
 empty(){this.children=[];}
 all(tag){return this.children.flatMap(child=>[...(child.tag===tag?[child]:[]),...child.all(tag)]);}
}
let saved=JSON.stringify({
 page:{preset:'custom',from:'2026-09-01',to:'2026-09-07',filters:{}},
 cards:{weight:{own:true,from:'2026-09-02',to:'2026-09-04',grain:'day'}},
});
const sandbox={chartCore:C,Intl,console,app:{vault:{getName:()=> 'Coverage Test'}},
 localStorage:{getItem:()=>saved,setItem:(key,value)=>saved=value},
 getComputedStyle:()=>({getPropertyValue:()=> '#000'}),
 ResizeObserver:class{observe(){}disconnect(){}},
 echarts:{init:()=>({setOption(){},on(){},resize(){},dispose(){}})}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync('shared/obsidian_ui/plugin-src/dashboard.js','utf8'),sandbox);

const root=new Element('div');
const rows=[
 {date:'2026-09-02',value:0,series:'Weight'},
 {date:'2026-09-02',value:1,series:'Weight'},
 {date:'2026-09-03',value:null,series:'Weight'},
 {date:'2026-09-04',value:2,series:'Weight'},
 {date:'2026-09-05',value:3,series:'Weight'},
];
const close=sandbox.renderInteractive({container:root,component:{register(){}}},cfg,'health',{
 charts:[{id:'weight',title:'Weight',type:'line',method:'mean',rows}],
});
assert.ok(root.all('div').some(element=>element.textContent==='Observed: Weight: 2 of 3 days'),
 'coverage uses the chart-specific inclusive date range');
assert.ok(root.all('div').some(element=>element.textContent===cfg.labels.coverage_note));
assert.equal(JSON.parse(saved).cards.weight.own,true);
close();
console.log('Health coverage: duplicates, zero, null, empty and chart-specific ranges passed');
