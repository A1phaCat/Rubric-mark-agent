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
  const rubricCount = page.locator('#recentRubrics .r-count').first();
  await expect(rubricCount).toHaveText(/\d+ criteria/);
  expect(await rubricCount.evaluate(el => getComputedStyle(el).whiteSpace)).toBe('nowrap');
  const longRubricName = page.locator('#recentRubrics .r-main').nth(1);
  expect(await longRubricName.evaluate(el => el.clientWidth <= el.scrollWidth)).toBeTruthy();
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
  await page.route(/\/api\/v1\/batches\/bat_sample_asgn1\/results$/, async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.batch.status = 'completed';
    body.batch.finalised_at = null;
    body.locked = false;
    await route.fulfill({ response, json:body });
  });
  await page.goto('/04-batch-complete.html?batch_id=bat_sample_asgn1');
  await expect(page.locator('html')).toHaveAttribute('data-api-state', 'ready');
  const finalise = page.getByRole('button', { name: 'Finalise & lock marks' });
  await finalise.click();
  const finaliseDialog = page.locator('#finaliseModal');
  await expect(finaliseDialog).toBeVisible();
  await expect(finaliseDialog.locator('#finaliseTitle')).toHaveText('Finalise and lock marks?');
  await expect(finaliseDialog).toContainText('provide a reason for the audit history');
  await expect(page.locator('#finaliseCancel')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(finaliseDialog).toBeHidden();
  await expect(finalise).toBeFocused();
  const edit = page.getByRole('link', { name: 'Edit marks' }).first();
  await expect(edit).toBeVisible();
  await edit.click();
  await expect(page.locator('.score-input').first()).toBeEnabled();

  await page.goto('/04-batch-complete.html?batch_id=bat_sample_quiz3');
  await expect(page.locator('html')).toHaveAttribute('data-api-state', 'ready');
  await expect(page.getByRole('link', { name: 'Edit marks' })).toHaveCount(0);
  const reopen = page.getByRole('button', { name: 'Reopen for changes' });
  await expect(reopen).toBeVisible();
  await reopen.click();
  const dialog = page.locator('#reopenModal');
  const reason = page.locator('#reopenReason');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('saved with the batch history');
  await expect(reason).toBeFocused();
  await expect(page.locator('#reopenConfirm')).toBeDisabled();
  await reason.fill('Correcting a moderation issue');
  await expect(page.locator('#reopenConfirm')).toBeEnabled();
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(reopen).toBeFocused();
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

test('end-of-review dialog discovers the next AI-ready submission without refresh', async ({ page }) => {
  const listing = await (await page.request.get('/api/v1/batches/bat_sample_asgn2/submissions')).json();
  const current = listing.items.find((item) => item.status === 'ai_done' || item.status === 'in_review');
  let queueChecks = 0;
  await page.route(new RegExp(`/api/v1/submissions/${current.id}/confirm$`), async route => route.fulfill({
    contentType:'application/json',
    body:JSON.stringify({
      submission_id:current.id,status:'confirmed',batch_status:'processing',next_id:null,
      remaining:{ready:0,processing:103,failed:0},
    }),
  }));
  await page.route(/\/api\/v1\/batches\/bat_sample_asgn2\/queue\/next/, async route => {
    queueChecks += 1;
    const nextReady = queueChecks > 1;
    await route.fulfill({contentType:'application/json',body:JSON.stringify({
      next_id:nextReady?'sub_new_ready':null,
      next_sid:nextReady?'SID-424242':null,
      remaining:{ready:nextReady?1:0,needs_manual:0,processing:nextReady?102:103,failed:0,confirmed:5,total:108},
    })});
  });

  await page.goto(`/03b-review-split.html?submission_id=${current.id}`);
  await page.locator('#btnNext').click();
  await expect(page.locator('#endCard')).toContainText('Waiting for the AI');
  await expect(page.locator('#endCard')).toContainText('no refresh needed');
  await expect(page.locator('#endCard')).toContainText('Next submission is ready', {timeout:7000});
  const openNext = page.getByRole('link', {name:'Open SID-424242 →'});
  await expect(openNext).toBeVisible();
  await expect(openNext).toHaveAttribute('href', /submission_id=sub_new_ready/);
});

test('large processing batches show compact live activity without overlapping actions', async ({ page }) => {
  const batch = {
    id:'bat_ui_activity', name:'Short response rubric (9 marks) — validation batch', status:'processing', display_status:'processing',
    version:2, pinned:true, created_at:'2026-10-27T00:00:00Z', due_at:null,
    term:{id:'term_2026s2',label:'Semester 2, 2026'},
    rubric:{id:'rub_ui',title:'Short response rubric with a deliberately long title (9 marks)',criteria_count:3,total_weight:9},
    counts:{total:108,processed:1,ready:1,confirmed:0,needs_manual:0,processing:107,active:3,queued:104,not_started:0,failed:0},
  };
  await page.route(/\/api\/v1\/batches$/, async route => route.fulfill({contentType:'application/json',body:JSON.stringify({items:[batch]})}));
  await page.setViewportSize({width:1080,height:800});
  await page.goto('/07-batches.html');

  const row = page.locator('.brow.is-processing');
  await expect(row).toBeVisible();
  const rubricBox = await row.locator('.b-rub').boundingBox();
  const actionsBox = await row.locator('.batch-actions').boundingBox();
  expect(rubricBox.x + rubricBox.width).toBeLessThanOrEqual(actionsBox.x);
  await expect(row.locator('.b-ptxt')).toContainText('3 active · 104 queued');
  expect(await row.locator('.bar span').evaluate(el => getComputedStyle(el, '::after').animationName)).toBe('batch-flow');
  expect(await row.locator('.pill.processing').evaluate(el => getComputedStyle(el).animationName)).toBe('batch-breathe');

  const waitingBatch = JSON.parse(JSON.stringify(batch));
  waitingBatch.counts.active = 0;
  waitingBatch.counts.queued = 107;
  waitingBatch.eta_seconds = 1080;
  waitingBatch.queue = {
    jobs_ahead:93,
    blocked_by:{id:'bat_earlier',name:'Earlier validation batch',status:'processing',created_at:'2026-10-27T00:46:00Z'},
  };
  await page.route(/\/api\/v1\/batches\/bat_ui_activity$/, async route => route.fulfill({contentType:'application/json',body:JSON.stringify({batch:waitingBatch})}));
  await page.route(/\/api\/v1\/batches\/bat_ui_activity\/submissions/, async route => route.fulfill({contentType:'application/json',body:JSON.stringify({
    total:108,page:1,page_size:50,items:[
      {id:'sub_waiting',sid:'SID-10001',filename:'SID-10001.pdf',status:'queued',progress:'Queued for extraction and AI grading',flags:[],version:1},
      {id:'sub_queued',sid:'SID-10002',filename:'SID-10002.pdf',status:'queued',progress:'Queued for extraction and AI grading',flags:[],version:1},
      {id:'sub_review',sid:'SID-10003',filename:'SID-10003.pdf',status:'in_review',progress:'In review',ai_total:8,flags:[],version:1},
      {id:'sub_ready',sid:'SID-10004',filename:'SID-10004.pdf',status:'ai_done',progress:'Ready for review',ai_total:8,flags:[],version:1},
      {id:'sub_cancelled',sid:'SID-10005',filename:'SID-10005.pdf',status:'cancelled',progress:'Cancelled',flags:[],version:1},
      {id:'sub_failed',sid:'SID-10006',filename:'SID-10006.pdf',status:'failed',progress:'Failed',flags:[],error:{message:'Provider error'},version:1},
    ],
  })}));
  await page.goto('/02-batch-status.html?batch_id=bat_ui_activity');
  await expect(page.locator('.live-work')).toHaveText(/Waiting behind.*Earlier validation batch.*93 jobs ahead/);
  await expect(page.locator('.live-work a')).toHaveAttribute('href', /batch_id=bat_earlier/);
  await expect(page.locator('.progress-stats .eta')).toHaveText('~18 min remaining');
  await expect(page.locator('.status-pill.in-review')).toHaveText('In review');
  await expect(page.locator('.status-pill.ready')).toHaveText('Ready for review');
  expect(await page.locator('.status-pill.in-review').evaluate(el => getComputedStyle(el).color)).toBe('rgb(0, 125, 193)');
  expect(await page.locator('.status-pill.ready').evaluate(el => getComputedStyle(el).color)).toBe('rgb(47, 122, 69)');
  await expect(page.locator('.status-pill.failed')).toHaveCount(2);
  await expect(page.locator('.status-pill.failed').nth(0)).toHaveText('Cancelled');
  await expect(page.locator('.status-pill.failed').nth(1)).toHaveText('Failed');
  await expect(page.locator('tr.active-work')).toHaveCount(0);
  await expect(page.locator('tr.queued-work')).toHaveCount(2);
  await expect(page.locator('.pager')).toContainText('Showing 1–30 of 108');
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

test('ZIP selections defer the submission count and estimate until unpacked', async ({ page }) => {
  await page.goto('/01-upload.html');
  await page.locator('#zipIn').setInputFiles({
    name:'submissions.zip',
    mimeType:'application/zip',
    buffer:Buffer.from('placeholder ZIP content'),
  });

  await expect(page.locator('#vSub')).toHaveText('1 ZIP · count after upload');
  await expect(page.locator('#vTime')).toHaveText('—');
  await expect(page.locator('#aiPrepEstimate')).toHaveAttribute('title', /after the ZIP is unpacked/i);
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
  await expect(queue.locator('.sid-format')).toContainText('Enter 5–12 digits or SID-123456');
  const firstName = await queue.locator('.file').first().locator('.nm').textContent();
  const firstRow = queue.locator('.file', { hasText:firstName });
  await firstRow.locator('.sid-input').fill('123456');
  await expect(firstRow).toHaveClass(/ok/);
  await expect(firstRow.locator('.sid-input')).toHaveValue('SID-123456');
  await expect(queue.locator('.file').last().locator('.nm')).toHaveText(firstName);
  await expect(queue.locator('summary')).toContainText('Fix 11 files');
  await expect(queue.locator('.sid-input').first()).toBeFocused();
});

test('rubric import keeps matrix review and returns a saved rubric to batch setup', async ({ page }) => {
  let savedPayload;
  const parsedRubric = {
    title:'Imported architecture rubric', total_score:10, total_score_source:'stated',
    criteria:[{
      name:'Architecture', weight:10, description:'Assess design trade-offs.', stated_percent:25,
      grading_mode:'analytic', scoring_mode:'score_range', score_mapping:'range', granularity:0.5,
      aspects:[{ label:'Trade-offs', required:true }], prov:{ name:'extracted' }, source_text:{ name:'Architecture (25%)' },
      levels:[
        { id:'excellent', label:'Excellent', points:10, min_score:8, max_score:10, description:'Well justified.', prov:{ description:'inferred' }, source_text:{ description:'Well justified.' } },
        { id:'developing', label:'Developing', points:7, min_score:0, max_score:7.5, description:'Partly justified.', prov:{ description:'extracted' }, source_text:{} },
      ],
    }],
  };
  await page.route('**/api/v1/rubrics/parse', async route => route.fulfill({
    contentType:'application/json',
    body:JSON.stringify({ rubric:parsedRubric, parser:'ai-recovery:test', warnings:[], assumptions:[], questions:[] }),
  }));
  await page.route('**/api/v1/rubrics', async route => {
    if (route.request().method() !== 'POST') return route.fallback();
    savedPayload = route.request().postDataJSON();
    await route.fulfill({
      status:201, contentType:'application/json',
      body:JSON.stringify({ rubric:{ id:'rub_e2e_import', version:1, title:savedPayload.title, source:savedPayload.source, criteria:savedPayload.criteria } }),
    });
  });

  await page.goto('/01a-rubric-import.html?from=setup');
  await expect(page.locator('#saveRubric')).toHaveText('Save & use in batch');
  await page.getByRole('tab', { name:'Paste / Image' }).click();
  await page.locator('#paste').fill('Rubric text');
  await page.locator('#pasteBtn').click();
  await expect(page.locator('#criteria .crit')).toHaveCount(1);
  await expect(page.getByRole('button', { name:'✓ Looks right' })).toBeVisible();
  await page.getByRole('button', { name:'+ Add level' }).click();
  const addedLevel = page.locator('#criteria .cell').last();
  await addedLevel.locator('.label-in').fill('Missing');
  await addedLevel.locator('.pts-in').fill('0');
  await page.locator('#addCriterion').click();
  const addedCriterion = page.locator('#criteria .crit').last();
  await expect(addedCriterion.locator('.c-name-ed')).toHaveAttribute('data-placeholder', 'Criterion name');
  await addedCriterion.locator('.c-name-ed').fill('Professional communication');
  await page.getByRole('button', { name:'✓ Looks right' }).click();
  await page.locator('#saveRubric').click();
  await page.waitForURL(/01-upload\.html#saved=1&rubric=/);
  await expect(page.locator('#rTitle')).toHaveValue('Imported architecture rubric');
  expect(savedPayload.criteria[0].scoring_mode).toBe('score_range');
  expect(savedPayload.criteria[0].aspects).toEqual([{ label:'Trade-offs', required:true }]);
  expect(savedPayload.criteria[0].levels[0].min_score).toBe(8);
  expect(savedPayload.criteria[0].levels[0].prov).toEqual({ description:'inferred' });
  expect(savedPayload.criteria[0].levels).toHaveLength(3);
  expect(savedPayload.criteria[1].name).toBe('Professional communication');
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

test('external AI consent uses the in-app modal and supports keyboard cancellation', async ({ page }) => {
  await page.goto('/01-upload.html');

  await page.evaluate(() => {
    window.__externalConsentResult = undefined;
    window.MarkerConfirmExternalProcessing('minimax').then((result) => {
      window.__externalConsentResult = result;
    });
  });

  const dialog = page.locator('#externalConsent');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('External AI processing');
  await expect(dialog.locator('#consentTitle')).toHaveText('Send submissions to Minimax?');
  await expect(dialog.locator('#consentCopy')).toContainText('Uploaded submission text will be sent to Minimax');
  await expect(page.locator('#consentContinue')).toBeFocused();

  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect.poll(() => page.evaluate(() => window.__externalConsentResult)).toBe(false);

  await page.evaluate(() => {
    window.__externalConsentResult = undefined;
    window.MarkerConfirmExternalProcessing('minimax').then((result) => {
      window.__externalConsentResult = result;
    });
  });
  await page.locator('#consentContinue').click();
  await expect(dialog).toBeHidden();
  await expect.poll(() => page.evaluate(() => window.__externalConsentResult)).toBe(true);
});

test('cancelling external processing restores focus and rubric edits discard the pending batch', async ({ page }) => {
  let deletedBatch = false;
  await page.route('**/api/v1/rubrics', async route => {
    if(route.request().method()!=='POST')return route.fallback();
    await route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({rubric:{id:'rub_pending',version:1}})});
  });
  await page.route('**/api/v1/batches', async route => {
    if(route.request().method()!=='POST')return route.fallback();
    await route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({batch:{id:'bat_pending',version:1}})});
  });
  await page.route('**/api/v1/batches/bat_pending/files', async route => route.fulfill({
    contentType:'application/json',
    body:JSON.stringify({summary:{accepted:1,duplicates:0,skipped:0,needs_sid:0},files:[{name:'SID-12345.txt',status:'accepted',sid_guess:'SID-12345',submission_id:'sub_pending',version:1}]})
  }));
  await page.route('**/api/v1/settings/ai', async route => route.fulfill({contentType:'application/json',body:JSON.stringify({provider:'minimax',model:'test'})}));
  await page.route('**/api/v1/settings/canvas', async route => route.fulfill({contentType:'application/json',body:'{}'}));
  await page.route('**/api/v1/batches/bat_pending/start', async route => {
    await new Promise(resolve => setTimeout(resolve, 500));
    await route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({error:{message:'Test stop'}})});
  });
  await page.route(/\/api\/v1\/batches\/bat_pending\?version=1$/, async route => {
    deletedBatch = true;
    await route.fulfill({status:204,body:''});
  });

  await page.goto('/01-upload.html');
  await page.locator('#pasteText').fill([
    'Draft rubric', 'CRITERION: Analysis', 'MAX: 3',
    'Excellent (3): Complete.', 'Missing (0): Absent.',
  ].join('\n'));
  await page.locator('#parseBtn').click();
  await expect(page.locator('.crit')).toHaveCount(1);
  await page.locator('#zipIn').setInputFiles({name:'SID-12345.txt',mimeType:'text/plain',buffer:Buffer.from('Submission')});
  const start=page.locator('#startBtn');
  await start.click();
  await expect(page.locator('#externalConsent')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('#externalConsent')).toBeHidden();
  await expect(start).toBeFocused();
  await expect(start).toHaveText('Start processing →');

  await start.click();
  await page.locator('#consentContinue').click();
  await expect(page.locator('#why')).toHaveText('AI is grading 1 criterion · estimated <1 min');
  await expect(start).toBeEnabled();

  await page.locator('.crit').first().locator('.fold').click();
  await page.locator('.crit').first().locator('[data-f="description"]').fill('Updated assessment description');
  await expect.poll(() => deletedBatch).toBe(true);
  await expect(start).toHaveText('Start batch →');
  await expect(page.locator('#zipFiles .upload-summary')).toContainText('1 file selected');
});

test('edited library rubrics create the batch with the saved new version', async ({ page }) => {
  await page.goto('/01-upload.html');
  await expect(page.locator('html')).toHaveAttribute('data-api-state', 'ready');
  await page.locator('#libList .lib-row').first().click();
  await page.locator('#rTitle').fill('Edited library rubric');
  await page.locator('#zipIn').setInputFiles({name:'SID-23456.txt',mimeType:'text/plain',buffer:Buffer.from('Submission')});
  await page.evaluate(() => {
    window.__updatedRubric = null;
    window.__createdBatch = null;
    MarkerAPI.getRubric = rubricId => Promise.resolve({rubric:{id:rubricId,version:7}});
    MarkerAPI.updateRubric = (rubricId, payload) => {
      window.__updatedRubric = {rubricId, payload};
      return Promise.resolve({rubric:{id:rubricId,version:8}});
    };
    MarkerAPI.createBatch = payload => {
      window.__createdBatch = payload;
      return Promise.resolve({batch:{id:'bat_edited_rubric',version:1}});
    };
    MarkerAPI.uploadFiles = () => Promise.resolve({summary:{accepted:0,duplicates:0,skipped:1,needs_sid:0},files:[]});
  });

  await page.locator('#startBtn').click();
  await expect.poll(() => page.evaluate(() => window.__createdBatch)).not.toBeNull();
  const saved = await page.evaluate(() => ({updated:window.__updatedRubric, batch:window.__createdBatch}));
  expect(saved.updated.payload.version).toBe(7);
  expect(saved.updated.payload.title).toBe('Edited library rubric');
  expect(saved.batch.rubric_id).toBe(saved.updated.rubricId);
  expect(saved.batch.rubric_version).toBe(8);
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

  const estimateFiles = Array.from({ length:10 }, (_, index) => ({
    name:`SID-${70000 + index}.txt`, mimeType:'text/plain', buffer:Buffer.from(`Submission ${index + 1}`),
  }));
  await page.locator('#zipIn').setInputFiles(estimateFiles);
  await expect(page.locator('#vRub')).toHaveText('Draft');
  await expect(page.locator('#vRub')).toHaveAttribute('title', 'Draft rubric');
  await expect(page.locator('#aiPrepEstimate .k')).toHaveText('AI prep');
  await expect(page.locator('#vTime')).toHaveText('~1–2 min');
  await expect(page.locator('#aiPrepEstimate')).toHaveAttribute('title', /rubric setup is reused once.*10 submissions are analysed independently.*one processing worker/i);
});

