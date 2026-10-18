// Read-only browser tests of the actual widget; never connects to MQTT or AWS.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
const widget = path.join(root, 'thingsboard/widgets');
const html = fs.readFileSync(path.join(widget, 'classroom.html'), 'utf8').replaceAll('__CLASSROOM_IMAGE__', 'data:,');
const css = fs.readFileSync(path.join(widget, 'classroom.css'), 'utf8');
const controller = fs.readFileSync(path.join(widget, 'classroom.js'), 'utf8');
const sceneLighting = JSON.parse(fs.readFileSync(path.join(widget, 'lighting-layout.json'), 'utf8'));

async function main() {
  const browser = await chromium.launch({channel:'chrome',headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1517,height:1000}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.setContent('<!doctype html><meta charset="utf-8"><style>body{margin:0}'+css+'</style><div id="widget">'+html+'</div>');
    await page.evaluate(({controller,sceneLighting}) => {
      window.testWidget = {ctx:{$container:[document.querySelector('#widget')],settings:{sceneLighting},data:[]}};
      new Function('self',controller+'\nself.onInit();')(window.testWidget);
      window.setTestValues = function(values) {
        window.testWidget.ctx.data=Object.entries(values).map(([name,value])=>({dataKey:{name},data:[[Date.now(),value]]}));
        window.testWidget.onDataUpdated();
      };
    }, {controller,sceneLighting});
    const summary = page.locator('.cl-people-summary');
    assert.equal((await page.locator('.cl-header h1').innerText()).replace(/\.$/,''),'Classroom A302');
    assert((await page.locator('.cl-room-badge').innerText()).startsWith('A302'));
    assert.equal(await summary.locator('.cl-people-title').innerText(),'Số người hiện trong lớp học');
    assert.equal(await summary.locator('[data-value="occupancy"]').innerText(),'—','Unknown count must not become zero.');
    assert.equal(await summary.locator('[data-value="total_entered"],[data-value="total_exited"]').count(),0);
    for (const occupancy of [0,1,2,35]) {
      await page.evaluate(occupancy=>window.setTestValues({occupancy,total_entered:100,total_exited:99,online:true,last_seen:Date.now(),counter_state:'IDLE',counter_needs_calibration:false,ir_a_blocked:false,ir_b_blocked:false}),occupancy);
      assert.deepEqual(await page.locator('[data-value="occupancy"]').allTextContents(),[String(occupancy),String(occupancy)],'Both locations must show occupancy, not entry/exit totals.');
    }
    await page.evaluate(()=>window.setTestValues({occupancy:2,online:false,last_seen:1,counter_needs_calibration:true,counter_errors:2}));
    assert.equal(await summary.locator('[data-value="occupancy"]').innerText(),'2','Offline retains last-known occupancy.');
    assert.match(await page.locator('[data-value="occupancy_note"]').innerText(),/Số cuối nhận/);
    assert.match(await page.locator('[data-value="counter_note"]').innerText(),/chưa được xác nhận/);
    assert(await page.locator('[data-counter="reset"]').isDisabled());
    for (const width of [1517,850,390]) {
      await page.setViewportSize({width,height:1000});
      assert(await page.locator('.cl-people-count').isVisible());
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No horizontal overflow at '+width+'px.');
    }
    assert.deepEqual(errors,[]);
    await page.evaluate(()=>window.testWidget.onDestroy());
    console.log('PASS occupancy panel: unknown, zero, updates, correct source, offline, calibration and responsive widths.');
  } finally { await browser.close(); }
}
async function live() {
  // Session supplied over stdin, never written to disk or printed.
  const config = JSON.parse(fs.readFileSync(0,'utf8'));
  const browser = await chromium.launch({channel:'chrome',headless:true});
  try {
    const context = await browser.newContext({viewport:{width:1517,height:1100},timezoneId:'Asia/Ho_Chi_Minh'});
    await context.addInitScript(storage=>{for(const [key,value] of Object.entries(storage))localStorage.setItem(key,value);},config.storage);
    const page = await context.newPage();
    await page.goto(config.url,{waitUntil:'domcontentloaded',timeout:60000});
    const summary = page.locator('.cl-people-summary');
    await summary.waitFor({timeout:60000});
    assert.equal((await page.locator('.cl-header h1').innerText()).replace(/\.$/,''),'Classroom A302');
    assert((await page.locator('.cl-room-badge').innerText()).startsWith('A302'));
    assert.equal(await summary.locator('.cl-people-title').innerText(),'Số người hiện trong lớp học');
    assert.equal(await summary.locator('[data-value="total_entered"],[data-value="total_exited"]').count(),0);
    const expected=String(config.expectedOccupancy);
    await page.waitForFunction(expected=>Array.from(document.querySelectorAll('[data-value="occupancy"]')).every(el=>el.textContent===expected),expected,{timeout:15000});
    assert.equal(await page.locator('[data-value="occupancy"]').count(),2);
    assert.deepEqual(await page.locator('[data-value="occupancy"]').allTextContents(),[expected,expected]);
    assert(await page.locator('[data-counter="reset"]').isVisible());
    for(const gate of ['a','b'])assert(await page.locator('[data-gate="'+gate+'"]').isVisible());
    await page.locator('.cl-people-panel').screenshot({path:config.screenshot});
    console.log('PASS live dashboard: current occupancy '+expected+' in both locations; entry/exit totals removed from panel; sensor status and reset retained.');
  } finally { await browser.close(); }
}
(process.argv.includes('--live') ? live() : main()).catch(error=>{console.error(error.message);process.exitCode=1;});
