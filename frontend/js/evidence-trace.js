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
    if (step.tool === 'finish') return ['info', 'Finished', clip(step.detail, 220)];
    return ['bad', 'Tool call error', step.detail];
  }

  function summary(steps) {
    var rounds = 0, verified = 0, rejected = 0, searches = 0, tokens = 0, cached = 0, fallback = false;
    steps.forEach(function (step) {
      if (step.kind === 'model') { rounds += 1; tokens += Number(step.input_tokens || 0); cached += Number(step.cached_tokens || 0); }
      if (step.kind === 'fallback') fallback = true;
      if (step.kind !== 'tool') return;
      if (step.tool === 'cite' && (step.outcome === 'valid' || step.outcome === 'relocated')) verified += 1;
      if (step.tool === 'cite' && step.outcome === 'invalid') rejected += 1;
      if (step.tool === 'search') searches += 1;
    });
    var parts = [plural(rounds, 'round'), plural(verified, 'quote') + ' verified'];
    if (rejected) parts.push(rejected + ' rejected');
    if (searches) parts.push(plural(searches, 'search'));
    if (fallback) parts.push('single read');
    return { text: parts.join(' · '), tokens: tokens, cached: cached };
  }

  function render(check, coverage) {
    var steps = check && Array.isArray(check.steps) ? check.steps : [];
    if (!steps.length) return null;
    var labels = {};
    (coverage || []).forEach(function (row) { if (row && row.aspect_id) labels[row.aspect_id] = row.label || row.aspect_id; });
    var totals = summary(steps), rows = [], round = 0;
    steps.forEach(function (step) {
      if (step.kind === 'model') {
        round = step.round;
        rows.push('<li class="round">Round ' + esc(round) + (step.latency_ms ? '<span>' + esc((step.latency_ms / 1000).toFixed(1)) + ' s</span>' : '') + '</li>');
        return;
      }
      var line = describe(step, labels);
      if (!line) return;
      rows.push('<li class="' + line[0] + '"><b>' + esc(line[1]) + '</b>' + (line[2] ? '<span>' + esc(line[2]) + '</span>' : '') + '</li>');
    });
    var node = document.createElement('details');
    node.className = 'trace';
    node.innerHTML = '<summary>How the evidence was found <span>' + esc(totals.text) + '</span></summary>'
      + '<ol>' + rows.join('') + '</ol>'
      + (totals.tokens ? '<p class="trace-foot">' + esc(totals.tokens.toLocaleString()) + ' input tokens · ' + esc(totals.cached.toLocaleString()) + ' read from the provider cache · tutor view only</p>' : '<p class="trace-foot">Tutor view only</p>');
    return node;
  }

  window.EvidenceTrace = { render: render };
})();
