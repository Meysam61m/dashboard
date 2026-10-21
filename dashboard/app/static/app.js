/* داشبورد مدیریتی مجتمع خراسان — بدون هیچ وابستگی خارجی (کاملاً آفلاین) */
'use strict';

const FA = '۰۱۲۳۴۵۶۷۸۹';
const fa = s => String(s).replace(/[0-9]/g, d => FA[+d]);
const nf = (v, d = 0) => (v === null || v === undefined || isNaN(v)) ? '—'
  : fa(new Intl.NumberFormat('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }).format(v));
const compact = v => {
  if (v === null || v === undefined || isNaN(v)) return '—';
  const a = Math.abs(v);
  if (a >= 1e9) return fa((v / 1e9).toFixed(1)) + ' میلیارد';
  if (a >= 1e6) return fa((v / 1e6).toFixed(1)) + ' میلیون';
  if (a >= 1e4) return fa(Math.round(v / 1e3)) + ' هزار';
  return nf(v);
};
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const PAGES = [
  { k: 'overview', t: 'نمای مدیریتی', i: '◈', g: 'مرور' },
  { k: 'fin', t: 'مالی و سودآوری', i: '◧', g: 'دامنه‌ها' },
  { k: 'hr', t: 'نیروی انسانی', i: '◔', g: '' },
  { k: 'pay', t: 'هزینهٔ پرسنلی', i: '◍', g: '' },
  { k: 'wh', t: 'انبار و ظرفیت', i: '▤', g: '' },
  { k: 'flt', t: 'ناوگان', i: '⛟', g: '' },
  { k: 'ops', t: 'عملیات و تناژ', i: '⇄', g: '' },
  { k: 'prj', t: 'پروژه‌ها', i: '◆', g: '' },
  { k: 'data', t: 'کیفیت و ورود داده', i: '⚙', g: 'سیستم' },
];

const state = { page: 'overview', branch: 'مجتمع', year: 1405, period: 'H1', meta: null, ai: null };
const $ = s => document.querySelector(s);
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h !== undefined) e.innerHTML = h; return e; };
const C = { navy: '#0E2A47', teal: '#0E8F8F', gold: '#C7A227', red: '#C0392B', green: '#1E8E5A', purple: '#6B4C9A', orange: '#D97706', blue: '#2563A8', grey: '#7A8C9E' };

function toast(msg, err) {
  const t = $('#toast'); t.textContent = msg; t.className = 'toast show' + (err ? ' err' : '');
  clearTimeout(t._h); t._h = setTimeout(() => t.className = 'toast', 5000);
}

/* ───────────────────────── راه‌اندازی */
async function boot() {
  state.meta = await (await fetch('/api/meta')).json();
  renderNav();
  const sb = $('#selBranch'), sp = $('#selPeriod'), sy = $('#selYear');
  sb.innerHTML = state.meta.branches.map(b => `<option${b === state.branch ? ' selected' : ''}>${esc(b)}</option>`).join('');
  sp.innerHTML = state.meta.periods.map(p => `<option value="${p.key}"${p.key === state.period ? ' selected' : ''}>${esc(p.label)}</option>`).join('');
  sy.innerHTML = state.meta.years.slice().reverse().map(y => `<option${y === state.year ? ' selected' : ''}>${fa(y)}</option>`).join('');
  sb.onchange = e => { state.branch = e.target.value; load(); };
  sp.onchange = e => { state.period = e.target.value; load(); };
  sy.onchange = e => { state.year = +e.target.value; load(); };
  await checkAI();
  const fromHash = (location.hash || '').replace('#', '');
  if (fromHash && PAGES.some(p => p.k === fromHash)) {
    state.page = fromHash;
    nav.querySelectorAll('a').forEach(x => x.classList.toggle('active', x.dataset.page === fromHash));
  }
  window.addEventListener('hashchange', () => {
    const h = (location.hash || '').replace('#', '');
    if (PAGES.some(p => p.k === h) && h !== state.page) {
      state.page = h;
      nav.querySelectorAll('a').forEach(x => x.classList.toggle('active', x.dataset.page === h));
      load();
    }
  });
  load();
}

function renderNav() {
  const nav = $('#nav');
  let html = '', lastG = null;
  PAGES.forEach(p => {
    if (p.g && p.g !== lastG) { html += `<div class="group">${esc(p.g)}</div>`; lastG = p.g; }
    html += `<a href="#${p.k}" data-page="${p.k}" class="${p.k === state.page ? 'active' : ''}">
      <span class="ico">${p.i}</span><span>${esc(p.t)}</span></a>`;
  });
  nav.innerHTML = html;
  nav.querySelectorAll('a').forEach(a => a.onclick = ev => {
    ev.preventDefault(); state.page = a.dataset.page;
    nav.querySelectorAll('a').forEach(x => x.classList.toggle('active', x === a));
    load();
  });
}

async function checkAI() {
  const badge = $('#aiBadge'), st = $('#aiState');
  try {
    const h = await (await fetch('/api/ai/health')).json();
    state.ai = h;
    if (h.online) {
      st.innerHTML = `<span class="dot on"></span>متصل به Ollama<br><span style="opacity:.6;font-size:10.5px">${esc(h.host)}</span>`;
    } else {
      st.innerHTML = `<span class="dot off"></span>Ollama در دسترس نیست<br><span style="opacity:.6;font-size:10.5px">${esc(h.host)}</span>`;
    }
  } catch (e) {
    st.innerHTML = `<span class="dot off"></span>وضعیت نامشخص`;
  }
}

/* ───────────────────────── بارگذاری صفحه */
async function load() {
  const c = $('#content');
  c.innerHTML = `<div class="panel"><div class="skel w60"></div><div class="skel w90"></div><div class="skel w75"></div></div>`;
  const q = new URLSearchParams({ page: state.page, branch: state.branch, year: state.year, period: state.period });
  const data = await (await fetch('/api/dashboard?' + q)).json();
  state.data = data;
  $('#pageTitle').textContent = data.title;
  $('#pageEn').textContent = data.en || '';
  c.innerHTML = '';

  if (data.cards?.length) c.appendChild(renderCards(data.cards));
  if (data.alerts?.length) c.appendChild(renderAlerts(data.alerts));

  if (data.page === 'data') { renderDataPage(c, data); return; }

  // نمودارها: دو ستونه
  const rows = [];
  for (let i = 0; i < (data.charts || []).length; i += 2) rows.push(data.charts.slice(i, i + 2));
  rows.forEach(pair => {
    const g = el('div', 'grid');
    pair.forEach(ch => g.appendChild(chartPanel(ch)));
    if (pair.length === 1) g.appendChild(el('div', 'panel', ''));
    c.appendChild(g);
  });

  (data.tables || []).forEach(tb => c.appendChild(tablePanel(tb)));

  // تحلیل هوش مصنوعی
  c.appendChild(aiPanel(data));
}

/* ───────────────────────── کارت‌ها */
function dirOf(card) {
  const { act, ly, direction } = card;
  if (act === null || ly === null || ly === undefined || act === undefined) return null;
  const diff = act - ly;
  if (Math.abs(diff) < 1e-9) return 'flat';
  const better = direction === 'down' ? diff < 0 : diff > 0;
  return better ? 'up' : 'down';
}
function toneOf(card) {
  const map = { 'FIN.REV': 'navy', 'FIN.COST': 'orange', 'FIN.NET': 'green', 'FIN.MARGIN': 'teal',
    'HR.HEAD': 'blue', 'PAY.TOT': 'purple', 'WH.OCC': 'gold', 'WH.AREA': 'teal',
    'FLT.COUNT': 'navy', 'FLT.TON.DEV': 'teal', 'OPS.TON': 'blue', 'PRJ.ABSORB': 'orange' };
  return map[card.code] || 'navy';
}
function renderCards(cards) {
  const w = el('div', 'cards');
  cards.forEach(card => {
    const d = dirOf(card);
    const arrow = d === 'up' ? '▲' : d === 'down' ? '▼' : '';
    const box = el('div', 'card ' + toneOf(card));
    const isPct = card.unit === '%';
    box.innerHTML = `
      <div class="lbl">${esc(card.title)}</div>
      <div class="val">${nf(card.act, card.decimals)}<small>${esc(card.unit)}</small></div>
      <div class="cmp">
        <span>بودجه: <b>${nf(card.bud, card.decimals)}</b></span>
        <span>دوره مشابه: <b>${nf(card.ly, card.decimals)}</b></span>
        ${d ? `<span class="delta ${d}">${arrow} ${fa(Math.abs((card.act - card.ly) / (Math.abs(card.ly) || 1) * 100).toFixed(1))}٪</span>` : ''}
      </div>
      <div class="formula">${esc(card.formula || '')}</div>`;
    w.appendChild(box);
  });
  return w;
}

/* ───────────────────────── هشدارها */
function renderAlerts(alerts) {
  const p = el('div', 'panel');
  p.innerHTML = `<h3>هشدارهای سیستم</h3><div class="sub">تولیدشده توسط قواعد قطعی — نه مدل زبانی</div><div class="alerts-grid" id="ag"></div>`;
  const ag = p.querySelector('#ag');
  alerts.forEach(a => {
    const d = el('div', 'alert ' + a.severity);
    d.innerHTML = `<div style="flex:1"><b>${esc(a.title)}</b><p>${esc(a.detail)}</p></div>
      <div class="id">${esc(a.id)}</div>`;
    ag.appendChild(d);
  });
  return p;
}

/* ───────────────────────── جدول */
function tablePanel(tb) {
  const p = el('div', 'panel');
  p.style.marginBottom = '16px';
  const nums = new Set(tb.numeric || []);
  const dec = tb.decimals || [];
  let head = '<tr>' + tb.columns.map((c, i) => `<th class="${nums.has(i) ? 'num' : ''}">${esc(c)}</th>`).join('') + '</tr>';
  let body = tb.rows.map(r => '<tr>' + r.map((v, i) => {
    if (!nums.has(i)) return `<td>${esc(v)}</td>`;
    const di = nums.has(i) ? [...nums].indexOf(i) : 0;
    const d = dec[di] ?? 0;
    const cls = typeof v === 'number' ? (v < 0 ? 'neg' : (i >= 3 ? 'pos' : '')) : '';
    return `<td class="num ${cls}">${nf(v, d)}</td>`;
  }).join('') + '</tr>').join('');
  p.innerHTML = `<h3>${esc(tb.title)}</h3><div class="scroll"><table><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
  return p;
}

/* ───────────────────────── نمودار */
function chartPanel(spec) {
  const p = el('div', 'panel chart');
  p.innerHTML = `<h3>${esc(spec.title)}</h3><div class="sub">${esc(spec.unit || '')}</div>`;
  const box = el('div');
  p.appendChild(box);
  requestAnimationFrame(() => {
    if (spec.type === 'line') box.innerHTML = lineChart(spec);
    else if (spec.type === 'donut') box.innerHTML = donutChart(spec);
    else box.innerHTML = barChart(spec);
  });
  if (spec.series?.length > 1 || spec.type === 'donut') {
    const lg = el('div', 'legend');
    const cols = spec.type === 'donut' ? donutColors(spec.series[0].values.length) : spec.series.map(s => s.color);
    spec.series.forEach((s, i) => {
      if (spec.type !== 'donut') lg.innerHTML += `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`;
    });
    if (spec.type === 'donut') {
      spec.labels.forEach((l, i) => lg.innerHTML += `<span><i style="background:${cols[i]}"></i>${esc(l)}</span>`);
    }
    p.appendChild(lg);
  }
  return p;
}

function donutColors(n) {
  return [C.navy, C.teal, C.gold, C.purple, C.orange, C.blue, C.green, C.grey].slice(0, n);
}

function lineChart(spec) {
  const W = 720, H = 250, pad = { t: 14, r: 16, b: 34, l: 56 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const all = spec.series.flatMap(s => s.values.filter(v => v != null));
  const max = Math.max(...all, 1), min = Math.min(0, ...all);
  const x = i => pad.l + (iw * i) / Math.max(spec.labels.length - 1, 1);
  const y = v => pad.t + ih - (ih * (v - min)) / (max - min || 1);
  let g = '';
  for (let i = 0; i <= 4; i++) {
    const v = min + (max - min) * i / 4, yy = y(v);
    g += `<line x1="${pad.l}" y1="${yy}" x2="${W - pad.r}" y2="${yy}" stroke="#EAF0F6" stroke-width="1"/>
          <text x="${pad.l - 8}" y="${yy + 4}" text-anchor="end" font-size="10" fill="#8fa3b5">${compact(v)}</text>`;
  }
  spec.labels.forEach((l, i) => {
    g += `<text x="${x(i)}" y="${H - 12}" text-anchor="middle" font-size="10.5" fill="#61798F">${esc(l)}</text>`;
  });
  spec.series.forEach(s => {
    const pts = s.values.map((v, i) => v == null ? null : [x(i), y(v)]).filter(Boolean);
    if (!pts.length) return;
    const d = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
    const area = d + ` L${pts[pts.length - 1][0]},${pad.t + ih} L${pts[0][0]},${pad.t + ih} Z`;
    g += `<path d="${area}" fill="${s.color}" opacity=".08"/>
          <path d="${d}" fill="none" stroke="${s.color}" stroke-width="2.4" stroke-linejoin="round"/>`;
    pts.forEach((p, i) => {
      g += `<circle cx="${p[0]}" cy="${p[1]}" r="3.6" fill="#fff" stroke="${s.color}" stroke-width="2.2">
        <title>${esc(spec.labels[i])}: ${nf(s.values[i], spec.decimals || 0)}</title></circle>`;
    });
  });
  return `<svg viewBox="0 0 ${W} ${H}" role="img">${g}</svg>`;
}

function barChart(spec) {
  const horiz = !!spec.horizontal;
  const n = spec.labels.length;
  if (horiz) {
    const W = 720, rowH = 27, labelW = 84, pad = { t: 8, b: 10 };
    const H = pad.t + pad.b + n * rowH;
    const x0 = W - labelW;                     // مبدأ = ۰
    const maxBarW = x0 - 72;                   // جای برچسب عدد در ابتدای نوار
    const vals = spec.series[0].values.map(v => v || 0);
    const max = Math.max(...vals.map(Math.abs), 1);
    let g = `<line x1="${x0}" y1="${pad.t}" x2="${x0}" y2="${H - pad.b}" stroke="#DDE7F1" stroke-width="1"/>`;
    spec.labels.forEach((lb, i) => {
      const v = vals[i], yy = pad.t + i * rowH + 5, bh = rowH - 13;
      const w = maxBarW * Math.abs(v) / max;
      const col = spec.series[0].colors_by_sign ? (v < 0 ? C.red : C.green) : (spec.series[0].color || C.navy);
      g += `<text x="${W - 4}" y="${yy + bh - 3}" text-anchor="end" font-size="10.5" fill="#16283A">${esc(lb)}</text>
            <rect x="${x0 - w}" y="${yy}" width="${Math.max(w, 1.5)}" height="${bh}" rx="3.5" fill="${col}">
              <title>${esc(lb)}: ${nf(v, spec.decimals || 0)}</title></rect>
            <text x="${Math.max(x0 - w - 7, 3)}" y="${yy + bh - 3}" text-anchor="end" font-size="10" fill="#61798F">${compact(v)}</text>`;
    });
    return `<svg viewBox="0 0 ${W} ${H}" role="img">${g}</svg>`;
  }
  // عمودی (گروهی)
  const W = 720, H = 260, pad = { t: 14, r: 14, b: 42, l: 60 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const all = spec.series.flatMap(s => s.values.filter(v => v != null));
  const max = Math.max(...all, 1), min = Math.min(0, ...all);
  const y = v => pad.t + ih - (ih * (v - min)) / (max - min || 1);
  const bandW = iw / n, ns = spec.series.length;
  const bw = Math.min(30, bandW * 0.62 / ns);
  let g = '';
  for (let i = 0; i <= 4; i++) {
    const v = min + (max - min) * i / 4, yy = y(v);
    g += `<line x1="${pad.l}" y1="${yy}" x2="${W - pad.r}" y2="${yy}" stroke="#EAF0F6"/>
          <text x="${pad.l - 8}" y="${yy + 4}" text-anchor="end" font-size="10" fill="#8fa3b5">${compact(v)}</text>`;
  }
  spec.labels.forEach((lb, i) => {
    const cx = pad.l + bandW * i + bandW / 2;
    g += `<text x="${cx}" y="${H - 16}" text-anchor="middle" font-size="10.5" fill="#61798F">${esc(lb)}</text>`;
    spec.series.forEach((s, si) => {
      const v = s.values[i];
      if (v == null) return;
      const xx = cx - (bw * ns) / 2 + si * bw;
      const y0 = y(0), y1 = y(v);
      const hh = Math.abs(y1 - y0);
      const col = s.colors_by_sign ? (v < 0 ? C.red : C.green) : s.color;
      g += `<rect x="${xx}" y="${Math.min(y0, y1)}" width="${bw - 3}" height="${Math.max(hh, 1)}" rx="3" fill="${col}">
              <title>${esc(lb)} — ${esc(s.name)}: ${nf(v, spec.decimals || 0)}</title></rect>`;
    });
  });
  return `<svg viewBox="0 0 ${W} ${H}" role="img">${g}</svg>`;
}

function donutChart(spec) {
  const vals = spec.series[0].values.map(v => v || 0);
  const tot = vals.reduce((a, b) => a + b, 0) || 1;
  const cols = donutColors(vals.length);
  const cx = 150, cy = 118, r = 84, ri = 50;
  let a0 = -Math.PI / 2, g = '';
  vals.forEach((v, i) => {
    const a1 = a0 + (v / tot) * Math.PI * 2;
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const p = (rad, ang) => [cx + rad * Math.cos(ang), cy + rad * Math.sin(ang)];
    const [x0, y0] = p(r, a0), [x1, y1] = p(r, a1), [x2, y2] = p(ri, a1), [x3, y3] = p(ri, a0);
    g += `<path d="M${x0},${y0} A${r},${r} 0 ${large} 1 ${x1},${y1} L${x2},${y2} A${ri},${ri} 0 ${large} 0 ${x3},${y3} Z"
            fill="${cols[i]}"><title>${esc(spec.labels[i])}: ${nf(v, 0)}</title></path>`;
    a0 = a1;
  });
  g += `<text x="${cx}" y="${cy - 4}" text-anchor="middle" font-size="20" font-weight="700" fill="#0E2A47">${nf(tot)}</text>
        <text x="${cx}" y="${cy + 16}" text-anchor="middle" font-size="11" fill="#61798F">${esc(spec.unit || '')}</text>`;
  let yy = 34;
  spec.labels.forEach((l, i) => {
    g += `<text x="290" y="${yy}" font-size="11.5" fill="#16283A">${esc(l)}</text>
          <text x="430" y="${yy}" font-size="11" fill="#61798F">${fa((vals[i] / tot * 100).toFixed(1))}٪ · ${nf(vals[i], 0)}</text>`;
    yy += 24;
  });
  return `<svg viewBox="0 0 480 240" role="img">${g}</svg>`;
}

/* ───────────────────────── تحلیل هوش مصنوعی */
function aiPanel(data) {
  const p = el('div', 'panel');
  p.id = 'aiPanel';
  const h = state.ai || {};
  const online = !!h.online;
  p.innerHTML = `
    <div class="ai-head">
      <h3>تحلیل هوشمند این صفحه</h3>
      <select id="aiModel" class="btn" style="padding:6px 10px">
        <option value="">مدل تحلیل (پیش‌فرض)</option>
        <option value="${esc(h.configured?.chat || 'qwen3.5:4b')}">${esc(h.configured?.chat || 'qwen3.5:4b')} — سریع</option>
        <option value="${esc(h.configured?.analysis || 'qwen3.5:9b')}">${esc(h.configured?.analysis || 'qwen3.5:9b')} — تحلیل</option>
        <option value="${esc(h.configured?.deep || 'gemma4:12b')}">${esc(h.configured?.deep || 'gemma4:12b')} — عمیق</option>
      </select>
      <button class="btn primary" id="aiRun">تولید تحلیل</button>
      <span class="ai-meta" id="aiTimer"></span>
    </div>
    <div id="aiBanner">${online
      ? `<div class="banner ok">متصل به Ollama روی <b>${esc(h.host)}</b> — تحلیل از روی اعداد همین صفحه و بدون تماس با اینترنت تولید می‌شود.</div>`
      : `<div class="banner warn"><b>Ollama در دسترس نیست</b> (${esc(h.host)}). داشبورد و همهٔ شاخص‌ها کار می‌کنند؛ با کلیک روی «تولید تحلیل» یک تحلیل قاعده‌محور (بدون مدل زبانی) نمایش داده می‌شود.</div>`}</div>
    <div id="aiBody" class="ai-body"><div class="sub">برای دیدن تحلیل، دکمهٔ «تولید تحلیل» را بزنید. روی CPU ممکن است تا چند دقیقه طول بکشد؛ نتیجه ذخیره می‌شود.</div></div>`;
  setTimeout(() => {
    const b = p.querySelector('#aiRun');
    if (b) b.onclick = runAI;
  }, 0);
  return p;
}

async function runAI() {
  const btn = document.querySelector('#aiRun');
  const body = document.querySelector('#aiBody');
  const timer = document.querySelector('#aiTimer');
  const model = document.querySelector('#aiModel')?.value || null;
  btn.disabled = true; btn.innerHTML = 'در حال تولید<span class="spin"></span>';
  body.innerHTML = `<div class="skel w90"></div><div class="skel w75"></div><div class="skel w90"></div><div class="skel w60"></div>`;
  const t0 = Date.now();
  const iv = setInterval(() => timer.textContent = fa(Math.floor((Date.now() - t0) / 1000)) + ' ثانیه', 500);
  try {
    const r = await fetch('/api/ai/analyze', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page: state.page, branch: state.branch, year: state.year, period: state.period, model, force: true })
    });
    const res = await r.json();
    renderAIResult(res);
  } catch (e) {
    body.innerHTML = `<div class="banner err">خطا در ارتباط با سرور: ${esc(e.message)}</div>`;
  } finally {
    clearInterval(iv); timer.textContent = '';
    btn.disabled = false; btn.textContent = 'تحلیل مجدد';
  }
}

function renderAIResult(res) {
  const body = document.querySelector('#aiBody');
  const banner = document.querySelector('#aiBanner');
  const p = res.payload || {};
  const v = res.validation || {};
  if (res.source === 'rules') {
    banner.innerHTML = `<div class="banner warn"><b>تحلیل قاعده‌محور</b> — مدل زبانی در دسترس نبود، بنابراین این متن از قواعد قطعی و اعداد همین صفحه ساخته شده است. ${res.error ? '<span style="opacity:.7;font-size:11px">(' + esc(res.error) + ')</span>' : ''}</div>`;
  } else {
    banner.innerHTML = `<div class="banner ok">تحلیل با مدل <b>${esc(res.model)}</b> تولید شد${res.cached ? ' (از حافظهٔ کش)' : ''}.</div>`;
  }
  let html = '';
  if (p.headline) html += `<div class="headline">${esc(p.headline)}</div>`;
  if (p.findings?.length) {
    html += `<div class="ai-sec"><h4>یافته‌ها</h4><ul>` +
      p.findings.map(f => `<li class="${esc(f.direction || 'flat')}">${f.kpi ? `<span class="chip">${esc(f.kpi)}</span>` : ''}${esc(f.text)}</li>`).join('') + `</ul></div>`;
  }
  if (p.drivers?.length) html += `<div class="ai-sec"><h4>عوامل هم‌روند</h4><ul>${p.drivers.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
  if (p.risks?.length) html += `<div class="ai-sec"><h4>ریسک‌ها</h4><ul>${p.risks.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
  if (p.actions?.length) html += `<div class="ai-sec"><h4>اقدام پیشنهادی</h4><ul>${p.actions.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
  if (p.data_gaps?.length) html += `<div class="ai-sec"><h4>دادهٔ ناقص</h4><ul>${p.data_gaps.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
  if (!html) html = `<div class="banner warn">پاسخی برای نمایش وجود ندارد.</div>`;
  const unknown = v.unknown || [];
  html += `<div class="trust">
      <span>مدل: ${esc(res.model || '—')}</span>
      <span>زمان: ${esc((res.created || '').replace('T', ' '))}</span>
      <span>اعداد بررسی‌شده: ${fa(v.checked || 0)}</span>
      ${unknown.length ? `<span style="color:#C0392B">عدد تأییدنشده: ${esc(unknown.join('، '))}</span>`
      : `<span style="color:#1E8E5A">همهٔ اعداد با بستهٔ واقعیت مطابق است</span>`}
    </div>`;
  body.innerHTML = html;
}

/* ───────────────────────── صفحهٔ داده */
function renderDataPage(c, data) {
  const dl = el('div', 'panel');
  dl.innerHTML = `<h3>قالب‌های ورود داده</h3><div class="sub">قالب را دانلود کنید، پر کنید و در همین صفحه بارگذاری کنید. ترتیب ردیف‌ها ثابت است تا کپی-پیست بازه‌ای کار کند.</div>
    <div class="tpl-grid">${Object.entries(state.meta?.templates || {}).map(([k, v]) =>
    `<div class="tpl"><b>${esc(v)}</b><a href="/api/template/${k}?year=${state.year}&period=${state.period}" download>دانلود</a></div>`).join('')}</div>`;
  c.appendChild(dl);

  const up = el('div', 'panel');
  up.innerHTML = `<h3>بارگذاری فایل اکسل</h3><div class="sub">ستون‌های موردانتظار: شعبه، سال، دوره، کد قلم، عنوان، ماه، مقدار، سناریو</div>
    <div class="drop" id="drop"><p style="font-size:15px;color:#0E2A47">فایل اکسل را اینجا رها کنید</p><p>یا برای انتخاب کلیک کنید — فقط قالب .xlsx</p><input type="file" id="file" accept=".xlsx" class="hidden"></div>
    <div id="impRes"></div>`;
  c.appendChild(up);

  const ex = el('div', 'panel');
  ex.style.marginTop = '16px';
  ex.innerHTML = `<h3>خروجی</h3><div class="sub">جدول کامل شاخص‌ها برای پیوست گزارش</div>
    <a class="btn" href="/api/export/kpi.xlsx?year=${state.year}&period=${state.period}" download>دریافت فایل اکسل شاخص‌ها</a>`;
  c.appendChild(ex);

  setTimeout(() => bindDrop(), 0);
}

async function bindDrop() {
  const drop = document.querySelector('#drop'), file = document.querySelector('#file');
  if (!drop) return;
  drop.onclick = () => file.click();
  drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
  drop.ondragleave = () => drop.classList.remove('over');
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); };
  file.onchange = () => { if (file.files[0]) upload(file.files[0]); };
}

async function upload(f) {
  const res = document.querySelector('#impRes');
  res.innerHTML = `<div class="skel w75"></div><div class="skel w60"></div>`;
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await fetch('/api/data/import', { method: 'POST', body: fd });
    const j = await r.json();
    if (!r.ok) {
      res.innerHTML = `<div class="banner err"><b>فایل پذیرفته نشد</b> — ${fa(j.error_count || (j.detail ? 1 : 0))} خطا<br>
        <ul style="margin:6px 0 0;padding-right:18px">${(j.errors || [{ msg: j.detail }]).slice(0, 8).map(e => `<li>ردیف ${fa(e.row || '?')}: ${esc(e.msg)}</li>`).join('')}</ul></div>`;
      return;
    }
    res.innerHTML = `<div class="banner ok"><b>ثبت شد</b> — ${fa(j.accepted)} ردیف پذیرفته شد، نسخهٔ دادهٔ ${fa(j.version)} ساخته شد و شاخص‌ها بازمحاسبه شدند.</div>`;
    toast('داده با موفقیت ثبت شد');
    setTimeout(load, 1200);
  } catch (e) {
    res.innerHTML = `<div class="banner err">خطا: ${esc(e.message)}</div>`;
  }
}

boot();
