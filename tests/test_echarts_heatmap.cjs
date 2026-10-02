const assert = require('node:assert/strict');
const echarts = require('../shared/obsidian_ui/vendor/echarts.js');

function renderHeatmap(name, points, min, max) {
 const chart = echarts.init(null, null, {renderer:'svg', ssr:true, width:900, height:440});
 try {
  chart.setOption({
   animation:false,
   xAxis:{type:'category', data:['a','b','c']},
   yAxis:{type:'category', data:['a','b','c']},
   visualMap:{dimension:2, min, max, inRange:{color:['#3b82f6','#ea580c']}},
   series:[{type:'heatmap', data:points, label:{show:true}}],
  });
  const series = chart.getModel().getSeries();
  assert.equal(series.length, 1, name+' must register heatmap');
  assert.ok(chart.getModel().getComponent('visualMap'));
  const data = series[0].getData();
  for (let i = 0; i < points.length; i++) {
   assert.ok(data.getItemGraphicEl(i), name+' must draw cell '+i+' (value '+points[i][2]+')');
   assert.equal(data.get('value', i), points[i][2], name+' must retain the value dimension');
  }
  assert.ok(chart.renderToSVGString().includes('<svg'));
  return points.map((_, i) => data.getItemVisual(i, 'style').fill);
 } finally {
  chart.dispose();
 }
}

const transitionColors = renderHeatmap('transitions', [[0,0,0],[1,1,7]], 0, 7);
assert.notEqual(transitionColors[0], transitionColors[1], 'zero and positive counts must use different colors');

// Sample count is an extra dimension. Colors must still follow the correlation value at index 2.
const correlationColors = renderHeatmap('correlation', [[0,0,-.8,60],[1,1,0,600],[2,2,.8,60]], -1, 1);
assert.equal(new Set(correlationColors).size, 3, 'negative, zero, and positive correlations need distinct colors');

console.log('Real ECharts: zero counts and negative/zero/positive correlation heatmaps passed');
