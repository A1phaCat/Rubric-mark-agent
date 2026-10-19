const { test, expect } = require('@playwright/test');

async function cleanupBatch(request, batchId) {
  if (!batchId) return;
  let response = await request.get(`/api/v1/batches/${batchId}`);
  if (!response.ok()) return;
  let batch = (await response.json()).batch;
  if (batch.status === 'processing') {
    const cancelled = await request.post(`/api/v1/batches/${batchId}/cancel`, {
      data: { version: batch.version, reason: 'E2E cleanup' },
    });
    if (cancelled.ok()) batch.version = (await cancelled.json()).version;
  }
  await request.delete(`/api/v1/batches/${batchId}?version=${batch.version}`);
}

const pages = [
  '00-home.html', '01-upload.html', '01a-rubric-import.html', '02-batch-status.html',
  '03b-review-split.html', '04-batch-complete.html', '05-mark-report.html',
  '06-rubrics.html', '07-batches.html'
];

for (const name of pages) {
  test(`mock smoke: ${name}`, async ({ page }) => {
    await page.goto(`/${name}?mocks=1`);
    await expect(page.locator('html')).toHaveAttribute('data-api-state', 'ready');
    await expect(page.locator('body')).toBeVisible();
  });
}

test('mock review uses injected single-item fixture, not a URL mode', async ({ page }) => {
  await page.addInitScript(() => { window.MARKER_TEST_FIXTURE = 'single'; });
  await page.goto('/03b-review-split.html?mocks=1&submission_id=sub_asgn2_000001');
  await expect(page.locator('html')).toHaveAttribute('data-api-state', 'ready');
  await page.locator('#btnNext').click();
  await expect(page.locator('#endCard')).toContainText('Batch complete');
});

test('local-fake API completes a new single-file batch', async ({ request, page }) => {
  let createdBatchId = null;
  try {
  const batchResponse = await request.post('/api/v1/batches', { data: { name:'E2E single file', unit:'TEST1000', term_id:'term_2026s2', due_at:null, rubric_id:'rub_criticalessay', rubric_version:1 } });
  expect(batchResponse.ok()).toBeTruthy();
  const batch = (await batchResponse.json()).batch;
  createdBatchId = batch.id;
  const upload = await request.post(`/api/v1/batches/${batch.id}/files`, { multipart: { files: { name:'SID-99999.txt', mimeType:'text/plain', buffer:Buffer.from('A deterministic test submission.') } } });
  expect(upload.ok()).toBeTruthy();
  const started = await request.post(`/api/v1/batches/${batch.id}/start?sample=3`, { data: { provider:'fake', model:'fake-marker-v1', concurrency:1, external_processing_acknowledged:false, estimated_cost_acknowledged:true } });
  expect(started.ok()).toBeTruthy();
  const listing = await request.get(`/api/v1/batches/${batch.id}/submissions`);
  const submission = (await listing.json()).items[0];
  const allBatches = await request.get('/api/v1/batches');
  expect((await allBatches.json()).items.some((item) => item.id === batch.id)).toBeTruthy();
  await page.goto(`/03b-review-split.html?submission_id=${submission.id}`);
  await expect(page.locator('#doc')).toContainText('A deterministic test submission.');
  await expect(page.locator('.doc-bar .file span')).toContainText('1 page');
  await page.locator('#btnNext').click();
  await expect(page.locator('#endCard')).toContainText('Batch complete');
  const results = await request.get(`/api/v1/batches/${batch.id}/results`);
  expect((await results.json()).batch.status).toBe('completed');
  const report = await request.get(`/api/v1/submissions/${submission.id}/report?audience=student`);
  const reportBody = await report.json();
  expect(reportBody.ai_total).toBeUndefined();
  } finally {
    await cleanupBatch(request, createdBatchId);
  }
});

test('setup UI parses variable levels and opens the newly created batch', async ({ page }) => {
  const originalSettings = await (await page.request.get('/api/v1/settings/ai')).json();
  let createdBatchId = null;
  let createdRubric = null;
  try {
    await page.request.put('/api/v1/settings/ai', { data: { provider:'fake', model:'fake-marker-v1', base_url:null } });
    await page.goto('/01-upload.html');
    await page.locator('#fillSample').click();
    await page.locator('#parseBtn').click();
    await expect(page.locator('#parseState')).toContainText('Found 3 criteria');
    await expect(page.locator('.crit')).toHaveCount(3);
    await page.locator('.crit').first().locator('.fold').click();
    await expect(page.locator('.crit').first().locator('.band')).toHaveCount(4);
    await page.locator('#zipIn').setInputFiles({
      name: 'SID-56320.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('A local validation submission.'),
    });
    await expect(page.locator('#startBtn')).toBeEnabled();
    await page.locator('#startBtn').click();
    await page.waitForURL(/02-batch-status\.html\?batch_id=bat_/);
    createdBatchId = new URL(page.url()).searchParams.get('batch_id');
    const createdBatchResponse = await page.request.get(`/api/v1/batches/${createdBatchId}`);
    const createdBatch = (await createdBatchResponse.json()).batch;
    createdRubric = createdBatch.rubric;
    await expect(page.locator('#batchMain h1')).toContainText('Short response rubric');
    await expect(page.locator('#batchMain')).toContainText('3 criteria');
    await expect(page.locator('#batchMain')).toContainText('9 marks');
    await expect(page.locator('#batchMain')).toContainText('SID-56320');
    await page.locator('.start-btn').click();
    await expect(page.locator('#doc')).toContainText('A local validation submission.');
    await expect(page.locator('.crit-card:visible')).toHaveCount(3);
    await expect(page.locator('.crit-strip a').first()).toContainText('C1');
    await expect(page.locator('.crit-card').first().locator('.crit-desc details')).not.toHaveAttribute('open', '');
    await expect(page.locator('.crit-card').first().locator('.crit-desc')).toContainText('Excellent (3)');
    await expect(page.locator('.ab-crumbs ol li:nth-child(2) a')).toContainText('Short response rubric');
    await expect(page.locator('#bcCur')).toHaveText('SID-56320');
    await expect(page.locator('.doc-bar .file b')).toHaveText('SID-56320.txt');
    await expect(page.locator('.doc-bar .file span')).toContainText('evidence span');
    await expect(page.locator('.crit-card:visible .evidence:visible')).toHaveCount(3);
    await expect(page.getByText('Show all evidence')).toBeVisible();
    await page.locator('.crit-card').first().locator('.score-input').fill('2');
    await page.locator('.crit-card').first().locator('.comment-field textarea').fill('Adjusted during E2E review.');
    await page.locator('#btnNext').click();
    await expect(page.locator('#endCard')).toContainText('Batch complete');
    await page.goto('/07-batches.html');
    await expect(page.locator('html')).toHaveAttribute('data-api-state', 'ready');
    const createdRow = page.locator('.brow', { hasText:'Short response rubric (9 marks) — validation batch' }).first();
    await expect(createdRow).toBeVisible();
    await expect(createdRow.locator('[data-act="delete"]')).toBeVisible();
    await page.goto('/06-rubrics.html');
    await expect(page.locator('html')).toHaveAttribute('data-api-state', 'ready');
    await page.locator('#q').fill('Short response rubric (9 marks)');
    await expect(page.locator('.rub').first()).toBeVisible();
    await page.locator('.rub').first().locator('[data-act="preview"]').first().click();
    await expect(page.locator('#dBody .crit')).toHaveCount(3);
    await expect(page.locator('#dBody .band')).toHaveCount(12);
    await expect(page.locator('#dChecks')).toContainText('Maximum total: 9 marks');
  } finally {
    await cleanupBatch(page.request, createdBatchId);
    if (createdRubric && createdRubric.id) {
      await page.request.delete(`/api/v1/rubrics/${createdRubric.id}?version=${createdRubric.version}`);
    }
    await page.request.put('/api/v1/settings/ai', {
      data: {
        provider: originalSettings.provider,
        model: originalSettings.model,
        base_url: originalSettings.base_url,
      },
    });
  }
});

