const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const core=require('../shared/obsidian_ui/plugin-src/core.js');
const cfg=JSON.parse(fs.readFileSync('config/obsidian_ui.en.yaml.example'));cfg.locale='en';

class Element {
 constructor(tag,opts={}){this.tag=tag;this.textContent=opts.text;this.children=[];this.attrs={};}
 createEl(tag,opts){const child=new Element(tag,opts);this.children.push(child);return child;}
 createDiv(opts){return this.createEl('div',opts);}
 setAttribute(key,value){this.attrs[key]=value;}
 empty(){this.children=[];}
 all(tag){return this.children.flatMap(child=>[...(child.tag===tag?[child]:[]),...child.all(tag)]);}
}

const storage=new Map();
const sandbox={chartCore:core,Intl,console,app:{vault:{getName:()=> 'Favorite Test'}},
 localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)},
 getComputedStyle:()=>({getPropertyValue:()=> '#000'}),
 ResizeObserver:class{observe(){}disconnect(){}},
 echarts:{init:()=>({setOption(){},on(){},resize(){},dispose(){}})}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync('shared/obsidian_ui/plugin-src/dashboard.js','utf8'),sandbox);

const row={date:'2026-09-01',value:1,series:'Series'};
const data={charts:[
 {id:'a',title:'Alpha',type:'line',method:'sum',rows:[row]},
 {id:'b',title:'Beta',type:'line',method:'sum',rows:[row]},
 {id:'c',title:'Gamma',type:'line',method:'sum',rows:[row]},
]};
function open(kind='health',source=data){
 const root=new Element('div');
 const close=sandbox.renderInteractive({container:root,component:{register(){}}},cfg,kind,source);
 return {root,close};
}
const titles=root=>root.all('section').map(section=>section.all('h3')[0]?.textContent);
const section=(root,title)=>root.all('section').find(card=>card.all('h3')[0]?.textContent===title);
const pin=(root,title)=>section(root,title).all('button').find(button=>
 button.textContent===cfg.labels.pin_chart||button.textContent===cfg.labels.unpin_chart);

let view=open();
pin(view.root,'Beta').onclick();
pin(view.root,'Gamma').onclick();
assert.deepEqual(titles(view.root),['Beta','Gamma','Alpha'],'pinned charts keep their original relative order');
let saved=JSON.parse(storage.get('assistant.charts.v1:Favorite Test:health'));
assert.deepEqual(saved.pins,['b','c'],'preferences contain stable chart IDs');
assert.equal(pin(view.root,'Beta').attrs['aria-pressed'],'true');

const favoritesLabel=view.root.all('label').find(label=>label.children.some(child=>child.textContent===cfg.labels.favorites_only));
const favoritesInput=favoritesLabel.children.find(child=>child.tag==='input');
favoritesInput.checked=true;favoritesInput.onchange();
assert.deepEqual(titles(view.root),['Beta','Gamma']);
pin(view.root,'Beta').onclick();
assert.deepEqual(titles(view.root),['Gamma'],'unpinning removes the chart from favorites-only view');
view.close();

view=open();
assert.deepEqual(titles(view.root),['Gamma'],'favorites persist when reopening the same dashboard');
saved=JSON.parse(storage.get('assistant.charts.v1:Favorite Test:health'));
assert.deepEqual(saved.pins,['c']);
const picker=view.root.all('select').find(select=>select.attrs['aria-label']===cfg.labels.chart_picker);
picker.value='a';picker.onchange();
assert.deepEqual(titles(view.root),[],'chart picker restricts the set before favorites');
const showAll=view.root.all('button').find(button=>button.textContent===cfg.labels.show_all_charts);
assert.ok(showAll,'empty favorites view offers a recovery action');showAll.onclick();
assert.deepEqual(titles(view.root),['Alpha']);
view.close();

const other=open('analytics');
assert.deepEqual(titles(other.root),['Alpha','Beta','Gamma'],'favorites are isolated between dashboards');
other.close();

storage.set('assistant.charts.v1:Favorite Test:health',JSON.stringify({pins:['gone','c']}));
const withoutGamma=open('health',{charts:data.charts.slice(0,2)});
saved=JSON.parse(storage.get('assistant.charts.v1:Favorite Test:health'));
assert.deepEqual(saved.pins,[],'obsolete chart IDs are removed');
withoutGamma.close();
console.log('Chart favorites: ordering, persistence, picker interaction, cleanup and dashboard isolation passed');
