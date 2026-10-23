// Date-only arithmetic uses UTC to avoid daylight-saving bucket drift.
const DAY=86400000;
const parse=s=>new Date(s+'T00:00:00Z');
const key=d=>d.toISOString().slice(0,10);
const add=(s,n)=>key(new Date(+parse(s)+n*DAY));
const today=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
function range(preset,anchor=today()){
 if(preset==='upcoming')return [anchor,add(anchor,13)];
 const d=parse(anchor),y=d.getUTCFullYear(),m=d.getUTCMonth();
 if(preset==='month')return [key(new Date(Date.UTC(y,m,1))),anchor];
 if(preset==='quarter')return [key(new Date(Date.UTC(y,Math.floor(m/3)*3,1))),anchor];
 if(preset==='year')return [key(new Date(Date.UTC(y,0,1))),anchor];
 return [add(anchor,-Number(preset||30)+1),anchor];
}
const valid=s=>/^\d{4}-\d{2}-\d{2}$/.test(s)&&Number.isFinite(+parse(s))&&key(parse(s))===s;
function bucket(date,grain){const d=parse(date);if(grain==='quarter'){d.setUTCDate(1);d.setUTCMonth(Math.floor(d.getUTCMonth()/3)*3);}if(grain==='month')d.setUTCDate(1);if(grain==='week')d.setUTCDate(d.getUTCDate()-(d.getUTCDay()+6)%7);return key(d);}
function next(date,grain){if(grain==='month'||grain==='quarter'){const d=parse(date);d.setUTCMonth(d.getUTCMonth()+(grain==='quarter'?3:1));return key(d);}return add(date,grain==='week'?7:1);}
function granularity(grain,from,to){return grain==='auto'?((+parse(to)-parse(from))/DAY>180?'month':(+parse(to)-parse(from))/DAY>45?'week':'day'):grain;}
function median(a){const b=[...a].sort((x,y)=>x-y),i=Math.floor(b.length/2);return b.length%2?b[i]:(b[i-1]+b[i])/2;}
function aggregate(rows,from,to,grain,method='sum'){
 const map=new Map();
 for(const r of [...rows].sort((a,b)=>a.date.localeCompare(b.date))){if(r.date<from||r.date>to||!Number.isFinite(r.value))continue;const k=bucket(r.date,grain);const a=map.get(k)||[];a.push(r.value);map.set(k,a);}
 const out=[];for(let date=bucket(from,grain);date<=to;date=next(date,grain)){
  const a=map.get(date);out.push({date,value:!a?null:method==='median'?median(a):method==='last'?a[a.length-1]:a.reduce((x,y)=>x+y,0)/(method==='mean'?a.length:1),count:a?.length||0});
 }return out;
}
function rolling(rows,days){if(!days)return rows;return rows.map(r=>{const a=rows.filter(x=>x.date<=r.date&&x.date>=add(r.date,1-days)&&Number.isFinite(x.value));return {...r,value:Number.isFinite(r.value)&&a.length?a.reduce((s,x)=>s+x.value,0)/a.length:null};});}
function previous(from,to){const n=Math.round((parse(to)-parse(from))/DAY)+1;return [add(from,-n),add(from,-1)];}
function coverage(rows,from,to){
 const total=valid(from)&&valid(to)&&from<=to?Math.round((parse(to)-parse(from))/DAY)+1:0;
 const observed=new Set(rows.filter(r=>r.date>=from&&r.date<=to&&Number.isFinite(r.value)).map(r=>r.date)).size;
 return {observed,total};
}
// Calendar presets compare corresponding dates; arbitrary ranges use equal day counts.
function shiftMonths(day,n){const d=parse(day),last=new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+n+1,0)).getUTCDate();return key(new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+n,Math.min(d.getUTCDate(),last))));}
function comparison(rows,from,to,grain,method='sum',smooth=0,preset='custom'){
 const months={month:1,quarter:3,year:12}[preset]||0;
 const period=months?[shiftMonths(from,-months),shiftMonths(to,-months)]:previous(from,to);
 const n=Math.round((parse(to)-parse(from))/DAY)+1;
 const align=day=>months?shiftMonths(day,months):add(day,n);
 // Smooth in source time with the same lookback as the current series.
 const source=rolling(rows.map(r=>({...r,sourceValue:r.value})),smooth).filter(r=>r.date>=period[0]&&r.date<=period[1]);
 const shifted=source.map(r=>({...r,sourceDate:r.date,date:align(r.date)}));
 const points=aggregate(shifted,from,to,grain,method);
 for(const point of points){
  const dates=shifted.filter(r=>bucket(r.date,grain)===point.date).map(r=>r.sourceDate).sort();
  point.sourceFrom=dates[0]||null;point.sourceTo=dates.at(-1)||null;
 }
 return {period,points,rows:shifted};
}
function paired(rows,x,y,lag,from,to){const lookup=new Map(rows.map(r=>[r.date,r]));return rows.filter(r=>r.date>=from&&r.date<=to&&Number.isFinite(r[y])).flatMap(r=>{const a=lookup.get(add(r.date,-lag));return Number.isFinite(a?.[x])?[[a[x],r[y],r.date]]:[];});}
function standardize(values){const a=values.filter(Number.isFinite);if(!a.length)return values.map(()=>null);const mean=a.reduce((s,x)=>s+x,0)/a.length,sd=Math.sqrt(a.reduce((s,x)=>s+(x-mean)**2,0)/a.length);return values.map(x=>Number.isFinite(x)&&sd>0?(x-mean)/sd:null);}
function spearman(points){
 if(points.length<2)return null;
 const rank=a=>a.map(x=>{const lo=a.filter(v=>v<x).length,eq=a.filter(v=>v===x).length;return lo+(eq+1)/2;});
 const x=standardize(rank(points.map(p=>p[0]))),y=standardize(rank(points.map(p=>p[1])));
 return x.some(v=>v===null)||y.some(v=>v===null)?null:x.reduce((s,v,i)=>s+v*y[i],0)/x.length;
}
module.exports={standardize,spearman,key,add,today,range,valid,bucket,next,granularity,aggregate,rolling,previous,coverage,comparison,shiftMonths,paired};
