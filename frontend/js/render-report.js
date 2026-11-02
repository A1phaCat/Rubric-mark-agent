/* Mark report (05): one confirmed submission, rendered from GET /submissions/{id}/report. */
(function () {
  function initials(name) { return String(name || '?').split(/[\s.]+/).filter(Boolean).map(function (p) { return p[0]; }).join('').slice(0, 2).toUpperCase(); }

  function render(ui, data) {
    var marker = data.marker ? data.marker.name : 'Tutor', internal = data.audience === 'internal';
    var status = data.locked ? '<span class="rel">✓ Finalised · marks locked</span>' : 'Confirmed · editable until the batch is finalised';
    var aiNote = internal && data.ai_total != null
      ? (Math.abs(data.adjustment) > 0.001 ? 'AI suggested <s>' + ui.num(data.ai_total) + '</s> · adjusted ' + (data.adjustment > 0 ? '+' : '−') + ui.num(Math.abs(data.adjustment)) + ' by tutor' : 'Confirmed as the AI suggested')
      : '';
    var breakdown = data.criteria.map(function (c) {
      return '<div class="bd-row"><span>' + ui.esc(c.name) + '</span><span class="track"><span style="width:' + (c.max_score ? c.score / c.max_score * 100 : 0) + '%"></span></span><span class="pts">' + ui.num(c.score) + ' / ' + ui.num(c.max_score) + '</span></div>';
    }).join('');
    var summary = overallHtml(ui, data, marker);
    var criteria = data.criteria.map(function (c) {
      var delta = internal && c.ai_score != null ? Math.round((c.score - c.ai_score) * 100) / 100 : 0;
      var sources = c.evidence.length ? '<div class="src evidence-used">Evidence used ' + c.evidence.map(function (e) { return '<span title="' + ui.esc(e.quote) + '">p.' + ui.esc(e.page) + ' ' + ui.esc(e.paragraph || '') + '</span>'; }).join('') + '</div>' : '';
      return '<article class="crit"><div class="crit-top"><div><h3>' + ui.esc(c.name) + '</h3><p class="desc">' + ui.esc(c.descriptor) + '</p></div><div class="pts"><b>' + ui.num(c.score) + '<small> / ' + ui.num(c.max_score) + '</small></b>' + (c.band ? '<span class="band ' + tier(c) + '" title="Level ' + (c.band_rank + 1) + ' of ' + c.band_count + ' on this criterion">' + ui.esc(c.band) + '</span>' : '') + '</div></div>' +
        (Math.abs(delta) > 0.001 ? '<span class="adj"><span class="delta">' + (delta > 0 ? '+' : '−') + ui.num(Math.abs(delta)) + '</span>AI suggested ' + ui.num(c.ai_score) + ' · adjusted by tutor</span>' : '') +
        (c.comment ? '<div class="comment"><span class="avatar">' + initials(marker) + '</span><div><div class="who"><b>' + ui.esc(marker) + '</b> · tutor comment</div><p>' + ui.esc(c.comment) + '</p></div></div>' : '') +
        (internal && c.internal_rationale ? '<div class="src rationale">AI rationale (internal) · ' + ui.esc(c.internal_rationale) + '</div>' : '') + sources + '</article>';
    }).join('');

    document.getElementById('reportMain').innerHTML =
      '<section class="report"><div class="rh"><div><div class="eyebrow">Mark report' + (internal ? ' · internal view' : ' · student view') + '</div><h1>' + ui.esc(data.batch.name) + '</h1>' +
      '<dl><dt>Student</dt><dd>' + ui.esc(data.submission.sid || data.submission.filename) + '</dd><dt>Marked by</dt><dd>' + ui.esc(marker) + '</dd>' +
      '<dt>Confirmed</dt><dd>' + ui.longDate(data.confirmed_at) + '</dd><dt>Status</dt><dd>' + status + '</dd></dl>' +
      '<div class="audience" role="group" aria-label="Report audience"><button type="button" data-a="internal" class="' + (internal ? 'on' : '') + '">Tutor view</button><button type="button" data-a="student" class="' + (internal ? '' : 'on') + '">Student view</button></div>' +
      (data.batch.is_sample ? '<div class="sample-note">Sample batch — preloaded demonstration data</div>' : '') + '</div>' +
      '<div class="score"><div class="big">' + ui.num(data.final_total) + '<small> / ' + ui.num(data.maximum) + '</small></div><span class="band ' + data.band + '">' + data.band + ' · ' + ui.esc(data.band_name) + '</span>' + (aiNote ? '<div class="ai-note">' + aiNote + '</div>' : '') + '</div></div>' +
      '<div class="breakdown" aria-label="Marks by criterion">' + breakdown + '</div></section>' + '<div id="overall">' + summary + '</div>' +
      '<h2 class="section-title">Feedback by criterion</h2>' + criteria +
      '<p class="footnote"><span class="dot"></span>Marks were suggested by AI from the evidence in this submission and confirmed or adjusted by a tutor. Every final mark and comment on this page was approved by a person.</p>';
    wireOverall(ui, data);
    Array.prototype.forEach.call(document.querySelectorAll('.audience button'), function (button) {
      button.addEventListener('click', function () {
        var params = new URLSearchParams(location.search); params.set('audience', button.dataset.a);
        history.replaceState(null, '', '?' + params.toString());
        MarkerAPI.getReport(data.submission.id, button.dataset.a).then(function (next) { window.__MARKER_PAGE_DATA = next; render(ui, next); });
      });
    });
  }

  /* ---------- Overall feedback: an AI draft from the confirmed marks, approved by the tutor ---------- */
  var drafting = {}, editing = {};
  function canEdit(data) { return data.audience === 'internal' && !data.locked; }
  function lines(items) { return (items || []).join('\n'); }
  function group(ui, title, items) {
    if (!items || !items.length) return '';
    return '<div class="fb-group"><h3>' + title + '</h3><ul>' + items.map(function (t) { return '<li>' + ui.esc(t) + '</li>'; }).join('') + '</ul></div>';
  }
  function overallHtml(ui, data, marker) {
    var fb = data.feedback, id = data.submission.id, head = '<div class="hd"><h2><span class="badge">AI</span>Overall feedback</h2>';
    if (!fb) {
      if (!canEdit(data)) return '';
      return '<section class="ai-sum" aria-label="Overall feedback">' + head + '</div><div class="fb-wait" id="fbWait"><span class="spin" aria-hidden="true"></span>Drafting overall feedback from your confirmed marks…</div></section>';
    }
    var draft = data.audience === 'internal' && fb.status !== 'approved', edit = canEdit(data) && (draft || editing[id]);
    var by = fb.approved_by_name || marker;
    var state = draft ? '<span class="draft">Draft</span> Not shown to the student until you approve it'
      : 'Approved by ' + ui.esc(by) + (data.audience === 'internal' && fb.source === 'ai' ? ' · drafted by AI from the confirmed marks' : '');
    var stale = data.audience === 'internal' && fb.stale ? '<p class="fb-stale">Marks or comments changed since this feedback was written. Regenerate it, or edit it to match.</p>' : '';
    if (edit) {
      return '<section class="ai-sum" aria-label="Overall feedback">' + head + '<span class="fb-state">' + state + '</span></div>' + stale +
        '<div class="fb-edit">' +
        '<label>Summary<textarea id="fbSummary" rows="3">' + ui.esc(fb.summary || '') + '</textarea></label>' +
        '<label>Strengths <small>one per line</small><textarea id="fbStrengths" rows="3">' + ui.esc(lines(fb.strengths)) + '</textarea></label>' +
        '<label>To improve <small>one per line</small><textarea id="fbImprovements" rows="3">' + ui.esc(lines(fb.improvements)) + '</textarea></label>' +
        '<label>Next steps <small>one per line</small><textarea id="fbNext" rows="2">' + ui.esc(lines(fb.next_steps)) + '</textarea></label>' +
        '<div class="fb-act"><span class="msg" id="fbMsg"></span><button type="button" class="fb-btn" data-fb="regenerate">Regenerate</button><button type="button" class="fb-btn" data-fb="save">Save draft</button><button type="button" class="fb-btn pri" data-fb="approve">Approve for the student</button></div></div></section>';
    }
    return '<section class="ai-sum" aria-label="Overall feedback">' + head + '<span class="fb-state">' + state + '</span></div>' + stale +
      '<p>' + ui.esc(fb.summary || '') + '</p>' + group(ui, 'Strengths', fb.strengths) + group(ui, 'To improve', fb.improvements) + group(ui, 'Next steps', fb.next_steps) +
      (canEdit(data) ? '<div class="fb-act"><button type="button" class="fb-btn" data-fb="regenerate">Regenerate</button><button type="button" class="fb-btn" data-fb="edit">Edit</button></div>' : '') + '</section>';
  }
  function wireOverall(ui, data) {
    var id = data.submission.id, box = document.getElementById('overall');
    function rerender(next) { window.__MARKER_PAGE_DATA = next; render(ui, next); }
    function fail(error) {
      var msg = document.getElementById('fbMsg'), wait = document.getElementById('fbWait');
      var text = 'Could not draft the overall feedback: ' + (error.message || 'provider error');
      if (msg) { msg.textContent = text; Array.prototype.forEach.call(box.querySelectorAll('.fb-btn'), function (b) { b.disabled = false; }); }
      else if (wait) wait.innerHTML = ui.esc(text) + ' <button type="button" class="fb-btn" data-fb="regenerate">Try again</button>';
    }
    function regenerate() {
      drafting[id] = true; editing[id] = false;
      Array.prototype.forEach.call(box.querySelectorAll('.fb-btn'), function (b) { b.disabled = true; });
      var msg = document.getElementById('fbMsg'); if (msg) msg.textContent = 'Drafting from your confirmed marks…';
      MarkerAPI.draftFeedback(id).then(rerender).catch(fail);
    }
    if (!data.feedback && canEdit(data) && !drafting[id]) regenerate();
    box.onclick = function (event) {
      var button = event.target.closest('[data-fb]'); if (!button) return;
      var action = button.dataset.fb;
      if (action === 'regenerate') { regenerate(); return; }
      if (action === 'edit') { editing[id] = true; render(ui, data); return; }
      var value = { summary: document.getElementById('fbSummary').value, strengths: document.getElementById('fbStrengths').value,
        improvements: document.getElementById('fbImprovements').value, next_steps: document.getElementById('fbNext').value, approve: action === 'approve' };
      Array.prototype.forEach.call(box.querySelectorAll('.fb-btn'), function (b) { b.disabled = true; });
      document.getElementById('fbMsg').textContent = action === 'approve' ? 'Approving…' : 'Saving…';
      MarkerAPI.saveFeedback(id, value).then(function (next) { editing[id] = false; rerender(next); }).catch(function (error) {
        document.getElementById('fbMsg').textContent = error.message || 'Could not save'; Array.prototype.forEach.call(box.querySelectorAll('.fb-btn'), function (b) { b.disabled = false; });
      });
    };
  }

  /* Map a level's position on its own scale (any number of levels) to five colour steps. */
  function tier(c) {
    var n = Math.max(1, (c.band_count || 1) - 1);
    return 't' + (Math.round((c.band_rank || 0) / n * 4) + 1);
  }

  window.MarkerPages = window.MarkerPages || {};
  window.MarkerPages.report = function (ui) {
    var params = new URLSearchParams(location.search), submissionId = params.get('submission_id');
    if (!submissionId) { location.replace('07-batches.html'); return Promise.resolve(null); }
    return MarkerAPI.getReport(submissionId, params.get('audience') === 'student' ? 'student' : 'internal').then(function (data) {
      window.__MARKER_PAGE_DATA = data;
      render(ui, data);
      var resultsUrl = '04-batch-complete.html?batch_id=' + encodeURIComponent(data.batch.id);
      var crumb = document.getElementById('bcBatch'); if (crumb) { crumb.textContent = data.batch.name; crumb.href = resultsUrl; }
      var up = document.getElementById('bcUp'); if (up) { up.href = resultsUrl; up.querySelector('.t').textContent = data.batch.name; }
      ui.setCrumb((data.submission.sid || 'Submission') + ' report');
      document.title = (data.submission.sid || 'Report') + ' — ' + data.batch.name + ' — AI-assisted marker';
      return data;
    }).catch(function (error) {
      if (error.code === 'report_not_ready') {
        document.getElementById('reportMain').innerHTML = '<section class="report"><div class="rh"><div><div class="eyebrow">Mark report</div><h1>Not confirmed yet</h1><p>A report is available once a tutor has confirmed every criterion.</p><p><a href="03b-review-split.html?submission_id=' + encodeURIComponent(submissionId) + '">Open the review →</a></p></div></div></section>';
        return null;
      }
      throw error;
    });
  };
})();
