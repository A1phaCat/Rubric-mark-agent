(function () {
  var useMocks = window.USE_MOCKS === true || new URLSearchParams(location.search).get('mocks') === '1';
  var base = '/api/v1';
  function request(path, options) {
    options=options||{};
    var headers=Object.assign({},options.headers||{});
    if (!(options.body instanceof FormData)) headers['Content-Type']='application/json';
    return fetch(base + path, Object.assign({},options,{headers:headers})).then(function (response) {
      if (!response.ok) return response.json().catch(function(){return {};}).then(function(body){ var error=new Error((body.error && body.error.message) || ('HTTP ' + response.status)); error.status=response.status; error.body=body; throw error; });
      var contentType=response.headers.get('content-type') || '';
      return contentType.indexOf('json') >= 0 ? response.json() : response;
    });
  }
  function mocked(name, args) { return window.MarkerMockAdapter[name].apply(window.MarkerMockAdapter, args || []); }
  window.MarkerAPI = {
    mode: useMocks ? 'mock' : 'api',
    homeSummary:function(){return useMocks ? mocked('homeSummary') : request('/me/summary');},
    homeQueue:function(limit){return useMocks ? mocked('homeQueue',[limit]) : request('/me/queue?limit='+(limit||5));},
    listRubrics:function(){return useMocks ? mocked('listRubrics') : request('/rubrics');},
    getRubric:function(id){return request('/rubrics/'+encodeURIComponent(id));},
    parseRubric:function(text,sourceName){return useMocks ? Promise.reject(new Error('Rubric parsing needs API mode. Open this page through the local backend on port 8000.')) : request('/rubrics/parse',{method:'POST',body:JSON.stringify({text:text,source_name:sourceName||null})});},
    parseRubricFile:function(file){var form=new FormData();form.append('file',file);return useMocks ? Promise.reject(new Error('Rubric parsing needs API mode.')) : request('/rubrics/parse-file',{method:'POST',body:form});},
    createRubric:function(value){return request('/rubrics',{method:'POST',body:JSON.stringify(value)});},
    listBatches:function(){return useMocks ? mocked('listBatches') : request('/batches');},
    createBatch:function(value){return request('/batches',{method:'POST',body:JSON.stringify(value)});},
    getBatch:function(id){return request('/batches/'+encodeURIComponent(id));},
    cancelBatch:function(id,version,reason){return request('/batches/'+encodeURIComponent(id)+'/cancel',{method:'POST',body:JSON.stringify({version:version,reason:reason||'Batch terminated by user'})});},
    deleteBatch:function(id,version){return request('/batches/'+encodeURIComponent(id)+'?version='+encodeURIComponent(version),{method:'DELETE'});},
    uploadFiles:function(batchId,files){var form=new FormData();Array.prototype.forEach.call(files,function(file){form.append('files',file);});return request('/batches/'+encodeURIComponent(batchId)+'/files',{method:'POST',body:form});},
    patchSubmission:function(batchId,submissionId,value){return request('/batches/'+encodeURIComponent(batchId)+'/submissions/'+encodeURIComponent(submissionId),{method:'PATCH',body:JSON.stringify(value)});},
    startBatch:function(batchId,value,sample){return request('/batches/'+encodeURIComponent(batchId)+'/start'+(sample?'?sample='+sample:''),{method:'POST',body:JSON.stringify(value)});},
    listSubmissions:function(batchId){return useMocks ? mocked('listSubmissions',[batchId]) : request('/batches/'+encodeURIComponent(batchId)+'/submissions');},
    getReview:function(submissionId){return useMocks ? mocked('review',[submissionId]) : request('/submissions/'+encodeURIComponent(submissionId)+'/review');},
    retrySubmission:function(submissionId,version){return request('/submissions/'+encodeURIComponent(submissionId)+'/retry',{method:'POST',body:JSON.stringify({stage:'mark',version:version})});},
    regrade:function(submissionId){return request('/submissions/'+encodeURIComponent(submissionId)+'/regrade',{method:'POST',body:'{}'});},
    saveCriterion:function(submissionId,criterionId,value){return request('/submissions/'+encodeURIComponent(submissionId)+'/criteria/'+encodeURIComponent(criterionId),{method:'PATCH',body:JSON.stringify(value)});},
    confirm:function(submissionId,version){return useMocks ? mocked('confirm',[submissionId]) : request('/submissions/'+encodeURIComponent(submissionId)+'/confirm',{method:'POST',body:JSON.stringify({version:version})});},
    getResults:function(batchId){return useMocks ? mocked('results',[batchId]) : request('/batches/'+encodeURIComponent(batchId)+'/results');},
    getReport:function(submissionId,audience){return useMocks ? mocked('report',[submissionId]) : request('/submissions/'+encodeURIComponent(submissionId)+'/report?audience='+(audience||'internal'));},
    getSettings:function(){return useMocks ? mocked('settings') : Promise.all([request('/settings/ai'),request('/settings/canvas')]).then(function(x){return {ai:x[0],canvas:x[1]};});},
    updateAISettings:function(value){return useMocks ? Promise.resolve(Object.assign({_mock:true},value)) : request('/settings/ai',{method:'PUT',body:JSON.stringify(value)});},
    testAI:function(value){return useMocks ? mocked('testAI') : request('/settings/ai/test',{method:'POST',body:JSON.stringify(value||{})});}
  };
})();

