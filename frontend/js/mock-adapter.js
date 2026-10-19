(function () {
  var cache = {};
  function load(path) {
    if (!cache[path]) cache[path] = fetch('/fixtures/demo/' + path).then(function (response) {
      if (!response.ok) throw new Error('Fixture not found: ' + path);
      return response.json();
    });
    return cache[path];
  }
  function marked(value) {
    if (value && !Array.isArray(value) && typeof value === 'object') value._mock = true;
    return value;
  }
  window.MarkerMockAdapter = {
    homeSummary: function () { return load('home.json').then(function (x) { return marked(x.summary); }); },
    homeQueue: function (limit) { return load('home.json').then(function (x) { return marked({items:x.queue.slice(0, limit || 5), limit:limit || 5}); }); },
    listRubrics: function () { return load('rubrics.json').then(function (items) { return {items:items, page:1, page_size:50, total:items.length, _mock:true}; }); },
    listBatches: function () { return load('batches.json').then(function (items) { return {items:items, page:1, page_size:50, total:items.length, _mock:true}; }); },
    listSubmissions: function (batchId) { return Promise.all([load('submissions/index.json'), load('batches.json')]).then(function (values) { var items=values[0].filter(function(x){return x.batch_id===batchId;}); var batch=values[1].find(function(x){return x.id===batchId;}); return {items:items, page:1, page_size:50, total:items.length, filter_counts:batch ? batch.counts : {}, _mock:true}; }); },
    review: function (submissionId) { return load('reviews/' + submissionId + '.json').catch(function(){return load('reviews/shared-sample.json');}).then(marked); },
    results: function (batchId) { return load('reports/results-' + batchId + '.json').then(marked); },
    report: function (submissionId) { return load('reports/' + submissionId + '.json').catch(function(){return load('reports/shared-sample.json');}).then(marked); },
    confirm: function (submissionId) {
      var mode = window.MARKER_TEST_FIXTURE || 'wait';
      var states = { single:{next_id:null,batch_status:'completed',remaining:{ready:0,processing:0,failed:0}}, last:{next_id:null,batch_status:'completed',remaining:{ready:0,processing:0,failed:0}}, wait:{next_id:null,batch_status:'in_review',remaining:{ready:0,processing:411,failed:0}} };
      return Promise.resolve(marked(Object.assign({submission_id:submissionId,status:'confirmed',confirmed_at:new Date().toISOString()}, states[mode] || states.wait)));
    },
    settings: function () { return load('settings.json').then(marked); },
    testAI: function () { return Promise.resolve({ok:true,latency_ms:0,model:'fake-marker-v1',models:['fake-marker-v1'],message:'FakeLLM is ready',_mock:true}); }
  };
})();

