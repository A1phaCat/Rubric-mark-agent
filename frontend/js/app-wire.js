(function () {
  /* Connects every page to the API. All data shown comes from the local database through
     MarkerAPI; page-specific renderers live in render-home.js, render-results.js and
     render-report.js and receive the helpers below. */

  /* ---------------------------------------------------------------- helpers */
  function esc(value) { return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;'); }
  function num(value) { if (value == null || value === '') return '—'; var n = Number(value); return Math.abs(n - Math.round(n)) < 0.005 ? String(Math.round(n)) : String(Math.round(n * 100) / 100); }
  function date(value) { var d = value ? new Date(value) : null; return d && !isNaN(d.getTime()) ? d : null; }
  function shortDate(value) { var d = date(value); return d ? d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', timeZone: 'Australia/Sydney' }) : '—'; }
  function longDate(value) { var d = date(value); return d ? d.toLocaleString('en-AU', { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'Australia/Sydney' }) : '—'; }
  function ago(value) {
    var d = date(value); if (!d) return '—';
    var m = Math.round((Date.now() - d.getTime()) / 6e4);
    if (m < 1) return 'just now'; if (m < 60) return m + ' min ago';
    var h = Math.round(m / 60); if (h < 24) return h + ' h ago';
    var days = Math.round(h / 24); if (days < 31) return days + (days === 1 ? ' day ago' : ' days ago');
    var mo = Math.round(days / 30); return mo + (mo === 1 ? ' month ago' : ' months ago');
  }
  var STATUS_LABELS = {
    uploaded: 'Not started', queued: 'Queued', extracting: 'Extracting text', marking: 'With the AI', ai_done: 'Ready for review', in_review: 'In review',
    needs_ocr: 'Needs manual marking', ocr_failed: 'Needs manual marking', confirmed: 'Confirmed', failed: 'Failed', excluded: 'Excluded', cancelled: 'Cancelled',
    draft: 'Draft', processing: 'Processing', completed: 'Complete', finalised: 'Finalised', failed_all: 'Failed'
  };
  function statusLabel(status) { return STATUS_LABELS[status] || String(status || '').replace(/_/g, ' '); }
  function pageName() { return (location.pathname.split('/').pop() || '00-home.html').toLowerCase(); }
  function reportError(error) {
    document.documentElement.dataset.apiState = 'error';
    console.error('Marker data load failed', error);
    var main = document.querySelector('main');
    if (main && !document.querySelector('[data-load-error]')) {
      var box = document.createElement('div');
      box.dataset.loadError = 'true'; box.setAttribute('role', 'alert');
      box.style.cssText = 'margin:16px 0;padding:12px 16px;border-radius:8px;background:#FBE9E5;color:#8A2A12;font:500 13px Inter,sans-serif';
      box.textContent = (error && error.status === 404 ? 'Not found: ' : 'Could not load data from the local server: ') + (error && error.message ? error.message : error);
      main.insertBefore(box, main.firstChild);
    }
  }
  /* "Showing 101–200 of 1,000" with previous/next; rendered only when there is more than one page. */
  function pager(total, page, size) {
    var pages = Math.max(1, Math.ceil(total / size));
    if (pages <= 1) return total ? '<p class="pager-note" style="font-size:12px;color:var(--ink-soft);margin:10px 2px">Showing all ' + total + '</p>' : '';
    var from = (page - 1) * size + 1, to = Math.min(total, page * size);
    return '<div class="pager" style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin:12px 2px;font-size:12.5px;color:var(--ink-soft)">' +
      '<span>Showing ' + from + '–' + to + ' of ' + total.toLocaleString('en-AU') + '</span><span style="display:flex;gap:6px">' +
      '<button type="button" class="chip" data-page="' + (page - 1) + '"' + (page <= 1 ? ' disabled' : '') + '>← Previous</button>' +
      '<span style="align-self:center">Page ' + page + ' / ' + pages + '</span>' +
      '<button type="button" class="chip" data-page="' + (page + 1) + '"' + (page >= pages ? ' disabled' : '') + '>Next →</button></span></div>';
  }
  function setCrumb(text) { var node = document.getElementById('bcCur'); if (node) node.textContent = text; }
  function stepTrack(status) {
    var node = document.getElementById('stepTrack'); if (!node) return;
    var steps = ['1. Set up batch', '2. Processing', '3. Review', '4. Finalised'];
    var current = { draft: 0, processing: 1, in_review: 2, completed: 2, finalised: 3 }[status];
    if (current == null) current = 2;
    node.innerHTML = steps.map(function (label, index) { return index < current ? '<span class="ok">✓</span> ' + label : index === current ? '<span class="current">' + label + '</span>' : label; }).join(' — ');
  }
  function batchHref(batch) {
    return (batch.status === 'completed' || batch.status === 'finalised' ? '04-batch-complete.html' : '02-batch-status.html') + '?batch_id=' + encodeURIComponent(batch.id);
  }
  /* Header "Batch n / N" and the footer previous/next follow the same order as the batch list. */
  function batchNav(batch) {
    return MarkerAPI.listBatches().then(function (data) {
      var list = data.items.filter(function (item) { return item.status !== 'cancelled'; });
      var index = list.findIndex(function (item) { return item.id === batch.id; });
      var n = document.getElementById('bpN'), total = document.getElementById('bpTotal'), segs = document.getElementById('bpSegs');
      if (n) n.textContent = index >= 0 ? index + 1 : '–';
      if (total) total.textContent = list.length;
      if (segs) segs.innerHTML = list.slice(0, 12).map(function (_, i) { return '<i class="' + (i <= index ? 'on' : '') + '"></i>'; }).join('');
      var dot = document.getElementById('bpDot'), status = document.getElementById('bpStatus'), counts = batch.counts || {};
      if (dot) dot.className = 'bp-dot ' + (batch.status === 'completed' || batch.status === 'finalised' ? 'done' : batch.status === 'in_review' ? 'review' : '');
      if (status) status.innerHTML = counts.failed ? '<b>' + counts.failed + '</b> failed — retry needed'
        : counts.processing ? '<b>' + counts.processing + '</b> still with AI'
        : batch.status === 'finalised' ? 'Finalised · marks locked'
        : batch.status === 'completed' ? 'Complete · editable'
        : '<b>' + (counts.ready || 0) + '</b> ready for review';
      function setBtn(id, item) {
        var a = document.getElementById(id); if (!a) return;
        if (!item) { a.setAttribute('aria-disabled', 'true'); a.removeAttribute('href'); a.removeAttribute('title'); a.querySelector('.n').textContent = 'None'; return; }
        a.removeAttribute('aria-disabled'); a.href = batchHref(item); a.title = item.name; a.querySelector('.n').textContent = item.name;
      }
      setBtn('bbPrev', index > 0 ? list[index - 1] : null);
      setBtn('bbNext', index >= 0 && index < list.length - 1 ? list[index + 1] : null);
    });
  }
  /* A criterion's own scale (any labels, 2–6 levels). Canvas-style bands show their range;
     levels without descriptors show label and points only. */
  function levelsHtml(def, aiLevel) {
    var levels = def.levels || [];
    var plain = !levels.some(function (level) { return String(level.description || '').trim(); });
    var about = def.description ? '<p class="crit-about">' + esc(def.description) + '</p>' : '';
    return about + '<details' + (plain ? ' open' : '') + '><summary>Rubric levels · ' + levels.length + (plain ? ' · labels and points only' : '') + '</summary><div class="level-list' + (plain ? ' plain' : '') + '">' + levels.map(function (level) {
      var top = level.points == null ? level.max_score : level.points, low = level.min_score;
      var pts = low != null && top != null && Number(low) < Number(top) ? num(low) + '–' + num(top) : num(top);
      var text = String(level.description || '').trim();
      return '<div' + (aiLevel && aiLevel === level.label ? ' class="is-ai" title="AI suggestion falls in this level"' : '') + '><strong>' + esc(level.label) + ' (' + esc(pts) + ')</strong>' + (text ? ': ' + esc(text) : '') + '</div>';
    }).join('') + '</div></details>';
  }
  function wireUser() {
    return MarkerAPI.me().then(applyUser).catch(function (error) { console.warn('Could not load the current user', error); });
  }
  /* Paint the stored account name into every header; also used after a rename. */
  function applyUser(me) {
    {
      var name = me.user.name, initials = name.split(/[\s.]+/).filter(Boolean).map(function (p) { return p[0]; }).join('').slice(0, 2).toUpperCase();
      document.querySelectorAll('.ab-uname').forEach(function (node) { node.textContent = name; });
      document.querySelectorAll('.ab-avatar').forEach(function (node) { node.textContent = initials; });
      document.querySelectorAll('.ab-user').forEach(function (node) { node.title = 'Local single-user mode'; });
      window.dispatchEvent(new CustomEvent('marker:user', { detail: { name: name, initials: initials } }));
    }
    return me;
  }
  var ui = { pager: pager, esc: esc, num: num, shortDate: shortDate, longDate: longDate, ago: ago, statusLabel: statusLabel, setCrumb: setCrumb, stepTrack: stepTrack, batchNav: batchNav, batchHref: batchHref, reportError: reportError, applyUser: applyUser };
  window.MarkerUI = ui;

  /* ------------------------------------------------------------- rubrics */
  function rubricShape(item) {
    var rubric = item.rubric || item, used = item.used_by || [];
    return {
      id: rubric.id, version: rubric.version, title: rubric.title, source: rubric.source, updated: Date.parse(rubric.updated_at),
      pinned: !!rubric.pinned, isSample: !!rubric.is_sample,
      usedBy: used.length ? used.map(function (batch) { return batch.batch_name; }) : (rubric.used_by_count ? ['In use by ' + rubric.used_by_count + ' batch' + (rubric.used_by_count === 1 ? '' : 'es')] : []),
      criteria: (rubric.criteria || []).map(function (c) { var levels = (c.levels || []).map(function (level) { return { id: level.id, label: level.label, points: level.points, min_score: level.min_score, max_score: level.max_score, min_inclusive: level.min_inclusive, max_inclusive: level.max_inclusive, description: level.description, prov: level.prov || {}, source_text: level.source_text || {} }; }); return { id: c.id, name: c.name, weight: c.weight, description: c.description || '', stated_percent: c.stated_percent, scoring_mode: c.scoring_mode, score_mapping: c.score_mapping, granularity: c.granularity, grading_mode: c.grading_mode, aspects: c.aspects || [], prov: c.prov || {}, source_text: c.source_text || {}, levels: levels, bands: levels.map(function (level) { return level.description; }) }; })
    };
  }
  function loadRubricLibrary() {
    return MarkerAPI.listRubrics().then(function (data) {
      return Promise.all(data.items.map(function (item) { return MarkerAPI.getRubric(item.id); })).then(function (items) {
        var converted = items.map(rubricShape);
        if (window.RubricLib) RubricLib.saveAll(converted);
        return { list: data, items: items, converted: converted };
      });
    });
  }
  function wireRubrics() {
    window.MarkerReloadRubrics = function () { return loadRubricLibrary().then(function (loaded) { window.__MARKER_PAGE_DATA = { items: loaded.items, total: loaded.list.total }; return loaded; }); };
    return window.MarkerReloadRubrics().then(function () {
      if (window.RubricListUI) window.RubricListUI.refresh();
      var openMatch = location.hash.match(/open=([\w-]+)/); if (openMatch && window.RubricListUI) window.RubricListUI.openById(openMatch[1]);
      var note = document.querySelector('.foot-note'); if (note) note.textContent = 'Saved in the local database. Pinned rubrics are listed first.';
    });
  }
  function wireSetup() {
    return loadRubricLibrary().then(function (loaded) {
      window.__MARKER_PAGE_DATA = { rubrics: loaded.list, settings: null };
      return MarkerAPI.getSettings().then(function (settings) {
        window.__MARKER_PAGE_DATA.settings = settings;
        window.dispatchEvent(new CustomEvent('marker:rubrics-loaded'));
        return window.__MARKER_PAGE_DATA;
      });
    });
  }

  /* -------------------------------------------------------- batch status */
  var FILTERS = [['all', 'All', 'total'], ['ready', 'Ready for review', 'ready'], ['low_confidence', 'Low confidence', 'low_confidence'], ['needs_manual', 'Needs manual marking', 'needs_manual'], ['processing', 'Processing', 'processing'], ['confirmed', 'Confirmed', 'confirmed'], ['failed', 'Failed', 'failed']];
  function wireBatchStatus() {
    var params = new URLSearchParams(location.search), batchId = params.get('batch_id'), filter = params.get('filter') || 'all', page = Math.max(1, Number(params.get('page') || 1)), PAGE_SIZE = 100;
    if (!batchId) { location.replace('07-batches.html'); return Promise.resolve(null); }
    var timer = null;
    function load() {
      return Promise.all([MarkerAPI.getBatch(batchId), MarkerAPI.listSubmissions(batchId, filter, page, PAGE_SIZE)]).then(function (values) {
        var batch = values[0].batch, submissions = values[1], counts = batch.counts || {}, rubric = batch.rubric || {};
        window.__MARKER_PAGE_DATA = { batch: batch, submissions: submissions };
        var maximum = Number(rubric.total_weight || 0), processed = Number(counts.processed || 0), all = Number(counts.total || 0), pct = all ? Math.round(processed / all * 100) : 0;
        var first = submissions.items.find(function (item) { return item.status === 'ai_done' || item.status === 'in_review'; }) || submissions.items.find(function (item) { return item.status === 'needs_ocr'; });
        var rows = submissions.items.map(function (item) {
          var ready = item.status === 'ai_done' || item.status === 'in_review', failed = item.status === 'failed', manual = item.status === 'needs_ocr' || item.status === 'ocr_failed', confirmed = item.status === 'confirmed';
          var label = failed ? 'Failed' : (ready || manual || confirmed) ? statusLabel(item.status) : (item.progress || statusLabel(item.status));
          var stateClass = ready ? 'ready' : failed ? 'failed' : confirmed ? 'reviewed' : manual ? 'failed' : 'processing';
          var flags = [];
          if (item.confidence === 'low' && ready) flags.push('<span class="flag">⚑ low confidence</span>');
          if (manual) flags.push('<span class="flag">⚑ no text layer · mark by hand</span>');
          if (item.flags.indexOf('adjusted') >= 0) flags.push('<span class="flag" style="color:var(--ink-soft)">adjusted from AI</span>');
          if (failed) { var message = item.error && item.error.message ? item.error.message : 'AI grading failed'; flags.push('<span class="flag">⚠ Processing failed</span><span class="error-msg" title="' + esc(message) + '">' + esc(message) + '</span><button type="button" class="retry-btn" data-retry="' + esc(item.id) + '" data-version="' + esc(item.version) + '">Retry remaining criteria</button>'); }
          var href = confirmed ? '05-mark-report.html?submission_id=' + encodeURIComponent(item.id) : (ready || manual) ? '03b-review-split.html?submission_id=' + encodeURIComponent(item.id) : '';
          var score = confirmed ? num(item.final_total) + ' / ' + num(maximum) + (item.ai_total != null && Math.abs(item.final_total - item.ai_total) > 0.001 ? ' <small style="color:var(--ink-soft)">AI ' + num(item.ai_total) + '</small>' : '') : item.ai_total == null ? '—' : num(item.ai_total) + ' / ' + num(maximum);
          return '<tr' + (href ? ' data-href="' + href + '" style="cursor:pointer"' : '') + '><td class="sid">' + esc(item.sid || item.filename) + '</td><td><span class="status-pill ' + stateClass + '"><span class="dot"></span>' + esc(label) + '</span></td><td class="score ' + (item.ai_total == null && !confirmed ? 'pending' : '') + '">' + score + '</td><td>' + (flags.join(' ') || '—') + '</td><td>' + esc(item.marker ? item.marker.name : '—') + '</td></tr>';
        }).join('');
        var done = batch.status === 'completed' || batch.status === 'finalised';
        var action = done ? '<a class="start-btn" href="04-batch-complete.html?batch_id=' + encodeURIComponent(batch.id) + '">View results →</a>'
          : first ? '<a class="start-btn" href="03b-review-split.html?submission_id=' + encodeURIComponent(first.id) + '">' + (counts.confirmed ? 'Continue reviewing →' : 'Start reviewing →') + '</a>' : '';
        var pin = '<button type="button" class="chip" id="pinBatch" title="Up to 3 pinned batches are shown on Home; pinning a fourth unpins the oldest">' + (batch.pinned ? '📌 Pinned' : 'Pin to top') + '</button>';
        var due = batch.due_at ? (new Date(batch.due_at) < new Date() ? 'closed ' : 'due ') + shortDate(batch.due_at) : null;
        var chips = FILTERS.filter(function (f) { return f[0] === 'all' || counts[f[2]] || f[0] === filter; }).map(function (f) { return '<button type="button" class="chip' + (f[0] === filter ? ' active' : '') + '" data-filter="' + f[0] + '">' + f[1] + ' (' + Number(counts[f[2]] || 0) + ')</button>'; }).join('');
        document.getElementById('batchMain').innerHTML =
          '<div class="top"><div><h1>' + esc(batch.name) + (batch.is_sample ? ' <span class="status-pill reviewed" style="vertical-align:4px">Sample</span>' : '') + '</h1><p class="sub">' + all + ' submission' + (all === 1 ? '' : 's') + ' · ' + esc(rubric.criteria_count || 0) + ' criteria · ' + num(maximum) + ' marks' + (due ? ' · ' + due : '') + ' · ' + statusLabel(batch.status) + '</p></div><div class="top-actions">' + pin + ' ' + action + '</div></div>' +
          '<div class="progress-card"><div class="progress-top"><span class="label">Batch progress</span><span class="val">' + processed + ' / ' + all + ' processed</span></div><div class="bar"><div class="bar-fill" style="width:' + pct + '%"></div></div>' +
          '<div class="progress-stats"><span><b>' + Number(counts.ready || 0) + '</b> ready</span><span><b>' + Number(counts.confirmed || 0) + '</b> confirmed</span><span><b>' + Number(counts.needs_manual || 0) + '</b> manual</span><span><b>' + Number(counts.processing || 0) + '</b> processing</span>' + (counts.not_started ? '<span><b>' + counts.not_started + '</b> not started</span>' : '') + '<span><b>' + Number(counts.failed || 0) + '</b> failed</span></div></div>' +
          '<div class="filters">' + chips + '</div>' +
          '<table><thead><tr><th>Submission</th><th>Status</th><th>Mark</th><th>Flags</th><th>Tutor</th></tr></thead><tbody>' + (rows || '<tr><td colspan="5" style="color:var(--ink-soft)">No submissions in this view.</td></tr>') + '</tbody></table>' + pager(submissions.total, page, PAGE_SIZE);
        document.querySelectorAll('#batchMain tr[data-href]').forEach(function (tr) { tr.addEventListener('click', function () { location.href = tr.dataset.href; }); });
        function go(nextFilter, nextPage) {
          filter = nextFilter; page = nextPage;
          var p = new URLSearchParams(location.search);
          if (filter === 'all') p.delete('filter'); else p.set('filter', filter);
          if (page > 1) p.set('page', page); else p.delete('page');
          history.replaceState(null, '', '?' + p.toString()); clearTimeout(timer); load().catch(reportError);
        }
        document.querySelectorAll('#batchMain [data-filter]').forEach(function (button) { button.addEventListener('click', function () { go(button.dataset.filter, 1); }); });
        document.querySelectorAll('#batchMain [data-page]').forEach(function (button) { button.addEventListener('click', function () { go(filter, Number(button.dataset.page)); window.scrollTo(0, 0); }); });
        document.getElementById('pinBatch').addEventListener('click', function () { MarkerAPI.pinBatch(batch.id, !batch.pinned).then(function (r) { if (r.unpinned && r.unpinned.length) alert('Up to 3 batches can be pinned to Home. Unpinned: ' + r.unpinned.map(function (x) { return x.name; }).join(', ')); load(); }).catch(reportError); });
        document.querySelectorAll('[data-retry]').forEach(function (button) { button.addEventListener('click', function (event) { event.preventDefault(); event.stopPropagation(); button.disabled = true; button.textContent = 'Retrying…'; MarkerAPI.retrySubmission(button.dataset.retry, Number(button.dataset.version)).then(function () { load(); }).catch(function (error) { button.disabled = false; button.textContent = 'Retry remaining criteria'; alert(error.message); }); }); });
        setCrumb(batch.name); stepTrack(batch.status);
        document.title = batch.name + ' — AI-assisted marker';
        clearTimeout(timer);
        if (Number(counts.processing || 0) > 0) timer = setTimeout(function () { load().catch(reportError); }, 3000);
        return batchNav(batch).then(function () { return window.__MARKER_PAGE_DATA; });
      });
    }
    return load();
  }

  /* ----------------------------------------------------------- batch list */
  function wireBatchList() {
    return MarkerAPI.listBatches().then(function (data) {
      window.__MARKER_PAGE_DATA = data;
      var items = (data.items || []).map(function (batch) {
        var counts = batch.counts || {}, total = Number(counts.total || 0), processed = Number(counts.processed || 0);
        var rawStatus = batch.display_status || batch.status || 'draft';
        var state = rawStatus === 'in_review' ? 'review' : (rawStatus === 'completed' || rawStatus === 'finalised' ? 'complete' : rawStatus === 'failed_all' ? 'processing' : rawStatus);
        var pct = state === 'complete' ? 100 : (total ? Math.round(processed / total * 100) : 0);
        var progress = state === 'draft' ? 'set-up not finished' : state === 'complete' ? (Number(counts.confirmed || 0) + ' / ' + total + ' confirmed' + (batch.status === 'finalised' ? ' · locked' : '')) : (processed + ' / ' + total + ' processed · ' + Number(counts.confirmed || 0) + ' confirmed');
        var termLabel = (batch.term && batch.term.label) || '', termMatch = termLabel.match(/Semester\s+(\d+),\s*(\d{4})/i);
        var term = termMatch ? (termMatch[2] + ' S' + termMatch[1]) : (termLabel || 'No term');
        var rubric = batch.rubric || {}, due = batch.due_at ? new Date(batch.due_at) : null;
        var when = due && !isNaN(due.getTime()) ? (due < new Date() ? 'closed ' : 'due ') + shortDate(batch.due_at) : 'created ' + shortDate(batch.created_at);
        return {
          id: batch.id, name: batch.name, term: term, st: state, sample: !!batch.is_sample, pinned: !!batch.pinned,
          n: total + ' submission' + (total === 1 ? '' : 's'), crit: Number(rubric.criteria_count || 0),
          rubric: [rubric.title || 'No rubric', rubric.id || ''], date: when,
          prog: [pct, progress, state === 'complete' ? 'var(--ink-soft)' : state === 'review' ? 'var(--info)' : 'var(--primary)'],
          href: batchHref(batch), home: batch.pinned, version: Number(batch.version || 0),
          canCancel: batch.status === 'processing', canDelete: batch.status !== 'processing' && batch.status !== 'finalised'
        };
      });
      if (window.BatchListUI) window.BatchListUI.setItems(items);
      return data;
    });
  }

  /* --------------------------------------------------------------- review */
  function wireReview() {
    var params = new URLSearchParams(location.search), submissionId = params.get('submission_id');
    if (!submissionId) { location.replace('00-home.html'); return Promise.resolve(null); }
    return MarkerAPI.getReview(submissionId).then(function (data) {
      window.__MARKER_PAGE_DATA = data;
      var submission = data.submission || {}, batch = data.batch || {}, counts = batch.counts || {};
      var sid = submission.sid || submission.id, batchUrl = '02-batch-status.html?batch_id=' + encodeURIComponent(batch.id || '');
      var manual = !!submission.needs_manual, locked = !data.can_edit;
      var allEvidence = data.evidence || [], hasEvidence = !!allEvidence.length, criteria = (data.rubric && data.rubric.criteria) || [];
      var criterionNumber = {}; criteria.forEach(function (item, index) { criterionNumber[item.definition.id] = index + 1; });
      function blockHTML(block) {
        var text = String(block.text || ''), matches = allEvidence.filter(function (item) { return Number(item.page || 1) === Number(block.page || 1) && String(item.paragraph || '') === String(block.label || '') && item.quote && text.indexOf(item.quote) >= 0; });
        if (!matches.length) return esc(text);
        var grouped = {}; matches.forEach(function (item) { var start = text.indexOf(item.quote), key = start + ':' + (start + item.quote.length); if (!grouped[key]) grouped[key] = { start: start, end: start + item.quote.length, ids: [], numbers: [] }; grouped[key].ids.push(item.id); var n = criterionNumber[item.criterion_id]; if (n && grouped[key].numbers.indexOf(n) < 0) grouped[key].numbers.push(n); });
        var ranges = Object.keys(grouped).map(function (key) { return grouped[key]; }).sort(function (a, b) { return a.start - b.start || (b.end - b.start) - (a.end - a.start); }), cursor = 0, html = '';
        ranges.forEach(function (range) { if (range.start < cursor) return; html += esc(text.slice(cursor, range.start)); html += '<mark class="ev" data-ev="' + esc(range.ids[0]) + '" data-evs="' + esc(range.ids.join(' ')) + '"><span class="tag">' + range.numbers.map(function (n) { return 'C' + n; }).join('/') + '</span>' + esc(text.slice(range.start, range.end)) + '</mark>'; cursor = range.end; });
        return html + esc(text.slice(cursor));
      }
      var existingCards = document.querySelectorAll('.crit-card'), markInner = document.querySelector('.mark-inner');
      var strip = document.querySelector('.crit-strip');
      while (existingCards.length < criteria.length) {
        let cloneIndex = existingCards.length, clone = existingCards[existingCards.length - 1].cloneNode(true);
        clone.id = 'c' + (cloneIndex + 1); clone.style.display = ''; clone.classList.remove('closed', 'linked', 'hl-active'); clone.dataset.evs = '';
        markInner.appendChild(clone);
        let navClone = strip.lastElementChild.cloneNode(true); navClone.href = '#' + clone.id; navClone.dataset.c = clone.id; navClone.style.display = ''; strip.appendChild(navClone);
        let cloneInput = clone.querySelector('.score-input'), cloneStatus = clone.querySelector('.status-text');
        let cloneField = clone.querySelector('.comment-field'), cloneComment = cloneField && cloneField.querySelector('textarea');
        function refreshClone() { var changed = Number(cloneInput.value) !== Number(cloneInput.dataset.ai); cloneField.classList.toggle('needs', changed && !cloneComment.value.trim()); cloneStatus.textContent = changed ? 'Adjusted from AI suggestion' : 'Matches AI suggestion — not yet confirmed'; recompute(); updateSummary(clone); }
        cloneInput.addEventListener('input', refreshClone); cloneComment.addEventListener('input', function () { updateSummary(clone); });
        clone.querySelector('.accept-btn').addEventListener('click', function () { cloneInput.value = cloneInput.dataset.ai; cloneInput.classList.add('confirmed'); cloneStatus.textContent = 'Confirmed'; cloneStatus.classList.add('confirmed'); var dot = document.getElementById('nav' + (cloneIndex + 1)); if (dot) dot.classList.add('done'); recompute(); updateSummary(clone); });
        clone.querySelector('.fold-btn').addEventListener('click', function () { toggleCard(clone); });
        clone.querySelector('.crit-title').addEventListener('click', function () { toggleCard(clone); });
        let cloneCtl = clone.querySelector('.crit-ctl');
        if (cloneCtl) { cloneCtl.querySelector('.hl-btn').addEventListener('click', function () { setCritHL(critHL === clone.id ? null : clone.id); }); cloneCtl.querySelector('.hl-prev').addEventListener('click', function () { stepCrit(-1); }); cloneCtl.querySelector('.hl-next').addEventListener('click', function () { stepCrit(1); }); }
        existingCards = document.querySelectorAll('.crit-card');
      }
      var cards = document.querySelectorAll('.crit-card'), nav = document.querySelectorAll('.crit-strip a');
      var total = 0, aiTotal = 0, submissionVersion = Number(submission.version || 0);

      var crumbBatch = document.querySelector('.ab-crumbs ol li:nth-child(2) a');
      if (crumbBatch) { crumbBatch.textContent = batch.name || 'Batch'; crumbBatch.href = batchUrl; }
      setCrumb(sid);
      var crumbUp = document.querySelector('.ab-crumbs .bc-up');
      if (crumbUp) { crumbUp.href = batchUrl; var crumbUpText = crumbUp.querySelector('.t'); if (crumbUpText) crumbUpText.textContent = batch.name || 'Batch'; }

      var lastReviewable = -1, reviewProgressTimer = null;
      function renderReviewProgress(nextCounts, animate) {
        var confirmed = Number(nextCounts.confirmed || 0), ready = Number(nextCounts.ready || 0), processing = Number(nextCounts.processing || 0), notStarted = Number(nextCounts.not_started || 0), batchTotal = Number(nextCounts.total || 0), manualCount = Number(nextCounts.needs_manual || 0);
        var reviewable = confirmed + ready + manualCount, safeTotal = batchTotal || 1, pgDone = document.getElementById('pgDone'), pgReady = document.getElementById('pgReady'), pgFill = document.getElementById('pgFill'), pgReadyFill = document.getElementById('pgReadyFill'), pgSub = document.getElementById('pgSub');
        if (pgDone) pgDone.textContent = confirmed;
        if (pgReady) {
          pgReady.textContent = reviewable;
          if (animate && lastReviewable >= 0 && reviewable > lastReviewable) { pgReady.classList.add('bump'); setTimeout(function () { pgReady.classList.remove('bump'); }, 800); }
        }
        if (pgFill) pgFill.style.width = (confirmed / safeTotal * 100) + '%';
        if (pgReadyFill) pgReadyFill.style.width = (reviewable / safeTotal * 100) + '%';
        if (pgSub) { pgSub.classList.toggle('done', processing + notStarted === 0); pgSub.innerHTML = processing + notStarted > 0 ? '<span class="dot"></span><span id="pgProc">' + (processing + notStarted) + '</span> still with AI · ' + batchTotal + ' in batch' : (ready + manualCount) > 0 ? '<span class="dot"></span>' + (ready + manualCount) + ' left to review · ' + batchTotal + ' in batch' : '<span class="dot"></span>All ' + batchTotal + ' reviewed'; }
        lastReviewable = reviewable;
        return processing + notStarted;
      }
      function pollReviewProgress() {
        MarkerAPI.getBatch(batch.id).then(function (latest) {
          var active = renderReviewProgress((latest.batch && latest.batch.counts) || {}, true);
          if (active > 0) reviewProgressTimer = setTimeout(pollReviewProgress, 3000);
        }).catch(function (error) {
          console.error('Review progress refresh failed', error);
          reviewProgressTimer = setTimeout(pollReviewProgress, 5000);
        });
      }
      var activeProcessing = renderReviewProgress(counts, false);
      if (activeProcessing > 0) reviewProgressTimer = setTimeout(pollReviewProgress, 3000);
      window.addEventListener('beforeunload', function () { clearTimeout(reviewProgressTimer); }, { once:true });

      var documentData = data.document || {}, fileName = document.querySelector('.doc-bar .file b'); if (fileName) fileName.textContent = submission.filename || sid;
      var mimeType = String(documentData.mime_type || '').toLowerCase(), isPdf = !!documentData.content_url && (mimeType.indexOf('pdf') >= 0 || /\.pdf$/i.test(submission.filename || ''));
      var extension = ((submission.filename || '').match(/\.([^.]+)$/) || [,'file'])[1].toUpperCase();
      var previewMode = isPdf ? 'Original PDF' : extension + ' text preview';
      var pageCount = Number(documentData.page_count || 0), fileMeta = document.querySelector('.doc-bar .file span');
      if (fileMeta) fileMeta.textContent = (manual ? pageCount + ' page' + (pageCount === 1 ? '' : 's') + ' · no text layer · mark manually' : (pageCount + ' page' + (pageCount === 1 ? '' : 's') + ' · ' + Number(documentData.word_count || 0).toLocaleString('en-AU') + ' words · ' + allEvidence.length + ' evidence span' + (allEvidence.length === 1 ? '' : 's'))) + ' · ' + previewMode;
      var documentRoot = document.getElementById('doc'), evidenceHTML = '';
      if ((documentData.paragraphs || []).length) {
        var pageMap = {}; (documentData.paragraphs || []).forEach(function (block) { var page = Number(block.page || 1); if (!pageMap[page]) pageMap[page] = []; pageMap[page].push(block); });
        evidenceHTML = Object.keys(pageMap).map(Number).sort(function (a, b) { return a - b; }).map(function (pageNumber) {
          var blocks = pageMap[pageNumber], heading = pageNumber === 1 ? '<h1>' + esc(documentData.title || submission.filename || sid) + '</h1><p class="byline">' + esc(sid) + ' · ' + esc(batch.name || 'Batch') + ' · ' + Number(documentData.word_count || 0).toLocaleString('en-AU') + ' words</p>' : '';
          return '<article class="sheet" data-page="' + pageNumber + '"><span class="pno">p.' + pageNumber + '</span>' + heading + blocks.map(function (block) { return block.kind === 'heading' ? '<h2>' + esc(block.text) + '</h2>' : '<p data-p="' + esc(block.label || '') + '">' + blockHTML(block) + '</p>'; }).join('') + '</article>';
        }).join('');
      } else {
        evidenceHTML = '<article class="sheet" data-page="1"><h1>' + esc(submission.filename || sid) + '</h1><p class="byline">No readable text was found in this file (for example, a scanned page). Open the original below and mark each criterion by hand.</p></article>';
      }
      documentRoot.innerHTML = evidenceHTML;
      var evidenceToggle = document.querySelector('.doc-tools .switch'), evidenceInput = document.getElementById('showAll');
      var evidenceById = {}; allEvidence.forEach(function (item) { evidenceById[item.id] = item; });
      var originalPage = 1, originalPdfController = null;
      function renderOriginal(page) {
        if (!isPdf) return;
        originalPage = Math.max(1, Number(page || originalPage || 1));
        documentRoot.classList.add('original-mode'); documentRoot.classList.toggle('show-all', !!(evidenceInput && evidenceInput.checked));
        if (originalPdfController) { originalPdfController.goToPage(originalPage); return; }
        if (window.OriginalPdfViewer) originalPdfController = window.OriginalPdfViewer.mount(documentRoot, { url: documentData.content_url, evidence: allEvidence.map(function (item) { var copy = Object.assign({}, item); copy.criterion_label = 'C' + (criterionNumber[item.criterion_id] || '?'); return copy; }) });
      }
      if (evidenceToggle) evidenceToggle.style.display = hasEvidence ? '' : 'none';
      if (isPdf) {
        if (evidenceInput) evidenceInput.checked = true;
        renderOriginal(1);
        var markPaneForOriginal = document.getElementById('markPane');
        if (markPaneForOriginal) markPaneForOriginal.addEventListener('click', function (event) { var source = event.target.closest('[data-ev]'), evidence = source && evidenceById[source.dataset.ev]; if (source && evidence) { originalPage = evidence.page || 1; if (originalPdfController) originalPdfController.goToEvidence(evidence.id); } }, true);
      }
      if (!manual && !locked && !document.querySelector('[data-regrade]')) {
        var regradeControl = document.createElement('span'), regradeButton = document.createElement('button'), regradeMeter = document.createElement('span'), regradeFill = document.createElement('span');
        regradeControl.className = 'regrade-control'; regradeButton.type = 'button'; regradeButton.className = 'icon-btn'; regradeButton.dataset.regrade = 'true'; regradeButton.textContent = hasEvidence ? 'Re-run AI evidence' : 'Retrieve evidence'; regradeMeter.className = 'regrade-meter'; regradeMeter.appendChild(regradeFill); regradeControl.appendChild(regradeButton); regradeControl.appendChild(regradeMeter); document.querySelector('.doc-tools').insertBefore(regradeControl, document.getElementById('collapse'));
        var regradeError = function (message) { var old = document.querySelector('.regrade-error'); if (old) old.remove(); var box = document.createElement('div'); box.className = 'regrade-error'; box.setAttribute('role', 'alert'); box.innerHTML = '<b>AI evidence retrieval stopped.</b><br>' + esc(message) + '<button type="button" aria-label="Close">×</button>'; box.querySelector('button').addEventListener('click', function () { box.remove(); }); document.body.appendChild(box); };
        var stopRegrade = function (message) { regradeControl.classList.remove('running'); regradeButton.disabled = false; regradeButton.textContent = hasEvidence ? 'Re-run AI evidence' : 'Retrieve evidence'; regradeFill.style.width = '0'; if (message) regradeError(message); };
        var pollRegrade = function () { MarkerAPI.getReview(submissionId).then(function (result) { var item = Object.assign({}, result.submission, { error: result.submission.error ? { message: result.submission.error } : null }); var progress = String(item.progress || ''), match = progress.match(/(\d+)\s*\/\s*(\d+)\s+criteria/), done = match ? Number(match[1]) : 0, count = match ? Number(match[2]) : criteria.length, pct = count ? Math.max(5, Math.round(done / count * 100)) : 5; regradeFill.style.width = pct + '%'; regradeButton.textContent = match ? 'Retrieving ' + done + '/' + count : 'Queued…'; if (item.status === 'ai_done' || item.status === 'in_review') { regradeFill.style.width = '100%'; regradeButton.textContent = 'Evidence ready'; setTimeout(function () { location.reload(); }, 350); return; } if (item.status === 'failed') { stopRegrade(item.error && item.error.message ? item.error.message : 'The AI provider did not return a usable result after three attempts.'); return; } setTimeout(pollRegrade, 1500); }).catch(function (error) { console.error('Regrade progress failed', error); stopRegrade(error.message); }); };
        var startRegrade = function () { regradeControl.classList.add('running'); regradeButton.disabled = true; regradeFill.style.width = '5%'; pollRegrade(); };
        regradeButton.addEventListener('click', function () { regradeControl.classList.add('running'); regradeButton.disabled = true; regradeButton.textContent = 'Queueing…'; regradeFill.style.width = '3%'; MarkerAPI.regrade(submissionId).then(startRegrade).catch(function (error) { console.error('Regrade request failed', error); stopRegrade(error.message); }); });
        if (submission.status === 'queued' || submission.status === 'marking') startRegrade();
      }
      var hint = document.querySelector('.actionbar .hint'); if (hint) hint.textContent = locked ? 'Batch finalised · marks are read-only' : manual ? 'No AI suggestion · enter a score and comment for every criterion' : hasEvidence ? 'Hover evidence to highlight · click to jump · Show all controls every retrieved passage' : 'No verified criterion evidence was returned for this submission';

      Array.prototype.forEach.call(cards, function (card, index) {
        var item = criteria[index];
        if (!item) { card.style.display = 'none'; if (nav[index]) nav[index].style.display = 'none'; return; }
        var def = item.definition || {}, levels = def.levels || [], confidence = item.confidence || 'none', noAI = item.ai_score == null;
        total += Number(def.weight || 0); aiTotal += Number(item.ai_score || 0);
        card.dataset.criterionId = def.id || ''; card.dataset.reviewVersion = String(item.version || 0); card.dataset.evs = (item.evidence_ids || []).join(',');
        card.classList.toggle('flagged', confidence === 'low');
        var title = card.querySelector('.crit-title'); if (title) title.textContent = 'C' + (index + 1) + ' · ' + def.name;
        var desc = card.querySelector('.crit-desc'); if (desc) desc.innerHTML = levelsHtml(def, item.ai_level);
        var badge = card.querySelector('.crit-weight-badge'); if (badge) badge.textContent = num(def.weight) + ' pts';
        var confidenceTag = card.querySelector('.conf-tag'); if (confidenceTag) { confidenceTag.className = 'conf-tag ' + (noAI ? 'none' : confidence); confidenceTag.innerHTML = '<span class="dot"></span>' + (noAI ? 'No AI suggestion' : confidence.charAt(0).toUpperCase() + confidence.slice(1) + ' confidence'); }
        var ai = card.querySelector('.ai-box .badge'); if (ai) ai.textContent = noAI ? 'Manual marking' : 'AI · ' + num(item.ai_score) + '/' + num(def.weight) + (item.ai_level ? ' · ' + item.ai_level : '');
        var reason = card.querySelector('.ai-box .reason'); if (reason) reason.textContent = item.rationale || '';
        var score = card.querySelector('.score-input'); if (score) { score.value = item.score == null ? '' : item.score; score.dataset.ai = noAI ? '' : item.ai_score; score.dataset.max = def.weight; score.max = def.weight; score.min = 0; score.step = 'any'; score.disabled = locked; if (noAI) score.placeholder = '—'; }
        var accept = card.querySelector('.accept-btn'); if (accept) accept.style.display = noAI || locked ? 'none' : '';
        var max = card.querySelector('.score-max'); if (max) max.textContent = '/ ' + num(def.weight);
        var comment = card.querySelector('.comment-field textarea'); if (comment) { comment.value = item.comment || ''; comment.disabled = locked; }
        var status = card.querySelector('.status-text'); if (status) status.textContent = item.status === 'confirmed' ? 'Confirmed' : noAI ? 'Needs your score' : item.status === 'edited' ? 'Adjusted — not yet confirmed' : 'Not yet confirmed';
        var criterionEvidence = allEvidence.filter(function (evidence) { return evidence.criterion_id === def.id; }), evidenceNode = card.querySelector('.evidence'), alsoNode = card.querySelector('.also'), control = card.querySelector('.crit-ctl');
        if (criterionEvidence.length) {
          card.dataset.evs = criterionEvidence.map(function (evidence) { EV_CARD[evidence.id] = card.id; return evidence.id; }).join(',');
          if (evidenceNode) { var first = criterionEvidence[0]; evidenceNode.style.display = ''; evidenceNode.dataset.ev = first.id; evidenceNode.innerHTML = '<span class="tab">p.' + esc(first.page) + ' ' + esc(first.paragraph || '') + '</span><span class="jump">Show in submission ↗</span><blockquote>“' + esc(first.quote) + '”</blockquote>'; }
          if (alsoNode) { if (criterionEvidence.length > 1) { alsoNode.style.display = ''; alsoNode.innerHTML = 'Also used: ' + criterionEvidence.slice(1).map(function (evidence) { return '<span class="chip" data-ev="' + esc(evidence.id) + '"><b>p.' + esc(evidence.page) + ' ' + esc(evidence.paragraph || '') + '</b><i>“' + esc(evidence.quote.length > 120 ? evidence.quote.slice(0, 117) + '…' : evidence.quote) + '”</i></span>'; }).join(''); } else alsoNode.style.display = 'none'; }
          if (control) { control.style.display = ''; var label = control.querySelector('.hl-lbl'); if (label) label.textContent = 'Highlight all · ' + criterionEvidence.length; }
        } else {
          Array.prototype.forEach.call(card.querySelectorAll('.evidence,.also,.crit-ctl'), function (node) { node.style.display = 'none'; });
        }
        updateSummary(card);
        if (nav[index]) { nav[index].style.display = ''; nav[index].dataset.c = card.id; nav[index].title = 'C' + (index + 1) + ' · ' + def.name; nav[index].innerHTML = '<span class="st" id="nav' + (index + 1) + '"></span>C' + (index + 1) + ' <span class="w">' + num(def.weight) + ' pts</span>'; }
      });
      var heading = document.querySelector('.doc-header h1'); if (heading) heading.textContent = 'Review — ' + sid;
      var summary = document.querySelector('.doc-header p'); if (summary) summary.textContent = criteria.length + ' criteria · rubric maximum ' + num(total) + ' marks' + (manual ? ' · manual marking' : ' · ' + pageCount + '-page submission parsed') + (batch.is_sample ? ' · sample batch' : '');
      var footer = document.getElementById('footerTotal'); if (footer) footer.textContent = manual ? '—' : num(aiTotal);
      var final = footer && footer.parentElement; if (final) { var textNode = Array.prototype.find.call(final.childNodes, function (node) { return node.nodeType === 3 && /\//.test(node.textContent); }); if (textNode) textNode.textContent = ' / ' + num(total) + ' '; }
      var suggested = document.getElementById('aiSug'); if (suggested) suggested.textContent = manual ? 'No AI suggestion' : 'AI suggested ' + num(aiTotal);
      if (typeof recompute === 'function') recompute();
      var previous = document.getElementById('btnPrev'); if (previous) { previous.disabled = history.length < 2; previous.addEventListener('click', function () { history.back(); }); }
      var skip = document.getElementById('btnSkip');
      if (skip) skip.addEventListener('click', function (event) {
        event.preventDefault(); event.stopImmediatePropagation();
        MarkerAPI.nextInQueue(batch.id, submissionId).then(function (next) { if (next.next_id) location.href = '03b-review-split.html?submission_id=' + encodeURIComponent(next.next_id); else location.href = batchUrl; }).catch(reportError);
      }, true);
      var next = document.getElementById('btnNext');
      if (next && locked) { next.disabled = true; next.textContent = 'Finalised · read only'; }
      else if (next && submission.status === 'confirmed') next.textContent = 'Save changes & next →';
      document.title = sid + ' — ' + (batch.name || 'Review') + ' — AI-assisted marker';
      document.addEventListener('click', function (event) {
        var button = event.target.closest('#btnNext'); if (!button || locked) return;
        event.preventDefault(); event.stopImmediatePropagation();
        var missing = criteria.filter(function (item, index) { var input = cards[index] && cards[index].querySelector('.score-input'); return !input || input.value === '' || isNaN(Number(input.value)) || Number(input.value) < 0 || Number(input.value) > Number(item.definition.weight); });
        if (missing.length) { alert('Enter a score between 0 and the maximum for: ' + missing.map(function (item) { return item.definition.name; }).join(', ')); return; }
        button.disabled = true; button.textContent = 'Saving…';
        var chain = Promise.resolve();
        criteria.forEach(function (item, index) {
          var card = cards[index]; if (!card) return;
          var score = card.querySelector('.score-input'), comment = card.querySelector('.comment-field textarea');
          var nextScore = Number(score.value), nextComment = comment ? comment.value : '';
          if (item.score != null && nextScore === Number(item.score) && nextComment === (item.comment || '')) return;
          chain = chain.then(function () { return MarkerAPI.saveCriterion(submissionId, item.definition.id, { score: nextScore, comment: nextComment, version: item.version }).then(function (saved) { submissionVersion = Number(saved.submission_version); item.score = saved.score; item.comment = saved.comment; item.version = saved.version; }); });
        });
        chain.then(function () { button.textContent = 'Confirming…'; return MarkerAPI.confirm(submissionId, submissionVersion); }).then(function (result) {
          if (result.next_id) { location.href = '03b-review-split.html?submission_id=' + encodeURIComponent(result.next_id); return; }
          result.batch_id = batch.id; showEnd(result); button.textContent = 'Confirmed';
        }).catch(function (error) { button.disabled = false; button.textContent = 'Confirm & next →'; reportError(error); alert(error.message); });
      }, true);
    });
  }
  function showEnd(result) {
    var card = document.getElementById('endCard'), body = document.getElementById('endBody'); if (!card || !body) return;
    var resultsUrl = '04-batch-complete.html?batch_id=' + encodeURIComponent(result.batch_id || ''), statusUrl = '02-batch-status.html?batch_id=' + encodeURIComponent(result.batch_id || '');
    if (result.batch_status === 'completed') body.innerHTML = '<div class="ec-icon ok">✓</div><div class="ec-kicker">Batch complete</div><h2 id="ecTitle">Everything is confirmed</h2><p class="ec-sub">Results stay editable until you finalise the batch.</p><div class="ec-actions"><a class="btn btn-primary" href="' + resultsUrl + '">View results →</a><a class="btn btn-ghost" href="05-mark-report.html?submission_id=' + encodeURIComponent(result.submission_id) + '">Mark report</a></div><div class="ec-links"><a href="00-home.html">Back to Home</a></div>';
    else if (result.remaining.failed > 0) body.innerHTML = '<div class="ec-kicker">Failed items need attention</div><h2 id="ecTitle">Review is paused</h2><p class="ec-sub">Retry or exclude the failed submissions from the batch page.</p><div class="ec-actions"><a class="btn btn-primary" href="' + statusUrl + '">Back to batch</a></div>';
    else body.innerHTML = '<div class="ec-icon wait"><span class="ec-spin"></span></div><div class="ec-kicker">Nothing ready right now</div><h2 id="ecTitle">All ready submissions reviewed</h2><p class="ec-sub">' + result.remaining.processing + ' still with the AI.</p><div class="ec-actions"><a class="btn btn-primary" href="' + statusUrl + '">Back to batch</a></div><div class="ec-links"><a href="00-home.html">Back to Home</a></div>';
    card.hidden = false;
  }

  /* --------------------------------------------------------------- router */
  document.addEventListener('DOMContentLoaded', function () {
    var name = pageName(), pages = window.MarkerPages || {};
    wireUser();
    var task =
      name === '00-home.html' || name === '' ? pages.home(ui)
      : name === '06-rubrics.html' ? wireRubrics()
      : name === '03b-review-split.html' ? wireReview()
      : name === '07-batches.html' ? wireBatchList()
      : name === '02-batch-status.html' ? wireBatchStatus()
      : name === '04-batch-complete.html' ? pages.results(ui)
      : name === '05-mark-report.html' ? pages.report(ui)
      : name === '01-upload.html' ? wireSetup()
      : null;
    Promise.resolve(task).then(function () { document.documentElement.dataset.apiState = 'ready'; }).catch(reportError);
  });
})();
