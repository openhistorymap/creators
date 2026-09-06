/* History & Archaeology creator directory.
   Data source of truth = the CSV files in data/. No build step, no server-side code. */

'use strict';

/* ------------------------------------------------------------------ CSV */

function parseCSV(text) {
  const rows = [];
  let row = [], field = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; } else { quoted = false; }
      } else field += c;
    } else if (c === '"') { quoted = true; }
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
    else if (c !== '\r') { field += c; }
  }
  if (field !== '' || row.length) { row.push(field); rows.push(row); }
  return rows;
}

function csvToObjects(text) {
  const rows = parseCSV(text);
  if (!rows.length) return [];
  const head = rows[0].map(h => h.trim());
  return rows.slice(1)
    .filter(r => r.some(v => v.trim() !== ''))
    .map(r => {
      const o = {};
      head.forEach((k, i) => { o[k] = (r[i] === undefined ? '' : r[i]).trim(); });
      return o;
    });
}

const list = s => (s || '').split(';').map(x => x.trim()).filter(Boolean);

/* ------------------------------------------------- year scale & format */

const Y_MIN = -50000, Y_MAX = 2030, Y_SPAN = Y_MAX - Y_MIN;
const STEPS = 1000;

// Cube-root warp. A linear axis from the Palaeolithic to now would squash all of
// recorded history into the last 5% of the bar; this gives recent millennia room
// without cutting off the deep past.
const yearToPos = y => 1 - Math.cbrt(Math.max(0, (Y_MAX - y) / Y_SPAN));
const posToYear = p => Math.round(Y_MAX - Math.pow(1 - p, 3) * Y_SPAN);

const sliderToYear = v => posToYear(v / STEPS);
const yearToSlider = y => Math.round(yearToPos(y) * STEPS);

function fmtYear(y) {
  const n = Math.abs(Math.round(y));
  if (y < 0) return n >= 10000 ? (n / 1000).toFixed(0) + 'k BCE' : n.toLocaleString() + ' BCE';
  return n + ' CE';
}
const fmtSpan = (a, b) => (a === b ? fmtYear(a) : fmtYear(a) + ' – ' + fmtYear(b));

/* ------------------------------------------------------------ palette */

const PROFILES = [['youtube', 'YT'], ['instagram', 'IG'], ['tiktok', 'TT'],
                  ['facebook', 'FB'], ['website', 'WWW']];

const LANGS = { en: 'English', it: 'Italiano', de: 'Deutsch', fr: 'Français',
                es: 'Español', nl: 'Nederlands', pt: 'Português' };

const LINK_LABELS = { youtube: 'YouTube', instagram: 'Instagram', tiktok: 'TikTok',
                      facebook: 'Facebook', website: 'Website' };

const PALETTE = ['#d9a441', '#7fb0a3', '#c98a6b', '#8f9fd1', '#c47f9e',
                 '#9db06a', '#d2735e', '#6fa8c4', '#b48ec4', '#c9a97f',
                 '#7fbf8c', '#cf8f8f'];

/* -------------------------------------------------------------- state */

const S = {
  creators: new Map(),
  places: new Map(),
  videos: [],
  yearMin: Y_MIN,
  yearMax: Y_MAX,
  platform: '*',
  creatorSel: new Set(),
  langSel: new Set(),
  tagSel: new Set(),
  placeSel: new Set(),
  query: ''
};

let map, markerLayer;
const $ = id => document.getElementById(id);

/* --------------------------------------------------------------- load */

async function loadCSV(path) {
  const res = await fetch(path, { cache: 'no-store' });
  if (!res.ok) throw new Error(path + ' → HTTP ' + res.status);
  return csvToObjects(await res.text());
}

async function boot() {
  let creators, places, videos;
  try {
    [creators, places, videos] = await Promise.all([
      loadCSV('data/influencers.csv'),
      loadCSV('data/places.csv'),
      loadCSV('data/videos.csv')
    ]);
  } catch (err) {
    document.body.insertAdjacentHTML('afterbegin',
      '<div class="empty"><p>Could not load the CSV data: ' + err.message +
      '<br>Serve this folder over HTTP (<code>./serve.sh</code>) — <code>file://</code> blocks fetch.</p></div>');
    return;
  }

  creators.forEach((c, i) => {
    c.color = PALETTE[i % PALETTE.length];
    c.count = 0;
    S.creators.set(c.id, c);
  });
  places.forEach(p => {
    p.lat = parseFloat(p.lat);
    p.lon = parseFloat(p.lon);
    if (Number.isFinite(p.lat) && Number.isFinite(p.lon)) S.places.set(p.id, p);
  });

  S.videos = videos.map(v => {
    const a = parseFloat(v.year_start), b = parseFloat(v.year_end);
    v.y0 = Number.isFinite(a) ? a : Y_MIN;
    v.y1 = Number.isFinite(b) ? b : v.y0;
    if (v.y1 < v.y0) { const t = v.y0; v.y0 = v.y1; v.y1 = t; }
    v.placeIds = list(v.places).filter(id => S.places.has(id));
    v.tags = list(v.tags);
    v.creator = S.creators.get(v.influencer_id) || null;
    if (v.creator) v.creator.count++;
    v.lang = v.creator ? (v.creator.language || '').toLowerCase() : '';
    v.haystack = [v.title, v.era, v.tags.join(' '), v.creator ? v.creator.name : '',
                  v.placeIds.map(id => S.places.get(id).name).join(' ')].join(' ').toLowerCase();
    return v;
  });

  $('count-videos').textContent = S.videos.length;
  $('count-creators').textContent = S.creators.size;
  $('count-places').textContent = S.places.size;

  initMap();
  buildLangFacet();
  buildCreatorFacet();
  buildTagFacet();
  bindControls();
  drawTicks();
  render();
}

/* ---------------------------------------------------------------- map */

function initMap() {
  map = L.map('map', { worldCopyJump: true, zoomControl: true }).setView([25, 12], 2);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 18,
    className: 'tiles-muted'
  }).addTo(map);
  markerLayer = L.layerGroup().addTo(map);

  // Popups are rebuilt on every render, so delegate instead of binding per marker.
  map.on('popupopen', e => {
    const link = e.popup.getElement().querySelector('.pfilter');
    if (!link) return;
    link.onclick = ev => {
      ev.preventDefault();
      toggle(S.placeSel, link.dataset.place);
      map.closePopup();
      render();
    };
  });
}

/* ------------------------------------------------------------- facets */

function buildCreatorFacet() {
  const box = $('creator-filter');
  box.innerHTML = '';

  const byCreator = new Map();
  S.videos.forEach(v => {
    if (!byCreator.has(v.influencer_id)) byCreator.set(v.influencer_id, []);
    byCreator.get(v.influencer_id).push(v);
  });

  [...S.creators.values()]
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
    .forEach(c => {
      const vids = byCreator.get(c.id) || [];

      const el = document.createElement('div');
      el.className = 'creator-row';
      el.dataset.id = c.id;

      const head = document.createElement('div');
      head.className = 'cr-head';
      head.innerHTML = '<span class="dot" style="background:' + c.color + '"></span>' +
                       '<span class="nm"></span>';
      head.querySelector('.nm').textContent = c.name;

      const links = document.createElement('span');
      links.className = 'creator-links';
      PROFILES.forEach(([field, label]) => {
        const href = (c[field] || '').trim();
        if (!href) return;
        const link = document.createElement('a');
        link.href = href;
        link.target = '_blank';
        link.rel = 'noopener';
        link.textContent = label;
        link.title = c.name + ' on ' + field;
        link.onclick = ev => ev.stopPropagation();   // follow the link, don't filter
        links.appendChild(link);
      });
      head.appendChild(links);

      const info = document.createElement('button');
      info.className = 'cr-info';
      info.type = 'button';
      info.textContent = 'i';
      info.title = 'Profile of ' + c.name;
      info.setAttribute('aria-label', 'Profile of ' + c.name);
      info.onclick = ev => { ev.stopPropagation(); openProfile(c.id); };
      head.appendChild(info);

      const n = document.createElement('span');
      n.className = 'n';
      n.textContent = vids.length;
      head.appendChild(n);
      el.appendChild(head);

      el.appendChild(sparkline(c, vids));

      const meta = document.createElement('div');
      meta.className = 'cr-meta';
      if (vids.length) {
        const lo = Math.min(...vids.map(v => v.y0));
        const hi = Math.max(...vids.map(v => v.y1));
        const places = new Set();
        vids.forEach(v => v.placeIds.forEach(p => places.add(p)));
        const reels = vids.filter(v => v.platform === 'reel').length;
        meta.textContent = fmtSpan(lo, hi) + ' · ' + places.size + ' place' +
                           (places.size === 1 ? '' : 's') +
                           (reels ? ' · ' + reels + ' reel' + (reels === 1 ? '' : 's') : '');
      } else {
        meta.textContent = 'no items indexed';
        meta.classList.add('muted');
      }
      el.appendChild(meta);

      el.onclick = () => { toggle(S.creatorSel, c.id); render(); };
      box.appendChild(el);
    });
  $('fc-creators').textContent = S.creators.size;
}

/* A creator's coverage drawn on the SAME warped year axis as the main timeline,
   so two profiles can be compared by eye. Static: it describes the creator's
   whole catalogue, not the current filter. */
const SPARK_BINS = 56;
function sparkline(c, vids) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'spark');
  svg.setAttribute('viewBox', '0 0 100 20');
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('aria-hidden', 'true');
  if (!vids.length) return svg;

  const bins = new Array(SPARK_BINS).fill(0);
  vids.forEach(v => {
    const lo = Math.max(0, Math.floor(yearToPos(Math.max(v.y0, Y_MIN)) * SPARK_BINS));
    const hi = Math.min(SPARK_BINS - 1, Math.floor(yearToPos(Math.min(v.y1, Y_MAX)) * SPARK_BINS));
    for (let i = lo; i <= hi; i++) bins[i]++;
  });
  const max = Math.max(...bins);
  const w = 100 / SPARK_BINS;

  // faint marker at year 0, so BCE/CE is readable without an axis
  const zero = document.createElementNS(svg.namespaceURI, 'line');
  const zx = (yearToPos(0) * 100).toFixed(2);
  zero.setAttribute('x1', zx); zero.setAttribute('x2', zx);
  zero.setAttribute('y1', '0'); zero.setAttribute('y2', '20');
  zero.setAttribute('class', 'spark-zero');
  svg.appendChild(zero);

  bins.forEach((v, i) => {
    if (!v) return;
    const h = Math.max(3, (v / max) * 20);
    const r = document.createElementNS(svg.namespaceURI, 'rect');
    r.setAttribute('x', (i * w).toFixed(2));
    r.setAttribute('y', (20 - h).toFixed(2));
    r.setAttribute('width', (w * 0.82).toFixed(2));
    r.setAttribute('height', h.toFixed(2));
    r.setAttribute('fill', c.color);
    svg.appendChild(r);
  });
  return svg;
}

function buildLangFacet() {
  const counts = new Map();
  S.videos.forEach(v => { if (v.lang) counts.set(v.lang, (counts.get(v.lang) || 0) + 1); });
  const box = $('lang-filter');
  box.innerHTML = '';
  [...counts.entries()].sort((a, b) => b[1] - a[1]).forEach(([code, n]) => {
    const b = document.createElement('button');
    b.className = 'chip lang';
    b.dataset.lang = code;
    b.textContent = (LANGS[code] || code) + ' ' + n;
    b.onclick = () => { toggle(S.langSel, code); render(); };
    box.appendChild(b);
  });
}

function buildTagFacet() {
  const counts = new Map();
  S.videos.forEach(v => v.tags.forEach(t => counts.set(t, (counts.get(t) || 0) + 1)));
  const box = $('tag-filter');
  box.innerHTML = '';
  [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .forEach(([tag, n]) => {
      const b = document.createElement('button');
      b.className = 'chip';
      b.dataset.tag = tag;
      b.textContent = tag + ' ' + n;
      b.onclick = () => { toggle(S.tagSel, tag); render(); };
      box.appendChild(b);
    });
  $('fc-tags').textContent = counts.size;
}

function toggle(set, key) { set.has(key) ? set.delete(key) : set.add(key); }


/* ------------------------------------------------------- creator profile */

function creatorItems(id) {
  return S.videos.filter(v => v.influencer_id === id)
                 .sort((a, b) => a.y0 - b.y0 || a.y1 - b.y1);
}

function openProfile(id) {
  const c = S.creators.get(id);
  if (!c) return;
  const vids = creatorItems(id);
  const box = $('profile');
  box.innerHTML = '';

  const close = document.createElement('button');
  close.className = 'profile-close';
  close.type = 'button';
  close.textContent = '×';
  close.setAttribute('aria-label', 'Close profile');
  close.onclick = closeProfile;
  box.appendChild(close);

  // header
  const head = document.createElement('header');
  head.className = 'profile-head';
  const badge = document.createElement('span');
  badge.className = 'profile-avatar';
  badge.style.background = c.color;
  badge.textContent = (c.name || '?').trim().charAt(0).toUpperCase();
  const htxt = document.createElement('div');
  const h2 = document.createElement('h2');
  h2.textContent = c.name;
  const handle = document.createElement('p');
  handle.className = 'profile-handle';
  handle.textContent = c.handle || '';
  if (c.language) {
    const lang = document.createElement('span');
    lang.className = 'profile-lang';
    lang.textContent = LANGS[c.language] || c.language;
    handle.appendChild(lang);
  }
  htxt.append(h2, handle);
  head.append(badge, htxt);
  box.appendChild(head);

  if (c.focus) {
    const f = document.createElement('p');
    f.className = 'profile-focus';
    f.textContent = c.focus;
    box.appendChild(f);
  }

  // links
  const links = document.createElement('div');
  links.className = 'profile-links';
  let any = false;
  PROFILES.forEach(([field, label]) => {
    const href = (c[field] || '').trim();
    if (!href) return;
    any = true;
    const a = document.createElement('a');
    a.href = href;
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = LINK_LABELS[field] || label;
    links.appendChild(a);
  });
  if (any) box.appendChild(links);

  // stats
  const places = new Set();
  vids.forEach(v => v.placeIds.forEach(p => places.add(p)));
  const reels = vids.filter(v => v.platform === 'reel').length;
  const stats = document.createElement('div');
  stats.className = 'profile-stats';
  const cells = [
    [vids.length, vids.length === 1 ? 'item' : 'items'],
    [reels, reels === 1 ? 'reel' : 'reels'],
    [vids.length - reels, 'long-form'],
    [places.size, places.size === 1 ? 'place' : 'places']
  ];
  cells.forEach(([n, label]) => {
    const d = document.createElement('div');
    d.innerHTML = '<b></b><span></span>';
    d.querySelector('b').textContent = n;
    d.querySelector('span').textContent = label;
    stats.appendChild(d);
  });
  box.appendChild(stats);

  if (vids.length) {
    const lo = Math.min(...vids.map(v => v.y0));
    const hi = Math.max(...vids.map(v => v.y1));
    const sec = document.createElement('div');
    sec.className = 'profile-section';
    sec.innerHTML = '<h3>Coverage</h3>';
    const span = document.createElement('p');
    span.className = 'profile-span';
    span.textContent = fmtSpan(lo, hi);
    sec.appendChild(span);
    const spark = sparkline(c, vids);
    spark.classList.add('spark-lg');
    sec.appendChild(spark);
    const ticks = document.createElement('div');
    ticks.className = 'profile-ticks';
    [-50000, -10000, -2000, 0, 1000, 2000].forEach(y => {
      const s = document.createElement('span');
      s.style.left = (yearToPos(y) * 100).toFixed(2) + '%';
      s.textContent = fmtYear(y);
      ticks.appendChild(s);
    });
    sec.appendChild(ticks);
    box.appendChild(sec);
  }

  // tags
  const tagCount = new Map();
  vids.forEach(v => v.tags.forEach(t => tagCount.set(t, (tagCount.get(t) || 0) + 1)));
  if (tagCount.size) {
    const sec = document.createElement('div');
    sec.className = 'profile-section';
    sec.innerHTML = '<h3>Themes</h3>';
    const row = document.createElement('div');
    row.className = 'chip-row';
    [...tagCount.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, 14).forEach(([t, n]) => {
        const b = document.createElement('button');
        b.className = 'chip';
        b.textContent = t + ' ' + n;
        b.onclick = () => { S.tagSel.add(t); closeProfile(); render(); };
        row.appendChild(b);
      });
    sec.appendChild(row);
    box.appendChild(sec);
  }

  // places
  if (places.size) {
    const sec = document.createElement('div');
    sec.className = 'profile-section';
    sec.innerHTML = '<h3>Places</h3>';
    const row = document.createElement('div');
    row.className = 'chip-row';
    [...places].map(id => S.places.get(id)).filter(Boolean)
      .sort((a, b) => a.name.localeCompare(b.name)).forEach(p => {
        const b = document.createElement('button');
        b.className = 'chip';
        b.textContent = p.name;
        b.onclick = () => {
          S.placeSel.add(p.id);
          closeProfile();
          render();
          map.setView([p.lat, p.lon], Math.max(map.getZoom(), 5));
        };
        row.appendChild(b);
      });
    sec.appendChild(row);
    box.appendChild(sec);
  }

  if ((c.notes || '').trim()) {
    const sec = document.createElement('div');
    sec.className = 'profile-section';
    sec.innerHTML = '<h3>Notes</h3>';
    const p = document.createElement('p');
    p.className = 'profile-notes';
    p.textContent = c.notes;
    sec.appendChild(p);
    box.appendChild(sec);
  }

  // every item, earliest first
  const sec = document.createElement('div');
  sec.className = 'profile-section';
  sec.innerHTML = '<h3>All items</h3>';
  if (!vids.length) {
    const p = document.createElement('p');
    p.className = 'profile-notes';
    p.textContent = 'No items indexed yet.';
    sec.appendChild(p);
  }
  vids.forEach(v => {
    const a = document.createElement('a');
    a.className = 'profile-item';
    a.href = v.url || '#';
    a.target = '_blank';
    a.rel = 'noopener';
    const yr = document.createElement('span');
    yr.className = 'pi-year';
    yr.textContent = fmtSpan(v.y0, v.y1);
    const t = document.createElement('span');
    t.className = 'pi-title';
    t.textContent = v.title;
    const b = document.createElement('span');
    b.className = 'badge ' + v.platform;
    b.textContent = v.platform === 'reel' ? 'reel' : 'yt';
    a.append(yr, t, b);
    sec.appendChild(a);
  });
  box.appendChild(sec);

  const filter = document.createElement('button');
  filter.className = 'profile-filter';
  filter.type = 'button';
  filter.textContent = 'Filter the directory to ' + c.name;
  filter.onclick = () => {
    S.creatorSel.clear();
    S.creatorSel.add(c.id);
    closeProfile();
    render();
  };
  box.appendChild(filter);

  box.hidden = false;
  $('scrim').hidden = false;
  box.scrollTop = 0;
  box.focus();
}

function closeProfile() {
  $('profile').hidden = true;
  $('scrim').hidden = true;
}

/* ----------------------------------------------------------- controls */

function bindControls() {
  const lo = $('year-min'), hi = $('year-max');
  lo.value = 0; hi.value = STEPS;

  const sync = () => {
    let a = +lo.value, b = +hi.value;
    if (a > b) { if (document.activeElement === lo) b = a, hi.value = b; else a = b, lo.value = a; }
    S.yearMin = sliderToYear(a);
    S.yearMax = sliderToYear(b);
    render();
  };
  lo.oninput = hi.oninput = sync;

  $('tl-reset').onclick = () => {
    lo.value = 0; hi.value = STEPS;
    S.yearMin = Y_MIN; S.yearMax = Y_MAX;
    render();
  };

  let t;
  $('q').oninput = e => {
    clearTimeout(t);
    t = setTimeout(() => { S.query = e.target.value.trim().toLowerCase(); render(); }, 120);
  };

  $('scrim').onclick = closeProfile;
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !$('profile').hidden) closeProfile();
  });

  $('platform-filter').onclick = e => {
    const b = e.target.closest('.chip');
    if (!b) return;
    S.platform = b.dataset.platform;
    [...e.currentTarget.children].forEach(c => c.classList.toggle('active', c === b));
    render();
  };
}

function drawTicks() {
  const marks = [-50000, -20000, -10000, -5000, -2000, 0, 1000, 1800, 2000];
  $('tl-ticks').innerHTML = marks.map(y =>
    '<span style="left:' + (yearToPos(y) * 100).toFixed(2) + '%">' + fmtYear(y) + '</span>'
  ).join('');
}

/* ------------------------------------------------------------ filters */

function matchesNonYear(v) {
  if (S.platform !== '*' && v.platform !== S.platform) return false;
  if (S.creatorSel.size && !S.creatorSel.has(v.influencer_id)) return false;
  if (S.langSel.size && !S.langSel.has(v.lang)) return false;
  if (S.tagSel.size && !v.tags.some(t => S.tagSel.has(t))) return false;
  if (S.placeSel.size && !v.placeIds.some(p => S.placeSel.has(p))) return false;
  if (S.query && !v.haystack.includes(S.query)) return false;
  return true;
}
const inYears = v => v.y1 >= S.yearMin && v.y0 <= S.yearMax;

/* ------------------------------------------------------------- render */

function render() {
  const preYear = S.videos.filter(matchesNonYear);      // drives the histogram
  const shown = preYear.filter(inYears);

  renderHistogram(preYear);
  renderRangeUI();
  renderActiveFilters();
  renderFacetStates();
  renderResults(shown);
  renderMarkers(shown);
}

function renderRangeUI() {
  const a = yearToPos(S.yearMin) * 100, b = yearToPos(S.yearMax) * 100;
  const fill = $('range-fill');
  fill.style.left = a + '%';
  fill.style.width = Math.max(0, b - a) + '%';
  $('tl-range').textContent = fmtSpan(S.yearMin, S.yearMax);
}

const BUCKETS = 110;
function renderHistogram(vids) {
  const bins = new Array(BUCKETS).fill(0);
  vids.forEach(v => {
    const lo = Math.max(0, Math.floor(yearToPos(Math.max(v.y0, Y_MIN)) * BUCKETS));
    const hi = Math.min(BUCKETS - 1, Math.floor(yearToPos(Math.min(v.y1, Y_MAX)) * BUCKETS));
    for (let i = lo; i <= hi; i++) bins[i]++;
  });
  const max = Math.max(1, ...bins);
  const loB = yearToPos(S.yearMin) * BUCKETS, hiB = yearToPos(S.yearMax) * BUCKETS;
  $('histogram').innerHTML = bins.map((n, i) =>
    '<i class="' + (i >= loB - 1 && i <= hiB ? 'on' : '') + '" style="height:' +
    (n ? Math.max(8, (n / max) * 100) : 1) + '%" title="' +
    fmtYear(posToYear(i / BUCKETS)) + ' · ' + n + '"></i>'
  ).join('');
}

function renderActiveFilters() {
  const box = $('active-filters');
  const items = [
    ...[...S.creatorSel].map(id => ({ k: 'creator', id, label: (S.creators.get(id) || {}).name || id })),
    ...[...S.langSel].map(l => ({ k: 'lang', id: l, label: LANGS[l] || l })),
    ...[...S.tagSel].map(t => ({ k: 'tag', id: t, label: '#' + t })),
    ...[...S.placeSel].map(p => ({ k: 'place', id: p, label: '⚲ ' + (S.places.get(p) || {}).name }))
  ];
  box.hidden = !items.length;
  box.innerHTML = '';
  items.forEach(it => {
    const b = document.createElement('button');
    b.className = 'chip';
    b.textContent = it.label;
    b.onclick = () => {
      ({ creator: S.creatorSel, lang: S.langSel, tag: S.tagSel,
         place: S.placeSel })[it.k].delete(it.id);
      render();
    };
    box.appendChild(b);
  });
}

function renderFacetStates() {
  document.querySelectorAll('#creator-filter .creator-row').forEach(el =>
    el.classList.toggle('active', S.creatorSel.has(el.dataset.id)));
  document.querySelectorAll('#tag-filter .chip').forEach(el =>
    el.classList.toggle('active', S.tagSel.has(el.dataset.tag)));
  document.querySelectorAll('#lang-filter .chip').forEach(el =>
    el.classList.toggle('active', S.langSel.has(el.dataset.lang)));
}

function renderResults(vids) {
  const box = $('results');
  box.innerHTML = '';
  $('empty').hidden = vids.length > 0;
  if (!vids.length) return;

  vids.sort((a, b) => a.y0 - b.y0 || a.y1 - b.y1);

  const head = document.createElement('div');
  head.className = 'group-head';
  head.textContent = vids.length + ' items · earliest first';
  box.appendChild(head);

  const frag = document.createDocumentFragment();
  vids.forEach(v => frag.appendChild(card(v)));
  box.appendChild(frag);
}

function card(v) {
  const a = document.createElement('a');
  a.className = 'card';
  a.href = v.url || '#';
  a.target = '_blank';
  a.rel = 'noopener';

  const plat = (v.platform || 'link').toLowerCase();

  const body = document.createElement('div');
  body.className = 'card-body';

  if (v.thumbnail) {
    const th = document.createElement('img');
    th.className = 'thumb';
    th.src = v.thumbnail;
    th.alt = '';
    th.loading = 'lazy';
    th.decoding = 'async';
    th.onerror = () => th.remove();
    a.appendChild(th);
  }

  const top = document.createElement('div');
  top.className = 'card-top';
  const h = document.createElement('h3');
  h.textContent = v.title;
  const badge = document.createElement('span');
  badge.className = 'badge ' + plat;
  badge.textContent = plat === 'reel' ? 'reel' : plat;
  top.append(h, badge);

  const by = document.createElement('p');
  by.className = 'by';
  if (v.creator) {
    by.innerHTML = '<span class="dot" style="background:' + v.creator.color + '"></span>';
    const nameBtn = document.createElement('button');
    nameBtn.type = 'button';
    nameBtn.className = 'by-name';
    nameBtn.textContent = v.creator.name;
    nameBtn.title = 'Profile of ' + v.creator.name;
    nameBtn.onclick = ev => {
      ev.preventDefault();          // the card itself is a link
      ev.stopPropagation();
      openProfile(v.creator.id);
    };
    by.appendChild(nameBtn);
  } else {
    by.textContent = 'unknown creator';
  }

  const meta = document.createElement('div');
  meta.className = 'meta';
  const yr = document.createElement('span');
  yr.className = 'years';
  yr.textContent = fmtSpan(v.y0, v.y1);
  meta.appendChild(yr);
  if (v.era) {
    const e = document.createElement('span');
    e.className = 'era';
    e.textContent = v.era;
    meta.appendChild(e);
  }
  v.placeIds.forEach(id => {
    const p = S.places.get(id);
    const c = document.createElement('span');
    c.className = 'place-chip';
    c.textContent = p.name;
    c.onclick = ev => { ev.preventDefault(); toggle(S.placeSel, id); render(); };
    meta.appendChild(c);
  });
  if ((v.verified || '').toLowerCase() !== 'yes') {
    const u = document.createElement('span');
    u.className = 'unverified';
    u.textContent = '⚑ unverified';
    u.title = v.notes || 'Link and metadata not yet checked';
    meta.appendChild(u);
  }

  body.append(top, by, meta);
  a.appendChild(body);
  return a;
}

function renderMarkers(vids) {
  markerLayer.clearLayers();
  const byPlace = new Map();
  vids.forEach(v => v.placeIds.forEach(id => {
    if (!byPlace.has(id)) byPlace.set(id, []);
    byPlace.get(id).push(v);
  }));

  byPlace.forEach((items, id) => {
    const p = S.places.get(id);
    const selected = S.placeSel.has(id);
    const m = L.circleMarker([p.lat, p.lon], {
      radius: 5 + Math.min(12, Math.sqrt(items.length) * 4),
      color: selected ? '#f0ebe2' : '#d9a441',
      weight: selected ? 2.5 : 1.5,
      fillColor: items.length === 1 && items[0].creator ? items[0].creator.color : '#d9a441',
      fillOpacity: .55
    });
    const links = items.slice(0, 8).map(v =>
      '<a href="' + (v.url || '#') + '" target="_blank" rel="noopener">· ' +
      escapeHTML(v.title) + ' <em>(' + fmtSpan(v.y0, v.y1) + ')</em></a>').join('');
    m.bindPopup('<b>' + escapeHTML(p.name) + '</b> — ' + items.length + ' item' +
      (items.length > 1 ? 's' : '') + links +
      (items.length > 8 ? '<em>…and ' + (items.length - 8) + ' more</em>' : '') +
      '<a href="#" class="pfilter" data-place="' + id + '">' +
      (selected ? '✕ clear place filter' : '⚲ filter to this place') + '</a>');
    markerLayer.addLayer(m);
  });
}

function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

boot();
