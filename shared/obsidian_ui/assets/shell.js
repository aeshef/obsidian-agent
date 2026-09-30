const cfg=JSON.parse(await dv.io.load("Assistant UI/config.json"));
const L=cfg.labels, kind=input?.kind||"main";
const root=dv.container.createDiv({cls:"au-shell"});
const nav=root.createEl("nav",{cls:"au-nav",attr:{"aria-label":L.brand}});
for(const [key,path] of Object.entries(cfg.paths)){
 const a=nav.createEl("a",{text:L[key],cls:key===kind?"is-active":"",attr:{href:path}});
 a.onclick=e=>{e.preventDefault();app.workspace.openLinkText(path,"");};
}
root.createDiv({cls:"au-eyebrow",text:L.brand});
root.createEl("h1",{cls:"au-title",text:L[kind]||L.overview});
root.createDiv({cls:"au-muted",text:L[kind+"_subtitle"]||L.subtitle});
if(cfg.read_only_mirror)root.createDiv({cls:"au-muted",text:L.mobile_readonly});
if(kind==="system"){
 const box=root.createDiv({cls:"au-status"});
 try {
  const report=JSON.parse(await dv.io.load("Assistant UI/status.json"));
  root.createDiv({cls:"au-muted",text:L.built+": "+String(report.checked_at||report.generated_at||L.unknown)});
  const checked=Date.parse(report.checked_at||report.generated_at||""), stale=!Number.isFinite(checked)||Date.now()-checked>cfg.layout.status_max_age_seconds*1000;
  if(stale)root.createDiv({cls:"au-notice",text:L.stale_report});
  for(const [key,val] of Object.entries(report.sources||{})){const item=box.createSpan();item.createSpan({cls:"au-dot "+(!stale&&val.status==="ok"?"ok":"warn")});item.createSpan({text:key+": "+(stale?L.unknown:val.status)+" · "+(val.captured_at||L.unknown)});}

 }catch(e){box.createSpan({text:L.unknown});}
 root.createDiv({cls:"au-muted",text:L.data_note});
}
