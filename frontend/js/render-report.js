/* Mark report (05): one confirmed submission, rendered from GET /submissions/{id}/report. */
(function () {
  function initials(name) { return String(name || '?').split(/[\s.]+/).filter(Boolean).map(function (p) { return p[0]; }).join('').slice(0, 2).toUpperCase(); }

  function render(ui, data) {
    var marker = data.marker ? data.marker.name : 'Tutor', internal = data.audience === 'internal', fb = data.feedback;
    var status = data.locked ? '<span class="rel">✓ Finalised · marks locked</span>' : 'Confirmed · editable until the batch is finalised';
    var aiNote = internal && data.ai_total != null
      ? (Math.abs(data.adjustment) > 0.001 ? 'AI suggested <s>' + ui.num(data.ai_total) + '</s> · adjusted ' + (data.adjustment > 0 ? '+' : '−') + ui.num(Math.abs(data.adjustment)) + ' by tutor' : 'Confirmed as the AI suggested')
      : '';
    var breakdown = data.criteria.map(function (c) {
      return '<div class="bd-row"><span>' + ui.esc(c.name) + '</span><span class="track"><span style="width:' + (c.max_score ? c.score / c.max_score * 100 : 0) + '%"></span></span><span class="pts">' + ui.num(c.score) + ' / ' + ui.num(c.max_score) + '</span></div>';
    }).join('');
    var summary = fb ? '<section class="ai-sum" aria-label="Summary"><div class="hd"><h2><span class="badge">AI</span>Summary of this submission</h2><span class="rev">Reviewed by ' + ui.esc(marker) + ' before release</span></div>' +
      '<p>' + ui.esc(fb.summary) + '</p><ul>' +
      (fb.strengths || []).map(function (t) { return '<li><b>Strongest:</b> ' + ui.esc(t) + '</li>'; }).join('') +
      (fb.improvements || []).map(function (t) { return '<li><b>To improve:</b> ' + ui.esc(t) + '</li>'; }).join('') +
      (fb.next_steps || []).map(function (t) { return '<li><b>Next step:</b> ' + ui.esc(t) + '</li>'; }).join('') + '</ul></section>' : '';
    var criteria = data.criteria.map(function (c) {
      var delta = internal && c.ai_score != null ? Math.round((c.score - c.ai_score) * 100) / 100 : 0;
      var sources = c.evidence.length ? '<div class="src evidence-used">Evidence used ' + c.evidence.map(function (e) { return '<span title="' + ui.esc(e.quote) + '">p.' + ui.esc(e.page) + ' ' + ui.esc(e.paragraph || '') + '</span>'; }).join('') + '</div>' : '';
      return '<article class="crit"><div class="crit-top"><div><h3>' + ui.esc(c.name) + '</h3><p class="desc">' + ui.esc(c.descriptor) + '</p></div><div class="pts"><b>' + ui.num(c.score) + '<small> / ' + ui.num(c.max_score) + '</small></b><span class="band ' + c.band + '">' + c.band + '</span></div></div>' +
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
      '<div class="breakdown" aria-label="Marks by criterion">' + breakdown + '</div></section>' + summary +
      '<h2 class="section-title">Feedback by criterion</h2>' + criteria +
      '<p class="footnote"><span class="dot"></span>Marks were suggested by AI from the evidence in this submission and confirmed or adjusted by a tutor. Every final mark and comment on this page was approved by a person.</p>';
    Array.prototype.forEach.call(document.querySelectorAll('.audience button'), function (button) {
      button.addEventListener('click', function () {
        var params = new URLSearchParams(location.search); params.set('audience', button.dataset.a);
        history.replaceState(null, '', '?' + params.toString());
        MarkerAPI.getReport(data.submission.id, button.dataset.a).then(function (next) { window.__MARKER_PAGE_DATA = next; render(ui, next); });
      });
    });
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
