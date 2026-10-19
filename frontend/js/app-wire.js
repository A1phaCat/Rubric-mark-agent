(function () {
  function esc(value) { return String(value == null ? '' : value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;'); }
  function pageName() { return (location.pathname.split('/').pop() || '00-home.html').toLowerCase(); }
  function reportError(error) { document.documentElement.dataset.apiState='error'; console.error('Marker data load failed',error); }
  function rubricShape(item) {
    var rubric=item.rubric||item, used=item.used_by||[];
    return {id:rubric.id,version:rubric.version,title:rubric.title,source:rubric.source,updated:Date.parse(rubric.updated_at),usedBy:used.length?used.map(function(batch){return batch.batch_name;}):(rubric.used_by_count?['In use by '+rubric.used_by_count+' batch'+(rubric.used_by_count===1?'':'es')]:[]),criteria:(rubric.criteria||[]).map(function(c){var levels=(c.levels||[]).map(function(level){return {id:level.id,label:level.label,points:level.points,min_score:level.min_score,max_score:level.max_score,description:level.description};});return {id:c.id,name:c.name,weight:c.weight,grading_mode:c.grading_mode,aspects:c.aspects||[],levels:levels,bands:levels.map(function(level){return level.description;})};})};
  }
  function wireHome() {
    return Promise.all([MarkerAPI.homeSummary(),MarkerAPI.homeQueue(5),MarkerAPI.listRubrics()]).then(function(values){
      window.__MARKER_PAGE_DATA={summary:values[0],queue:values[1],rubrics:values[2]};
      var box=document.getElementById('recentRubrics'); if (!box) return;
      box.innerHTML=values[2].items.slice(0,3).map(function(r){return '<a class="r" href="06-rubrics.html#open='+encodeURIComponent(r.id)+'"><span>'+esc(r.title)+'<small>Version '+r.version+'</small></span><span>'+r.criteria_count+' criteria</span></a>';}).join('')+'<a class="r-add" href="01a-rubric-import.html">+ Import a rubric</a>';
    });
  }
  function wireRubrics() {
    return MarkerAPI.listRubrics().then(function(data){
      var details=MarkerAPI.mode==='mock'?Promise.resolve(data.items):Promise.all(data.items.map(function(item){return MarkerAPI.getRubric(item.id).catch(function(){return item;});}));
      return details.then(function(items){
        window.__MARKER_PAGE_DATA={items:items,page:data.page,page_size:data.page_size,total:data.total};
        var converted=items.map(rubricShape), byId={}; converted.forEach(function(r){byId[r.id]=r;});
        RubricLib.all=function(){return converted.slice();}; RubricLib.get=function(id){return byId[id]||null;}; RubricLib.recent=function(n){return converted.slice(0,n);};
        var q=document.getElementById('q'); if(q) q.dispatchEvent(new Event('input'));
        var openMatch=location.hash.match(/open=([\w-]+)/);if(openMatch&&window.RubricListUI)window.RubricListUI.openById(openMatch[1]);
        var note=document.querySelector('.foot-note'); if(note) note.textContent='Saved locally in SQLite and loaded through the API.';
      });
    });
  }
  function wireBatchStatus() {
    var batchId=new URLSearchParams(location.search).get('batch_id');
    if(!batchId)return MarkerAPI.listSubmissions('bat_asgn2');
    return Promise.all([MarkerAPI.getBatch(batchId),MarkerAPI.listSubmissions(batchId)]).then(function(values){
      var batch=values[0].batch, submissions=values[1], counts=batch.counts||{}, rubric=batch.rubric||{};
      window.__MARKER_PAGE_DATA={batch:batch,submissions:submissions};
      var first=submissions.items.find(function(item){return item.status==='ai_done'||item.status==='in_review';});
      var total=Number(rubric.total_weight||0), processed=Number(counts.processed||0), all=Number(counts.total||0), pct=all?Math.round(processed/all*100):0;
      var rows=submissions.items.map(function(item){
        var ready=item.status==='ai_done'||item.status==='in_review', failed=item.status==='failed';
        var label=ready?'Ready for review':failed?'Failed':(item.progress||item.status.replace(/_/g,' '));
        var stateClass=ready?'ready':failed?'failed':'processing';
        var flags=item.confidence==='low'?'<span class="flag">⚑ low confidence</span>':'—';
        if(failed){var message=item.error&&item.error.message?item.error.message:'AI grading failed';flags='<span class="flag">⚠ Processing failed</span><span class="error-msg" title="'+esc(message)+'">'+esc(message)+'</span><button type="button" class="retry-btn" data-retry="'+esc(item.id)+'" data-version="'+esc(item.version)+'">Retry remaining criteria</button>';}
        return '<tr'+(ready?' onclick="location.href=\'03b-review-split.html?submission_id='+encodeURIComponent(item.id)+'\'"':'')+'><td class="sid">'+esc(item.sid||item.filename)+'</td><td><span class="status-pill '+stateClass+'"><span class="dot"></span>'+esc(label)+'</span></td><td class="score '+(item.ai_total==null?'pending':'')+'">'+(item.ai_total==null?'—':esc(item.ai_total)+' / '+esc(total))+'</td><td>'+flags+'</td><td>J. Alvarez</td></tr>';
      }).join('');
      document.getElementById('batchMain').innerHTML='<div class="top"><div><h1>'+esc(batch.name)+'</h1><p class="sub">'+all+' submission'+(all===1?'':'s')+' · '+esc(rubric.criteria_count||0)+' criteria · '+esc(total)+' marks</p></div><div class="top-actions">'+(first?'<a class="start-btn" href="03b-review-split.html?submission_id='+encodeURIComponent(first.id)+'">Start reviewing →</a>':'')+'</div></div><div class="progress-card"><div class="progress-top"><span class="label">Batch progress</span><span class="val">'+processed+' / '+all+' processed</span></div><div class="bar"><div class="bar-fill" style="width:'+pct+'%"></div></div><div class="progress-stats"><span><b>'+Number(counts.ready||0)+'</b> ready</span><span><b>'+Number(counts.processing||0)+'</b> processing</span><span><b>'+Number(counts.confirmed||0)+'</b> confirmed</span><span><b>'+Number(counts.failed||0)+'</b> failed</span></div></div><div class="filters"><span class="chip active">All ('+all+')</span><span class="chip">Ready for review ('+Number(counts.ready||0)+')</span><span class="chip">Low confidence ('+Number(counts.low_confidence||0)+')</span><span class="chip">Processing ('+Number(counts.processing||0)+')</span></div><table><thead><tr><th>Submission</th><th>Status</th><th>AI suggested total</th><th>Flags</th><th>Tutor</th></tr></thead><tbody>'+rows+'</tbody></table>';
      Array.prototype.forEach.call(document.querySelectorAll('[data-retry]'),function(button){button.addEventListener('click',function(event){event.preventDefault();event.stopPropagation();button.disabled=true;button.textContent='Retrying…';MarkerAPI.retrySubmission(button.dataset.retry,Number(button.dataset.version)).then(function(){location.reload();}).catch(function(error){button.disabled=false;button.textContent='Retry remaining criteria';reportError(error);alert(error.message);});});});
      var crumb=document.getElementById('bcCur');if(crumb)crumb.textContent=batch.name;
      var status=document.getElementById('bpStatus');if(status)status.innerHTML=Number(counts.failed||0)>0?'<b>'+Number(counts.failed||0)+'</b> failed — retry needed':batch.display_status==='processing'?'<b>'+Number(counts.processing||0)+'</b> still with AI':'<b>'+Number(counts.ready||0)+'</b> ready for review';
      var step=document.getElementById('stepTrack');if(step)step.innerHTML='1. Set up batch — 2. Processing — <span class="current">3. Review</span>';
      ['bbPrev','bbNext'].forEach(function(id){var node=document.getElementById(id);if(node){node.setAttribute('aria-disabled','true');node.removeAttribute('href');node.querySelector('.n').textContent='None';}});
      document.title=batch.name+' — AI-assisted marker';
      if(Number(counts.processing||0)>0)setTimeout(function(){wireBatchStatus().catch(reportError);},3000);
      return window.__MARKER_PAGE_DATA;
    });
  }
  function wireBatchList() {
    return MarkerAPI.listBatches().then(function(data){
      window.__MARKER_PAGE_DATA=data;
      var items=(data.items||[]).map(function(batch){
        var counts=batch.counts||{}, total=Number(counts.total||0), processed=Number(counts.processed||0);
        var rawStatus=batch.display_status||batch.status||'draft';
        var state=rawStatus==='in_review'?'review':(rawStatus==='completed'||rawStatus==='finalised'?'complete':rawStatus);
        var pct=state==='complete'?100:(total?Math.round(processed/total*100):0);
        var progress=state==='draft'?'set-up not finished':state==='complete'?(Number(counts.confirmed||0)+' / '+total+' confirmed'):(processed+' / '+total+' processed');
        var termLabel=(batch.term&&batch.term.label)||'Semester 2, 2026', termMatch=termLabel.match(/Semester\s+(\d+),\s*(\d{4})/i);
        var term=termMatch?(termMatch[2]+' S'+termMatch[1]):termLabel;
        var rubric=batch.rubric||{}, due=batch.due_at?new Date(batch.due_at):null;
        var date=due&&!isNaN(due.getTime())?'due '+due.toLocaleDateString('en-AU',{day:'numeric',month:'short'}):'created locally';
        return {
          id:batch.id,name:batch.name,term:term,st:state,
          n:total+' submission'+(total===1?'':'s'),crit:Number(rubric.criteria_count||0),
          rubric:[rubric.title||'No rubric',rubric.id||''],date:date,
          prog:[pct,progress,state==='complete'?'var(--ink-soft)':state==='review'?'var(--info)':'var(--primary)'],
          href:state==='complete'?'04-batch-complete.html?batch_id='+encodeURIComponent(batch.id):'02-batch-status.html?batch_id='+encodeURIComponent(batch.id),
          home:state==='processing'||state==='review',version:Number(batch.version||0),
          canCancel:batch.status==='processing',
          canDelete:batch.status!=='processing'&&batch.status!=='finalised'
        };
      });
      if(MarkerAPI.mode!=='mock'&&window.BatchListUI)window.BatchListUI.setItems(items);
      return data;
    });
  }
  function showEnd(result) {
    var card=document.getElementById('endCard'), body=document.getElementById('endBody'); if(!card||!body)return;
    if(result.batch_status==='completed') body.innerHTML='<div class="ec-icon ok">✓</div><div class="ec-kicker">Batch complete</div><h2 id="ecTitle">Everything is confirmed</h2><p class="ec-sub">The completion check ran in the same transaction as confirmation.</p><div class="ec-actions"><a class="btn btn-primary" href="04-batch-complete.html?batch_id='+encodeURIComponent(result.batch_id||'')+'">View results →</a></div>';
    else if(result.remaining.failed>0) body.innerHTML='<div class="ec-kicker">Failed items need attention</div><h2 id="ecTitle">Review is paused</h2><p class="ec-sub">Retry or exclude the failed submissions from the batch page.</p>';
    else body.innerHTML='<div class="ec-icon wait"><span class="ec-spin"></span></div><div class="ec-kicker">Nothing ready right now</div><h2 id="ecTitle">All ready submissions reviewed</h2><p class="ec-sub">'+result.remaining.processing+' still with the AI.</p>';
    card.hidden=false;
  }
  function wireReview() {
    var params=new URLSearchParams(location.search), submissionId=params.get('submission_id')||'sub_asgn2_000001';
    return MarkerAPI.getReview(submissionId).then(function(data){
      window.__MARKER_PAGE_DATA=data;
      var submission=data.submission||{}, batch=data.batch||{}, counts=batch.counts||{};
      var sid=submission.sid||submission.id, batchUrl='02-batch-status.html?batch_id='+encodeURIComponent(batch.id||'');
      var isDemoSample=!!data.demo_banner, allEvidence=data.evidence||[], hasEvidence=!!allEvidence.length, criteria=(data.rubric&&data.rubric.criteria)||[];
      var criterionNumber={};criteria.forEach(function(item,index){criterionNumber[item.definition.id]=index+1;});
      function blockHTML(block){
        var text=String(block.text||''), matches=allEvidence.filter(function(item){return Number(item.page||1)===Number(block.page||1)&&String(item.paragraph||'')===String(block.label||'')&&item.quote&&text.indexOf(item.quote)>=0;});
        if(!matches.length)return esc(text);
        var grouped={};matches.forEach(function(item){var start=text.indexOf(item.quote), key=start+':'+(start+item.quote.length);if(!grouped[key])grouped[key]={start:start,end:start+item.quote.length,ids:[],numbers:[]};grouped[key].ids.push(item.id);var n=criterionNumber[item.criterion_id];if(n&&grouped[key].numbers.indexOf(n)<0)grouped[key].numbers.push(n);});
        var ranges=Object.keys(grouped).map(function(key){return grouped[key];}).sort(function(a,b){return a.start-b.start||(b.end-b.start)-(a.end-a.start);}), cursor=0, html='';
        ranges.forEach(function(range){if(range.start<cursor)return;html+=esc(text.slice(cursor,range.start));html+='<mark class="ev" data-ev="'+esc(range.ids[0])+'" data-evs="'+esc(range.ids.join(' '))+'"><span class="tag">'+range.numbers.map(function(n){return 'C'+n;}).join('/')+'</span>'+esc(text.slice(range.start,range.end))+'</mark>';cursor=range.end;});
        return html+esc(text.slice(cursor));
      }
      var existingCards=document.querySelectorAll('.crit-card'), markInner=document.querySelector('.mark-inner');
      var strip=document.querySelector('.crit-strip');
      while(existingCards.length<criteria.length){
        let cloneIndex=existingCards.length, clone=existingCards[existingCards.length-1].cloneNode(true);
        clone.id='c'+(cloneIndex+1);clone.style.display='';clone.classList.remove('closed','linked','hl-active');clone.dataset.evs='';
        markInner.appendChild(clone);
        let navClone=strip.lastElementChild.cloneNode(true);navClone.href='#'+clone.id;navClone.dataset.c=clone.id;navClone.style.display='';strip.appendChild(navClone);
        let cloneInput=clone.querySelector('.score-input'), cloneStatus=clone.querySelector('.status-text');
        let cloneField=clone.querySelector('.comment-field'), cloneComment=cloneField&&cloneField.querySelector('textarea');
        function refreshClone(){var changed=Number(cloneInput.value)!==Number(cloneInput.dataset.ai);cloneField.classList.toggle('needs',changed&&!cloneComment.value.trim());cloneStatus.textContent=changed?'Adjusted from AI suggestion':'Matches AI suggestion — not yet confirmed';recompute();updateSummary(clone);}
        cloneInput.addEventListener('input',refreshClone);cloneComment.addEventListener('input',function(){updateSummary(clone);});
        clone.querySelector('.accept-btn').addEventListener('click',function(){cloneInput.value=cloneInput.dataset.ai;cloneInput.classList.add('confirmed');cloneStatus.textContent='Confirmed';cloneStatus.classList.add('confirmed');var dot=document.getElementById('nav'+(cloneIndex+1));if(dot)dot.classList.add('done');recompute();updateSummary(clone);});
        clone.querySelector('.fold-btn').addEventListener('click',function(){toggleCard(clone);});
        clone.querySelector('.crit-title').addEventListener('click',function(){toggleCard(clone);});
        let cloneCtl=clone.querySelector('.crit-ctl');
        if(cloneCtl){cloneCtl.querySelector('.hl-btn').addEventListener('click',function(){setCritHL(critHL===clone.id?null:clone.id);});cloneCtl.querySelector('.hl-prev').addEventListener('click',function(){stepCrit(-1);});cloneCtl.querySelector('.hl-next').addEventListener('click',function(){stepCrit(1);});}
        existingCards=document.querySelectorAll('.crit-card');
      }
      var cards=document.querySelectorAll('.crit-card'), nav=document.querySelectorAll('.crit-strip a');
      var total=0,aiTotal=0,submissionVersion=Number(submission.version||0);

      var crumbBatch=document.querySelector('.ab-crumbs ol li:nth-child(2) a');
      if(crumbBatch){crumbBatch.textContent=batch.name||'Batch';crumbBatch.href=batchUrl;}
      var crumbCurrent=document.getElementById('bcCur');if(crumbCurrent)crumbCurrent.textContent=sid;
      var crumbUp=document.querySelector('.ab-crumbs .bc-up');
      if(crumbUp){crumbUp.href=batchUrl;var crumbUpText=crumbUp.querySelector('.t');if(crumbUpText)crumbUpText.textContent=batch.name||'Batch';}

      var confirmed=Number(counts.confirmed||0), ready=Number(counts.ready||0), processing=Number(counts.processing||0), batchTotal=Number(counts.total||0);
      var reviewable=confirmed+ready, safeTotal=batchTotal||1;
      var pgDone=document.getElementById('pgDone');if(pgDone)pgDone.textContent=confirmed;
      var pgReady=document.getElementById('pgReady');if(pgReady)pgReady.textContent=reviewable;
      var pgFill=document.getElementById('pgFill');if(pgFill)pgFill.style.width=(confirmed/safeTotal*100)+'%';
      var pgReadyFill=document.getElementById('pgReadyFill');if(pgReadyFill)pgReadyFill.style.width=(reviewable/safeTotal*100)+'%';
      var pgSub=document.getElementById('pgSub');
      if(pgSub){pgSub.classList.toggle('done',processing===0);pgSub.innerHTML=processing>0?'<span class="dot"></span><span id="pgProc">'+processing+'</span> still with AI · '+batchTotal+' in batch':ready>0?'<span class="dot"></span>'+ready+' ready for review · '+batchTotal+' in batch':'<span class="dot"></span>All '+batchTotal+' reviewed';}

      var documentData=data.document||{}, fileName=document.querySelector('.doc-bar .file b');if(fileName)fileName.textContent=submission.filename||sid;
      var pageCount=Number(documentData.page_count||0), fileMeta=document.querySelector('.doc-bar .file span');if(fileMeta)fileMeta.textContent=isDemoSample?'Demo sample · no submission evidence':(pageCount+' page'+(pageCount===1?'':'s')+' · '+Number(documentData.word_count||0).toLocaleString('en-AU')+' words · '+allEvidence.length+' evidence span'+(allEvidence.length===1?'':'s'));
      var documentRoot=document.getElementById('doc'), evidenceHTML='';
      if(!isDemoSample&&(documentData.paragraphs||[]).length){
        var pageMap={};(documentData.paragraphs||[]).forEach(function(block){var page=Number(block.page||1);if(!pageMap[page])pageMap[page]=[];pageMap[page].push(block);});
        evidenceHTML=Object.keys(pageMap).map(Number).sort(function(a,b){return a-b;}).map(function(pageNumber){
          var blocks=pageMap[pageNumber], heading=pageNumber===1?'<h1>'+esc(documentData.title||submission.filename||sid)+'</h1><p class="byline">'+esc(sid)+' · '+esc(batch.name||'Batch')+' · '+Number(documentData.word_count||0).toLocaleString('en-AU')+' words</p>':'';
          return '<article class="sheet" data-page="'+pageNumber+'"><span class="pno">p.'+pageNumber+'</span>'+heading+blocks.map(function(block){return block.kind==='heading'?'<h2>'+esc(block.text)+'</h2>':'<p data-p="'+esc(block.label||'')+'">'+blockHTML(block)+'</p>';}).join('')+'</article>';
        }).join('');
        documentRoot.innerHTML=evidenceHTML;
      }
      var sampleTitle=document.querySelector('.sheet h1');if(sampleTitle&&isDemoSample)sampleTitle.textContent='Demo sample essay';
      var sampleByline=document.querySelector('.sheet .byline');if(sampleByline&&isDemoSample)sampleByline.textContent='Shared placeholder for '+sid+' · not the uploaded submission';
      if(isDemoSample){
        Array.prototype.forEach.call(document.querySelectorAll('#doc mark.ev'),function(mark){var parent=mark.parentNode;while(mark.firstChild)parent.insertBefore(mark.firstChild,mark);parent.removeChild(mark);});
      }
      var evidenceToggle=document.querySelector('.doc-tools .switch'), evidenceInput=document.getElementById('showAll');
      var mimeType=String(documentData.mime_type||'').toLowerCase(), isPdf=!isDemoSample&&!!documentData.content_url&&(mimeType.indexOf('pdf')>=0||/\.pdf$/i.test(submission.filename||''));
      var evidenceById={};allEvidence.forEach(function(item){evidenceById[item.id]=item;});
      var originalPage=1, originalPdfController=null;
      function renderOriginal(page){
        if(!isPdf)return;
        originalPage=Math.max(1,Number(page||originalPage||1));
        documentRoot.classList.add('original-mode');documentRoot.classList.toggle('show-all',!!(evidenceInput&&evidenceInput.checked));
        if(originalPdfController){originalPdfController.goToPage(originalPage);return;}
        if(window.OriginalPdfViewer)originalPdfController=window.OriginalPdfViewer.mount(documentRoot,{url:documentData.content_url,evidence:allEvidence.map(function(item){var copy=Object.assign({},item);copy.criterion_label='C'+(criterionNumber[item.criterion_id]||'?');return copy;})});
      }
      function renderEvidence(){
        documentRoot.classList.remove('original-mode');documentRoot.innerHTML=evidenceHTML;
        documentRoot.classList.toggle('show-all',!!(evidenceInput&&evidenceInput.checked));
      }
      if(evidenceToggle)evidenceToggle.style.display=(hasEvidence&&(!isPdf||!!evidenceHTML))?'':'none';
      if(isPdf){
        if(evidenceInput)evidenceInput.checked=true;
        if(evidenceToggle){var labelText=Array.prototype.filter.call(evidenceToggle.childNodes,function(node){return node.nodeType===3;}).pop();if(labelText)labelText.nodeValue=' Show all evidence';}
        renderOriginal(1);
        var markPaneForOriginal=document.getElementById('markPane');
        if(markPaneForOriginal){
          markPaneForOriginal.addEventListener('click',function(event){
            var source=event.target.closest('[data-ev]'), evidence=source&&evidenceById[source.dataset.ev];
            if(source&&evidence){originalPage=evidence.page||1;if(originalPdfController)originalPdfController.goToEvidence(evidence.id);}
          },true);
        }
      }
      if(!isDemoSample&&!document.querySelector('[data-regrade]')){
        var regradeControl=document.createElement('span'), regradeButton=document.createElement('button'), regradeMeter=document.createElement('span'), regradeFill=document.createElement('span');
        regradeControl.className='regrade-control';regradeButton.type='button';regradeButton.className='icon-btn';regradeButton.dataset.regrade='true';regradeButton.textContent=hasEvidence?'Re-run AI evidence':'Retrieve evidence';regradeMeter.className='regrade-meter';regradeMeter.appendChild(regradeFill);regradeControl.appendChild(regradeButton);regradeControl.appendChild(regradeMeter);document.querySelector('.doc-tools').insertBefore(regradeControl,document.getElementById('collapse'));
        function regradeError(message){var old=document.querySelector('.regrade-error');if(old)old.remove();var box=document.createElement('div');box.className='regrade-error';box.setAttribute('role','alert');box.innerHTML='<b>AI evidence retrieval stopped.</b><br>'+esc(message)+'<button type="button" aria-label="Close">×</button>';box.querySelector('button').addEventListener('click',function(){box.remove();});document.body.appendChild(box);}
        function stopRegrade(message){regradeControl.classList.remove('running');regradeButton.disabled=false;regradeButton.textContent=hasEvidence?'Re-run AI evidence':'Retrieve evidence';regradeFill.style.width='0';if(message)regradeError(message);}
        function pollRegrade(){MarkerAPI.listSubmissions(batch.id).then(function(result){var item=(result.items||[]).find(function(row){return row.id===submissionId;});if(!item)throw new Error('Submission progress is unavailable.');var progress=String(item.progress||''),match=progress.match(/(\d+)\s*\/\s*(\d+)\s+criteria/),done=match?Number(match[1]):0,count=match?Number(match[2]):criteria.length,pct=count?Math.max(5,Math.round(done/count*100)):5;regradeFill.style.width=pct+'%';regradeButton.textContent=match?'Retrieving '+done+'/'+count:'Queued…';if(item.status==='ai_done'||item.status==='in_review'){regradeFill.style.width='100%';regradeButton.textContent='Evidence ready';setTimeout(function(){location.reload();},350);return;}if(item.status==='failed'){var detail=item.error&&item.error.message?item.error.message:'The AI provider did not return a usable result after three attempts.';stopRegrade(detail);return;}setTimeout(pollRegrade,1500);}).catch(function(error){console.error('Regrade progress failed',error);stopRegrade(error.message);});}
        function startRegrade(){regradeControl.classList.add('running');regradeButton.disabled=true;regradeFill.style.width='5%';pollRegrade();}
        regradeButton.addEventListener('click',function(){regradeControl.classList.add('running');regradeButton.disabled=true;regradeButton.textContent='Queueing…';regradeFill.style.width='3%';MarkerAPI.regrade(submissionId).then(startRegrade).catch(function(error){console.error('Regrade request failed',error);stopRegrade(error.message);});});
        if(submission.status==='queued'||submission.status==='marking')startRegrade();
      }
      var hint=document.querySelector('.actionbar .hint');if(hint)hint.textContent=hasEvidence?'Hover evidence to highlight · click to jump · Show all controls every retrieved passage':(isDemoSample?'FakeLLM validation · no evidence extracted for this submission':'Uploaded document parsed · no verified criterion evidence was returned');

      Array.prototype.forEach.call(cards,function(card,index){
        var item=criteria[index];
        if(!item){card.style.display='none';if(nav[index])nav[index].style.display='none';return;}
        var def=item.definition||{}, levels=def.levels||[], confidence=item.confidence||'medium';
        total+=Number(def.weight||0);aiTotal+=Number(item.ai_score||0);
        card.dataset.criterionId=def.id||'';card.dataset.reviewVersion=String(item.version||0);card.dataset.evs=(item.evidence_ids||[]).join(',');
        var title=card.querySelector('.crit-title');if(title)title.textContent='C'+(index+1)+' · '+def.name;
        var desc=card.querySelector('.crit-desc');if(desc)desc.innerHTML='<details><summary>Rubric levels · '+levels.length+'</summary><div class="level-list">'+levels.map(function(level){var points=level.points==null?level.max_score:level.points;return '<div><strong>'+esc(level.label)+' ('+esc(points)+')</strong>: '+esc(level.description)+'</div>';}).join('')+'</div></details>';
        var badge=card.querySelector('.crit-weight-badge');if(badge)badge.textContent=def.weight+' pts';
        var confidenceTag=card.querySelector('.conf-tag');if(confidenceTag){confidenceTag.className='conf-tag '+confidence;confidenceTag.innerHTML='<span class="dot"></span>'+confidence.charAt(0).toUpperCase()+confidence.slice(1)+' confidence';}
        var ai=card.querySelector('.ai-box .badge');if(ai)ai.textContent='AI · '+item.ai_score+'/'+def.weight;
        var reason=card.querySelector('.ai-box .reason');if(reason)reason.textContent=item.rationale||'Deterministic local FakeLLM suggestion.';
        var score=card.querySelector('.score-input');if(score){score.value=item.score;score.dataset.ai=item.ai_score;score.dataset.max=def.weight;score.max=def.weight;}
        var max=card.querySelector('.score-max');if(max)max.textContent='/ '+def.weight;
        var comment=card.querySelector('.comment-field textarea');if(comment)comment.value=item.comment||'';
        var status=card.querySelector('.status-text');if(status)status.textContent='Not yet confirmed';
        var criterionEvidence=allEvidence.filter(function(evidence){return evidence.criterion_id===def.id;}), evidenceNode=card.querySelector('.evidence'), alsoNode=card.querySelector('.also'), control=card.querySelector('.crit-ctl');
        if(criterionEvidence.length){
          card.dataset.evs=criterionEvidence.map(function(evidence){EV_CARD[evidence.id]=card.id;return evidence.id;}).join(',');
          if(evidenceNode){var first=criterionEvidence[0];evidenceNode.style.display='';evidenceNode.dataset.ev=first.id;evidenceNode.innerHTML='<span class="tab">p.'+esc(first.page)+' '+esc(first.paragraph||'')+'</span><span class="jump">Show in submission ↗</span><blockquote>“'+esc(first.quote)+'”</blockquote>';}
          if(alsoNode){if(criterionEvidence.length>1){alsoNode.style.display='';alsoNode.innerHTML='Also used: '+criterionEvidence.slice(1).map(function(evidence){return '<span class="chip" data-ev="'+esc(evidence.id)+'"><b>p.'+esc(evidence.page)+' '+esc(evidence.paragraph||'')+'</b><i>“'+esc(evidence.quote.length>120?evidence.quote.slice(0,117)+'…':evidence.quote)+'”</i></span>';}).join('');}else alsoNode.style.display='none';}
          if(control){control.style.display='';var label=control.querySelector('.hl-lbl');if(label)label.textContent='Highlight all · '+criterionEvidence.length;}
        }else{
          Array.prototype.forEach.call(card.querySelectorAll('.evidence,.also,.crit-ctl'),function(node){node.style.display='none';});
          var sum=card.querySelector('.crit-sum');if(sum)sum.innerHTML='Your score <b>'+esc(item.score)+' / '+esc(def.weight)+'</b> · Not yet confirmed · No submission evidence';
        }
        updateSummary(card);
        if(nav[index]){nav[index].style.display='';nav[index].dataset.c=card.id;nav[index].title='C'+(index+1)+' · '+def.name;nav[index].innerHTML='<span class="st" id="nav'+(index+1)+'"></span>C'+(index+1)+' <span class="w">'+def.weight+' pts</span>';}
      });
      var heading=document.querySelector('.doc-header h1');if(heading)heading.textContent='Review — '+sid;
      var summary=document.querySelector('.doc-header p');if(summary)summary.textContent=criteria.length+' criteria · rubric maximum '+total+' marks'+(isDemoSample?' · demo content only':' · '+pageCount+'-page submission parsed');
      var footer=document.getElementById('footerTotal');if(footer)footer.textContent=aiTotal;
      var final=footer&&footer.parentElement;if(final){var textNode=Array.prototype.find.call(final.childNodes,function(node){return node.nodeType===3&&/\//.test(node.textContent);});if(textNode)textNode.textContent=' / '+total+' ';}
      var suggested=document.getElementById('aiSug');if(suggested)suggested.textContent='AI suggested '+aiTotal;
      var previous=document.getElementById('btnPrev');if(previous)previous.disabled=true;
      var skip=document.getElementById('btnSkip');if(skip){skip.textContent='Back to batch';skip.title='Return to this batch';skip.addEventListener('click',function(event){event.preventDefault();location.href=batchUrl;});}
      document.title=sid+' — '+(batch.name||'Review')+' — AI-assisted marker';
      if(data.demo_banner){var oldBanner=document.querySelector('[data-demo-review-banner]');if(oldBanner)oldBanner.remove();var banner=document.createElement('div');banner.dataset.demoReviewBanner='true';banner.textContent=data.demo_banner;banner.setAttribute('role','status');banner.style.cssText='position:fixed;z-index:90;top:58px;left:50%;transform:translateX(-50%);padding:7px 14px;border-radius:0 0 8px 8px;background:#7a2e16;color:white;font:600 12px Inter,sans-serif';document.body.appendChild(banner);}
      document.addEventListener('click',function(event){
        var button=event.target.closest('#btnNext'); if(!button)return;
        event.preventDefault(); event.stopImmediatePropagation(); button.disabled=true; button.textContent='Saving…';
        var chain=Promise.resolve();
        criteria.forEach(function(item,index){
          var card=cards[index];if(!card)return;
          var score=card.querySelector('.score-input'), comment=card.querySelector('.comment-field textarea');
          var nextScore=Number(score.value), nextComment=comment?comment.value:'';
          if(nextScore===Number(item.score||0)&&nextComment===(item.comment||''))return;
          chain=chain.then(function(){return MarkerAPI.saveCriterion(submissionId,item.definition.id,{score:nextScore,comment:nextComment,version:item.version}).then(function(saved){submissionVersion=Number(saved.submission_version);item.score=saved.score;item.comment=saved.comment;item.version=saved.version;});});
        });
        chain.then(function(){button.textContent='Confirming…';return MarkerAPI.confirm(submissionId,submissionVersion);}).then(function(result){result.batch_id=batch.id;showEnd(result);button.textContent='Confirmed';}).catch(function(error){button.disabled=false;button.textContent='Confirm & next →';reportError(error);});
      },true);
    });
  }
  function loadPageData(name) {
    if(name==='07-batches.html') return wireBatchList();
    if(name==='02-batch-status.html') return wireBatchStatus();
    if(name==='04-batch-complete.html') return MarkerAPI.getResults(new URLSearchParams(location.search).get('batch_id')||'bat_quiz3');
    if(name==='05-mark-report.html') return MarkerAPI.getReport(new URLSearchParams(location.search).get('submission_id')||'sub_quiz3_000002','internal');
    if(name==='01-upload.html'||name==='01a-rubric-import.html') return Promise.all([MarkerAPI.listRubrics(),MarkerAPI.getSettings()]);
    return Promise.resolve(null);
  }
  function disableCanvas() {
    Array.prototype.forEach.call(document.querySelectorAll('h1,h2,h3,label,button,option'),function(node){
      if(/canvas/i.test(node.textContent||'')){
        var section=node.closest('section,.pane,.panel,.source,.am-row')||node.parentElement;
        if(section) Array.prototype.forEach.call(section.querySelectorAll('button,input,select,textarea'),function(control){control.disabled=true;control.title='Not available in local MVP';});
      }
    });
  }
  document.addEventListener('DOMContentLoaded',function(){
    document.documentElement.dataset.apiMode=MarkerAPI.mode; disableCanvas();
    var name=pageName(), task=name==='00-home.html'||name===''?wireHome():name==='06-rubrics.html'?wireRubrics():name==='03b-review-split.html'?wireReview():loadPageData(name).then(function(data){window.__MARKER_PAGE_DATA=data;});
    Promise.resolve(task).then(function(){document.documentElement.dataset.apiState='ready';}).catch(reportError);
  });
})();

