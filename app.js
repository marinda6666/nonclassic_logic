'use strict';
const $=id=>document.getElementById(id);
const F={EPS:1e-6,LEVELS:[]};
async function api(path,body){
  let response;
  try{response=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});}
  catch(e){throw Error('Нет связи с Python API. Проверьте Docker и обновите страницу.');}
  const data=await response.json();
  if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:Array.isArray(data.detail)?data.detail.map(v=>v.loc.join('.')+': '+v.msg).join('; '):'Ошибка сервера.');
  return data;
}
const colors=['#d5fc7b','#b8abff','#ff9c76','#79dce8','#f5a5ce','#a6c8ff','#f3d57c','#8fddbb','#bbbcc8','#d5aa78'];
let items=[],analysis=null,logs=[],lastResult=null;
const fmt=(x,n=3)=>Number.isFinite(x)?x.toLocaleString('ru-RU',{maximumFractionDigits:n}):'—';
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function cutAt(v,alpha){let i=F.LEVELS.findIndex(a=>a>=alpha);if(i<=0)return v.cuts[0];const t=(alpha-F.LEVELS[i-1])/(F.LEVELS[i]-F.LEVELS[i-1]);return v.cuts[i-1].map((x,j)=>x+t*(v.cuts[i][j]-x));}
function syncAnalysisControls(){if(!analysis)return;$('metric').value=analysis.metric;$('alpha').value=analysis.alpha??.5;$('cluster-mode').value=analysis.mode;$('clusters').value=Math.min(10,analysis.groups.length);if(analysis.threshold!==null)$('threshold').value=analysis.threshold;$('metric').onchange();$('cluster-mode').onchange();}
function log(action,details){logs.push({time:new Date().toISOString(),action,details});renderLog();}
function notice(message,error=false){$('notice').textContent=message;$('notice').className='notice'+(error?' error':'');$('notice').hidden=false;}
function safe(fn){return async function(e){if(e)e.preventDefault();if(document.body.dataset.busy)return;document.body.dataset.busy='true';document.querySelectorAll('button').forEach(b=>b.disabled=true);try{await fn(e);}catch(err){notice(err.message,true);log('Ошибка',err.message);}finally{delete document.body.dataset.busy;document.querySelectorAll('button').forEach(b=>b.disabled=false);}};}
function download(name,data,type='text/plain;charset=utf-8'){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([data],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000);}
function tab(name){document.querySelectorAll('.tab').forEach(v=>v.classList.toggle('active',v.id===name));document.querySelectorAll('button.nav').forEach(v=>v.classList.toggle('active',v.dataset.tab===name));$('page-title').textContent=({overview:'Обзор эксперимента',arithmetic:'Операции с величинами',data:'Библиотека величин',journal:'Протокол эксперимента'})[name];}
document.querySelectorAll('button.nav').forEach(v=>v.onclick=()=>tab(v.dataset.tab));
function axes(xmin,xmax,ymin,ymax,xlabel,ylabel,w=760,h=310){
  if(xmin===xmax){xmin-=1;xmax+=1;}if(ymin===ymax){ymin-=1;ymax+=1;}
  const left=58,right=22,top=20,bottom=47;
  const X=x=>left+(x-xmin)/(xmax-xmin)*(w-left-right),Y=y=>h-bottom-(y-ymin)/(ymax-ymin)*(h-top-bottom);
  let svg='';
  for(let i=0;i<=5;i++){const x=xmin+(xmax-xmin)*i/5,y=ymin+(ymax-ymin)*i/5;svg+=`<path d="M${X(x)} ${top}V${h-bottom}" stroke="#292e35"/><path d="M${left} ${Y(y)}H${w-right}" stroke="#292e35"/><text x="${X(x)}" y="${h-bottom+20}" text-anchor="middle">${esc(fmt(x,2))}</text><text x="${left-10}" y="${Y(y)+4}" text-anchor="end">${esc(fmt(y,2))}</text>`;}
  svg+=`<text class="axis-title" x="${w/2}" y="${h-5}" text-anchor="middle">${xlabel}</text><text class="axis-title" x="${left}" y="12">${ylabel}</text>`;
  return {X,Y,svg,w,h};
}
function plotCurves(target,values,explicitColors=false){
  if(!values.length){$(target).innerHTML='<div class="empty">Добавьте величины или сгенерируйте набор.</div>';return;}
  let min=Math.min(...values.map(v=>v.cuts[0][0])),max=Math.max(...values.map(v=>v.cuts[0][1]));const padding=(max-min)*.035||1;
  const a=axes(min-padding,max+padding,0,1,'x','μ(x)'),{X,Y}=a;let svg=a.svg;
  if(target==='curves'&&analysis?.metric==='alpha')svg+=`<path d="M${X(min-padding)} ${Y(analysis.alpha)}H${X(max+padding)}" stroke="#fff" stroke-dasharray="6 4"/><text x="${X(max)}" y="${Y(analysis.alpha)+14}" text-anchor="end">α = ${fmt(analysis.alpha,6)}</text>`;
  values.forEach((v,j)=>{
    const color=explicitColors?colors[j%colors.length]:(analysis?colors[analysis.labels[items.indexOf(v)]%colors.length]:colors[j%3]);
    const points=v.cuts.map((c,i)=>[c[0],F.LEVELS[i]]).concat(v.cuts.map((c,i)=>[c[1],F.LEVELS[i]]).reverse());
    const path=points.map(([x,y],i)=>`${i?'L':'M'}${X(x).toFixed(2)},${Y(y).toFixed(2)}`).join(' ');
    svg+=`<path class="tooltip" d="${path}" fill="${color}" fill-opacity=".045" stroke="${color}" stroke-width="${explicitColors?2.6:1.9}" opacity=".85"><title>${esc(v.name)} · центроид ${esc(fmt(v.centroid))}${v.type==='weibull'?` · γ=${fmt(v.shape)} σ=${fmt(v.scale)}`:''}</title></path>`;
  });
  $(target).innerHTML=`<svg role="img" aria-label="Функции принадлежности нечётких величин" viewBox="0 0 ${a.w} ${a.h}">${svg}</svg>`;
}
function renderScatter(){
  const alpha=analysis?.metric==='alpha'?analysis.alpha:.5;
  $('scatter-caption').textContent=`Проекция: центроид × ширина среза α = ${fmt(alpha,6)}`;
  const values=items.map(v=>{const c=cutAt(v,alpha);return [v.centroid,c[1]-c[0]];});
  if(!values.length){$('scatter').innerHTML='<div class="empty">Набор пуст.</div>';return;}
  const xs=values.map(v=>v[0]),ys=values.map(v=>v[1]),px=(Math.max(...xs)-Math.min(...xs))*.08||1,py=(Math.max(...ys)-Math.min(...ys))*.12||1;
  const a=axes(Math.min(...xs)-px,Math.max(...xs)+px,Math.max(0,Math.min(...ys)-py),Math.max(...ys)+py,'Центроид',`Ширина α = ${fmt(alpha,6)}`,760,280);let svg=a.svg;
  values.forEach(([x,y],i)=>{const c=analysis?analysis.labels[i]:0;svg+=`<circle cx="${a.X(x)}" cy="${a.Y(y)}" r="4.3" fill="${colors[c%colors.length]}" fill-opacity=".7" stroke="#14171b" stroke-width="1.1"><title>${esc(items[i].name)} · центроид ${fmt(x)} · ширина ${fmt(y)}${analysis?' · кластер '+(c+1):''}</title></circle>`;});
  $('scatter').innerHTML=`<svg role="img" aria-label="Карта кластеров" viewBox="0 0 760 280">${svg}</svg>`;
  $('cluster-legend').innerHTML=analysis?analysis.groups.slice(0,15).map((g,c)=>`<span><i style="background:${colors[c%colors.length]}"></i>К${c+1} · ${g.length}</span>`).join('')+(analysis.groups.length>15?'<span>Остальные группы — в таблице</span>':''):'<span>Цвет появится после анализа</span>';
}
function renderTable(){const query=$('search').value.toLowerCase();const rows=items.map((v,i)=>({v,i})).filter(({v})=>v.name.toLowerCase().includes(query));$('table-count').textContent=`${rows.length} из ${items.length}`;$('data-body').innerHTML=rows.map(({v,i})=>`<tr><td><button data-edit="${i}">${esc(v.name)}</button></td><td>${v.type==='weibull'?'Вейбулла':'α-срезы'}</td><td>${fmt(v.shape)}</td><td>${fmt(v.scale)}</td><td>${fmt(v.shift)}</td><td>${fmt(v.centroid)}</td><td>[${fmt(v.cuts[50][0])}; ${fmt(v.cuts[50][1])}]</td><td>${analysis?'К'+(analysis.labels[i]+1):'—'}</td><td><button class="delete" data-delete="${i}" aria-label="Удалить ${esc(v.name)}">Удалить</button></td></tr>`).join('');}
function renderLog(){$('log-content').textContent=logs.map(v=>`${v.time}  ${v.action}\n${typeof v.details==='string'?v.details:JSON.stringify(v.details)}\n`).join('\n');}
function render(){
  $('stat-n').textContent=items.length;$('stat-k').textContent=analysis?analysis.groups.length:'—';$('stat-s').textContent=analysis&&analysis.silhouette!==null?fmt(analysis.silhouette):'—';$('stat-method').textContent=analysis?(analysis.mode==='fixed'?'k-means · '+analysis.iterations+' итераций':'Одиночная связь · порог '+fmt(analysis.threshold)):'запустите анализ';
  for(const id of ['operand-a','operand-b']){const old=$(id).value;$(id).innerHTML=items.map((v,i)=>`<option value="${i}">${esc(v.name)}</option>`).join('');if(old&&Number(old)<items.length)$(id).value=old;}
  $('curve-caption').textContent=`${Math.min(12,items.length)} из ${items.length} величин · наведите на кривую`;
  plotCurves('curves',items.slice(0,12));renderScatter();renderTable();
  if(analysis){$('analysis-meta').textContent=`${analysis.metric==='alpha'?'Отсечение по уровню α = '+fmt(analysis.alpha,6):analysis.metric==='cuts'?'Метрика всех α-срезов':'Метрика центроидов'} · сумма квадратов расстояний ${fmt(analysis.inertia)} · ${analysis.converged?'сходимость достигнута':'достигнут лимит итераций'}`;$('cluster-summary').innerHTML=analysis.groups.map((g,c)=>{const cs=g.map(i=>items[i].centroid);return `<div class="cluster-card" style="--cluster-color:${colors[c%colors.length]}"><h4><span style="color:${colors[c%colors.length]}">●</span> Кластер ${c+1}</h4><div class="cluster-meter"><span style="width:${g.length/items.length*100}%"></span></div><strong>${g.length} <small style="font-size:11px;font-weight:400">величин</small></strong><p>Центроид группы: ${fmt(cs.reduce((s,v)=>s+v,0)/g.length)}</p><p>Диапазон центроидов: ${fmt(Math.min(...cs))}–${fmt(Math.max(...cs))}</p></div>`;}).join('');}
  else{$('analysis-meta').textContent='Анализ ещё не выполнен';$('cluster-summary').innerHTML='<div class="empty">Запустите кластеризацию, чтобы увидеть состав групп.</div>';}
}
function changed(){analysis=null;lastResult=null;$('operation-result').textContent='Набор изменён. Выполните операцию заново.';$('operation-plot').innerHTML='';render();}
async function runAnalysis(){analysis=await api('cluster',{items,options:{metric:$('metric').value,alpha:$('metric').value==='alpha'?Number($('alpha').value):.5,mode:$('cluster-mode').value,k:Number($('clusters').value),threshold:Number($('threshold').value)}});log('Кластерный анализ',{mode:analysis.mode,metric:analysis.metric,alpha:analysis.alpha,k:analysis.groups.length,threshold:analysis.threshold,iterations:analysis.iterations,converged:analysis.converged,inertia:analysis.inertia,silhouette:analysis.silhouette,sizes:analysis.groups.map(g=>g.length)});render();notice(`Анализ завершён: ${analysis.groups.length} кластеров. ${analysis.converged?'':'Достигнут лимит итераций.'}`);}
async function generateSet(count){const result=await api('generate',{count,seed:$('random-seed').checked?null:Number($('seed').value)});items=result.items;$('seed').value=result.seed;log('Генерация',{count:items.length,seed:result.seed,scheme:result.generator,shapeRange:[1,6],scaleRange:[.5,10],shift:0});}
$('random-seed').onchange=()=>{$('seed').readOnly=$('random-seed').checked;};
$('random-seed').onchange();
$('generate-form').onsubmit=safe(async()=>{await generateSet(Number($('count').value));changed();notice(`Создан новый набор из ${items.length} величин. Seed: ${$('seed').value}. Предыдущий набор заменён.`);});
$('cluster-form').onsubmit=safe(runAnalysis);
$('metric').onchange=()=>{const active=$('metric').value==='alpha';$('alpha-settings').hidden=!active;$('alpha').disabled=!active;$('alpha').required=active;};
$('metric').onchange();
$('cluster-mode').onchange=()=>{const fixed=$('cluster-mode').value==='fixed';$('k-label').hidden=!fixed;$('threshold-label').hidden=fixed;$('clusters').required=fixed;$('mode-hint').textContent=fixed?'Детерминированная инициализация':'Связные компоненты графа расстояний';};
function readValue(){return api('values',{name:$('value-name').value,type:'weibull',shape:Number($('shape').value),scale:Number($('scale').value),shift:Number($('shift').value)});}
$('value-form').onsubmit=safe(async()=>{if(items.length>=500)throw Error('Максимум 500 величин в проекте.');const v=await readValue();items.push(v);log('Добавлена величина',{name:v.name,shape:v.shape,scale:v.scale,shift:v.shift});changed();$('operand-a').value=items.length-1;plotOperands();notice(`Добавлена величина «${v.name}».`);});
$('update-btn').onclick=safe(async()=>{const i=Number($('operand-a').value);if(!items[i])throw Error('Выберите величину A.');const v=await readValue();items[i]=v;log('Присвоение параметров',{index:i,...v,cuts:undefined});changed();notice('Параметры величины A изменены.');});
function plotOperands(){const a=items[Number($('operand-a').value)],b=items[Number($('operand-b').value)];plotCurves('operation-plot',[a,b,lastResult].filter(Boolean),true);}
$('operand-a').onchange=()=>{lastResult=null;plotOperands();};$('operand-b').onchange=()=>{lastResult=null;plotOperands();};
$('operation-form').onsubmit=safe(async()=>{const a=items[Number($('operand-a').value)],b=items[Number($('operand-b').value)],op=$('operator').value;if(!a||!b)throw Error('Добавьте аргументы.');if(op==='compare'){const r=await api('operations',{a,b,operation:'compare'});lastResult=null;$('operation-result').textContent=`${a.name} ${r.relation} ${b.name} по центроидам: ${fmt(r.a)} и ${fmt(r.b)}. Расстояние α-срезов: ${fmt(r.distance)}. Это выбранное ранжирование, а не полный порядок нечётких множеств.`;log('Сравнение',{a:a.name,b:b.name,...r});}else{if(items.length>=500)throw Error('Максимум 500 величин.');const r=await api('operations',{a,b,operation:op,name:$('result-name').value});items.push(r);analysis=null;render();lastResult=r;$('operation-result').textContent=`${a.name} ${op} ${b.name} → ${r.name}. Результат добавлен в набор. Центроид: ${fmt(r.centroid)}; α=0,5: [${fmt(r.cuts[50][0])}; ${fmt(r.cuts[50][1])}]. Цвета графика: A — лаймовый, B — лавандовый, R — оранжевый.`;log('Арифметика',{a:a.name,b:b.name,operation:op,result:r.name,cuts:r.cuts,centroid:r.centroid});}plotCurves('operation-plot',[a,b,lastResult].filter(Boolean),true);});
$('data-body').onclick=safe(e=>{const button=e.target.closest('button');if(!button)return;if(button.dataset.delete!==undefined){const i=Number(button.dataset.delete);log('Удаление',{name:items[i].name,index:i});items.splice(i,1);changed();return;}const i=Number(button.dataset.edit),v=items[i];$('operand-a').value=i;if(v.type==='weibull'){$('value-name').value=v.name;$('shape').value=v.shape;$('scale').value=v.scale;$('shift').value=v.shift;}lastResult=null;tab('arithmetic');plotOperands();notice(v.type==='weibull'?'Параметры загружены в редактор.':'Величина представлена α-срезами; её можно использовать как аргумент операции.');});
$('search').oninput=renderTable;
$('export-btn').onclick=safe(()=>{log('Экспорт проекта',{count:items.length});download('weibull-project.json',JSON.stringify({format:'weibull-lab',version:1,epsilon:F.EPS,levels:F.LEVELS,items,analysisOptions:analysis?{mode:analysis.mode,metric:analysis.metric,alpha:analysis.alpha,k:analysis.mode==='fixed'?analysis.groups.length:3,threshold:analysis.threshold}:null,logs},null,2),'application/json');notice('Проект сохранён в JSON.');});
$('import-btn').onclick=()=>$('import-file').click();
$('import-file').onchange=safe(async()=>{const file=$('import-file').files[0];if(!file)return;try{if(file.size>15e6)throw Error('Файл больше 15 МБ.');const p=JSON.parse(await file.text());const restored=await api('projects/validate',p);items=restored.items;logs=restored.logs;analysis=restored.analysis;syncAnalysisControls();lastResult=null;log('Импорт',{file:file.name,count:items.length});render();$('operation-result').textContent='Проект загружен. Выберите операцию.';plotOperands();notice('Проект загружен. Кластеризация пересчитана на Python по сохранённым настройкам.');}finally{$('import-file').value='';}});
$('log-btn').onclick=()=>download('weibull-session.log',logs.map(v=>`${v.time}\t${v.action}\t${typeof v.details==='string'?v.details:JSON.stringify(v.details)}`).join('\n'));
$('csv-btn').onclick=safe(()=>{if(!items.length)throw Error('Набор пуст.');const cell=v=>'"'+(typeof v==='string'?v.replace(/^[=+@-]/,"'$&"):String(v??'')).replace(/"/g,'""')+'"';const rows=[['name','type','shape','scale','shift','centroid','alpha_0.5_left','alpha_0.5_right','cluster'],...items.map((v,i)=>[v.name,v.type,v.shape,v.scale,v.shift,v.centroid,...v.cuts[50],analysis?analysis.labels[i]+1:''])];download('weibull-data.csv','\uFEFF'+rows.map(row=>row.map(cell).join(';')).join('\r\n'),'text/csv;charset=utf-8');notice('Таблица экспортирована в CSV.');});
safe(async()=>{const config=await api('config');F.EPS=config.epsilon;F.LEVELS=config.levels;await generateSet(150);log('Запуск',{backend:'Python / FastAPI',count:150,seed:Number($('seed').value),epsilon:F.EPS,levels:F.LEVELS.length});render();await runAnalysis();$('notice').hidden=true;$('operand-b').value='1';plotOperands();})();
