const assert=require('node:assert/strict');
const echarts=require('../shared/obsidian_ui/vendor/echarts.js');
for(const [name,points,min,max] of [['transitions',[[0,0,2],[1,1,7]],0,7],['correlation',[[0,0,-.8,60],[1,1,.8,60]],-1,1]]){
 const c=echarts.init(null,null,{renderer:'svg',ssr:true,width:900,height:440});
 c.setOption({animation:false,xAxis:{type:'category',data:['a','b']},yAxis:{type:'category',data:['a','b']},visualMap:{dimension:2,min,max,inRange:{color:['#3b82f6','#ea580c']}},series:[{type:'heatmap',data:points,label:{show:true}}]});
 const series=c.getModel().getSeries();assert.equal(series.length,1,name+' must register heatmap');assert.ok(c.getModel().getComponent('visualMap'));
 const data=series[0].getData();assert.ok(data.getItemGraphicEl(0),name+' must draw a cell');assert.ok(data.getItemGraphicEl(1));
 assert.notEqual(data.getItemVisual(0,'style').fill,data.getItemVisual(1,'style').fill,name+' colors follow value, not sample size');
 assert.ok(c.renderToSVGString().includes('<svg'));c.dispose();
}
console.log('Real ECharts: heatmap cells and correlation color scale passed');
