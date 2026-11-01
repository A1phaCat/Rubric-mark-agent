/* How the AI found a criterion's evidence: a collapsible timeline on the tutor's review screen.
   Built from the evidence check's recorded steps; never shown on the student report. */
(function () {
  'use strict';

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function clip(text, length) {
    text = String(text || '');
    return text.length > length ? text.slice(0, length - 1) + '…' : text;
  }

  function plural(count, word) {
    return count + ' ' + word + (count === 1 ? '' : 's');
  }

  function aspectNames(ids, labels) {
    return (ids || []).map(function (id) { return labels[id] || id; }).join(', ');
  }

  function where(data) {
    return data && data.page ? 'p.' + data.page + (data.paragraph ? ' ' + data.paragraph : '') : (data && data.paragraph_id) || '';
  }

  // One line per step: [state, label, detail]
  function describe(step, labels) {
    var data = step.data || {};
    if (step.kind === 'read') return ['info', 'Read the whole submission', step.detail];
    if (step.kind === 'nudge') return ['info', 'Asked to search first', aspectNames(data.aspect_ids, labels)];
    if (step.kind === 'limit') return ['warn', 'Stopped at the round limit', 'Kept the evidence already verified'];
    if (step.kind === 'fallback') return ['warn', 'Switched to a single read', step.detail.replace(/^Read in one pass instead: /, '')];
    if (step.kind !== 'tool') return null;
    var aspects = aspectNames(data.aspect_ids, labels);
    if (step.tool === 'cite') {
      if (step.outcome === 'valid') return ['ok', 'Quote verified · ' + where(data), '“' + clip(step.detail, 140) + '”' + (aspects ? ' → ' + aspects : '')];
      if (step.outcome === 'relocated') return ['ok', 'Quote verified · found at ' + where(data), '“' + clip(step.detail, 140) + '”' + (aspects ? ' → ' + aspects : '')];
      if (step.outcome === 'merged') return ['ok', 'Same quote, more aspects', aspects];
      if (step.outcome === 'invalid') return ['bad', 'Quote rejected · not in the submission', '“' + clip(step.detail, 140) + '”'];
      if (step.outcome === 'limit') return ['warn', 'Quote limit reached', ''];
      return ['bad', 'Citation not recorded', step.detail];
    }
    if (step.tool === 'search') {
      var hits = (data.hits || []).length;
      return [hits ? 'info' : 'warn', 'Searched “' + clip(data.query || step.detail, 60) + '”', (hits ? plural(hits, 'matching paragraph') : 'No matching paragraphs') + (aspects ? ' · for ' + aspects : '')];
    }
    if (step.tool === 'finish' && step.outcome === 'deferred') return ['warn', 'Tried to finish with aspects not yet searched for', clip(step.detail, 220)];
    if (step.tool === 'finish' && step.outcome === 'incomplete') return ['warn', 'Asked to answer for every aspect', aspectNames(data.aspect_ids, labels)];
    if (step.tool === 'finish') return ['info', 'Finished', clip(step.detail, 220)];
    return ['bad', 'Tool call error', step.detail];
  }

  function summary(steps) {
    var rounds = 0, verified = 0, rejected = 0, searches = 0, tokens = 0, cached = 0, fallback = false, answers = [];
    steps.forEach(function (step) {
      if (step.kind === 'model') { rounds += 1; tokens += Number(step.input_tokens || 0); cached += Number(step.cached_tokens || 0); }
      if (step.kind === 'fallback') fallback = true;
      if (step.kind !== 'tool') return;
      if (step.tool === 'cite' && (step.outcome === 'valid' || step.outcome === 'relocated')) verified += 1;
      if (step.tool === 'cite' && step.outcome === 'invalid') rejected += 1;
      if (step.tool === 'search') searches += 1;
      if (step.tool === 'finish' && step.outcome === 'done') answers = (step.data && step.data.aspects) || [];
    });
    if (fallback && !rounds) return { text: 'tool check unavailable · single read', tokens: tokens, cached: cached };
    var parts = [plural(rounds, 'round'), plural(verified, 'quote') + ' verified'];
    if (rejected) parts.push(rejected + ' rejected');
    if (searches) parts.push(plural(searches, 'search'));
    if (answers.length) parts.push(answers.filter(function (a) { return a.meets_standard; }).length + ' of ' + answers.length + ' aspects meet the standard');
    if (fallback) parts.push('single read');
    return { text: parts.join(' · '), tokens: tokens, cached: cached };
  }

  // The two answers per aspect given when the check finished, as timeline rows.
  function answerRows(step, labels) {
    var answers = (step.data && step.data.aspects) || [];
    return answers.map(function (answer) {
      var state = answer.meets_standard ? 'ok' : answer.addressed ? 'warn' : 'bad';
      var verdict = answer.meets_standard ? 'Meets the standard' : answer.addressed ? 'Covered, below the standard' : 'Not covered';
      return '<li class="aspect ' + state + '"><b>' + esc(labels[answer.aspect_id] || answer.aspect_id) + '</b><span>'
        + esc(verdict) + (answer.reason ? ' — ' + esc(clip(answer.reason, 200)) : '') + '</span></li>';
    });
  }

  // What the grade step listed as falling short of the best level, and whether that held the mark down.
  function deductionRows(check, labels) {
    var deductions = check && Array.isArray(check.deductions) ? check.deductions : null;
    if (!deductions) return [];
    var rows = ['<li class="round">Before the level was chosen</li>'];
    if (!deductions.length) rows.push('<li class="ok"><b>No deductions</b><span>Nothing found below the best level</span></li>');
    deductions.forEach(function (item) {
      var material = item.severity === 'material';
      var place = item.evidence === 'absent' ? 'not in the submission' : item.evidence;
      rows.push('<li class="' + (material ? 'bad' : 'warn') + '"><b>' + esc(material ? 'Material' : 'Minor') + ' · '
        + esc(labels[item.aspect_id] || item.aspect_id) + '</b><span>' + esc(clip(item.issue, 240))
        + (place ? ' (' + esc(place) + ')' : '') + '</span></li>');
    });
    if (check.capped === 'deduction') rows.push('<li class="info"><b>Held below the best level</b><span>A material deduction stands</span></li>');
    if (check.capped === 'coverage') rows.push('<li class="info"><b>Held below the best level</b><span>Not every aspect is supported</span></li>');
    return rows;
  }

  function deductionSummary(check) {
    var deductions = check && Array.isArray(check.deductions) ? check.deductions : null;
    if (!deductions) return '';
    var material = deductions.filter(function (item) { return item.severity === 'material'; }).length;
    return material ? plural(material, 'material deduction') : deductions.length ? plural(deductions.length, 'minor deduction') : 'no deductions';
  }

  function render(check, coverage) {
    var steps = check && Array.isArray(check.steps) ? check.steps : [];
    var hasDeductions = check && Array.isArray(check.deductions);
    if (!steps.length && !hasDeductions) return null;
    var labels = {};
    (coverage || []).forEach(function (row) { if (row && row.aspect_id) labels[row.aspect_id] = row.label || row.aspect_id; });
    var totals = steps.length ? summary(steps) : { text: '', tokens: 0, cached: 0 }, rows = [], round = 0;
    steps.forEach(function (step) {
      if (step.kind === 'model') {
        round = step.round;
        rows.push('<li class="round">Round ' + esc(round) + (step.latency_ms ? '<span>' + esc((step.latency_ms / 1000).toFixed(1)) + ' s</span>' : '') + '</li>');
        return;
      }
      var line = describe(step, labels);
      if (!line) return;
      rows.push('<li class="' + line[0] + '"><b>' + esc(line[1]) + '</b>' + (line[2] ? '<span>' + esc(line[2]) + '</span>' : '') + '</li>');
      if (step.tool === 'finish' && step.outcome === 'done') rows = rows.concat(answerRows(step, labels));
    });
    rows = rows.concat(deductionRows(check, labels));
    var heading = [totals.text, deductionSummary(check)].filter(Boolean).join(' · ');
    var node = document.createElement('details');
    node.className = 'trace';
    node.innerHTML = '<summary>' + (steps.length ? 'How the evidence was found' : 'How the level was chosen') + ' <span>' + esc(heading) + '</span></summary>'
      + '<ol>' + rows.join('') + '</ol>'
      + (totals.tokens ? '<p class="trace-foot">' + esc(totals.tokens.toLocaleString()) + ' input tokens · ' + esc(totals.cached.toLocaleString()) + ' read from the provider cache · tutor view only</p>' : '<p class="trace-foot">Tutor view only</p>');
    return node;
  }

  window.EvidenceTrace = { render: render };
})();
