// End-to-end test against the Python/FastAPI application.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const path=require('node:path'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
  fs.mkdirSync(path.resolve('tests/downloads'),{recursive:true});
  const browser=await chromium.launch({headless:true,downloadsPath:path.resolve('tests/downloads'),...(process.env.BROWSER_PATH?{executablePath:process.env.BROWSER_PATH}:{})});
  const page=await browser.newPage({acceptDownloads:true,viewport:{width:1440,height:1100}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const requests=[];page.on('request',r=>{if(r.method()==='POST')requests.push(new URL(r.url()).pathname);});
  async function click(selector){await page.locator(selector).click();await page.waitForFunction(()=>!document.body.dataset.busy);}
  await page.goto(process.env.APP_URL||'http://localhost:8080');
  await page.waitForFunction(()=>document.getElementById('stat-k').textContent==='3');
  assert.equal(await page.locator('#stat-n').innerText(),'150');
  await fs.promises.mkdir('docs/assets',{recursive:true});
  await page.screenshot({path:'docs/assets/workspace.png',fullPage:true});
  async function generate(){const response=page.waitForResponse(r=>r.url().endsWith('/api/generate')&&r.request().method()==='POST');await click('#generate-form button');return (await response).json();}
  assert.equal(await page.locator('#random-seed').isChecked(),true);
  assert.equal(await page.locator('#seed').evaluate(n=>n.readOnly),true);
  await page.locator('#count').fill('300');
  const randomA=await generate(),randomB=await generate();
  assert.notDeepEqual(randomA.items,randomB.items);
  assert.equal(Number(await page.locator('#seed').inputValue()),randomB.seed);
  await page.locator('#random-seed').uncheck();
  assert.equal(await page.locator('#seed').evaluate(n=>n.readOnly),false);
  await page.locator('#seed').fill('42');
  const fixedA=await generate(),fixedB=await generate();
  assert.deepEqual(fixedA,fixedB);
  assert.equal(await page.locator('#stat-n').innerText(),'300');
  await click('#cluster-form button');assert.equal(await page.locator('#stat-k').innerText(),'3');
  await page.selectOption('#cluster-mode','threshold');await click('#cluster-form button');
  assert.ok(Number(await page.locator('#stat-k').innerText())>=1);
  await page.selectOption('#metric','alpha');
  assert.equal(await page.locator('#alpha-settings').isVisible(),true);
  for(const mode of ['fixed','threshold']){
    await page.selectOption('#cluster-mode',mode);
    for(const alpha of ['0.73456','1']){
      await page.locator('#alpha').fill(alpha);await click('#cluster-form button');
      assert.match(await page.locator('#analysis-meta').innerText(),/Отсечение по уровню α/);
      assert.ok(Number(await page.locator('#stat-k').innerText())>=1);
    }
  }
  await page.locator('#alpha').fill('0.73456');await click('#cluster-form button');
  const alphaDownload=page.waitForEvent('download');await click('#export-btn');
  await (await alphaDownload).saveAs('tests/tmp-alpha.json');
  const alphaProject=JSON.parse(fs.readFileSync('tests/tmp-alpha.json','utf8'));
  assert.equal(alphaProject.analysisOptions.alpha,.73456);
  await page.selectOption('#metric','center');
  await page.locator('#import-file').setInputFiles('tests/tmp-alpha.json');
  await page.waitForFunction(()=>!document.body.dataset.busy);
  assert.equal(await page.locator('#metric').inputValue(),'alpha');
  assert.equal(await page.locator('#alpha').inputValue(),'0.73456');
  assert.match(await page.locator('#scatter-caption').innerText(),/0,73456/);
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.setViewportSize({width:1440,height:1100});
  await page.screenshot({path:'docs/assets/alpha-clustering.png',fullPage:true});
  fs.unlinkSync('tests/tmp-alpha.json');
  await click('[data-tab="arithmetic"]');
  for(const op of ['+','-','*','/','compare']){await page.selectOption('#operator',op);await click('#operation-form button');assert.ok(!(await page.locator('#operation-result').innerText()).includes('Выберите аргументы'));}
  await page.locator('#value-name').fill('Zero');await page.locator('#shape').fill('2');await page.locator('#scale').fill('1');await page.locator('#shift').fill('-.5');await click('#value-form button[type=submit]');
  const len=await page.locator('#operand-b option').count();await page.selectOption('#operand-a','0');await page.selectOption('#operand-b',String(len-1));await page.selectOption('#operator','/');await click('#operation-form button');assert.match(await page.locator('#notice').innerText(),/ноль/);
  const download=page.waitForEvent('download');await click('#export-btn');const saved=await download;await saved.saveAs('tests/tmp-project.json');
  const before=await page.locator('#stat-n').innerText();await page.locator('#import-file').setInputFiles('tests/tmp-project.json');await page.waitForFunction(()=>document.getElementById('notice').textContent.startsWith('Проект загружен'));assert.equal(await page.locator('#stat-n').innerText(),before);
  await click('[data-tab="data"]');await page.locator('#search').fill('Zero');assert.equal(await page.locator('#data-body tr').count(),1);await click('#data-body .delete');assert.equal(await page.locator('#data-body tr').count(),0);
  await click('[data-tab="journal"]');assert.match(await page.locator('#log-content').innerText(),/Импорт/);
  const logDownload=page.waitForEvent('download');await click('#log-btn');await (await logDownload).saveAs('tests/downloads/session.log');
  assert.match(fs.readFileSync('tests/downloads/session.log','utf8'),/Арифметика/);
  await click('[data-tab="overview"]');
  const csvDownload=page.waitForEvent('download');await click('#csv-btn');await (await csvDownload).saveAs('tests/downloads/data.csv');
  assert.equal(fs.readFileSync('tests/downloads/data.csv','utf8').trim().split('\n').length,Number(await page.locator('#stat-n').innerText())+1);
  await page.setViewportSize({width:390,height:844});await click('[data-tab="overview"]');
  await page.screenshot({path:'docs/assets/mobile.png',fullPage:true});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Mobile horizontal overflow');
  for(const endpoint of ['/api/generate','/api/cluster','/api/values','/api/operations','/api/projects/validate'])assert.ok(requests.includes(endpoint),'Missing backend call '+endpoint);
  const beforeFailure=await page.locator('#stat-n').innerText();
  await page.route('**/api/generate',route=>route.abort());await click('#generate-form button');assert.match(await page.locator('#notice').innerText(),/Нет связи/);assert.equal(await page.locator('#stat-n').innerText(),beforeFailure);await page.unroute('**/api/generate');
  assert.deepEqual(errors,[]);console.log('UI PASS: '+(process.env.APP_URL||'http://localhost:8080')+', initial demo, 300 objects, both clustering modes, five operations, division guard, JSON roundtrip, search/delete, journal, mobile layout.');
  await browser.close();fs.unlinkSync('tests/tmp-project.json');
})().catch(e=>{console.error(e);process.exit(1);});
