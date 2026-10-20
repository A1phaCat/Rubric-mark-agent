/* Shared rubric library for the prototype.
   One list, used by Home (3 most recent), the Rubrics page (full list, preview, edit)
   and the import / set-up pages (saving a rubric adds or updates it here).
   An in-memory facade over the API: app-wire.js loads it from the database on every page load,
   and edits/deletes on the Rubrics page are written back through MarkerAPI. */
(function (global) {
  var LEVELS = ['HD', 'DI', 'CR', 'PS', 'FL'];

  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  function slug(s) { return String(s || 'rubric').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'rubric'; }

  var memory = [];  /* filled from GET /api/v1/rubrics by app-wire.js; nothing is seeded in the browser */
  var Lib = {
    LEVELS: LEVELS,
    all: function () {
      return clone(memory);  /* API order: pinned first, newest first */
    },
    saveAll: function (list) { memory = clone(list); },
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
        criteria: (b.criteria || []).map(function (c) { var levels=(c.levels||[]).map(function(level){return clone(level);});var bands=levels.length?levels.map(function(level){return level.description;}):(c.bands||[]).slice();return { name:c.name,weight:Number(c.weight),grading_mode:c.grading_mode,aspects:clone(c.aspects||[]),levels:levels,bands:bands }; })
      });
    },
    /* Shape the set-up page expects */
    toBatchRubric: function (r) {
      var d = new Date();
      return { libId: r.id, title: r.title, source: 'Rubric library · ' + r.source, savedAt: d.getHours() + ':' + String(d.getMinutes()).padStart(2, '0'),
        criteria: r.criteria.map(function (c) { var levels=(c.levels||[]).map(function(level){return clone(level);});return { name:c.name,weight:Number(c.weight),grading_mode:c.grading_mode,aspects:clone(c.aspects||[]),conf:['high','From your library'],note:'Saved in your rubric library.',levels:levels,bands:levels.length?levels.map(function(level){return level.description;}):(c.bands||[]).slice() }; }) };
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
