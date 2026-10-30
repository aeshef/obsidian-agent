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

// Table search filters all supplied rows before pagination and leaves the chart alone.
let chartBuilds=0;
sandbox.echarts.init=()=>({setOption(){chartBuilds++;},on(){},resize(){},dispose(){}});
persisted=JSON.stringify({page:{preset:'custom',from:'2026-09-01',to:'2026-09-04',filters:{}}});
cfg.interactive.table_page_size=2;
const searchContainer=new Element('div');
const searchRows=[
 {date:'2026-09-01',x:'Food',series:'Spend',value:1,description:'First merchant'},
 {date:'2026-09-02',x:'Food',series:'Spend',value:2,description:'Second merchant'},
 {date:'2026-09-03',x:'Food',series:'Spend',value:3,description:'<b>Shop</b>'},
 {date:'2026-09-04',x:'Food',series:'Spend',value:4,description:'Last merchant'},
];
const stopSearch=sandbox.renderInteractive({container:searchContainer,component:{register(){}}},cfg,'search-test',{
 charts:[{id:'merchants',title:'Merchants',type:'categorical',snapshot:'2026-09-04',rows:searchRows}],
});
searchContainer.all('button').find(b=>b.textContent===cfg.labels.show_table).onclick();
const beforeSearch=chartBuilds;
const input=searchContainer.all('input').find(i=>i.attrs['aria-label']===cfg.labels.table_search);
assert.ok(input,'search input must have a localized accessible label');
assert.equal(searchContainer.all('tbody')[0].all('tr').length,2,'first page only');
input.value='LAST';input.oninput();
assert.equal(chartBuilds,beforeSearch,'typing must not rebuild the chart');
assert.equal(searchContainer.all('tbody')[0].all('tr').length,1,'search includes later pages');
assert.ok(searchContainer.all('td').some(e=>e.textContent==='Last merchant'));
assert.equal(searchContainer.all('div').find(e=>e.textContent==='1 of 4 rows')?.textContent,'1 of 4 rows');
input.value='<B>SHOP</B>';input.oninput();
assert.ok(searchContainer.all('td').some(e=>e.textContent==='<b>Shop</b>'),'HTML-like text stays plain text');
assert.equal(searchContainer.all('b').length,0,'cell text must not become markup');
input.value='missing';input.oninput();
assert.equal(searchContainer.all('tbody')[0].all('tr').length,0);
assert.equal(searchContainer.all('div').find(e=>e.textContent===cfg.labels.table_no_matches)?.hidden,false);
input.value='';input.oninput();
assert.equal(searchContainer.all('tbody')[0].all('tr').length,2,'clearing restores first page');
searchContainer.all('button').find(b=>b.textContent===cfg.labels.more).onclick();
assert.equal(searchContainer.all('tbody')[0].all('tr').length,4,'pagination resumes after clearing');
assert.equal(chartBuilds,beforeSearch);
assert.ok(!persisted.includes('LAST')&&!persisted.includes('SHOP'),'query is not persisted');
stopSearch();console.log('Table search: pagination, clearing, plain text and chart isolation passed');
