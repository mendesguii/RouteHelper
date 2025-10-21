// app.js diagnostics
try { console.log('[RouteHelper] app.js loaded'); } catch(_) {}

// Bulma 1.x dark mode via data-theme attribute (no custom CSS overrides)
(function(){
  var storageKey = 'bulma-theme';
  var root = document.documentElement;
  function getSavedTheme(){ return localStorage.getItem(storageKey) || 'auto'; }
  function applyTheme(theme){
    try { root.setAttribute('data-theme', theme); } catch(_) {}
    updateIcon(theme);
  }
  function updateIcon(theme){
    var btn = document.getElementById('theme-toggle');
    var icon = document.getElementById('theme-icon');
    if (!btn || !icon) return;
    var t = theme || (root.getAttribute('data-theme') || 'auto');
    icon.textContent = t === 'dark' ? '🌙' : (t === 'light' ? '☀️' : '🖥️');
    btn.title = 'Theme: ' + t;
  }
  function saveAndApply(theme){ localStorage.setItem(storageKey, theme); applyTheme(theme); }
  // Initial
  applyTheme(getSavedTheme());
  // Toggle handler
  document.addEventListener('click', function(ev){
    var btn = ev.target && (ev.target.id === 'theme-toggle' ? ev.target : (ev.target.closest && ev.target.closest('#theme-toggle')));
    if (!btn) return;
    ev.preventDefault();
    var cur = root.getAttribute('data-theme') || 'auto';
    var next = (cur === 'light') ? 'dark' : (cur === 'dark' ? 'auto' : 'light');
    saveAndApply(next);
  });
  // Sync across tabs
  window.addEventListener('storage', function(e){ if (e.key === storageKey) applyTheme(getSavedTheme()); });
  // Ensure icon after htmx loads
  if (window.htmx) {
    document.body.addEventListener('htmx:load', function(){ updateIcon(root.getAttribute('data-theme') || 'auto'); });
    // include current theme in all requests (used by /route_map to choose tiles)
    document.body.addEventListener('htmx:configRequest', function(ev){
      try {
        var t = root.getAttribute('data-theme') || 'auto';
        ev.detail.parameters = ev.detail.parameters || {};
        ev.detail.parameters.theme = t;
      } catch(_) {}
    });
  }
})();

// No custom theme management: use Bulma defaults only
// (Theme toggle button is inert unless you re-enable custom theming.)

(function(){
  function updateVatsimLink(fplTa, fileLink){
    if (!fplTa || !fileLink) return;
    var raw = encodeURIComponent(fplTa.value || '');
    fileLink.href = 'https://my.vatsim.net/pilots/flightplan/beta?raw=' + raw;
  }

  function bindResultUI(){
    var container = document;
    var fplTa = container.getElementById('icao-fpl-text');
    var routeTa = container.getElementById('route-text');
    var fileLink = container.getElementById('vatsim-file-link');
    var csInput = container.getElementById('callsign-input');
    var csExamples = container.querySelectorAll('.callsign-example');
    var depTimeInput = container.getElementById('dep-time-input');
    var useNowBtn = container.getElementById('use-now-btn');
    var originEl = container.querySelector('input[name="origin"]');
    var ORIGIN_ICAO = (window.ORIGIN_ICAO || (originEl ? originEl.value : '') || '').toUpperCase();

    function updateIcaoFpl(opts){
      if (!fplTa) return;
      var fpl = fplTa.value || '';
      var m = fpl.match(/\n-((?:N|M)[0-9A-Z]+)(F\d{3})([^\n)]*)/);
      if (!m) { updateVatsimLink(fplTa, fileLink); return; }
      var full = m[0];
      var spd = m[1];
      var lvl = m[2];
      var rteTail = m[3] || '';
      var newLvl = lvl;
      var newRoute = null;
      if (opts && opts.newLevelFL) {
        var digits = String(opts.newLevelFL).replace(/[^0-9]/g,'').padStart(3,'0');
        newLvl = 'F' + digits;
      }
      if (opts && typeof opts.newRoute === 'string') {
        newRoute = opts.newRoute.trim();
      }
      var rebuilt = '\n-' + spd + newLvl + (newRoute !== null ? (newRoute ? ' ' + newRoute : '') : rteTail);
      fplTa.value = fpl.replace(full, rebuilt);
      updateVatsimLink(fplTa, fileLink);
    }

    function updateIcaoDepTime(hhmm){
      if (!fplTa) return;
      var v = (hhmm || '').replace(/[^0-9]/g,'').slice(0,4);
      if (v.length !== 4) return;
      var fpl = fplTa.value || '';
  var re = new RegExp('\\n-' + ORIGIN_ICAO + '(\\d{4})');
      if (re.test(fpl)){
        fplTa.value = fpl.replace(re, function(s, t){ return s.replace(t, v); });
      }
      updateVatsimLink(fplTa, fileLink);
    }

    function updateIcaoCallsign(newCs){
      if (!fplTa) return;
      var fpl = fplTa.value || '';
      var cs = (newCs || '').toUpperCase().replace(/[^A-Z0-9]/g,'').slice(0,8);
      if (!cs) return;
      fplTa.value = fpl.replace(/\(FPL-([^-]+)-IS/, '(FPL-' + cs + '-IS');
      updateVatsimLink(fplTa, fileLink);
    }

    // Init VATSIM link
    updateVatsimLink(fplTa, fileLink);

    // Callsign input
    if (csInput && fplTa && !csInput.dataset.bound){
      var mcs = (fplTa.value || '').match(/\(FPL-([^-]+)-IS/);
      if (mcs) csInput.value = (mcs[1] || '').toUpperCase();
      var csDebounce;
      csInput.addEventListener('input', function(){
        var start = this.selectionStart, end = this.selectionEnd;
        this.value = (this.value || '').toUpperCase().replace(/[^A-Z0-9]/g,'');
        try { this.setSelectionRange(start, end); } catch(_) {}
        clearTimeout(csDebounce);
        var val = this.value;
        csDebounce = setTimeout(function(){ updateIcaoCallsign(val); }, 200);
      });
      csInput.dataset.bound = '1';
    }

    // Callsign examples
    csExamples.forEach(function(tag){
      if (tag.dataset.bound) return;
      tag.addEventListener('click', function(){
        var val = (this.getAttribute('data-cs') || '').toUpperCase();
        if (!val) return;
        if (csInput) { csInput.value = val; }
        updateIcaoCallsign(val);
      });
      tag.setAttribute('role','button');
      tag.setAttribute('tabindex','0');
      tag.addEventListener('keydown', function(ev){ if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); this.click(); } });
      tag.dataset.bound = '1';
    });

    // Eligible FL tags
    var flTags = container.querySelectorAll('.alt-fl .tag.is-clickable');
    flTags.forEach(function(tag){
      if (tag.dataset.bound) return;
      tag.addEventListener('click', function(){
        var txt = (this.textContent || '').trim();
        var routeStr = routeTa ? routeTa.value.trim() : null;
        updateIcaoFpl({ newLevelFL: txt, newRoute: routeStr });
        flTags.forEach(function(t){ t.classList.remove('is-active'); });
        this.classList.add('is-active');
        try {
          var toast = document.createElement('div');
          toast.textContent = 'Level updated to ' + txt;
          toast.style.position = 'fixed'; toast.style.right = '16px'; toast.style.bottom = '16px';
          toast.style.background = 'rgba(30,30,30,0.92)'; toast.style.color = '#fff'; toast.style.padding = '8px 12px';
          toast.style.borderRadius = '6px'; toast.style.zIndex = '9999'; toast.style.fontSize = '0.9rem';
          if (document.documentElement.classList.contains('dark')) {
            toast.style.background = 'rgba(20,20,20,0.9)'; toast.style.color = '#e8e8e8';
          }
          document.body.appendChild(toast);
          setTimeout(function(){ toast.remove(); }, 1600);
        } catch(e) {}
      });
      tag.addEventListener('keydown', function(ev){ if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); this.click(); } });
      tag.setAttribute('role','button');
      tag.setAttribute('tabindex','0');
      tag.dataset.bound = '1';
    });

    // Route textarea live update of FPL route
    if (routeTa && !routeTa.dataset.bound){
      var debounce;
      routeTa.addEventListener('input', function(){
        clearTimeout(debounce);
        var val = this.value;
        debounce = setTimeout(function(){ updateIcaoFpl({ newRoute: val }); }, 250);
      });
      routeTa.dataset.bound = '1';
    }

    // UTC clock tick (query element each time so it works after swaps)
    function tickUTC(){
      try {
        var el = container.getElementById('utc-clock');
        if (!el) return;
        var now = new Date();
        var hh = String(now.getUTCHours()).padStart(2,'0');
        var mm = String(now.getUTCMinutes()).padStart(2,'0');
        el.textContent = hh + ':' + mm + 'Z';
      } catch(e) {}
    }
    tickUTC();
    if (!window.__utcInterval){
      window.__utcInterval = setInterval(tickUTC, 1000 * 30);
    }

    // Dep time prefill + input
    if (depTimeInput && !depTimeInput.dataset.bound){
      (function(){
        var txt = (fplTa ? fplTa.value : '');
        var m3 = txt.match(new RegExp('\\n-' + ORIGIN_ICAO + '(\\d{4})'));
        if (m3 && m3[1]) depTimeInput.value = m3[1];
      })();
      var depDebounce;
      depTimeInput.addEventListener('input', function(){
        var start = this.selectionStart, end = this.selectionEnd;
        this.value = (this.value || '').replace(/[^0-9]/g,'').slice(0,4);
        try { this.setSelectionRange(start, end); } catch(_) {}
        clearTimeout(depDebounce);
        var v = this.value;
        depDebounce = setTimeout(function(){ updateIcaoDepTime(v); }, 250);
      });
      depTimeInput.dataset.bound = '1';
    }
    if (useNowBtn && !useNowBtn.dataset.bound){
      useNowBtn.addEventListener('click', function(){
        var now = new Date();
        var hh = String(now.getUTCHours()).padStart(2,'0');
        var mm = String(now.getUTCMinutes()).padStart(2,'0');
        var v = hh + mm;
        if (depTimeInput) depTimeInput.value = v;
        updateIcaoDepTime(v);
      });
      useNowBtn.dataset.bound = '1';
    }
  }

  // Initial bind (in case content already present)
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindResultUI);
  } else {
    bindResultUI();
  }

  // Re-bind on htmx swaps that touch #results
  if (window.htmx) {
    document.body.addEventListener('htmx:afterSwap', function(ev){
      try {
        var t = (ev && ev.detail && ev.detail.target) || ev.target;
        if (!t) return;
        var isResults = false;
        if (t.id === 'results') { isResults = true; }
        else if (typeof t.closest === 'function' && t.closest('#results')) { isResults = true; }
        if (isResults) {
          bindResultUI();
        }
      } catch(e) {}
    });
    // Some setups prefer htmx:load on injected fragments
    document.body.addEventListener('htmx:load', function(ev){
      try {
        var res = document.getElementById('results');
        if (res && (res.contains(ev.target) || ev.target === res)) {
          bindResultUI();
        }
      } catch(e) {}
    });
  }
})();

// Global error hook to catch unexpected runtime errors
if (!window.__routeHelperErrorHook) {
  window.__routeHelperErrorHook = true;
  window.addEventListener('error', function(e){
    try { console.warn('[RouteHelper] JS error:', e && e.message ? e.message : e); } catch(_) {}
  });
}
