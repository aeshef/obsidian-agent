const cfg=JSON.parse(await dv.io.load('Assistant UI/config.json'));
const H=cfg.home,L=H.labels,limit=H.list_limit,root=dv.container.createDiv({cls:'au-home'});
const today=dv.date('today').toISODate(),week=dv.date('today').minus({days:H.week_days-1}).toISODate();
const load=async path=>{try{return JSON.parse(await dv.io.load(path));}catch{return null;}};
const [progress,health,finance,calendar]=await Promise.all([
 cfg.paths.progress?load('Assistant UI/progress.json'):null,
 cfg.paths.health?load('Assistant UI/health.json'):null,
 cfg.paths.finance?load('Assistant UI/finance.json'):null,
 cfg.home_sources.calendar?load(cfg.home_sources.calendar):null]);
const rows=id=>progress?.charts?.find(c=>c.id===id)?.rows||[];
const create=(p,tag,text,cls)=>p.createEl(tag,{text,cls});
function link(p,path,label=L.more){if(!path)return;const a=create(p,'a',label,'au-home-link');a.href=path;a.onclick=e=>{e.preventDefault();app.workspace.openLinkText(path,'');};}
function section(p,title,path){const box=create(p,'section',null,'au-home-panel'),head=create(box,'div',null,'au-home-head');create(head,'h2',title);link(head,path);return box;}
function metric(p,title,value,path){const box=create(p,'div',null,'au-metric');create(box,'div',title,'au-label');create(box,'div',String(value),'au-value');if(path)link(box,path);}
function item(p,title,meta,urgent=false){const box=create(p,'div',null,'au-home-item'+(urgent?' is-urgent':''));create(box,'div',meta,'au-muted');create(box,'div',title);return box;}
if(cfg.paths.progress){
 const heading=create(root,'div',null,'au-home-head');create(heading,'h2',L.overview);link(heading,cfg.paths.progress);
 const open=rows('deadline_horizon'),grid=create(root,'div',null,'au-grid');
 metric(grid,L.open,progress?open.length:'—');
 metric(grid,L.active,progress?open.filter(r=>r.in_work).length:'—');
 metric(grid,L.blocked,progress?open.filter(r=>r.blocked).length:'—');
 metric(grid,L.done,progress?rows('tasks_completed').filter(r=>r.date>=week&&r.date<=today).length:'—');
 const columns=create(root,'div',null,'au-home-columns');
 const attention=section(columns,L.attention,cfg.paths.progress);
 const upcoming=dv.date('today').plus({days:H.week_days}).toISODate();
 const deadlines=rows('deadline_dates').filter(r=>r.date<=upcoming).sort((a,b)=>a.date.localeCompare(b.date));
 for(const row of deadlines.slice(0,limit))item(attention,row.description,row.date+' · '+(row.date<today?L.overdue:row.date===today?L.today:L.upcoming),row.date<today);
 if(!deadlines.length)create(attention,'p',progress?L.no_deadlines:L.no_data,'au-muted');
 const meetings=section(columns,L.meetings,cfg.paths.calendar);
 const now=dv.date('now').toFormat('HH:mm');
 const events=(calendar?.events||[]).filter(e=>!e.is_cancelled&&!e.is_allday&&e.date>=today&&(e.date>today||String(e.end||'')>now)).sort((a,b)=>(a.date+' '+a.start).localeCompare(b.date+' '+b.start));
 for(const e of events.slice(0,limit))item(meetings,e.title,e.date+' · '+e.start+'–'+e.end);
 if(!events.length)create(meetings,'p',calendar?L.no_meetings:L.no_data,'au-muted');
 const focus=section(root,L.focus,input?.goals),quarter='Q'+Math.ceil(dv.date('today').month/3);
 const goalsPage=dv.page(input?.goals||'');
 const goals=Array.from(goalsPage?.file?.tasks||[]).filter(t=>(t.text||'').includes('#'+input.focusTag+'/'+quarter));
 if(goals.length){
  const done=goals.filter(t=>t.completed).length;
  create(focus,'div',quarter+' · '+done+'/'+goals.length+' '+L.goals_done,'au-muted');
  const bar=create(focus,'progress',null,'au-home-progress');bar.max=goals.length;bar.value=done;
  const list=create(focus,'div',null,'au-home-goals');
  for(const t of goals.filter(t=>!t.completed).slice(0,limit))item(list,t.text.split('\n')[0].replace(/#[^\s]+/g,'').trim(),quarter);
 }else create(focus,'p',L.no_focus,'au-muted');
}
const sources=section(root,L.freshness,cfg.paths.system),sourceGrid=create(sources,'div',null,'au-home-columns');
if(cfg.paths.health){
 const dates=(health?.charts||[]).filter(c=>['steps','exercise_min','iphone_sleep_hours'].includes(c.id)).flatMap(c=>(c.rows||[]).map(r=>r.date)).sort();
 const last=dates.at(-1),age=last?dv.date(today).diff(dv.date(last),'days').days:Infinity;
 const box=item(sourceGrid,age>=H.fresh_days?L.health_waiting:L.health_ok,L.health,age>=H.fresh_days);
 create(box,'div',last?L.last_day+': '+last:L.no_health,'au-muted');
 link(box,cfg.paths.health);
}
for(const [name,data,path,day] of [[cfg.labels.progress,progress,cfg.paths.progress,progress?.generated_at],[cfg.labels.finance,finance,cfg.paths.finance,finance?.generated_at],[cfg.labels.calendar,calendar,cfg.paths.calendar,calendar?.meta?.source_captured_at||calendar?.meta?.last_updated]]){
 if(!path)continue;const date=day?dv.date(String(day).replace(' ','T')):null;const age=date?.isValid?dv.date('now').diff(date,'days').days:Infinity;const box=item(sourceGrid,name,L.snapshot+': '+(date?.isValid?date.toFormat('dd.MM.yyyy HH:mm'):L.no_data),age>=H.fresh_days);link(box,path);
}
