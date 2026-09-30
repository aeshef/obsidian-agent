module.exports=async({app,quickAddApi,obsidian})=>{
 const cfg=JSON.parse(await app.vault.adapter.read("Assistant UI/config.json")),L=cfg.labels;
 if(cfg.read_only_mirror){new obsidian.Notice(L.mobile_readonly);return;}
 const source=app.workspace.getActiveFile();if(!source||source.extension!=="md"){new obsidian.Notice(L.open_note);return;}
 const projects=app.vault.getMarkdownFiles().filter(f=>app.metadataCache.getFileCache(f)?.frontmatter?.type==="project"&&f.path!==source.path);
 if(!projects.length){new obsidian.Notice(L.create_project_first);return;}
 const target=await quickAddApi.suggester(projects.map(f=>f.basename),projects);if(!target)return;
 await app.fileManager.processFrontMatter(source,fm=>{const old=Array.isArray(fm.projects)?fm.projects:fm.projects?[fm.projects]:[];fm.projects=[...new Set([...old,"[["+target.path.replace(/\.md$/,"")+"]]"])];});
 new obsidian.Notice(L.linked);
};
