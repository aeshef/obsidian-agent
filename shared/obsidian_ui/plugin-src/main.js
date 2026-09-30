const {Plugin}=require('obsidian');
module.exports=class extends Plugin {
 renderDashboard(dv,cfg,kind,data){return renderInteractive(dv,cfg,kind,data);}
 onload(){
  const open=async()=>{
   const leaf=this.app.workspace.activeLeaf,file=this.app.workspace.getActiveFile();
   if(!leaf||!file||leaf.view.getViewType()!=="markdown")return;
   if(this.app.metadataCache.getFileCache(file)?.frontmatter?.["assistant-ui"]!==true)return;
   const state=leaf.view.getState();
   if(state.mode!=="preview")await leaf.setViewState({type:"markdown",state:{...state,mode:"preview",source:false}});
  };
  // file-open fires before the Markdown view restores its saved editor state.
  // Apply the dashboard mode after that restoration, not inside the event.
  let timer;
  const schedule=()=>{
   clearTimeout(timer);
   timer=setTimeout(()=>void open().catch(console.error),200);
  };
  this.register(()=>clearTimeout(timer));
  this.registerEvent(this.app.workspace.on('file-open',schedule));
  this.registerEvent(this.app.workspace.on('active-leaf-change',schedule));
  this.app.workspace.onLayoutReady(schedule);
 }
};
