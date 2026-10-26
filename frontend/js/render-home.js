/* Home: every number, card and queue item is rendered from the API. */
(function () {
  var GRADE_COLORS = { HD: '#8F3F24', DI: '#B85A35', CR: '#D9895F', PS: '#EDB999', FL: '#E9E2DA' };
  var STATE = {
    draft: ['done', 'Draft'], processing: ['processing', 'Processing'], in_review: ['reviewing', 'In review'],
    completed: ['done', 'Complete'], finalised: ['final', 'Finalised'], failed_all: ['processing', 'Failed'], cancelled: ['done', 'Cancelled']
  };

  function greeting(name) {
    var hour = new Date().getHours();
    return (hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening') + ', ' + name;
  }

  function batchHref(batch) {
    return (batch.status === 'completed' || batch.status === 'finalised' ? '04-batch-complete.html' : '02-batch-status.html') + '?batch_id=' + encodeURIComponent(batch.id);
  }

  function confidenceBlock(ui, batch) {
    var c = batch.insights.confidence, processed = c.high + c.medium + c.low + c.none, total = batch.counts.total || 1;
    function seg(value, color) { return value ? '<span style="width:' + (value / total * 100).toFixed(1) + '%; background:' + color + '"></span>' : ''; }
    return '<div class="conf"><div class="label"><span>AI confidence, processed so far</span><span>' + processed + ' / ' + batch.counts.total + '</span></div>' +
      '<div class="bar" aria-label="Confidence breakdown">' + seg(c.high, 'var(--conf-high)') + seg(c.medium, 'var(--conf-med-dot)') + seg(c.low, 'var(--conf-low)') + seg(batch.counts.needs_manual, 'var(--conf-none)') + '</div>' +
      '<div class="legend"><span class="tag high"><span class="dot"></span>High <b>' + c.high + '</b></span><span class="tag medium"><span class="dot"></span>Medium <b>' + c.medium + '</b></span><span class="tag low"><span class="dot"></span>Low <b>' + c.low + '</b></span><span class="tag none"><span class="dot"></span>Manual <b>' + batch.counts.needs_manual + '</b></span></div></div>';
  }

  function gradeBlock(ui, batch) {
    var grades = batch.insights.grades, keys = Object.keys(grades), avg = batch.insights.average_final;
    return '<div class="conf"><div class="label"><span>Final grades</span><span>' + (avg == null ? '—' : 'avg ' + ui.num(avg) + ' / ' + ui.num(batch.insights.maximum)) + '</span></div>' +
      '<div class="dist">' + keys.map(function (k) { return grades[k] ? '<span style="flex:' + grades[k] + '; background:' + GRADE_COLORS[k] + '"></span>' : ''; }).join('') + '</div>' +
      '<div class="mini">' + keys.map(function (k) { return '<span><i class="lv" style="background:' + GRADE_COLORS[k] + '"></i>' + k + ' <b>' + grades[k] + '</b></span>'; }).join('') + '</div></div>';
  }

  function batchCard(ui, batch) {
    var counts = batch.counts, pill = STATE[batch.display_status] || STATE[batch.status] || STATE.draft, rubric = batch.rubric || {};
    var due = batch.due_at ? (new Date(batch.due_at) < new Date() ? 'closed ' : 'due ') + ui.shortDate(batch.due_at) : 'no due date';
    var meta = counts.total + ' submission' + (counts.total === 1 ? '' : 's') + ' · ' + (rubric.criteria_count || 0) + ' criteria · ' + due;
    var done = batch.status === 'completed' || batch.status === 'finalised';
    var body = done ? gradeBlock(ui, batch) : confidenceBlock(ui, batch);
    var figs = done
      ? '<span><b>' + counts.confirmed + '</b> confirmed</span><span><b>' + counts.adjusted + '</b> adjusted from AI</span><span>' + (batch.status === 'finalised' ? 'marks locked' : 'editable until finalised') + '</span>'
      : '<span><b>' + counts.ready + '</b> ready for review</span><span><b>' + counts.confirmed + ' / ' + counts.total + '</b> confirmed</span>' + (counts.processing ? '<span><b>' + counts.processing + '</b> still with AI</span>' : counts.needs_manual ? '<span><b>' + counts.needs_manual + '</b> need manual marking</span>' : '');
    return '<a class="panel batch" href="' + batchHref(batch) + '"><div class="batch-top"><div><h3 class="batch-title">' + ui.esc(batch.name) + (batch.is_sample ? '<span class="sample-tag" title="Sample batch">Sample</span>' : '') + (batch.pinned ? '<span class="pin-mark" title="Pinned">📌</span>' : '') + '</h3>' +
      '<div class="batch-meta">' + ui.esc(meta) + '</div></div><span class="pill ' + pill[0] + '"><span class="dot"></span>' + pill[1] + '</span></div>' + body +
      '<div class="batch-foot"><div class="figs">' + figs + '</div><span class="go">' + (done ? 'View results →' : 'Open batch →') + '</span></div></a>';
  }

  function queueItem(ui, item) {
    var manual = item.reason === 'needs_manual';
    var why = manual ? 'No text layer · mark by hand' : (item.criterion_name ? item.criterion_name + ' · ' : 'All criteria · ') + (item.confidence || 'unknown') + ' confidence';
    var tag = manual ? '<span class="tag manual">Manual</span>' : '<span class="tag ' + item.confidence + '"><span class="dot"></span>' + ({ low: 'Low', medium: 'Med', high: 'High' }[item.confidence] || '—') + '</span>';
    return '<a class="q-item" href="03b-review-split.html?submission_id=' + encodeURIComponent(item.submission_id) + '"><div class="q-main"><div class="q-sid">' + ui.esc(item.sid || item.submission_id) + '</div><div class="q-why">' + ui.esc(item.batch_name) + ' · ' + ui.esc(why) + '</div></div>' + tag + '<span class="q-score">' + (item.ai_total == null ? '—' : ui.num(item.ai_total)) + '</span></a>';
  }

  window.MarkerPages = window.MarkerPages || {};
  window.MarkerPages.home = function (ui) {
    return Promise.all([MarkerAPI.me(), MarkerAPI.homeSummary(), MarkerAPI.homeQueue(5), MarkerAPI.listBatches(), MarkerAPI.listRubrics()]).then(function (values) {
      var me = values[0], summary = values[1], queue = values[2], batches = values[3], rubrics = values[4];
      window.__MARKER_PAGE_DATA = { me: me, summary: summary, queue: queue, batches: batches, rubrics: rubrics };

      document.getElementById('homeTerm').textContent = me.term ? me.term.label : '';
      document.getElementById('homeGreeting').textContent = greeting(me.user.name);
      window.addEventListener('marker:user', function (event) { document.getElementById('homeGreeting').textContent = greeting(event.detail.name); });
      var needing = summary.batches_needing_review;
      document.getElementById('homeLede').textContent = (needing ? needing + ' batch' + (needing === 1 ? ' needs' : 'es need') + ' your review. ' : 'Nothing is waiting for review. ') + 'The AI finds evidence for each criterion; you decide every final mark.';

      var ready = summary.ready_for_review, first = ready.by_batch[0], low = summary.low_confidence, manual = summary.needs_manual, week = summary.confirmed_this_week;
      var nextHref = ready.next_submission_id ? '03b-review-split.html?submission_id=' + encodeURIComponent(ready.next_submission_id) : '07-batches.html';
      var lowBatch = low.by_batch[0], manualBatch = manual.by_batch[0];
      var stats = document.getElementById('homeStats');
      stats.removeAttribute('aria-busy');
      stats.innerHTML =
        '<a class="stat accent" href="' + nextHref + '"><span class="k">Ready for your review</span><span class="v">' + ready.count + ' <small>submission' + (ready.count === 1 ? '' : 's') + '</small></span><span class="s">' + (first ? ui.esc(first.batch_name) + (ready.by_batch.length > 1 ? ' + ' + (ready.by_batch.length - 1) + ' more' : '') : 'all caught up') + '</span></a>' +
        '<a class="stat" href="' + (lowBatch ? '02-batch-status.html?batch_id=' + encodeURIComponent(lowBatch.batch_id) + '&filter=low_confidence' : '07-batches.html') + '"><span class="k"><span class="dot" style="background:var(--conf-low)"></span>Low confidence to check</span><span class="v">' + low.count + '</span><span class="s">flagged for a closer look</span></a>' +
        '<a class="stat" href="' + (manualBatch ? '02-batch-status.html?batch_id=' + encodeURIComponent(manualBatch.batch_id) + '&filter=needs_manual' : '07-batches.html') + '"><span class="k"><span class="dot" style="background:var(--conf-none)"></span>Need manual marking</span><span class="v">' + manual.count + '</span><span class="s">no readable text found</span></a>' +
        '<div class="stat"><span class="k"><span class="dot" style="background:var(--info)"></span>Confirmed this week</span><span class="v">' + week.count + '</span><span class="s">' + week.by_me + ' by you</span></div>';

      /* Home shows at most three batches: the (at most three) pinned ones, then the newest. */
      var shown = batches.items.filter(function (b) { return b.status !== 'cancelled'; }).slice(0, 3);
      var reset = document.getElementById('resetSamples');
      if (reset && !reset.dataset.wired) {
        reset.dataset.wired = '1';
        reset.addEventListener('click', function () {
          if (!confirm('Reset the sample batches? Their marks, comments and confirmations go back to the starting state. Your own batches and rubrics are kept.')) return;
          reset.disabled = true; reset.textContent = 'Resetting…';
          MarkerAPI.resetSamples().then(function () { location.reload(); }).catch(function (error) { reset.disabled = false; reset.textContent = '↺ Reset samples'; alert(error.message); });
        });
      }
      document.getElementById('homeBatches').innerHTML = shown.length ? shown.map(function (b) { return batchCard(ui, b); }).join('') : '<p class="home-empty">No batches yet. Start one with “New marking batch”.</p>';

      var items = queue.items;
      document.getElementById('queueNote').textContent = first ? first.batch_name.split(' — ')[0] + ' · ' + ready.count + ' ready' : '';
      document.getElementById('homeQueue').innerHTML = items.length ? items.map(function (item) { return queueItem(ui, item); }).join('') : '<p class="home-empty">Nothing waiting for review.</p>';
      var foot = document.getElementById('queueFoot');
      foot.hidden = !items.length;
      if (items.length) document.getElementById('queueStart').href = '03b-review-split.html?submission_id=' + encodeURIComponent(items[0].submission_id);

      /* The three most recently created or edited rubrics. */
      var recent = rubrics.items.slice().sort(function (a, b) { return Date.parse(b.updated_at) - Date.parse(a.updated_at); }).slice(0, 3);
      document.getElementById('recentRubrics').innerHTML = recent.map(function (r) {
        return '<a class="r" href="06-rubrics.html#open=' + encodeURIComponent(r.id) + '"><span class="r-main" title="' + ui.esc(r.title) + '">' + ui.esc(r.title) + '<small>Updated ' + ui.ago(r.updated_at) + (r.is_sample ? ' · sample' : '') + '</small></span><span class="r-count">' + r.criteria_count + ' criteria</span></a>';
      }).join('') + '<a class="r-add" href="01a-rubric-import.html">+ Import a rubric</a>';
    });
  };
})();
