const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');
const pixelmatch = require('pixelmatch').default || require('pixelmatch');
const { PNG } = require('pngjs');

const pages = ['00-home.html','01-upload.html','01a-rubric-import.html','02-batch-status.html','03b-review-split.html','04-batch-complete.html','05-mark-report.html','06-rubrics.html','07-batches.html'];
const sizes = [{name:'desktop',width:1440,height:1000},{name:'mobile',width:390,height:844}];

for (const name of pages) for (const size of sizes) {
  test(`visual ${name} ${size.name}`, async ({ page }) => {
    const baselinePath=path.join('prototype','screenshots',`${name}-${size.name}.png`);
    test.skip(!fs.existsSync(baselinePath),'Run make screenshots once.');
    await page.setViewportSize({width:size.width,height:size.height});
    const asgn2=await (await page.request.get('/api/v1/batches/bat_sample_asgn2/submissions')).json();
    const quiz3=await (await page.request.get('/api/v1/batches/bat_sample_quiz3/submissions')).json();
    const ready=asgn2.items.find((item)=>item.status==='ai_done'||item.status==='in_review');
    const query={'02-batch-status.html':'?batch_id=bat_sample_asgn2','03b-review-split.html':`?submission_id=${ready.id}`,'04-batch-complete.html':'?batch_id=bat_sample_quiz3','05-mark-report.html':`?submission_id=${quiz3.items[0].id}`}[name]||'';
    await page.goto(`/${name}${query}`,{waitUntil:'networkidle'});
    await expect(page.locator('html')).toHaveAttribute('data-api-state','ready');
    const actualBuffer=await page.screenshot({fullPage:true});
    const baseline=PNG.sync.read(fs.readFileSync(baselinePath)), actual=PNG.sync.read(actualBuffer);
    const width=Math.min(baseline.width,actual.width), height=Math.min(baseline.height,actual.height);
    const a=new PNG({width,height}), b=new PNG({width,height});
    PNG.bitblt(baseline,a,0,0,width,height,0,0); PNG.bitblt(actual,b,0,0,width,height,0,0);
    const different=pixelmatch(a.data,b.data,null,width,height,{threshold:0.12});
    const dimensionPenalty=Math.abs(baseline.width*baseline.height-actual.width*actual.height);
    const percent=(different+dimensionPenalty)/Math.max(baseline.width*baseline.height,actual.width*actual.height)*100;
    console.log(`${name} ${size.name}: ${percent.toFixed(3)}% different`);
    expect(percent).toBeLessThan(25);
  });
}
