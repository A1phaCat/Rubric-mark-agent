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

/* Every page is rendered from the database. The sample batches are loaded with
   `python -m app.sample.seed`; their submission IDs are looked up through the API. */
async function sampleUrls(request) {
  const asgn2 = await (await request.get('/api/v1/batches/bat_sample_asgn2/submissions')).json();
  const quiz3 = await (await request.get('/api/v1/batches/bat_sample_quiz3/submissions')).json();
  const ready = asgn2.items.find((item) => item.status === 'ai_done' || item.status === 'in_review');
  return {
    '00-home.html': '/00-home.html',
    '01-upload.html': '/01-upload.html',
    '01a-rubric-import.html': '/01a-rubric-import.html',
    '02-batch-status.html': '/02-batch-status.html?batch_id=bat_sample_asgn2',
    '03b-review-split.html': `/03b-review-split.html?submission_id=${ready.id}`,
    '04-batch-complete.html': '/04-batch-complete.html?batch_id=bat_sample_quiz3',
    '05-mark-report.html': `/05-mark-report.html?submission_id=${quiz3.items[0].id}`,
    '06-rubrics.html': '/06-rubrics.html',
    '07-batches.html': '/07-batches.html',
  };
}

test('every page renders sample data from the API', async ({ page }) => {
  const urls = await sampleUrls(page.request);
  for (const url of Object.values(urls)) {
    await page.goto(url);
    await expect(page.locator('html')).toHaveAttribute('data-api-state', 'ready');
    await expect(page.locator('[data-load-error]')).toHaveCount(0);
  }
});

test('home lists pinned sample batches and the database counts', async ({ page }) => {
  await page.goto('/00-home.html');
  await expect(page.locator('html')).toHaveAttribute('data-api-state', 'ready');
  await expect(page.locator('#homeBatches .batch')).toHaveCount(3);
  await expect(page.locator('#homeBatches')).toContainText('ASGN2 — Critical Essay');
  await expect(page.locator('#homeStats .stat').nth(2)).toContainText('1');
  await expect(page.locator('#homeQueue .q-item').first()).toContainText('SID-');
});

test('results and report pages render stored marks, feedback and evidence', async ({ page }) => {
  await page.goto('/04-batch-complete.html?batch_id=bat_sample_quiz3');
  await expect(page.locator('html')).toHaveAttribute('data-api-state', 'ready');
  await expect(page.locator('#resultsMain h1')).toContainText('Quiz 3');
  await expect(page.locator('table.subs tbody tr')).toHaveCount(5);
  await page.locator('table.subs .rep').first().click();
  await expect(page.locator('html')).toHaveAttribute('data-api-state', 'ready');
  await expect(page.locator('.ai-sum')).toBeVisible();
  await expect(page.locator('.crit .evidence-used').first()).toContainText('p.1');
  await page.locator('.audience [data-a="student"]').click();
  await expect(page.locator('.eyebrow')).toContainText('student view');
  await expect(page.locator('.ai-note')).toHaveCount(0);
});

test('completed results can re-enter review while finalised results stay locked', async ({ page }) => {
  await page.goto('/04-batch-complete.html?batch_id=bat_sample_asgn1');
  await expect(page.locator('html')).toHaveAttribute('data-api-state', 'ready');
  const edit = page.getByRole('link', { name: 'Edit marks' }).first();
  await expect(edit).toBeVisible();
  await edit.click();
  await expect(page.locator('.score-input').first()).toBeEnabled();

  await page.goto('/04-batch-complete.html?batch_id=bat_sample_quiz3');
  await expect(page.locator('html')).toHaveAttribute('data-api-state', 'ready');
  await expect(page.getByRole('link', { name: 'Edit marks' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Reopen for changes' })).toBeVisible();
});

test('review header refreshes batch progress while AI processing continues', async ({ page }) => {
  const listing = await (await page.request.get('/api/v1/batches/bat_sample_asgn2/submissions')).json();
  const ready = listing.items.find((item) => item.status === 'ai_done' || item.status === 'in_review');
  await page.route(/\/api\/v1\/submissions\/[^/]+\/review$/, async (route) => {
    const response = await route.fetch(), body = await response.json();
    body.batch.counts.processing = 1;
    await route.fulfill({ response, json:body });
  });
  await page.route(/\/api\/v1\/batches\/bat_sample_asgn2$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ batch: { id:'bat_sample_asgn2', counts:{ total:48, confirmed:17, ready:5, needs_manual:0, processing:26, not_started:0 } } }),
    });
  });

  await page.goto(`/03b-review-split.html?submission_id=${ready.id}`);
  await expect(page.locator('#pgDone')).toHaveText('17', { timeout:7000 });
  await expect(page.locator('#pgReady')).toHaveText('22');
  await expect(page.locator('#pgProc')).toHaveText('26');
});

test('large submission selections collapse matched files into a summary', async ({ page }) => {
  await page.goto('/01-upload.html');
  const files = Array.from({ length:20 }, (_, index) => ({
    name:`SID-${10000 + index}.txt`,
    mimeType:'text/plain',
    buffer:Buffer.from(`Submission ${index + 1}`),
  }));
  await page.locator('#zipIn').setInputFiles(files);

  await expect(page.locator('#zipFiles .upload-summary')).toContainText('20 files selected');
  await expect(page.locator('#zipFiles .upload-summary')).toContainText('20 SIDs found');
  await expect(page.locator('#zipFiles .file-details')).not.toHaveAttribute('open', '');
  await expect(page.locator('#zipFiles .file-details summary')).toHaveText('View all 20 matched files');
  await expect(page.locator('#zipFiles .file-list-scroll .file')).toHaveCount(20);
});

test('SID repair queue confirms valid input and advances to the next file', async ({ page }) => {
  await page.goto('/01-upload.html');
  const files = Array.from({ length:12 }, (_, index) => ({
    name:`submission-${index + 1}.txt`,
    mimeType:'text/plain',
    buffer:Buffer.from(`Submission ${index + 1}`),
  }));
  await page.locator('#zipIn').setInputFiles(files);

  const queue = page.locator('#zipFiles .fix-details');
  await expect(queue).toHaveAttribute('open', '');
  await expect(queue.locator('summary')).toContainText('Fix 12 files');
  const firstName = await queue.locator('.file').first().locator('.nm').textContent();
  const firstRow = queue.locator('.file', { hasText:firstName });
  await firstRow.locator('.sid-input').fill('123456');
  await expect(firstRow).toHaveClass(/ok/);
  await expect(firstRow.locator('.sid-input')).toHaveValue('SID-123456');
  await expect(queue.locator('.file').last().locator('.nm')).toHaveText(firstName);
  await expect(queue.locator('summary')).toContainText('Fix 11 files');
  await expect(queue.locator('.sid-input').first()).toBeFocused();
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
    await page.locator('#pasteText').fill([
      'Short response rubric (9 marks)', '',
      '1. Accuracy — 3 marks', 'Excellent (3): Correct and complete.', 'Good (2): Mostly correct.', 'Basic (1): Partly correct.', 'Missing (0): Absent.', '',
      '2. Reasoning — 3 marks', 'Excellent (3): Clear and supported.', 'Good (2): Sound but brief.', 'Basic (1): Limited.', 'Missing (0): None.', '',
      '3. Communication — 3 marks', 'Excellent (3): Precise.', 'Good (2): Clear overall.', 'Basic (1): Sometimes unclear.', 'Missing (0): Cannot be assessed.',
    ].join('\n'));
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
    // A batch created during the demo is saved and pinned above the samples.
    await expect(page.locator('.brow').first()).toContainText('Short response rubric (9 marks) — validation batch');
    await expect(createdRow.locator('[data-act="pin"]')).toContainText('Pinned');
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

test('setup UI locates and repairs a criterion with only one scoring level', async ({ page }) => {
  await page.goto('/01-upload.html');
  await page.locator('#pasteText').fill([
    'Draft rubric',
    'CRITERION: Analysis',
    'MAX: 3',
    'Excellent (3): Complete and well supported.',
  ].join('\n'));
  await page.locator('#parseBtn').click();

  const shortLevels = page.locator('[data-check="short-levels"]');
  await expect(shortLevels).toContainText('1 criterion needs at least 2 scoring levels');
  await shortLevels.click();
  await expect(page.locator('.crit').first()).toHaveClass(/open/);
  await expect(page.locator('.crit').first().locator('[data-add-level]')).toBeFocused();

  await page.locator('.crit').first().locator('[data-add-level]').click();
  await expect(page.locator('.crit').first().locator('.band')).toHaveCount(2);
  const added = page.locator('.crit').first().locator('.band').last();
  await added.locator('[data-f="level-label"]').fill('Missing');
  await added.locator('[data-f="level-points"]').fill('0');

  await expect(page.locator('[data-check="short-levels"]')).toHaveCount(0);
  await expect(page.locator('[data-check="level-fields"]')).toHaveCount(0);
  await expect(page.locator('.crit').first()).not.toHaveClass(/flagged/);
});

