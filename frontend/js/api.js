(function () {
  /* The only place the browser knows backend URLs. Every page reads and writes through
     these calls; there is no mock or fixture mode — data always comes from the local DB. */
  var base = '/api/v1';
  function request(path, options) {
    options = options || {};
    var headers = Object.assign({}, options.headers || {});
    if (!(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
    return fetch(base + path, Object.assign({}, options, { headers: headers })).then(function (response) {
      if (!response.ok) return response.json().catch(function () { return {}; }).then(function (body) { var error = new Error((body.error && body.error.message) || ('HTTP ' + response.status)); error.status = response.status; error.code = body.error && body.error.code; error.body = body; throw error; });
      var contentType = response.headers.get('content-type') || '';
      return contentType.indexOf('json') >= 0 ? response.json() : response;
    });
  }
  function id(value) { return encodeURIComponent(value); }
  function query(params) {
    var parts = Object.keys(params || {}).filter(function (key) { return params[key] != null && params[key] !== ''; }).map(function (key) { return encodeURIComponent(key) + '=' + encodeURIComponent(params[key]); });
    return parts.length ? '?' + parts.join('&') : '';
  }
  window.MarkerAPI = {
    me: function () { return request('/me'); },
    homeSummary: function () { return request('/me/summary'); },
    homeQueue: function (limit) { return request('/me/queue?limit=' + (limit || 5)); },
    listRubrics: function () { return request('/rubrics'); },
    getRubric: function (rubricId) { return request('/rubrics/' + id(rubricId)); },
    parseRubric: function (text, sourceName) { return request('/rubrics/parse', { method: 'POST', body: JSON.stringify({ text: text, source_name: sourceName || null }) }); },
    parseRubricFile: function (file) { var form = new FormData(); form.append('file', file); return request('/rubrics/parse-file', { method: 'POST', body: form }); },
    createRubric: function (value) { return request('/rubrics', { method: 'POST', body: JSON.stringify(value) }); },
    updateRubric: function (rubricId, value) { return request('/rubrics/' + id(rubricId), { method: 'PUT', body: JSON.stringify(value) }); },
    pinRubric: function (rubricId, pinned) { return request('/rubrics/' + id(rubricId) + '/pin', { method: 'PUT', body: JSON.stringify({ pinned: pinned }) }); },
    deleteRubric: function (rubricId, version) { return request('/rubrics/' + id(rubricId) + '?version=' + id(version), { method: 'DELETE' }); },
    listBatches: function (params) { return request('/batches' + query(params)); },
    createBatch: function (value) { return request('/batches', { method: 'POST', body: JSON.stringify(value) }); },
    getBatch: function (batchId) { return request('/batches/' + id(batchId)); },
    pinBatch: function (batchId, pinned) { return request('/batches/' + id(batchId) + '/pin', { method: 'PUT', body: JSON.stringify({ pinned: pinned }) }); },
    cancelBatch: function (batchId, version, reason) { return request('/batches/' + id(batchId) + '/cancel', { method: 'POST', body: JSON.stringify({ version: version, reason: reason || 'Batch terminated by user' }) }); },
    deleteBatch: function (batchId, version) { return request('/batches/' + id(batchId) + '?version=' + id(version), { method: 'DELETE' }); },
    finaliseBatch: function (batchId, version) { return request('/batches/' + id(batchId) + '/finalise', { method: 'POST', body: JSON.stringify({ version: version }) }); },
    reopenBatch: function (batchId, version, reason) { return request('/batches/' + id(batchId) + '/reopen', { method: 'POST', body: JSON.stringify({ version: version, reason: reason }) }); },
    uploadFiles: function (batchId, files) { var form = new FormData(); Array.prototype.forEach.call(files, function (file) { form.append('files', file); }); return request('/batches/' + id(batchId) + '/files', { method: 'POST', body: form }); },
    patchSubmission: function (batchId, submissionId, value) { return request('/batches/' + id(batchId) + '/submissions/' + id(submissionId), { method: 'PATCH', body: JSON.stringify(value) }); },
    startBatch: function (batchId, value, sample) { return request('/batches/' + id(batchId) + '/start' + (sample ? '?sample=' + sample : ''), { method: 'POST', body: JSON.stringify(value) }); },
    listSubmissions: function (batchId, filter) { return request('/batches/' + id(batchId) + '/submissions' + query({ filter: filter && filter !== 'all' ? filter : null, page_size: 500 })); },
    nextInQueue: function (batchId, after) { return request('/batches/' + id(batchId) + '/queue/next' + query({ after: after })); },
    getReview: function (submissionId) { return request('/submissions/' + id(submissionId) + '/review'); },
    retrySubmission: function (submissionId, version) { return request('/submissions/' + id(submissionId) + '/retry', { method: 'POST', body: JSON.stringify({ stage: 'mark', version: version }) }); },
    regrade: function (submissionId) { return request('/submissions/' + id(submissionId) + '/regrade', { method: 'POST', body: '{}' }); },
    saveCriterion: function (submissionId, criterionId, value) { return request('/submissions/' + id(submissionId) + '/criteria/' + id(criterionId), { method: 'PATCH', body: JSON.stringify(value) }); },
    confirm: function (submissionId, version) { return request('/submissions/' + id(submissionId) + '/confirm', { method: 'POST', body: JSON.stringify({ version: version }) }); },
    getResults: function (batchId) { return request('/batches/' + id(batchId) + '/results'); },
    exportCsvUrl: function (batchId) { return base + '/batches/' + id(batchId) + '/export.csv'; },
    getReport: function (submissionId, audience) { return request('/submissions/' + id(submissionId) + '/report?audience=' + (audience || 'internal')); },
    getSettings: function () { return Promise.all([request('/settings/ai'), request('/settings/canvas')]).then(function (x) { return { ai: x[0], canvas: x[1] }; }); },
    updateAISettings: function (value) { return request('/settings/ai', { method: 'PUT', body: JSON.stringify(value) }); },
    testAI: function (value) { return request('/settings/ai/test', { method: 'POST', body: JSON.stringify(value || {}) }); }
  };
})();
