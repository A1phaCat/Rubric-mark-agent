/* Account menu (top-right avatar) — shared by every page.
   One connection in the local MVP: the AI model that suggests marks (Canvas is post-MVP and hidden).
   The working frontend sends settings and connection tests to the backend; secrets never enter localStorage. */
(function () {
  /* The university service runs on Azure OpenAI. "Own key" options below it. */
  /* No built-in model names: the model list comes from the provider (Test), or you type it. */
  var UNI = { label: 'Azure OpenAI' };
  var PROVIDERS = {
    minimax:   { label: 'MiniMax (China mainland)', ph: 'MiniMax API key', base: 'https://api.minimaxi.com/v1', live: true },
    azure:     { label: 'Azure OpenAI (your own resource)', ph: 'Azure key', base: 'https://<resource>.openai.azure.com' },
    anthropic: { label: 'Anthropic', ph: 'sk-ant-…', base: 'https://api.anthropic.com/v1', live: 'anthropic' },
    openai:    { label: 'OpenAI', ph: 'sk-…', base: 'https://api.openai.com/v1', live: true }
  };
  var DEFAULTS = {
    ai: { provider: 'minimax', model: '', key: '', base: '', ok: true, useUni: true, hasKey: false },
    canvas: { url: '', token: '', ok: false }
  };

  function load() { return JSON.parse(JSON.stringify(DEFAULTS)); }
  function save(s) {
    if (!window.MarkerAPI) return Promise.resolve(s);
    return window.MarkerAPI.updateAISettings({ provider:s.ai.useUni ? 'university' : s.ai.provider, model:s.ai.model, base_url:s.ai.base || null, api_key:s.ai.key || null, uses_university_gateway:s.ai.useUni });
  }
  function esc(t) { return String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;'); }
  function mask(k) { return k ? k.slice(0, 6) + '…' + k.slice(-4) : ''; }

  var css = '' +
    '.ab-user{ cursor:pointer; border-radius:999px; padding-top:4px; padding-bottom:4px; padding-right:4px; position:relative; }' +
    '.ab-user:hover .ab-avatar, .ab-user[aria-expanded="true"] .ab-avatar{ box-shadow:0 0 0 2px rgba(255,255,255,.55); }' +
    '.ab-user:focus-visible{ outline:2px solid #fff; outline-offset:2px; }' +
    '.ab-user .am-badge{ position:absolute; right:2px; bottom:3px; width:10px; height:10px; border-radius:50%; background:#F2A900; border:2px solid var(--chrome,#424242); }' +
    '.am{ position:fixed; z-index:200; width:360px; max-width:calc(100vw - 24px); background:var(--surface,#fff); color:var(--ink,#424242); border:1px solid var(--border,#E2D8CE); border-radius:12px; box-shadow:0 16px 40px rgba(40,36,33,.22); font:14px/1.45 Inter,system-ui,sans-serif; overflow:hidden; }' +
    '.am[hidden]{ display:none; }' +
    '.am-who{ display:flex; align-items:center; gap:12px; padding:16px 18px; border-bottom:1px solid var(--border,#E2D8CE); }' +
    '.am-who .av{ width:36px; height:36px; border-radius:50%; background:#9A8F86; color:#fff; display:flex; align-items:center; justify-content:center; font-size:13px; font-weight:600; flex:none; }' +
    '.am-who b{ display:block; font-weight:600; } .am-who small{ color:var(--ink-soft,#6E655E); font-size:12px; }' +
    '.am-who-t{ flex:1; min-width:0; } .am-who-t input{ width:100%; font:inherit; font-weight:600; border:1px solid transparent; border-radius:6px; padding:2px 6px; margin-left:-6px; background:transparent; color:inherit; }' +
    '.am-who-t input:hover, .am-who-t input:focus{ border-color:var(--border,#E2D8CE); background:#fff; outline:none; } .am-who small{ display:block; }' +
    '.am-h{ padding:12px 18px 4px; font:500 11px "IBM Plex Mono",monospace; letter-spacing:.06em; text-transform:uppercase; color:var(--ink-soft,#6E655E); }' +
    '.am-row{ border-top:1px solid var(--border,#E2D8CE); }' +
    '.am-row:first-of-type{ border-top:0; }' +
    '.am-sum{ display:flex; align-items:center; gap:10px; width:100%; padding:11px 18px; border:0; background:none; text-align:left; cursor:pointer; font:inherit; color:inherit; }' +
    '.am-sum:hover{ background:var(--tint,#FAF6F1); }' +
    '.am-ic{ width:30px; height:30px; border-radius:8px; background:var(--tint,#FAF6F1); border:1px solid var(--border,#E2D8CE); display:flex; align-items:center; justify-content:center; flex:none; color:var(--ink-soft,#6E655E); }' +
    '.am-sum .t{ flex:1; min-width:0; } .am-sum .t b{ display:block; font-weight:500; font-size:13.5px; }' +
    '.am-sum .t small{ display:flex; align-items:center; gap:6px; font-size:12px; color:var(--ink-soft,#6E655E); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }' +
    '.am-dot{ width:7px; height:7px; border-radius:50%; background:#2F7A45; flex:none; } .am-dot.off{ background:#F2A900; } .am-dot.err{ background:#C8102E; }' +
    '.am-chev{ color:var(--ink-soft,#6E655E); transition:transform .15s; } .am-row.open .am-chev{ transform:rotate(180deg); }' +
    '.am-body{ display:none; padding:4px 18px 16px 58px; } .am-row.open .am-body{ display:block; }' +
    '.am-f{ display:block; margin-top:10px; } .am-f > span{ display:block; font-size:12px; color:var(--ink-soft,#6E655E); margin-bottom:4px; }' +
    '.am-f input[type=text], .am-f input[type=password], .am-f select{ width:100%; height:34px; border:1px solid var(--border-strong,#D3C7BB); border-radius:7px; padding:0 10px; font:13px Inter,system-ui,sans-serif; background:#fff; color:var(--ink,#424242); }' +
    '.am-f input:focus, .am-f select:focus{ outline:none; border-color:var(--primary,#E64626); }' +
    '.am-f input.mono{ font-family:"IBM Plex Mono",monospace; font-size:12px; }' +
    '.am-f > .am-key{ display:flex; gap:6px; margin:0; } .am-key input{ flex:1; min-width:0; }' +
    '.am-note{ display:block; margin-top:4px; font-size:11.5px; color:var(--ink-soft,#6E655E); } .am-note.live{ color:#2F7A45; }' +
    '.am-eye{ width:48px; height:34px; flex:none; border:1px solid var(--border-strong,#D3C7BB); border-radius:7px; background:#fff; cursor:pointer; color:var(--ink-soft,#6E655E); font-size:12px; }' +
    '.am-chk{ display:flex; align-items:flex-start; gap:8px; margin-top:6px; font-size:13px; cursor:pointer; } .am-chk input{ margin-top:3px; accent-color:var(--primary,#E64626); }' +
    '.am-chk small{ display:block; font-size:12px; color:var(--ink-soft,#6E655E); }' +
    '.am-act{ display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-top:12px; } .am-act .msg{ flex:1 1 140px; line-height:1.35; font-size:12px; color:var(--ink-soft,#6E655E); } .am-act .msg.ok{ color:#2F7A45; } .am-act .msg.err{ color:#C8102E; }' +
    '.am-btn{ height:32px; padding:0 14px; border-radius:7px; border:1px solid var(--border-strong,#D3C7BB); background:#fff; font:500 12.5px Inter,system-ui,sans-serif; cursor:pointer; color:var(--ink,#424242); }' +
    '.am-btn.pri{ background:var(--primary,#E64626); border-color:var(--primary,#E64626); color:#fff; }' +
    '.am-btn:hover{ filter:brightness(.97); }' +
    '.am-foot{ display:flex; justify-content:space-between; align-items:center; gap:10px; padding:11px 18px; background:var(--tint,#FAF6F1); border-top:1px solid var(--border,#E2D8CE); font-size:11.5px; color:var(--ink-soft,#6E655E); }' +
    '.am-foot a{ color:var(--ink-soft,#6E655E); font-size:12.5px; }';

  var ICON_AI = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg>';
  var ICON_CV = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="5.5" r="1.3"/><circle cx="12" cy="18.5" r="1.3"/><circle cx="5.5" cy="12" r="1.3"/><circle cx="18.5" cy="12" r="1.3"/></svg>';
  var CHEV = '<svg class="am-chev" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>';

  function aiSummary(s) {
    if (s.ai.useUni) return ['', 'University · Azure OpenAI · ' + s.ai.model];
    if (!s.ai.key && !s.ai.hasKey) return ['off', 'Add an API key'];
    return [s.ai.ok ? '' : 'err', (s.ai.provider === 'minimax' ? 'MiniMax' : PROVIDERS[s.ai.provider].label) + ' · ' + s.ai.model + ' · ' + (s.ai.key ? mask(s.ai.key) : 'key saved')];
  }
  function cvSummary(s) {
    return ['off', 'Not available in local MVP'];
  }

  /* Model suggestions: the live list from the provider once fetched for this provider + base URL;
     otherwise none — type the model (or Azure deployment) name. */
  var NOT_CHAT = /embed|whisper|tts|speech|audio|dall-e|image|video|music|moderation|transcribe|realtime|search|davinci|babbage|voice/i;
  function modelsFor(S, prov, base) {
    var f = S.ai.fetched;
    if (f && f.prov === prov && f.base === base && f.models.length) return { list: f.models, live: true, at: f.at };
    return { list: [], live: false };
  }
  function modelNote(m) {
    return m.live ? m.list.length + ' models from your API · updated ' + ago(m.at) : 'Type the model or deployment name, or press Test to load the models your key can use';
  }
  function ago(t) { var m = Math.round((Date.now() - t) / 6e4); return m < 1 ? 'just now' : m < 60 ? m + ' min ago' : Math.round(m / 60) + ' h ago'; }
  function fillModels(input, list, keep) {
    var next=input;
    if(list.length){
      if(input.tagName!=='SELECT'){
        next=document.createElement('select');next.id='amModel';next.className='mono';input.replaceWith(next);
      }
      next.innerHTML=list.map(function(m){return '<option value="'+esc(m)+'">'+esc(m)+'</option>';}).join('');
      next.value=list.indexOf(keep)>=0?keep:list[0];
    }else{
      if(input.tagName==='SELECT'){
        next=document.createElement('input');next.type='text';next.id='amModel';next.className='mono';next.setAttribute('list','amModelList');next.placeholder='model or deployment name';next.autocomplete='off';next.spellcheck=false;input.replaceWith(next);
      }
      if(keep!=null)next.value=keep;
      var options=document.getElementById('amModelList');if(options)options.innerHTML='';
    }
    return next;
  }

  function modelControl(value,list){
    if(list.length)return '<select class="mono" id="amModel">'+list.map(function(m){return '<option value="'+esc(m)+'"'+(m===value?' selected':'')+'>'+esc(m)+'</option>';}).join('')+'</select><datalist id="amModelList"></datalist>';
    return '<input type="text" class="mono" id="amModel" list="amModelList" value="'+esc(value)+'" placeholder="model or deployment name" autocomplete="off" spellcheck="false"><datalist id="amModelList"></datalist>';
  }

  /* GET {base}/models — resolves to { ok, status, models[], err, raw } */
  function listModels(prov, base, key) {
    return window.MarkerAPI.testAI({ provider:prov, base_url:base, api_key:key }).then(function (j) {
      return { ok:j.ok, status:j.ok ? 200 : 502, models:j.models || [], err:j.ok ? '' : j.message, raw:JSON.stringify(j) };
    });
  }

  /* Real request for MiniMax (OpenAI-compatible): POST {base}/chat/completions */
  var lastTest = null;
  function liveTest(base, key, model, msg) {
    var t0 = Date.now();
    window.MarkerAPI.testAI({ provider:'openai', model:model, base_url:base, api_key:key }).then(function (j) {
      var ok = j.ok; lastTest = { key:key, ok:ok };
      msg.className = 'msg ' + (ok ? 'ok' : 'err');
      msg.textContent = ok ? '✓ Connected · ' + model + ' · ' + (Date.now() - t0) + ' ms' : j.message;
      msg.title = JSON.stringify(j).slice(0, 400);
    }).catch(function (err) {
      lastTest = null;
      msg.className = 'msg err';
      msg.textContent = 'Could not reach ' + base.replace(/^https?:\/\//, '') + ' from the browser (network or CORS). The key may still be fine.';
      msg.title = String(err);
    });
  }

  function init() {
    var user = document.querySelector('.ab-user'); if (!user) return;
    var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    user.setAttribute('role', 'button'); user.setAttribute('tabindex', '0');
    user.setAttribute('aria-haspopup', 'dialog'); user.setAttribute('aria-expanded', 'false');
    user.setAttribute('title', 'Account and connections');

    var S = load();
    var WHO = { name: (user.querySelector('.ab-uname') || {}).textContent || 'Tutor', initials: (user.querySelector('.ab-avatar') || {}).textContent || '' };
    window.addEventListener('marker:user', function (event) { WHO = event.detail; });
    var menu = document.createElement('div'); menu.className = 'am'; menu.hidden = true;
    menu.setAttribute('role', 'dialog'); menu.setAttribute('aria-label', 'Account and connections');
    document.body.appendChild(menu);
    if(window.MarkerAPI)MarkerAPI.getSettings().then(function(config){var ai=config.ai||{}, provider=ai.provider||'university';S.ai.provider=provider==='university'||!PROVIDERS[provider]?'minimax':provider;S.ai.model=ai.model||'';S.ai.base=ai.base_url||'';S.ai.useUni=provider==='university';S.ai.hasKey=!!ai.has_api_key;S.ai.ok=S.ai.useUni||S.ai.hasKey;if(!menu.hidden)draw(null);badge();}).catch(function(){});

    function badge() {
      var warn = !S.ai.useUni && !S.ai.hasKey && (!S.ai.key || !S.ai.ok);
      var b = user.querySelector('.am-badge');
      if (warn && !b) { b = document.createElement('span'); b.className = 'am-badge'; b.setAttribute('aria-hidden', 'true'); user.appendChild(b); }
      if (!warn && b) b.remove();
    }

    function draw(openId) {
      var p = PROVIDERS[S.ai.provider], a = aiSummary(S), c = cvSummary(S), mf = modelsFor(S, S.ai.provider, S.ai.base || p.base || '');
      menu.innerHTML =
        '<div class="am-who"><span class="av">' + esc(WHO.initials) + '</span><span class="am-who-t"><input type="text" id="amName" value="' + esc(WHO.name) + '" maxlength="80" aria-label="Your display name" spellcheck="false"><small>Tutor · local single-user mode · <span id="amNameMsg">name shown in headers and reports</span></small></span><button class="am-btn" type="button" id="amNameSave">Save</button></div>' +
        '<div class="am-h">Connections</div>' +
        '<div class="am-row' + (openId === 'ai' ? ' open' : '') + '" data-id="ai">' +
          '<button class="am-sum" type="button" aria-expanded="' + (openId === 'ai') + '"><span class="am-ic">' + ICON_AI + '</span><span class="t"><b>AI model</b><small><span class="am-dot ' + a[0] + '"></span>' + esc(a[1]) + '</small></span>' + CHEV + '</button>' +
          '<div class="am-body">' +
            '<label class="am-chk"><input type="checkbox" id="amUni"' + (S.ai.useUni ? ' checked' : '') + '><span>Use the university’s AI service<small>Azure OpenAI, no key needed. Turn off to use your own API key.</small></span></label>' +
            '<div id="amOwn"' + (S.ai.useUni ? ' hidden' : '') + '>' +
              '<label class="am-f"><span>Provider</span><select id="amProv">' + Object.keys(PROVIDERS).map(function (k) { return '<option value="' + k + '"' + (k === S.ai.provider ? ' selected' : '') + '>' + PROVIDERS[k].label + '</option>'; }).join('') + '</select></label>' +
              '<label class="am-f" id="amBaseWrap"' + (p.base ? '' : ' hidden') + '><span>Base URL</span><input type="text" class="mono" id="amBase" value="' + esc(S.ai.base || p.base || '') + '" spellcheck="false"></label>' +
              '<label class="am-f"><span>API key</span><span class="am-key"><input type="password" class="mono" id="amKey" placeholder="' + p.ph + '" value="' + esc(S.ai.key) + '" autocomplete="off" spellcheck="false"><button class="am-eye" type="button" data-eye="amKey" aria-label="Show key">Show</button></span></label>' +
            '</div>' +
            '<label class="am-f"><span>Model</span>' + modelControl(S.ai.model,S.ai.useUni?[]:mf.list) + '<small class="am-note' + (mf.live ? ' live' : '') + '" id="amModelNote">' + esc(S.ai.useUni ? 'The deployment name configured on the university gateway' : modelNote(mf)) + '</small></label>' +
            '<div class="am-act"><span class="msg" id="amAiMsg"></span><button class="am-btn" type="button" data-test="ai">Test</button><button class="am-btn pri" type="button" data-save="ai">Save</button></div>' +
          '</div>' +
        '</div>' +
        /* Canvas is hidden until the integration exists (post-MVP). */
        '<div class="am-foot"><span>Keys are stored server-side only.</span><a href="#" id="amOut">Sign out</a></div>';
      badge();
    }

    function place() {
      var r = user.getBoundingClientRect();
      menu.style.top = Math.round(r.bottom + 8) + 'px';
      menu.style.right = Math.max(12, Math.round(window.innerWidth - r.right)) + 'px';
    }
    function open() { draw(null); place(); menu.hidden = false; user.setAttribute('aria-expanded', 'true'); }
    function close() { menu.hidden = true; user.setAttribute('aria-expanded', 'false'); }
    function toggle() { if (menu.hidden) open(); else close(); }

    user.addEventListener('click', function (e) { e.stopPropagation(); toggle(); });
    user.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
    document.addEventListener('click', function (e) { if (!menu.hidden && e.composedPath().indexOf(menu) < 0) close(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !menu.hidden) { close(); user.focus(); } });
    window.addEventListener('resize', function () { if (!menu.hidden) place(); });

    menu.addEventListener('click', function (e) {
      var sum = e.target.closest('.am-sum');
      if (sum) { var row = sum.parentNode, was = row.classList.contains('open'); draw(was ? null : row.dataset.id); return; }
      var eye = e.target.closest('[data-eye]');
      if (eye) { var inp = document.getElementById(eye.dataset.eye); var show = inp.type === 'password'; inp.type = show ? 'text' : 'password'; eye.textContent = show ? 'Hide' : 'Show'; return; }
      if (e.target.id === 'amNameSave') {
        var nm = document.getElementById('amName').value.trim(), nmsg = document.getElementById('amNameMsg');
        if (!nm) { nmsg.textContent = 'Name cannot be empty'; return; }
        nmsg.textContent = 'Saving…';
        MarkerAPI.updateMe({ name: nm }).then(function (me) { if (window.MarkerUI && MarkerUI.applyUser) MarkerUI.applyUser(me); var av = menu.querySelector('.am-who .av'); if (av) av.textContent = WHO.initials; nmsg.textContent = '✓ Saved'; })
          .catch(function (err) { nmsg.textContent = err.message || 'Could not save the name'; });
        return;
      }
      if (e.target.id === 'amOut') { e.preventDefault(); alert('Signing out is not part of this demo.'); return; }
      var t = e.target.closest('[data-test]'), sv = e.target.closest('[data-save]');
      if (!t && !sv) return;
      var which = (t || sv).getAttribute(t ? 'data-test' : 'data-save');
      if (which === 'ai') {
        var uni = document.getElementById('amUni').checked;
        var key = uni ? S.ai.key : document.getElementById('amKey').value.trim();
        var prov = uni ? S.ai.provider : document.getElementById('amProv').value;
        var model = document.getElementById('amModel').value;
        var base = uni ? '' : (document.getElementById('amBase').value.trim().replace(/\/+$/, ''));
        var okAi = uni || key.length >= 20 || S.ai.hasKey;
        var msg = document.getElementById('amAiMsg');
        if (t) {
          msg.className = 'msg'; msg.textContent = 'Checking…';
          if (!uni && !key && !S.ai.hasKey) { msg.className = 'msg err'; msg.textContent = 'Paste an API key first'; return; }
          if (!uni && PROVIDERS[prov].live) {
            var sel = document.getElementById('amModel'), note = document.getElementById('amModelNote');
            listModels(prov, base, key).then(function (res) {
              if (res.ok && res.models.length) {
                lastTest = { key: key, ok: true };
                S.ai.fetched = { prov: prov, base: base, models: res.models, at: Date.now() };
                var keep = res.models.indexOf(sel.value) >= 0 ? sel.value : res.models[0];
                fillModels(sel, res.models, keep);
                note.textContent = modelNote(modelsFor(S, prov, base)); note.className = 'am-note live';
                msg.className = 'msg ok'; msg.textContent = '✓ Connected · ' + res.models.length + ' models available';
                msg.title = res.raw.slice(0, 400);
              } else if (res.status === 404 || res.status === 405) {
                liveTest(base, key, model, msg);   // host has no /models — fall back to a tiny chat request
              } else {
                lastTest = { key: key, ok: false };
                msg.className = 'msg err'; msg.textContent = 'HTTP ' + res.status + (res.err ? ' — ' + res.err : ''); msg.title = res.raw.slice(0, 400);
              }
            }).catch(function (err) {
              lastTest = null; msg.className = 'msg err';
              msg.textContent = 'Could not reach ' + base.replace(/^https?:\/\//, '') + ' from the browser (network or CORS). The key may still be fine.';
              msg.title = String(err);
            });
            return;
          }
          /* Ask the backend to actually reach the provider; never report success without a response. */
          window.MarkerAPI.testAI({ provider: uni ? 'university' : prov, model: model || null, base_url: base || null, api_key: key || null }).then(function (j) {
            lastTest = { key: key, ok: !!j.ok };
            msg.className = 'msg ' + (j.ok ? 'ok' : 'err');
            msg.textContent = j.ok ? '✓ Connected' + (model ? ' · ' + model : '') + ' · ' + j.latency_ms + ' ms' : (j.message || 'Connection failed');
          }).catch(function (err) { lastTest = null; msg.className = 'msg err'; msg.textContent = err.message || 'Connection failed'; });
          return;
        }
        if (!model.trim()) { msg.className = 'msg err'; msg.textContent = 'Enter the model or deployment name'; return; }
        if (lastTest && lastTest.key === key) okAi = lastTest.ok;
        var nextAi = { provider: prov, model: model, key: key, base: base, ok: okAi, useUni: uni, hasKey:S.ai.hasKey||!!key, fetched: S.ai.fetched };
        msg.className = 'msg'; msg.textContent = 'Saving…';
        save({ai:nextAi,canvas:S.canvas}).then(function(saved){
          S.ai = nextAi;
          S.ai.key = '';
          S.ai.hasKey = !!saved.has_api_key;
          S.ai.ok = S.ai.useUni || S.ai.hasKey;
          draw(null);
        }).catch(function(error){
          msg.className = 'msg err';
          msg.textContent = error.message || 'Could not save AI settings';
        });
      }
    });
    menu.addEventListener('change', function (e) {
      if (e.target.id === 'amUni' || e.target.id === 'amProv') {
        var uni = document.getElementById('amUni').checked, prov = document.getElementById('amProv').value;
        document.getElementById('amOwn').hidden = uni;
        document.getElementById('amBaseWrap').hidden = !PROVIDERS[prov].base;
        if (e.target.id === 'amProv') document.getElementById('amBase').value = PROVIDERS[prov].base || '';
        var mf2 = modelsFor(S, prov, document.getElementById('amBase').value.trim().replace(/\/+$/, ''));
        var list = uni ? [] : mf2.list;
        var nt = document.getElementById('amModelNote'); nt.textContent = uni ? 'The deployment name configured on the university gateway' : modelNote(mf2); nt.className = 'am-note' + (mf2.live && !uni ? ' live' : '');
        fillModels(document.getElementById('amModel'), list, list.length ? list[0] : null);
        var mm = document.getElementById('amAiMsg'); mm.textContent = ''; mm.className = 'msg';
        document.getElementById('amKey').placeholder = PROVIDERS[prov].ph;
      }
    });
    badge();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
