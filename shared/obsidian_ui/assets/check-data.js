module.exports=async({app,quickAddApi,obsidian})=>{
 const cfg=JSON.parse(await app.vault.adapter.read("Assistant UI/config.json"));
 await app.workspace.openLinkText(cfg.paths.system,"");
 app.workspace.trigger("dataview:refresh-views");
 new obsidian.Notice(cfg.labels.status_refreshed);
};
