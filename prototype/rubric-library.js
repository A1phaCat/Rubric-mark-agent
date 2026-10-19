/* Shared rubric library for the prototype.
   One list, used by Home (3 most recent), the Rubrics page (full list, preview, edit)
   and the import / set-up pages (saving a rubric adds or updates it here).
   Stored in this browser only (localStorage), seeded with sample rubrics. */
(function (global) {
  var KEY = 'dryrun.library.v1';
  var LEVELS = ['HD', 'DI', 'CR', 'PS', 'FL'];

  function days(n) { return Date.now() - n * 864e5; }

  var SEED = [
    { id: 'critical-essay', title: 'Critical Essay — HD/D/C/P', source: 'Uploaded PDF · parsed by AI', updated: days(0.02), usedBy: ['ASGN2 — Critical Essay'],
      criteria: [
        { name: 'Argument structure', weight: 30, bands: ['A clear, well-sequenced thesis carried consistently through each section.', 'A clear thesis; most sections connect back to it, with minor lapses.', 'Thesis is present but sequencing is uneven; some sections drift from it.', 'Thesis is implied or vague; the structure is hard to follow in places.', 'No identifiable thesis or organising structure.'] },
        { name: 'Evidence & sources', weight: 25, bands: ['Sources are current, credible, and integrated — not just listed.', 'Credible sources, mostly integrated into the argument.', 'Adequate sources, though some are listed rather than used.', 'Few sources, weakly connected to the claims they support.', 'Little or no supporting evidence.'] },
        { name: 'Critical analysis', weight: 30, bands: ['Goes beyond description to weigh competing explanations.', 'Evaluates some alternatives, though not always in depth.', 'Mostly descriptive, with occasional analysis.', 'Largely descriptive; little evaluation of ideas.', 'No analysis evident.'] },
        { name: 'Writing clarity', weight: 15, bands: ['Precise, concise prose with few mechanical errors.', 'Clear prose with minor errors that don’t affect meaning.', 'Generally understandable; some errors slow the reader.', 'Meaning is mostly clear, but errors are frequent.', 'Frequent errors obscure meaning.'] }
      ] },
    { id: 'literature-review', title: 'Literature Review', source: 'From Canvas', updated: days(2), usedBy: ['ASGN1 — Literature Review'],
      criteria: [
        { name: 'Scope & search strategy', weight: 15, bands: ['Search is systematic, documented and clearly bounded.', 'Search is sound and mostly documented.', 'Search is reasonable but loosely described.', 'Search is narrow or unclear.', 'No evident search strategy.'] },
        { name: 'Synthesis of sources', weight: 30, bands: ['Sources are compared and grouped into clear themes.', 'Most sources are synthesised into themes.', 'Some synthesis; parts read as a list of summaries.', 'Mostly a list of summaries.', 'Sources are not connected.'] },
        { name: 'Critical evaluation', weight: 25, bands: ['Weighs the strength and limits of each body of work.', 'Evaluates key sources with some depth.', 'Some evaluation, mostly descriptive.', 'Little evaluation.', 'No evaluation.'] },
        { name: 'Research gap', weight: 15, bands: ['Gap is precise and follows directly from the review.', 'Gap is clear and mostly supported.', 'Gap is stated but loosely supported.', 'Gap is vague.', 'No gap identified.'] },
        { name: 'Referencing & style', weight: 15, bands: ['Consistent, accurate referencing; polished writing.', 'Minor referencing or style slips.', 'Several referencing errors.', 'Frequent errors.', 'Referencing missing or unusable.'] }
      ] },
    { id: 'short-answer', title: 'Short Answer (quiz)', source: 'Pasted text · parsed by AI', updated: days(9), usedBy: ['Quiz 3 — Short Answers'],
      criteria: [
        { name: 'Q1 — Concept definitions', weight: 30, bands: ['Precise definitions with a correct example for each.', 'Correct definitions; examples mostly apt.', 'Mostly correct; one definition loose.', 'Several definitions incomplete.', 'Definitions missing or wrong.'] },
        { name: 'Q2 — Applying the model', weight: 40, bands: ['Model applied correctly to every part of the case.', 'Applied correctly with a minor slip.', 'Applied to most of the case.', 'Partly applied; key steps missing.', 'Model not applied.'] },
        { name: 'Q3 — Evaluating trade-offs', weight: 30, bands: ['Weighs trade-offs and reaches a justified position.', 'Weighs trade-offs; position partly justified.', 'Names trade-offs but mostly describes them.', 'Lists options without weighing them.', 'No trade-offs discussed.'] }
      ] },
    { id: 'final-project-report', title: 'Final Project Report', source: 'From Canvas', updated: days(5), usedBy: ['ASGN3 — Final Project Report (draft)'],
      criteria: [
        { name: 'Introduction', weight: 5, bands: ['Clearly explains and fully meets all criteria to a professional standard.', 'Properly explains and meets the substantial majority of criteria.', 'Meets some criteria but misses or does not clearly address others.', 'Explains some basic criteria but misses a major portion.', 'Fails to explain most criteria; contents not relevant.'] },
        { name: 'System Specifications and Architecture Design', weight: 25, bands: ['Comprehensively addresses all criteria with in-depth, well-evidenced architecture and user stories.', 'Extensively addresses the majority; good architecture and user stories.', 'Addresses some criteria; acceptable architecture and brief user stories.', 'Misses a considerable portion; weak architecture and evidence.', 'Fails to address the criteria.'] },
        { name: 'Quality of Work', weight: 40, bands: ['Thoroughly addresses all criteria with strong evidence of working, tested features.', 'Addresses a substantial majority with good evidence.', 'Addresses most criteria; some evidence missing.', 'Misses a considerable portion; limited evidence.', 'Fails to address most criteria.'] },
        { name: 'Quality of Group Processes and Individual Contributions', weight: 20, bands: ['Meets all criteria with clear evidence of balanced collaboration.', 'Meets most criteria; good evidence of collaboration.', 'Meets some criteria; basic evidence.', 'Explains a few criteria; minimal evidence.', 'Fails most criteria.'] },
        { name: 'Reflections and Conclusions', weight: 5, bands: ['Excellent analysis with a prioritised improvement plan.', 'Adequate analysis covering most areas.', 'Basic analysis; basic next steps.', 'Partial analysis; vague actions.', 'Little to no meaningful analysis.'] },
        { name: 'Documentation Organization & Writing', weight: 5, bands: ['Professionally structured; links work; evidence easy to access.', 'Mostly clear and consistent; minor gaps.', 'Some gaps, missing captions or links.', 'Structure needs substantial work.', 'Low readability; many broken links.'] }
      ] },
    { id: 'group-presentation', title: 'Group Presentation', source: 'From Canvas', updated: days(41), usedBy: [],
      criteria: [
        { name: 'Content & accuracy', weight: 35, bands: ['Accurate, well-chosen content.', 'Accurate with minor gaps.', 'Mostly accurate.', 'Several inaccuracies.', 'Largely inaccurate.'] },
        { name: 'Structure', weight: 20, bands: ['Clear arc with smooth hand-overs.', 'Clear structure.', 'Structure mostly followable.', 'Hard to follow.', 'No structure.'] },
        { name: 'Delivery', weight: 25, bands: ['Confident, engaging, well paced.', 'Clear and mostly engaging.', 'Clear but flat.', 'Hard to hear or follow.', 'Not delivered.'] },
        { name: 'Answering questions', weight: 20, bands: ['Thoughtful, accurate answers.', 'Good answers.', 'Adequate answers.', 'Weak answers.', 'No answers.'] }
      ] },
    { id: 'reflective-journal', title: 'Reflective Journal', source: 'Uploaded DOCX · parsed by AI', updated: days(120), usedBy: [],
      criteria: [
        { name: 'Depth of reflection', weight: 50, bands: ['Links experience to theory and future practice.', 'Clear reflection with some theory.', 'Some reflection, mostly descriptive.', 'Mostly descriptive.', 'No reflection.'] },
        { name: 'Use of evidence', weight: 30, bands: ['Specific, well-chosen examples.', 'Relevant examples.', 'General examples.', 'Few examples.', 'None.'] },
        { name: 'Writing', weight: 20, bands: ['Clear and concise.', 'Clear with minor errors.', 'Understandable.', 'Errors slow the reader.', 'Hard to read.'] }
      ] }
  ];

  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  function slug(s) { return String(s || 'rubric').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'rubric'; }

  var Lib = {
    LEVELS: LEVELS,
    all: function () {
      var list = null;
      try { list = JSON.parse(localStorage.getItem(KEY)); } catch (e) {}
      if (!Array.isArray(list) || !list.length) list = clone(SEED);
      return list.sort(function (a, b) { return b.updated - a.updated; });
    },
    saveAll: function (list) { try { localStorage.setItem(KEY, JSON.stringify(list)); } catch (e) {} },
    get: function (id) { return this.all().filter(function (r) { return r.id === id; })[0] || null; },
    recent: function (n) { return this.all().slice(0, n || 3); },
    upsert: function (r) {
      var list = this.all(), i = -1;
      list.forEach(function (x, k) { if (x.id === r.id) i = k; });
      r.updated = Date.now();
      if (i >= 0) list[i] = r; else list.unshift(r);
      this.saveAll(list); return r;
    },
    remove: function (id) { this.saveAll(this.all().filter(function (r) { return r.id !== id; })); },
    total: function (r) { return r.criteria.reduce(function (s, c) { return s + (Number(c.weight) || 0); }, 0); },
    /* A rubric saved on the import / set-up pages ({title, source, criteria:[{name, weight, bands}]}) */
    fromBatchRubric: function (b, usedBy) {
      var title = String(b.title || 'Untitled rubric').replace(/\s+rubric$/i, '');
      var id = b.libId || slug(title), existing = this.get(id);
      if (existing && b.libId) title = existing.title;   // keep the library's name
      return this.upsert({
        id: id, title: title, source: b.source || 'Imported',
        usedBy: existing ? existing.usedBy : (usedBy ? [usedBy] : []),
        criteria: (b.criteria || []).map(function (c) { return { name: c.name, weight: Number(c.weight), bands: (c.bands || []).slice(0, 5) }; })
      });
    },
    /* Shape the set-up page expects */
    toBatchRubric: function (r) {
      var d = new Date();
      return { libId: r.id, title: r.title, source: 'Rubric library · ' + r.source, savedAt: d.getHours() + ':' + String(d.getMinutes()).padStart(2, '0'),
        criteria: r.criteria.map(function (c) { return { name: c.name, weight: Number(c.weight), conf: ['high', 'From your library'], note: 'Saved in your rubric library.', bands: c.bands.slice() }; }) };
    },
    ago: function (t) {
      var m = Math.round((Date.now() - t) / 6e4);
      if (m < 1) return 'just now'; if (m < 60) return m + ' min ago';
      var h = Math.round(m / 60); if (h < 24) return h + ' h ago';
      var d = Math.round(h / 24); if (d < 31) return d + (d === 1 ? ' day ago' : ' days ago');
      var mo = Math.round(d / 30); return mo + (mo === 1 ? ' month ago' : ' months ago');
    }
  };
  global.RubricLib = Lib;
})(window);
