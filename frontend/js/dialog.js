/* In-page dialogs in the app's own style, replacing the browser's confirm() / alert().

   MarkerDialog.confirm({ title, message, note, kicker, icon, confirmLabel, cancelLabel, tone })
     → Promise<boolean>   (true only when the main button is pressed)
   MarkerDialog.alert({ title, message, kicker, icon, okLabel })
     → Promise<void>

   icon: 'pause' | 'play' | 'stop' | 'trash' | 'warn' | 'info' | 'reset'
   tone: 'primary' (default) | 'danger' — the colour of the main button and icon.
   Esc, the Cancel button and a click on the backdrop all answer "no"; focus stays in the dialog. */
(function () {
  var ICONS = {
    pause: '<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>',
    play: '<path d="M7 5l12 7-12 7z"/>',
    stop: '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
    trash: '<path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12"/><path d="M9 7V4h6v3"/>',
    warn: '<path d="M12 3l10 18H2z"/><path d="M12 10v5"/><path d="M12 18v.01"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><path d="M12 7.5v.01"/>',
    reset: '<path d="M4 7v5h5"/><path d="M5.5 16a8 8 0 1 0 .5-9l-2 2"/>'
  };
  var CSS =
    '.md-scrim{ position:fixed; inset:0; z-index:200; display:flex; align-items:center; justify-content:center; padding:20px; background:rgba(40,36,33,.42); animation:md-fade .12s ease-out; }' +
    '@keyframes md-fade{ from{ opacity:0; } to{ opacity:1; } }' +
    '.md-box{ width:min(480px,100%); padding:28px; border:1px solid var(--border,#E2D8CE); border-radius:18px; background:var(--surface,#fff); color:var(--ink,#424242); box-shadow:0 22px 60px rgba(40,36,33,.24); font-family:Inter,system-ui,sans-serif; }' +
    '.md-icon{ display:flex; align-items:center; justify-content:center; width:64px; height:64px; margin:0 auto 14px; border-radius:50%; background:#FFF3CC; color:#D88D00; }' +
    '.md-box.danger .md-icon{ background:var(--risk-bg,#FBE5E8); color:var(--risk,#C8102E); }' +
    '.md-box.calm .md-icon{ background:var(--tint,#FAF6F1); color:var(--ink-soft,#6E655E); }' +
    '.md-kicker{ margin-bottom:8px; color:var(--ink-soft,#6E655E); font:500 11px "IBM Plex Mono",monospace; letter-spacing:.08em; text-align:center; text-transform:uppercase; }' +
    '.md-box h2{ margin:0 0 8px; font:600 25px/1.25 "Source Serif 4",Georgia,serif; text-align:center; }' +
    '.md-copy{ margin:0 auto 18px; max-width:400px; color:var(--ink-soft,#6E655E); font-size:14px; line-height:1.55; text-align:center; white-space:pre-line; }' +
    '.md-note{ margin:0; padding:12px 14px; border:1px solid var(--border,#E2D8CE); border-radius:9px; background:var(--tint,#FAF6F1); color:var(--ink-soft,#6E655E); font-size:12.5px; line-height:1.45; text-align:center; }' +
    '.md-actions{ display:grid; grid-template-columns:1fr 1fr; gap:9px; margin-top:20px; }' +
    '.md-actions.single{ grid-template-columns:1fr; }' +
    '.md-btn{ display:inline-flex; align-items:center; justify-content:center; height:46px; padding:0 16px; border:1px solid var(--border-strong,#CFC3B7); border-radius:9px; background:var(--surface,#fff); color:var(--ink,#424242); font:500 14px Inter,system-ui,sans-serif; cursor:pointer; }' +
    '.md-btn:hover{ background:var(--tint,#FAF6F1); }' +
    '.md-btn:focus-visible{ outline:none; box-shadow:0 0 0 3px rgba(230,70,38,.25); }' +
    '.md-btn.main{ border-color:var(--primary,#E64626); background:var(--primary,#E64626); color:#fff; }' +
    '.md-btn.main:hover{ background:#CF3B20; }' +
    '.md-box.danger .md-btn.main{ border-color:var(--risk,#C8102E); background:var(--risk,#C8102E); }' +
    '.md-box.danger .md-btn.main:hover{ background:#A50D26; }';

  function esc(value) { return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function ensureStyle() {
    if (document.getElementById('md-style')) return;
    var style = document.createElement('style'); style.id = 'md-style'; style.textContent = CSS;
    document.head.appendChild(style);
  }

  function open(options, single) {
    ensureStyle();
    var o = options || {}, tone = o.tone === 'danger' ? 'danger' : o.tone === 'calm' ? 'calm' : '';
    var previousFocus = document.activeElement;
    var scrim = document.createElement('div');
    scrim.className = 'md-scrim';
    scrim.innerHTML =
      '<div class="md-box ' + tone + '" role="' + (single ? 'alertdialog' : 'dialog') + '" aria-modal="true" aria-labelledby="mdTitle" aria-describedby="mdCopy">' +
        (o.icon && ICONS[o.icon] ? '<div class="md-icon" aria-hidden="true"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + ICONS[o.icon] + '</svg></div>' : '') +
        (o.kicker ? '<div class="md-kicker">' + esc(o.kicker) + '</div>' : '') +
        '<h2 id="mdTitle">' + esc(o.title || (single ? 'Notice' : 'Are you sure?')) + '</h2>' +
        (o.message ? '<p class="md-copy" id="mdCopy">' + esc(o.message) + '</p>' : '') +
        (o.note ? '<p class="md-note">' + esc(o.note) + '</p>' : '') +
        '<div class="md-actions' + (single ? ' single' : '') + '">' +
          '<button type="button" class="md-btn main" data-answer="yes">' + esc(single ? (o.okLabel || 'OK') : (o.confirmLabel || 'Continue')) + '</button>' +
          (single ? '' : '<button type="button" class="md-btn" data-answer="no">' + esc(o.cancelLabel || 'Cancel') + '</button>') +
        '</div>' +
      '</div>';
    document.body.appendChild(scrim);
    var buttons = Array.prototype.slice.call(scrim.querySelectorAll('.md-btn'));
    // Destructive questions start on Cancel so Enter does not confirm by accident.
    (tone === 'danger' && !single ? buttons[1] : buttons[0]).focus();
    return new Promise(function (resolve) {
      function finish(answer) {
        document.removeEventListener('keydown', keydown, true);
        scrim.remove();
        if (previousFocus && previousFocus.focus) previousFocus.focus();
        resolve(answer);
      }
      function keydown(event) {
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); finish(false); return; }
        if (event.key !== 'Tab') return;
        var index = buttons.indexOf(document.activeElement);
        event.preventDefault();
        buttons[(index + (event.shiftKey ? buttons.length - 1 : 1)) % buttons.length].focus();
      }
      scrim.addEventListener('click', function (event) {
        var button = event.target.closest('[data-answer]');
        if (button) finish(button.dataset.answer === 'yes');
        else if (event.target === scrim) finish(false);
      });
      document.addEventListener('keydown', keydown, true);
    });
  }

  window.MarkerDialog = {
    confirm: function (options) { return open(options, false); },
    alert: function (options) {
      if (typeof options === 'string') options = { message: options };
      return open(Object.assign({ icon: 'info', tone: 'calm' }, options), true).then(function () {});
    }
  };
})();
