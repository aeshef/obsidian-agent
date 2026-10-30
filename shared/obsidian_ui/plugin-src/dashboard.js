function renderInteractive(dv,cfg,kind,data){
 const C=chartCore,L=cfg.labels,root=dv.container.createDiv({cls:'au-explorer'}),cleanups=[];
 const storageKey='assistant.charts.v1:'+app.vault.getName()+':'+kind;
 let saved={};try{saved=JSON.parse(localStorage.getItem(storageKey)||'{}');}catch{}
 // Display-only controls must not reopen a dashboard in a previous QA/table state.
 for(const card of Object.values(saved.cards||{})){delete card.table;delete card.expanded;}
 const save=()=>{try{localStorage.setItem(storageKey,JSON.stringify(saved));}catch{}};
 const initial=()=>({preset:kind==='calendar'?'upcoming':String(cfg.interactive.default_days),from:C.range(kind==='calendar'?'upcoming':cfg.interactive.default_days)[0],to:C.range(kind==='calendar'?'upcoming':cfg.interactive.default_days)[1],filters:{}});
 let state=Object.assign(initial(),saved.page||{});state.filters||={};saved.page=state;saved.cards||={};
 // Relative presets follow today when reopening. Explicit ranges remain fixed.
 if(state.preset!=='custom')[state.from,state.to]=C.range(state.preset);
 const fmt=v=>v===null||v===undefined?'—':new Intl.NumberFormat(cfg.locale,{maximumFractionDigits:2}).format(v);
 const el=(p,tag,text,cls)=>p.createEl(tag,{text,cls});
 const btn=(p,text,fn)=>{const b=el(p,'button',text);b.type='button';b.onclick=fn;return b;};
 function select(p,label,options,value,fn){const wrap=el(p,'label',null,'au-control');el(wrap,'span',label);const s=el(wrap,'select');s.setAttribute('aria-label',label);for(const [v,t] of options){const o=el(s,'option',t);o.value=v;}s.value=value;s.onchange=()=>fn(s.value);return s;}
 function dateInput(p,label,value,fn){const wrap=el(p,'label',null,'au-control');el(wrap,'span',label);const d=el(wrap,'input');d.type='date';d.value=value;d.setAttribute('aria-label',label);d.onchange=()=>fn(d.value);return d;}
 function check(p,label,value,fn){const w=el(p,'label',null,'au-check'),i=el(w,'input');i.type='checkbox';i.checked=!!value;el(w,'span',label);i.onchange=()=>fn(i.checked);}
 function legal(from,to){return C.valid(from)&&C.valid(to)&&from<=to&&(Date.parse(to)-Date.parse(from))/86400000<=cfg.interactive.max_range_days;}
 function clear(){for(const cleanup of cleanups.splice(0))cleanup();}
 if(dv.component?.register)dv.component.register(clear);
 else {const obs=new MutationObserver(()=>{if(!root.isConnected){clear();obs.disconnect();}});obs.observe(document.body,{childList:true,subtree:true});}
 const palette=cfg.chart.series_palette;
 // Stable color assignment over the full dataset, independent of active filters.
 const totals={};for(const c of data.charts||[])for(const r of c.rows)totals[r.series]=(totals[r.series]||0)+Math.abs(r.value||0);
 const names=Object.keys(totals).sort((a,b)=>totals[b]-totals[a]||a.localeCompare(b));
 names.unshift(L.other);
 const color=n=>palette[Math.max(0,names.indexOf(n))%palette.length];
 function table(parent,headers,rows){
  const search=el(parent,'label',null,'au-control');el(search,'span',L.table_search);
  const input=el(search,'input');input.type='search';input.value='';input.setAttribute('aria-label',L.table_search);
  const count=el(parent,'div',null,'au-muted'),empty=el(parent,'div',L.table_no_matches,'au-muted');
  const wrap=el(parent,'div',null,'au-table-wrap'),t=el(wrap,'table',null,'au-table'),head=el(el(t,'thead'),'tr');
  headers.forEach(x=>el(head,'th',x));const body=el(t,'tbody');let matched=rows,offset=0;
  const more=btn(parent,L.more,append);
  function append(){
   for(const row of matched.slice(offset,offset+cfg.interactive.table_page_size)){
    const tr=el(body,'tr');row.slice(0,headers.length).forEach(x=>el(tr,'td',String(x??'—')));
   }
   offset+=cfg.interactive.table_page_size;more.hidden=offset>=matched.length;
  }
  function update(){
   const query=input.value.trim().toLocaleLowerCase(cfg.locale);
   matched=query?rows.filter(row=>row.slice(0,headers.length).some(value=>String(value??'').toLocaleLowerCase(cfg.locale).includes(query))):rows;
   count.textContent=L.table_match_count.replace('{matched}',matched.length).replace('{total}',rows.length);
   empty.hidden=matched.length!==0;body.empty();offset=0;append();
  }
  input.oninput=update;update();
 }
 function chart(parent,option,onClick){const host=el(parent,'div',null,'au-echart');const instance=echarts.init(host,null,{renderer:'svg'});const style=getComputedStyle(root);instance.setOption({animation:false,color:palette,backgroundColor:'transparent',textStyle:{color:style.getPropertyValue('--text-normal').trim()},...option});const ro=new ResizeObserver(()=>instance.resize());ro.observe(host);if(onClick)instance.on('click',onClick);cleanups.push(()=>{ro.disconnect();instance.dispose();});return instance;}
 function filter(rows,fields){return rows.filter(r=>Object.entries(state.filters).every(([f,v])=>!v||(fields&&!fields.includes(f))||(Array.isArray(r[f])?r[f].includes(v):String(r[f]??L.unknown)===v)));}
 function render(){
  clear();root.empty();save();
  el(root,'h2',L.interactive).title=L.local_preferences;
  const toolbar=el(root,'div',null,'au-toolbar');
  select(toolbar,L.period,[...(kind==='calendar'?[['upcoming',L.upcoming]]:[]),['30',L.last30],['90',L.last90],['month',L.month],['quarter',L.quarter],['year',L.year],['custom',L.custom]],state.preset,v=>{state.preset=v;if(v!=='custom')[state.from,state.to]=C.range(v);render();});
  let from=state.from,to=state.to;
  dateInput(toolbar,L.from,from,v=>from=v);dateInput(toolbar,L.to,to,v=>to=v);
  const error=el(root,'div','','au-muted');
  btn(toolbar,L.apply,()=>{if(!legal(from,to)){error.textContent=L.invalid_dates;return;}state.from=from;state.to=to;state.preset='custom';render();});
  for(const [text,dir] of [[L.previous,-1],[L.next,1]])btn(toolbar,text,()=>{const n=Math.round((Date.parse(state.to)-Date.parse(state.from))/86400000)+1;state.from=C.add(state.from,dir*n);state.to=C.add(state.to,dir*n);state.preset='custom';render();});
  const fields=data.filters||[];for(const f of fields){const values=[...new Set((data.charts||[]).flatMap(c=>c.rows.flatMap(r=>r[f]??[])).filter(x=>x!==undefined))].sort();select(toolbar,kind==='calendar'&&f==='account'?L.calendar_filter:L[f], [['',L.all_values],...values.map(x=>[x,x])],state.filters[f]||'',v=>{state.filters[f]=v;render();});}
  btn(toolbar,L.reset,()=>{state=initial();saved.page=state;saved.cards={};render();});
  el(root,'div',`${state.from} → ${state.to} · ${L.built}: ${data.generated_at||L.unknown}`,'au-muted');
  if(data.source_updated)el(root,'div',L.source+': '+data.source_updated,'au-muted');
  if(data.note)el(root,'div',data.note,'au-notice');
  if(kind==='finance')financeSummary();
  if(data.charts?.length>1)select(toolbar,L.chart_picker,[['',L.all_charts],...data.charts.map(c=>[c.id,c.title])],state.chart||'',v=>{state.chart=v;render();});
  for(const spec of data.charts||[])if(!state.chart||state.chart===spec.id)renderCard(spec);
  if(data.pairs)renderPairs();
 }
 function financeSummary(){
  const rows=filter(data.transactions).filter(r=>r.date>=state.from&&r.date<=state.to),grid=el(root,'div',null,'au-grid');
  const total=t=>rows.filter(r=>r.type===t).reduce((s,r)=>s+r.amount,0);
  for(const [title,value] of [[L.income,total('income')],[L.expense,total('expense')],[L.net,total('income')-total('expense')]]){const box=el(grid,'div',null,'au-metric');el(box,'div',title,'au-label');el(box,'div',fmt(value)+' '+data.currency,'au-value');}
  if(!rows.length)el(root,'div',L.missing,'au-notice');
 }
 function renderCard(spec){
  const defaults={own:false,from:state.from,to:state.to,grain:'auto',compare:false,table:false,expanded:false,smooth:'0',share:false};
  const s=Object.assign(defaults,saved.cards[spec.id]||{});saved.cards[spec.id]=s;
  const card=el(root,'section',null,'au-chart-card'+(spec.type==='correlation'?' au-matrix-card':'')+(s.expanded?' au-expanded':''));el(card,'h3',spec.title);
  if(spec.note)el(card,'div',spec.note,'au-notice');
  if(spec.source_updated)el(card,'div',L.source_date+': '+spec.source_updated,'au-muted');
  if(['correlation','scatter','normalized'].includes(spec.type)){renderAnalysis(spec,card,s);return;}
  if(spec.type==='categorical'||spec.type==='heatmap'){renderBreakdown(spec,card,s);return;}
  const controls=el(card,'div',null,'au-toolbar');
  select(controls,L.period,[['page',L.inherit],['own',L.own]],s.own?'own':'page',v=>{s.own=v==='own';render();});
  if(s.own){dateInput(controls,L.from,s.from,v=>{if(legal(v,s.to)){s.from=v;render();}});dateInput(controls,L.to,s.to,v=>{if(legal(s.from,v)){s.to=v;render();}});}
  const from=s.own?s.from:state.from,to=s.own?s.to:state.to;
  select(controls,L.grain,['auto','day','week','month','quarter'].map(x=>[x,L[x]]),s.grain,v=>{s.grain=v;render();});
  check(controls,L.compare,s.compare,v=>{s.compare=v;render();});
  if(spec.smooth)select(controls,L.smooth,[['0',L.none],['7','7 '+L.day],['30',L.last30]],s.smooth,v=>{s.smooth=v;render();});
  if(spec.type==='bar')check(controls,L.share,s.share,v=>{s.share=v;render();});
  const tableButton=btn(controls,s.table?L.hide_table:L.show_table,()=>{s.table=!s.table;render();});
  tableButton.setAttribute('aria-expanded',String(s.table));
  btn(controls,s.expanded?L.collapse:L.expand,()=>{s.expanded=!s.expanded;render();});
  let rows=filter(spec.rows,spec.filter_fields);
  if(spec.max_series&&!state.filters.category){const totals={};for(const r of spec.rows)totals[r.series]=(totals[r.series]||0)+r.value;const keep=Object.keys(totals).sort((a,b)=>totals[b]-totals[a]).slice(0,spec.max_series);rows=rows.map(r=>({...r,series:keep.includes(r.series)?r.series:L.other}));}
  const grain=C.granularity(s.grain,from,to),preset=s.own?'custom':state.preset,comparisonPeriod=C.comparison([],from,to,grain,spec.method,0,preset).period,pfrom=s.compare?comparisonPeriod[0]:from,series=[...new Set(rows.filter(r=>r.date>=pfrom&&r.date<=to).map(r=>r.series))].sort();
  const current=series.map(name=>({name,points:C.aggregate(C.rolling(rows.filter(r=>r.series===name),Number(s.smooth)),from,to,grain,spec.method)}));
  const days=new Set(rows.filter(r=>r.date>=from&&r.date<=to&&Number.isFinite(r.value)).map(r=>r.date));
  el(card,'div',`${from} → ${to} · ${L[spec.method]} · ${L[grain]} · ${L.observed_days}: ${days.size}`,'au-muted');
  el(card,'div',L.boundary,'au-muted');
  if(spec.filter_fields&&Object.keys(state.filters).some(f=>state.filters[f]&&!spec.filter_fields.includes(f)))el(card,'div',L.filter_scope+': '+spec.filter_fields.map(f=>L[f]).join(', '),'au-notice');
  const priorDays=new Set(rows.filter(r=>r.date>=comparisonPeriod[0]&&r.date<=comparisonPeriod[1]&&Number.isFinite(r.value)).map(r=>r.date));
  if(!days.size){el(card,'div',L.empty,'au-notice');if(!s.compare||!priorDays.size)return;}
  const dates=current[0]?.points.map(p=>p.date)||[];
  if(s.share){for(let i=0;i<dates.length;i++){const total=current.reduce((v,c)=>v+(c.points[i].value||0),0);for(const c of current)if(c.points[i].value!==null)c.points[i].value=total?100*c.points[i].value/total:0;}}
  let prev=[];if(s.compare){const [pfrom,pto]=comparisonPeriod;el(card,'div',L.previous+': '+pfrom+' → '+pto,'au-muted');
   el(card,'div',L[(['month','quarter','year'].includes(preset))?'compare_calendar':'compare_equal_days'],'au-muted');
   if(!priorDays.size)el(card,'div',L.compare_missing,'au-notice');
   prev=series.map(name=>({name,...C.comparison(rows.filter(r=>r.series===name),from,to,grain,spec.method,Number(s.smooth),preset)}));
   if(s.share)for(let i=0;i<dates.length;i++){const total=prev.reduce((v,c)=>v+(c.points[i].value||0),0);for(const c of prev)if(c.points[i].value!==null)c.points[i].value=total?100*c.points[i].value/total:0;}
  }
  const plots=current.map(c=>({name:c.name,type:spec.type,stack:spec.stack===true||(spec.type==='bar'&&spec.stack!==false)?'current':undefined,areaStyle:spec.area?{}:undefined,connectNulls:false,showSymbol:dates.length<60,itemStyle:{color:color(c.name)},data:c.points.map(p=>p.value)}));
  for(const c of prev)plots.push({name:c.name+' · '+L.previous,type:spec.type,stack:spec.stack===true||(spec.type==='bar'&&spec.stack!==false)?'previous':undefined,connectNulls:false,showSymbol:true,symbol:'emptyCircle',symbolSize:7,lineStyle:{type:'dashed',width:2},itemStyle:{color:color(c.name),opacity:.65,borderWidth:1,borderColor:color(c.name)},data:c.points.map(p=>p.value)});
  card.title=L.select_bucket;
  const details=el(card,'div',null,'au-point-details');
  chart(card,{tooltip:{trigger:'axis',renderMode:'richText',confine:true,formatter:items=>items.map(item=>{const previous=item.seriesIndex>=current.length;const point=(previous?prev[item.seriesIndex-current.length]:current[item.seriesIndex])?.points[item.dataIndex];const dates=previous?(point?.sourceFrom?(point.sourceFrom+' → '+point.sourceTo):L.compare_missing):item.axisValue;return item.seriesName+' · '+dates+': '+fmt(item.value);}).join('\n')},legend:{type:'scroll',top:0},grid:{left:65,right:25,top:60,bottom:85},xAxis:{type:'category',data:dates},yAxis:{type:'value',name:s.share?'%':spec.unit||'',axisLabel:{formatter:fmt}},dataZoom:[{type:'inside',filterMode:'none'},{type:'slider',bottom:8}],series:plots},e=>{
   details.empty();if(!dates.includes(e.name))return;const end=C.next(e.name,grain);
   const prior=e.seriesIndex>=current.length;
   const selected=prior?prev.flatMap(c=>c.rows).filter(r=>r.date>=from&&r.date<=to&&r.date>=e.name&&r.date<end).map(r=>({...r,date:r.sourceDate,value:r.sourceValue})):rows.filter(r=>r.date>=from&&r.date<=to&&r.date>=e.name&&r.date<end);
   el(details,'h4',L.selected_bucket+': '+e.name+(prior?' · '+L.previous:''));table(details,[L.date,L.series,L.value,kind==='calendar'?L.calendar_filter:L.account,L.description],selected.map(r=>[r.date,r.category||r.series,fmt(r.value),r.account||'—',r.description||'']));
  });
  if(s.table)table(card,[L.date,...series,...prev.map(c=>c.name+' · '+L.previous)],dates.map((d,i)=>[d,...current.map(c=>fmt(c.points[i].value)),...prev.map(c=>fmt(c.points[i].value))]));
 }
 function renderBreakdown(spec,card,s){
  const bar=el(card,'div',null,'au-toolbar');
  if(!spec.snapshot){
   select(bar,L.period,[['page',L.inherit],['own',L.own]],s.own?'own':'page',v=>{s.own=v==='own';render();});
   if(s.own){dateInput(bar,L.from,s.from,v=>{if(legal(v,s.to)){s.from=v;render();}});dateInput(bar,L.to,s.to,v=>{if(legal(s.from,v)){s.to=v;render();}});}
  }
  const from=s.own?s.from:state.from,to=s.own?s.to:state.to;
  el(card,'div',spec.snapshot?L.snapshot_note+' · '+spec.snapshot:from+' → '+to,'au-notice');
  if(spec.filter_fields&&Object.keys(state.filters).some(f=>state.filters[f]&&!spec.filter_fields.includes(f)))el(card,'div',L.filter_scope+': '+(spec.filter_fields.map(f=>L[f]).join(', ')||L.none),'au-notice');
  const rows=filter(spec.rows,spec.filter_fields).filter(r=>spec.snapshot||(r.date>=from&&r.date<=to));
  if(!rows.length){el(card,'div',L.empty,'au-notice');return;}
  const xs=[...new Set(rows.map(r=>r.x))],ys=[...new Set(rows.map(r=>r.series))],values=new Map();
  for(const r of rows){const k=JSON.stringify([r.x,r.series]);values.set(k,(values.get(k)||0)+r.value);}
  const get=(x,y)=>values.get(JSON.stringify([x,y]))||0;
  const plots=spec.type==='heatmap'?[{type:'heatmap',data:xs.flatMap((x,i)=>ys.map((y,j)=>[i,j,get(x,y)])),label:{show:true}}]:ys.map(y=>({name:y,type:'bar',stack:'total',data:xs.map(x=>get(x,y)),itemStyle:{color:color(y)}}));
  if(spec.horizontal){
   const details=el(card,'div',null,'au-point-details');
   chart(card,{tooltip:{trigger:'axis',renderMode:'richText',confine:true},legend:{type:'scroll',top:0},grid:{left:110,right:45,top:50,bottom:30},xAxis:{type:'value',minInterval:1},yAxis:{type:'category',data:xs,inverse:true,axisLabel:{formatter:v=>v.slice(8,10)+'.'+v.slice(5,7)}},series:plots.map(p=>({...p,barMaxWidth:24,label:{show:true,position:'inside',formatter:p=>p.value||''}}))},e=>{
    details.empty();el(details,'h4',L.selected_bucket+': '+e.name);
    table(details,[L.date,L.category,L.description],rows.filter(r=>r.x===e.name).map(r=>[r.date,r.category||r.series,r.description||'']));
   });
  }else{
  chart(card,{tooltip:{trigger:spec.type==='heatmap'?'item':'axis',renderMode:'richText',confine:true},legend:spec.type==='heatmap'?undefined:{type:'scroll'},grid:{left:160,right:30,top:65,bottom:110},xAxis:{type:'category',data:xs,axisLabel:{rotate:25}},yAxis:spec.type==='heatmap'?{type:'category',data:ys}:{type:'value'},visualMap:spec.type==='heatmap'?{dimension:2,min:0,max:Math.max(...values.values(),1),calculable:true,orient:'horizontal',bottom:0}:undefined,series:plots});
  }
  btn(bar,s.table?L.hide_table:L.show_table,()=>{s.table=!s.table;render();});
  btn(bar,s.expanded?L.collapse:L.expand,()=>{s.expanded=!s.expanded;render();});
  if(s.table)table(card,[L.date,L.series,L.value,L.description],rows.map(r=>[r.date,r.x+' · '+r.series,r.value,r.description||'']));
 }
 function renderAnalysis(spec,card,s){
  const bar=el(card,'div',null,'au-toolbar'),metrics=spec.metrics||[],label=k=>L[k]||k;
  select(bar,L.period,[['page',L.inherit],['own',L.own]],s.own?'own':'page',v=>{s.own=v==='own';render();});
  if(s.own){dateInput(bar,L.from,s.from,v=>{if(legal(v,s.to)){s.from=v;render();}});dateInput(bar,L.to,s.to,v=>{if(legal(s.from,v)){s.to=v;render();}});}
  const from=s.own?s.from:state.from,to=s.own?s.to:state.to;
  let rows=spec.rows.filter(r=>r.date>=from&&r.date<=to);
  el(card,'div',from+' → '+to+' · '+L.correlation_note,'au-notice');
  if(metrics.length<2||!rows.length){el(card,'div',L.empty);return;}
  s.x=metrics.includes(s.x)?s.x:metrics[0];s.y=metrics.includes(s.y)?s.y:metrics[1];s.lag=Number(s.lag||0);
  if(spec.type!=='correlation')for(const f of ['x','y'])select(bar,L[f+'_metric'],metrics.map(k=>[k,label(k)]),s[f],v=>{s[f]=v;render();});
  btn(bar,s.expanded?L.collapse:L.expand,()=>{s.expanded=!s.expanded;render();});
  btn(bar,s.table?L.hide_table:L.show_table,()=>{s.table=!s.table;render();});
  if(spec.type==='correlation'){
   const points=[];
   metrics.forEach((x,i)=>metrics.forEach((y,j)=>{const pairs=C.paired(rows,x,y,0,from,to),rho=C.spearman(pairs);if(pairs.length>=spec.min_pairs&&rho!==null)points.push([i,j,rho,pairs.length]);}));
   chart(card,{tooltip:{renderMode:'richText',formatter:p=>label(metrics[p.data[0]])+' / '+label(metrics[p.data[1]])+'\nρ = '+fmt(p.data[2])+' · n = '+p.data[3]},grid:{left:165,right:20,top:30,bottom:160},xAxis:{type:'category',data:metrics.map(label),axisLabel:{rotate:50,interval:0}},yAxis:{type:'category',data:metrics.map(label)},visualMap:{dimension:2,min:-1,max:1,orient:'horizontal',bottom:0,inRange:{color:['#3b82f6','#f1f5f9','#ea580c']}},series:[{type:'heatmap',data:points,label:{show:metrics.length<10,formatter:p=>fmt(p.data[2])}}]});
   if(s.table)table(card,[L.x_metric,L.y_metric,'ρ',L.pairs],points.map(p=>[label(metrics[p[0]]),label(metrics[p[1]]),fmt(p[2]),p[3]]));
  }else if(spec.type==='scatter'){
   select(bar,L.lag,[0,1,2,3,7].map(v=>[String(v),String(v)]),String(s.lag),v=>{s.lag=Number(v);render();});
   const points=C.paired(spec.rows,s.x,s.y,s.lag,from,to);
   el(card,'div',L.pairs+': '+points.length+' · ρ = '+fmt(C.spearman(points)),'au-muted');
   chart(card,{tooltip:{renderMode:'richText',formatter:p=>p.data[2]+'\n'+label(s.x)+': '+fmt(p.data[0])+'\n'+label(s.y)+': '+fmt(p.data[1])},grid:{left:75,right:40,top:30,bottom:80},xAxis:{type:'value',name:label(s.x),nameLocation:'middle',nameGap:35,scale:true},yAxis:{type:'value',name:label(s.y),scale:true},dataZoom:[{type:'inside'},{type:'slider'}],series:[{type:'scatter',data:points}]});
   if(s.table)table(card,[L.date,label(s.x),label(s.y)],points.map(p=>[p[2],fmt(p[0]),fmt(p[1])]));
  }else{
   el(card,'div',L.normalized_note,'au-muted');
   const dates=rows.map(r=>r.date),series=[s.x,s.y].map(k=>({name:label(k),type:'line',connectNulls:false,data:C.standardize(rows.map(r=>r[k]))}));
   chart(card,{tooltip:{trigger:'axis',renderMode:'richText'},legend:{type:'scroll'},grid:{left:65,right:25,top:60,bottom:85},xAxis:{type:'category',data:dates},yAxis:{type:'value',name:'z-score'},dataZoom:[{type:'inside'},{type:'slider'}],series});
   if(s.table)table(card,[L.date,...series.map(x=>x.name)],dates.map((d,i)=>[d,...series.map(x=>fmt(x.data[i]))]));
  }
 }

 function renderPairs(){
  const card=el(root,'section',null,'au-chart-card');el(card,'h3',L.correlation);const bar=el(card,'div',null,'au-toolbar');
  const s=saved.pairs||={x:data.metrics[0],y:data.metrics[1],lag:0};
  for(const f of ['x','y'])select(bar,L[f+'_metric'],data.metrics.map(x=>[x,L[x]||x]),s[f],v=>{s[f]=v;render();});
  select(bar,L.lag,[0,1,2,3,7].map(x=>[String(x),String(x)]),String(s.lag),v=>{s.lag=Number(v);render();});
  const points=C.paired(data.pairs,s.x,s.y,s.lag,state.from,state.to);
  el(card,'div',L.pairs+': '+points.length+' · '+L.correlation_note,'au-notice');
  if(!points.length){el(card,'div',L.empty);return;}
  chart(card,{tooltip:{trigger:'item',renderMode:'richText',formatter:p=>`${p.data[2]}\n${L[s.x]}: ${fmt(p.data[0])}\n${L[s.y]}: ${fmt(p.data[1])}`},grid:{left:75,right:40,top:30,bottom:80},xAxis:{type:'value',name:L[s.x],nameLocation:'middle',nameGap:35,scale:true},yAxis:{type:'value',name:L[s.y],scale:true},dataZoom:[{type:'inside'},{type:'slider'}],series:[{type:'scatter',symbolSize:9,data:points}]});
 }
 render();return clear;
}
