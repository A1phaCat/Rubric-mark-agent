/* Results (04): summary, grade distribution, per-criterion table and submission list from GET /results. */
(function () {
  var LV = { HD: 'var(--lv1)', DI: 'var(--lv2)', CR: 'var(--lv3)', PS: 'var(--lv4)', FL: 'var(--lv5)' };
  var STATUS = { finalised: ['final', 'Finalised'], completed: ['completed', 'Complete'], in_review: ['completed', 'In review'], processing: ['completed', 'Processing'] };

  function bandOf(score, maximum) {
    var pct = maximum ? score / maximum * 100 : 0;
    return pct >= 85 ? 'HD' : pct >= 75 ? 'DI' : pct >= 65 ? 'CR' : pct >= 50 ? 'PS' : 'FL';
  }

  function requestReopenReason() {
    var modal = document.getElementById('reopenModal'), form = document.getElementById('reopenForm');
    var reason = document.getElementById('reopenReason'), confirm = document.getElementById('reopenConfirm');
    var cancel = document.getElementById('reopenCancel'), previousFocus = document.activeElement;
    reason.value = ''; confirm.disabled = true; modal.hidden = false;
    return new Promise(function (resolve) {
      function finish(value) {
        modal.hidden = true;
        reason.removeEventListener('input', update);
        form.removeEventListener('submit', submit);
        cancel.removeEventListener('click', cancelDialog);
        modal.removeEventListener('click', backdrop);
        document.removeEventListener('keydown', keydown);
        if (previousFocus && previousFocus.focus) previousFocus.focus();
        resolve(value);
      }
      function update() { confirm.disabled = !reason.value.trim(); }
      function submit(event) { event.preventDefault(); var value = reason.value.trim(); if (value) finish(value); }
      function cancelDialog() { finish(null); }
      function backdrop(event) { if (event.target === modal) finish(null); }
      function keydown(event) {
        if (event.key === 'Escape') { event.preventDefault(); finish(null); return; }
        if (event.key !== 'Tab') return;
        var focusable = [reason, confirm, cancel].filter(function (node) { return !node.disabled; });
        var first = focusable[0], last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
      reason.addEventListener('input', update);
      form.addEventListener('submit', submit);
      cancel.addEventListener('click', cancelDialog);
      modal.addEventListener('click', backdrop);
      document.addEventListener('keydown', keydown);
      setTimeout(function () { reason.focus(); }, 0);
    });
  }

  function requestFinaliseConfirmation() {
    var modal = document.getElementById('finaliseModal'), confirm = document.getElementById('finaliseConfirm');
    var cancel = document.getElementById('finaliseCancel'), previousFocus = document.activeElement;
    modal.hidden = false;
    return new Promise(function (resolve) {
      function finish(value) {
        modal.hidden = true;
        confirm.removeEventListener('click', confirmDialog);
        cancel.removeEventListener('click', cancelDialog);
        modal.removeEventListener('click', backdrop);
        document.removeEventListener('keydown', keydown);
        if (previousFocus && previousFocus.focus) previousFocus.focus();
        resolve(value);
      }
      function confirmDialog() { finish(true); }
      function cancelDialog() { finish(false); }
      function backdrop(event) { if (event.target === modal) finish(false); }
      function keydown(event) {
        if (event.key === 'Escape') { event.preventDefault(); finish(false); return; }
        if (event.key !== 'Tab') return;
        if (event.shiftKey && document.activeElement === confirm) { event.preventDefault(); cancel.focus(); }
        else if (!event.shiftKey && document.activeElement === cancel) { event.preventDefault(); confirm.focus(); }
      }
      confirm.addEventListener('click', confirmDialog);
      cancel.addEventListener('click', cancelDialog);
      modal.addEventListener('click', backdrop);
      document.addEventListener('keydown', keydown);
      setTimeout(function () { cancel.focus(); }, 0);
    });
  }

  function rowHTML(ui, item, maximum, locked) {
    var confirmed = item.status === 'confirmed', fin = item.final_total, ai = item.ai_total;
    var mark = confirmed
      ? '<span class="mark">' + (ai != null && Math.abs(ai - fin) > 0.001 ? '<span class="ai">' + ui.num(ai) + '</span>' : '') + '<span class="fin">' + ui.num(fin) + ' / ' + ui.num(maximum) + '</span><span class="band ' + bandOf(fin, maximum) + '">' + bandOf(fin, maximum) + '</span></span>'
      : '<span class="mark"><span class="ai" style="text-decoration:none">' + (ai == null ? '—' : 'AI ' + ui.num(ai)) + '</span></span>';
    var change;
    if (!confirmed) change = '<span class="change same">' + ui.esc(ui.statusLabel(item.status)) + '</span>';
    else if (ai == null) change = '<span class="change same">Marked manually</span>';
    else {
      var delta = Math.round((fin - ai) * 100) / 100, bandChanged = bandOf(fin, maximum) !== bandOf(ai, maximum);
      change = Math.abs(delta) < 0.001 && item.flags.indexOf('adjusted') < 0 ? '<span class="change same">Matches AI</span>'
        : '<span class="change"><span class="delta ' + (delta < 0 ? 'down' : 'up') + '">' + (delta > 0 ? '+' : delta < 0 ? '−' : '±') + ui.num(Math.abs(delta)) + '</span><span>adjusted by tutor' + (bandChanged ? '<small>band changed ' + bandOf(ai, maximum) + ' → ' + bandOf(fin, maximum) + '</small>' : '') + '</span></span>';
    }
    var link = confirmed ? '<span class="row-actions"><a class="rep" href="05-mark-report.html?submission_id=' + encodeURIComponent(item.id) + '">View report</a>' + (locked ? '' : '<a class="rep" href="03b-review-split.html?submission_id=' + encodeURIComponent(item.id) + '">Edit marks</a>') + '</span>'
      : (locked ? '—' : '<a class="rep" href="03b-review-split.html?submission_id=' + encodeURIComponent(item.id) + '">Review</a>');
    return '<tr data-adjusted="' + (confirmed && item.flags.indexOf('adjusted') >= 0 ? 1 : 0) + '" data-confirmed="' + (confirmed ? 1 : 0) + '" data-band-changed="' + (confirmed && ai != null && bandOf(fin, maximum) !== bandOf(ai, maximum) ? 1 : 0) + '">' +
      '<td class="sid">' + ui.esc(item.sid || item.filename) + '</td><td>' + mark + '</td><td>' + change + '</td><td>' + ui.esc(item.marker ? item.marker.name : '—') + '</td><td>' + link + '</td></tr>';
  }

  /* USD with enough digits for sub-cent calls; null means a model is missing from the price table. */
  function money(value) {
    if (value == null) return 'unpriced';
    var digits = value === 0 ? 2 : value < 0.01 ? 4 : value < 1 ? 3 : 2;
    return '$' + value.toFixed(digits);
  }
  function cents(value) { return value == null ? '' : ' <small>' + (value * 100).toFixed(value * 100 < 1 ? 2 : 1) + '¢</small>'; }

  /* AI usage card from GET /usage; shown only when the batch has recorded model calls
     (sample batches replay recorded results and make none). */
  function usageCardHTML(ui, usage) {
    var t = usage && usage.totals;
    if (!t || !t.calls) return '';
    var p = usage.pricing || {}, tokens = function (n) { return Number(n || 0).toLocaleString('en-AU'); };
    var perSub = t.cost_per_submission_usd, total = t.cost_usd;
    var unpriced = (p.unpriced_models || []).length
      ? '<p class="note usage-unpriced"><span class="dot"></span>No price for ' + p.unpriced_models.map(ui.esc).join(', ') + ' — add it to the price table. Priced calls so far: ' + money(t.priced_cost_usd) + '.</p>' : '';
    var models = (usage.by_model || []).map(function (m) {
      return '<tr><td>' + ui.esc(m.model) + '</td><td class="num">' + m.calls + '</td><td class="num">' + tokens(m.input_tokens) + '</td><td class="num">' + tokens(m.cached_tokens) + '</td><td class="num">' + tokens(m.output_tokens) + '</td><td class="num">' + money(m.cost_usd) + '</td></tr>';
    }).join('');
    return '<div class="card usage-card" id="usageCard" style="margin-bottom:24px"><h2>AI usage &amp; cost <small>' + t.calls + ' model call' + (t.calls === 1 ? '' : 's') + ' · ' + t.submissions_with_calls + ' submission' + (t.submissions_with_calls === 1 ? '' : 's') + '</small></h2>' +
      '<div class="kpis"><div class="kpi"><b data-usage="per-submission">' + money(perSub) + cents(perSub) + '</b><span>per submission<br>' + (t.max_submission_cost_usd == null ? '' : 'highest ' + money(t.max_submission_cost_usd)) + '</span></div>' +
      '<div class="kpi"><b data-usage="total">' + money(total) + '</b><span>this batch<br>all calls, retries included</span></div>' +
      '<div class="kpi"><b data-usage="per-call">' + money(t.cost_per_call_usd) + '</b><span>per model call<br>average</span></div>' +
      '<div class="kpi"><b>' + tokens(t.tokens_per_submission) + '</b><span>tokens per submission<br>input + output</span></div></div>' +
      '<table class="crit-table" style="margin-top:16px"><thead><tr><th>Model</th><th class="num">Calls</th><th class="num">Input tokens</th><th class="num">Cached</th><th class="num">Output tokens</th><th class="num">Cost</th></tr></thead><tbody>' + models + '</tbody></table>' +
      unpriced + '<p class="note usage-source"><span class="dot"></span>Estimated from recorded token counts at list prices in ' + ui.esc(p.currency || 'USD') + ' ' + ui.esc(p.unit || 'per 1M tokens') + ', checked ' + ui.esc(p.checked_at || 'unknown') + '. Not an invoice.</p></div>';
  }
  window.MarkerUsage = { money: money, cardHTML: usageCardHTML };

  window.MarkerPages = window.MarkerPages || {};
  window.MarkerPages.results = function (ui) {
    var batchId = new URLSearchParams(location.search).get('batch_id');
    if (!batchId) { location.replace('07-batches.html'); return Promise.resolve(null); }
    return Promise.all([MarkerAPI.getResults(batchId), MarkerAPI.getUsage(batchId).catch(function () { return null; })]).then(function (values) {
      var data = values[0], usage = values[1];
      data.usage = usage;
      window.__MARKER_PAGE_DATA = data;
      var batch = data.batch, s = data.summary, maximum = s.maximum, counts = batch.counts, locked = data.locked;
      var rows = data.submissions.items, pill = STATUS[batch.status] || ['completed', ui.statusLabel(batch.status)];
      var complete = batch.status === 'completed' || batch.status === 'finalised';
      var when = batch.status === 'finalised' ? 'finalised ' + ui.shortDate(batch.finalised_at) + ' · marks locked'
        : batch.status === 'completed' ? 'completed ' + ui.shortDate(batch.completed_at) + ' · editable until finalised' : 'review in progress';
      var actions = '<a class="btn" href="' + MarkerAPI.exportCsvUrl(batch.id) + '" download><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></svg>Export grades (CSV)</a>' +
        (batch.status === 'completed' ? '<button class="btn" type="button" id="finaliseBtn">Finalise &amp; lock marks</button>' : '') +
        (batch.status === 'finalised' ? '<span class="btn synced">Finalised · ' + ui.shortDate(batch.finalised_at) + '</span><button class="btn" type="button" id="reopenBtn">Reopen for changes</button>' : '') +
        (!complete ? '<a class="btn" href="02-batch-status.html?batch_id=' + encodeURIComponent(batch.id) + '">Back to review</a>' : '');

      var maxCount = Math.max.apply(null, data.distribution.map(function (d) { return d.count; }).concat([1]));
      var dist = data.distribution.map(function (d) {
        return '<div class="col" title="' + ui.esc(d.name) + ' · ' + ui.num(d.min_score) + '–' + ui.num(d.max_score) + '"><span class="n">' + d.count + '</span><span class="b" style="height:' + Math.max(d.count / maxCount * 100, d.count ? 6 : 2) + '%;background:' + LV[d.band] + (d.band === 'FL' ? ';border:1px solid var(--lv4)' : '') + '"></span><span class="g">' + d.band + '</span></div>';
      }).join('');

      var mostAdjusted = data.criteria.slice().sort(function (a, b) { return b.adjusted_count - a.adjusted_count; })[0];
      var criteriaRows = data.criteria.map(function (c) {
        return '<tr><td>' + ui.esc(c.name) + '</td><td class="num">' + (c.average_final == null ? '—' : ui.num(c.average_final) + ' / ' + ui.num(c.max_score)) + '</td><td class="num">' + (c.average_ai == null ? '—' : ui.num(c.average_ai)) + '</td><td class="num' + (mostAdjusted && c === mostAdjusted && c.adjusted_count ? ' hot' : '') + '">' + c.adjusted_count + '</td></tr>';
      }).join('');
      var note = mostAdjusted && mostAdjusted.adjusted_count
        ? ui.esc(mostAdjusted.name) + ' had the most tutor adjustments (' + mostAdjusted.adjusted_count + ' of ' + s.confirmed + ' confirmed submissions).'
        : 'Tutors confirmed every criterion as the AI suggested.';

      var adjustedCount = rows.filter(function (r) { return r.status === 'confirmed' && r.flags.indexOf('adjusted') >= 0; }).length;
      var bandChanged = rows.filter(function (r) { return r.status === 'confirmed' && r.ai_total != null && bandOf(r.final_total, maximum) !== bandOf(r.ai_total, maximum); }).length;
      var confirmedCount = rows.filter(function (r) { return r.status === 'confirmed'; }).length;

      document.getElementById('resultsMain').innerHTML =
        '<div class="top"><div><h1>' + ui.esc(batch.name) + ' <span class="pill ' + pill[0] + '"><span class="dot"></span>' + pill[1] + '</span>' + (batch.is_sample ? '<span class="pill sample">Sample</span>' : '') + '</h1>' +
        '<p class="sub">' + counts.total + ' submission' + (counts.total === 1 ? '' : 's') + ' · ' + ((batch.rubric || {}).criteria_count || 0) + ' criteria · out of ' + ui.num(maximum) + ' · ' + when + '</p></div><div class="actions">' + actions + '</div></div>' +
        '<div class="summary"><div class="card"><h2>' + (complete ? 'Review complete' : 'Review progress') + ' <small>' + s.confirmed + ' confirmed</small></h2>' +
        '<div class="done-row"><span>Submissions confirmed by a tutor</span><span class="val">' + counts.confirmed + ' / ' + counts.total + '</span></div><div class="bar"><span style="width:' + (counts.total ? counts.confirmed / counts.total * 100 : 0) + '%"></span></div>' +
        '<div class="kpis"><div class="kpi"><b>' + (s.average_final == null ? '—' : ui.num(s.average_final)) + '</b><span>average mark<br>' + (s.average_ai == null ? '' : 'AI suggested ' + ui.num(s.average_ai)) + '</span></div>' +
        '<div class="kpi"><b>' + s.adjusted_count + ' <small>' + ui.num(s.adjusted_percent) + '%</small></b><span>submissions adjusted<br>from the AI</span></div>' +
        '<div class="kpi"><b>' + s.comments_count + '</b><span>criterion<br>comments</span></div>' +
        '<div class="kpi"><b>' + s.marker_count + '</b><span>tutor' + (s.marker_count === 1 ? '' : 's') + ' · ' + s.markers.map(function (m) { return ui.esc(m.name); }).join(', ') + '</span></div></div></div>' +
        '<div class="card"><h2>Grade distribution <small>final marks</small></h2><div class="dist" aria-label="Grade distribution">' + dist + '</div></div></div>' +
        usageCardHTML(ui, usage) +
        '<div class="card" style="margin-bottom:24px"><h2>By criterion <small>where tutors changed the AI most</small></h2><table class="crit-table"><thead><tr><th>Criterion</th><th class="num">Avg mark</th><th class="num">AI avg</th><th class="num">Adjusted</th></tr></thead><tbody>' + criteriaRows + '</tbody></table><p class="note"><span class="dot"></span>' + note + '</p></div>' +
        '<div class="filters"><button type="button" class="chip active" data-f="all">All (' + rows.length + ')</button><button type="button" class="chip" data-f="adjusted">Adjusted by tutor (' + adjustedCount + ')</button><button type="button" class="chip" data-f="same">Matches AI (' + (confirmedCount - adjustedCount) + ')</button><button type="button" class="chip" data-f="band">Band changed (' + bandChanged + ')</button></div>' +
        '<div class="table-wrap"><table class="subs"><thead><tr><th>Submission</th><th>Final mark</th><th>Tutor changes</th><th>Tutor</th><th>Actions</th></tr></thead><tbody>' + rows.map(function (r) { return rowHTML(ui, r, maximum, locked); }).join('') + '</tbody></table>' +
        '<div id="resultsPager" style="padding:0 16px"></div><div class="foot"><span id="showing">' + rows.length + ' submissions</span><span>' + (locked ? 'Marks are locked — reopen the batch to change them' : 'Marks can still be changed from the review page') + '</span></div></div>';

      /* Filter, then page 100 rows at a time so batches of 1,000+ stay fast to render and scroll. */
      var PAGE = 100, current = { f: 'all', page: 1 };
      function matches(tr, f) { return f === 'all' || (f === 'adjusted' && tr.dataset.adjusted === '1') || (f === 'same' && tr.dataset.confirmed === '1' && tr.dataset.adjusted === '0') || (f === 'band' && tr.dataset.bandChanged === '1'); }
      function apply() {
        var all = Array.prototype.slice.call(document.querySelectorAll('table.subs tbody tr')), hits = all.filter(function (tr) { return matches(tr, current.f); });
        var pages = Math.max(1, Math.ceil(hits.length / PAGE)); current.page = Math.min(current.page, pages);
        all.forEach(function (tr) { tr.hidden = true; });
        hits.slice((current.page - 1) * PAGE, current.page * PAGE).forEach(function (tr) { tr.hidden = false; });
        var holder = document.getElementById('resultsPager'); holder.innerHTML = ui.pager(hits.length, current.page, PAGE);
        holder.querySelectorAll('[data-page]').forEach(function (b) { b.addEventListener('click', function () { current.page = Number(b.dataset.page); apply(); document.querySelector('.filters').scrollIntoView({ block: 'start' }); }); });
        document.getElementById('showing').textContent = hits.length + ' of ' + rows.length + ' submissions';
      }
      Array.prototype.forEach.call(document.querySelectorAll('.filters .chip'), function (chip) {
        chip.addEventListener('click', function () {
          document.querySelectorAll('.filters .chip').forEach(function (c) { c.classList.toggle('active', c === chip); });
          current = { f: chip.dataset.f, page: 1 }; apply();
        });
      });
      apply();
      var finalise = document.getElementById('finaliseBtn');
      if (finalise) finalise.addEventListener('click', function () {
        requestFinaliseConfirmation().then(function (confirmed) {
          if (!confirmed) return;
          finalise.disabled = true;
          MarkerAPI.finaliseBatch(batch.id, batch.version).then(function () { location.reload(); }).catch(function (error) { finalise.disabled = false; MarkerDialog.alert(ui.actionError('Could not finalise the batch', error)); });
        });
      });
      var reopen = document.getElementById('reopenBtn');
      if (reopen) reopen.addEventListener('click', function () {
        requestReopenReason().then(function (reason) {
          if (!reason) return;
          reopen.disabled = true;
          MarkerAPI.reopenBatch(batch.id, batch.version, reason).then(function () { location.reload(); }).catch(function (error) { reopen.disabled = false; MarkerDialog.alert(ui.actionError('Could not reopen the batch', error)); });
        });
      });
      ui.setCrumb(batch.name);
      ui.stepTrack(batch.status);
      document.title = batch.name + ' results — AI-assisted marker';
      return ui.batchNav(batch).then(function () { return data; });
    });
  };
})();
