const cfg=JSON.parse(await dv.io.load('Assistant UI/config.json')),kind=input?.kind||'finance';
try {
 const data=JSON.parse(await dv.io.load('Assistant UI/'+kind+'.json'));
 const plugin=app.plugins.plugins['assistant-dashboard-ux'];
 if(!plugin?.renderDashboard)throw new Error('Assistant Dashboards unavailable');
 plugin.renderDashboard(dv,cfg,kind,data);
}catch(error){dv.paragraph(cfg.labels.load_error);console.error('Assistant dashboard:',kind,error);}
