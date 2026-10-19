const { test, expect } = require('@playwright/test');
const path = require('path');

const pages = ['00-home.html','01-upload.html','01a-rubric-import.html','02-batch-status.html','03b-review-split.html','04-batch-complete.html','05-mark-report.html','06-rubrics.html','07-batches.html'];
const sizes = [{name:'desktop',width:1440,height:1000},{name:'mobile',width:390,height:844}];

for (const name of pages) for (const size of sizes) {
  test(`capture ${name} ${size.name}`, async ({ page }) => {
    await page.setViewportSize({width:size.width,height:size.height});
    await page.goto(`/prototype/${name}`, {waitUntil:'networkidle'});
    await expect(page.locator('body')).toBeVisible();
    await page.screenshot({path:path.join('prototype','screenshots',`${name}-${size.name}.png`),fullPage:true});
  });
}

