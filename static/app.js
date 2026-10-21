'use strict';

// Ponte com o app Android (só existe dentro do APK).
const NATIVE = window.PControlApp || null;

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const SVG_NS = 'http://www.w3.org/2000/svg';

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

function icon(name, cls = '') {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', `i ${cls}`);
  const use = document.createElementNS(SVG_NS, 'use');
  use.setAttribute('href', `#i-${name}`);
  svg.append(use);
  return svg;
}

const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem(`pc.${key}`); return v == null ? fallback : JSON.parse(v); } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(`pc.${key}`, JSON.stringify(value)); } catch { /* sem armazenamento */ }
  },
};

function fmtBytes(n) {
  if (n == null) return '';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1).replace('.', ',')} ${units[i]}`;
}

function fmtDuration(sec) {
  const d = Math.floor(sec / 86400), hrs = Math.floor(sec % 86400 / 3600), m = Math.floor(sec % 3600 / 60);
  if (d) return `${d}d ${hrs}h`;
  if (hrs) return `${hrs}h ${m}min`;
  return `${m}min`;
}

function vibrate(ms = 12) { try { navigator.vibrate?.(ms); } catch { /* sem vibração */ } }

// --- API ---------------------------------------------------------------

async function api(path, { method = 'GET', body } = {}) {
  const opts = { method, headers: {}, credentials: 'same-origin' };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new Error('Sem conexão com o PC.');
  }
  if (res.status === 401) {
    showLogin();
    throw new Error('Entre de novo.');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Erro ${res.status}`);
  return data;
}
const post = (path, body = {}) => api(path, { method: 'POST', body });

// --- toast, folhas e páginas ---------------------------------------------

let toastTimer = 0;
function toast(msg, kind = '') {
  const el = $('#toast');
  el.textContent = msg;
  el.className = `toast show ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = 'toast'; }, 2600);
}

async function attempt(fn, okMsg) {
  try {
    const result = await fn();
    if (okMsg) toast(okMsg);
    return result;
  } catch (err) {
    toast(err.message, 'err');
    return undefined;
  }
}

function sheet({ title, message, actions = [], input = null, extra = null }) {
  return new Promise(resolve => {
    const root = $('#sheet');
    root.innerHTML = '';
    const panel = h('div', { class: 'sheet-panel' });
    let field = null;
    const close = value => {
      root.classList.remove('open');
      setTimeout(() => { root.hidden = true; root.innerHTML = ''; }, 200);
      resolve(value);
    };
    if (title) panel.append(h('div', { class: 'sheet-title', text: title }));
    if (message) panel.append(h('div', { class: 'sheet-msg', text: message }));
    if (extra) panel.append(extra);
    if (input) {
      field = h('input', { class: 'field', value: input.value || '', placeholder: input.placeholder || '', enterkeyhint: 'done' });
      field.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); close(field.value); } });
      panel.append(field);
    }
    for (const a of actions) {
      const cls = `sheet-btn${a.danger ? ' danger' : ''}${a.primary ? ' primary' : ''}`;
      panel.append(h('button', { class: cls, onclick: () => close(input ? field.value : a.id) },
        a.icon ? icon(a.icon) : null, a.label));
    }
    panel.append(h('button', { class: 'sheet-btn cancel', onclick: () => close(null) }, 'Cancelar'));
    root.append(h('div', { class: 'sheet-backdrop', onclick: () => close(null) }), panel);
    root.hidden = false;
    requestAnimationFrame(() => root.classList.add('open'));
    if (field) setTimeout(() => { field.focus(); field.select(); }, 80);
  });
}

const confirmSheet = (title, message, label, danger = true) =>
  sheet({ title, message, actions: [{ id: 'ok', label, danger, primary: !danger }] }).then(v => v === 'ok');

const promptSheet = (title, value = '', placeholder = '', okLabel = 'Salvar') =>
  sheet({ title, input: { value, placeholder }, actions: [{ id: 'ok', label: okLabel, primary: true }] });

function openPage(title, { center = false, onClose } = {}) {
  const body = h('div', { class: `page-body${center ? ' center' : ''}` });
  const page = h('div', { class: 'page' },
    h('div', { class: 'page-head' },
      h('h2', { text: title }),
      h('button', { class: 'icon-btn', 'aria-label': 'Fechar', onclick: () => close() }, icon('x'))),
    body);
  const close = () => { page.remove(); onClose?.(); };
  document.body.append(page);
  return { body, close, page };
}

// --- login e inicialização -------------------------------------------------

let loggedIn = false;
let info = null;

function showLogin(errorMsg) {
  loggedIn = false;
  Conn.close();
  $('#app').hidden = true;
  $('#login').hidden = false;
  $('#login-error').hidden = !errorMsg;
  $('#login-error').textContent = errorMsg || '';
  $('#login-native-settings').hidden = !NATIVE;
  setTimeout(() => $('#login-pass').focus(), 100);
}

$('#login-form').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = $('#login-form button[type=submit]');
  btn.disabled = true;
  try {
    const headers = { 'Content-Type': 'application/json' };
    if (NATIVE) headers['X-PControl-App'] = '1';
    const res = await fetch('/api/login', {
      method: 'POST', headers, credentials: 'same-origin',
      body: JSON.stringify({ password: $('#login-pass').value }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'Não deu para entrar.');
    if (NATIVE && data.token) NATIVE.saveToken(data.token);
    $('#login-pass').value = '';
    await start();
  } catch (err) {
    $('#login-error').hidden = false;
    $('#login-error').textContent = err.message === 'Failed to fetch' ? 'Sem conexão com o PC.' : err.message;
  } finally {
    btn.disabled = false;
  }
});

$('#login-native-settings').addEventListener('click', () => NATIVE?.openSettings());
$('#native-settings').addEventListener('click', () => NATIVE?.openSettings());

async function start() {
  try {
    info = await api('/api/info');
  } catch (err) {
    if (!loggedIn && $('#login').hidden) showLogin();
    return;
  }
  loggedIn = true;
  $('#login').hidden = true;
  $('#app').hidden = false;
  $('#native-settings').hidden = !NATIVE;
  $('#host-name').textContent = info.host;
  document.title = `PControl · ${info.host}`;
  $('#conn-via').textContent = { lan: 'Wi-Fi', tailscale: 'Tailscale', local: 'Neste PC' }[info.via] || '';
  NATIVE?.connected?.(JSON.stringify({ lan: info.lan, tailscale: info.tailscale, host: info.host }));
  Conn.connect();
  showTab(store.get('tab', 'screen'));
}

// --- conexão em tempo real (WebSocket) -------------------------------------

const Conn = {
  ws: null,
  open: false,
  retry: 0,
  timer: 0,
  connect() {
    if (this.ws || !loggedIn) return;
    clearTimeout(this.timer);
    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
    ws.binaryType = 'blob';
    this.ws = ws;
    ws.onopen = () => {
      this.open = true;
      this.retry = 0;
      $('#conn-dot').className = 'dot online';
    };
    ws.onmessage = e => {
      if (typeof e.data === 'string') Screen.onMessage(JSON.parse(e.data));
      else Screen.onFrame(e.data);
    };
    ws.onclose = () => {
      this.ws = null;
      this.open = false;
      $('#conn-dot').className = 'dot offline';
      Screen.onClose();
      if (!loggedIn) return;
      const delay = Math.min(800 * 2 ** this.retry, 8000);
      this.retry++;
      this.timer = setTimeout(() => this.check(), delay);
    };
  },
  fails: 0,
  async check() {
    try {
      await api('/api/info');
      this.fails = 0;
      this.connect();
    } catch {
      // No app, se o caminho atual caiu (saiu do Wi-Fi, por exemplo), ele tenta o outro.
      if (++this.fails >= 2) NATIVE?.reconnect?.();
      if (loggedIn) this.timer = setTimeout(() => this.check(), 3000);
    }
  },
  send(msg) {
    if (this.open) this.ws.send(JSON.stringify(msg));
  },
  close() {
    clearTimeout(this.timer);
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
      this.open = false;
    }
  },
};

document.addEventListener('visibilitychange', () => {
  if (document.hidden || !loggedIn) return;
  if (!Conn.ws) { Conn.retry = 0; Conn.check(); }
  Screen.requestFrame();
});

// --- abas ------------------------------------------------------------------

let currentTab = null;
function showTab(name) {
  if (!Tabs[name]) name = 'screen';
  if (currentTab && currentTab !== name) Tabs[currentTab].hide?.();
  currentTab = name;
  for (const tab of $$('.tab')) tab.hidden = tab.dataset.tab !== name;
  for (const btn of $$('.tabbar button')) btn.classList.toggle('active', btn.dataset.tab === name);
  store.set('tab', name);
  Tabs[name].show?.();
}
for (const btn of $$('.tabbar button')) btn.addEventListener('click', () => showTab(btn.dataset.tab));

// --- Tela --------------------------------------------------------------------

const QUALITY = {
  baixa: { label: 'Econômica', scale: 0.4, quality: 40 },
  media: { label: 'Normal', scale: 0.6, quality: 55 },
  alta: { label: 'Alta', scale: 0.8, quality: 68 },
  max: { label: 'Máxima', scale: 1, quality: 80 },
};
const ZOOMS = [1, 1.5, 2, 3, 4];

const Screen = (() => {
  const viewport = $('#viewport');
  const img = $('#screen-img');
  const cursorEl = $('#cursor');
  const statusEl = $('#screen-status');
  const hintEl = $('#gesture-hint');
  const settings = Object.assign({ quality: 'media', fps: 15, sens: 2, mode: 'touchpad', monitor: 0 }, store.get('screen', {}));

  let monitors = [];
  let natural = { w: 16, h: 9 };
  let base = { w: 0, h: 0 };
  let cursor = { x: 0.5, y: 0.5 };
  let zoomIdx = 0;
  let tx = 0, ty = 0;
  let freezePan = false;
  let active = false;
  let inflight = false, inflightAt = 0;
  let prevUrl = null;
  let frames = 0, bytes = 0, lastFps = 0;
  let holding = false;

  const save = () => store.set('screen', settings);
  const zoom = () => ZOOMS[zoomIdx];

  function sendConfig() {
    const q = QUALITY[settings.quality] || QUALITY.media;
    Conn.send({ t: 'cfg', monitor: settings.monitor, scale: q.scale, quality: q.quality, fps: settings.fps });
  }

  function layout() {
    const vw = viewport.clientWidth, vh = viewport.clientHeight;
    if (!vw || !vh) return;
    const ratio = natural.w / natural.h;
    let bw = vw, bh = vw / ratio;
    if (bh > vh) { bh = vh; bw = vh * ratio; }
    base = { w: bw, h: bh };
    img.style.width = `${bw}px`;
    img.style.height = `${bh}px`;
    place(true);
  }

  // Posiciona a imagem; com zoom, a vista acompanha o cursor quando ele chega perto da borda.
  function place(follow) {
    const vw = viewport.clientWidth, vh = viewport.clientHeight;
    const z = zoom();
    const sw = base.w * z, sh = base.h * z;
    if (follow && !freezePan && z > 1) {
      const cx = tx + cursor.x * sw, cy = ty + cursor.y * sh;
      const mx = vw * 0.22, my = vh * 0.22;
      if (cx < mx) tx += mx - cx; else if (cx > vw - mx) tx -= cx - (vw - mx);
      if (cy < my) ty += my - cy; else if (cy > vh - my) ty -= cy - (vh - my);
    }
    tx = sw <= vw ? (vw - sw) / 2 : clamp(tx, vw - sw, 0);
    ty = sh <= vh ? (vh - sh) / 2 : clamp(ty, vh - sh, 0);
    img.style.transform = `translate(${tx}px, ${ty}px) scale(${z})`;
    const visible = cursor.x >= 0 && cursor.x <= 1 && cursor.y >= 0 && cursor.y <= 1;
    cursorEl.style.display = visible ? '' : 'none';
    cursorEl.style.transform = `translate(${tx + cursor.x * sw}px, ${ty + cursor.y * sh}px)`;
  }

  function setZoom(idx) {
    zoomIdx = clamp(idx, 0, ZOOMS.length - 1);
    const z = zoom();
    const vw = viewport.clientWidth, vh = viewport.clientHeight;
    tx = vw / 2 - cursor.x * base.w * z;
    ty = vh / 2 - cursor.y * base.h * z;
    $('#zoom-label').textContent = `${z}x`.replace('.', ',');
    place(false);
  }

  function setStatus(text) {
    statusEl.textContent = text || '';
    statusEl.hidden = !text;
  }

  function requestFrame() {
    if (!active || document.hidden || !Conn.open || inflight) return;
    inflight = true;
    inflightAt = performance.now();
    Conn.send({ t: 'frame' });
  }

  setInterval(() => {
    // Se um quadro se perdeu, pede de novo.
    if (inflight && performance.now() - inflightAt > 8000) { inflight = false; requestFrame(); }
    if (active) {
      const now = performance.now();
      const secs = (now - lastFps) / 1000 || 1;
      $('#fps').textContent = frames ? `${Math.round(frames / secs)} fps` : '';
      $('#fps').title = frames ? `${fmtBytes(bytes / frames)} por quadro` : '';
      frames = 0; bytes = 0; lastFps = now;
    }
  }, 1000);

  function onFrame(blob) {
    frames++;
    bytes += blob.size;
    const url = URL.createObjectURL(blob);
    img.onload = () => {
      if (prevUrl) URL.revokeObjectURL(prevUrl);
      prevUrl = url;
      inflight = false;
      setStatus('');
      requestFrame();
    };
    img.onerror = () => { URL.revokeObjectURL(url); inflight = false; requestFrame(); };
    img.src = url;
  }

  function onMessage(msg) {
    if (msg.t === 'hello') {
      monitors = msg.monitors || [];
      settings.monitor = clamp(settings.monitor, 0, Math.max(monitors.length - 1, 0));
      const mon = monitors[settings.monitor];
      if (mon) natural = { w: mon.width, h: mon.height };
      sendConfig();
      layout();
      inflight = false;
      if (!prevUrl) setStatus('Carregando a tela…');
      requestFrame();
    } else if (msg.t === 'cursor') {
      cursor = { x: msg.x, y: msg.y };
      place(true);
    } else if (msg.t === 'status' && msg.msg === 'unavailable') {
      setStatus('O PC está na tela de bloqueio ou num aviso do Windows. Não dá para ver a tela agora.');
    }
  }

  function onClose() {
    inflight = false;
    setStatus(loggedIn ? 'Reconectando…' : '');
  }

  // --- gestos ---

  const pointers = new Map();
  let g = null;
  let lastTap = 0;
  let moveAcc = { x: 0, y: 0 }, moveTo = null, scrollAcc = { x: 0, y: 0 }, raf = 0;

  function flush() {
    raf = 0;
    const mx = Math.trunc(moveAcc.x), my = Math.trunc(moveAcc.y);
    if (mx || my) {
      Conn.send({ t: 'move', dx: mx, dy: my });
      moveAcc.x -= mx; moveAcc.y -= my;
    }
    if (moveTo) { Conn.send({ t: 'moveto', x: moveTo.x, y: moveTo.y }); moveTo = null; }
    const sy = Math.trunc(scrollAcc.y * 4), sx = Math.trunc(-scrollAcc.x * 4);
    if (sy || sx) {
      Conn.send({ t: 'scroll', dy: sy, dx: sx });
      scrollAcc.y -= sy / 4; scrollAcc.x += sx / 4;
    }
  }
  const schedule = () => { if (!raf) raf = requestAnimationFrame(flush); };
  function button(b, a) {
    if (raf) { cancelAnimationFrame(raf); flush(); }
    Conn.send({ t: 'btn', b, a });
  }

  function toScreen(x, y) {
    const r = img.getBoundingClientRect();
    if (!r.width) return { x: 0.5, y: 0.5 };
    return { x: clamp((x - r.left) / r.width, 0, 1), y: clamp((y - r.top) / r.height, 0, 1) };
  }

  function hint(text) {
    hintEl.textContent = text;
    hintEl.hidden = false;
    clearTimeout(hint.t);
    hint.t = setTimeout(() => { hintEl.hidden = true; }, 900);
  }

  viewport.addEventListener('contextmenu', e => e.preventDefault());

  viewport.addEventListener('pointerdown', e => {
    e.preventDefault();
    if (e.pointerType === 'mouse' && e.button === 2) {
      Conn.send({ t: 'moveto', ...toScreen(e.clientX, e.clientY) });
      button('right', 'click');
      return;
    }
    try { viewport.setPointerCapture(e.pointerId); } catch { /* ok */ }
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY, t: performance.now() });
    const now = performance.now();
    if (pointers.size === 1) {
      g = { start: now, sx: e.clientX, sy: e.clientY, max: 1, moved: false, dragging: false, consumed: false, scrolled: 0, longTimer: 0 };
      if (settings.mode === 'touchpad') {
        g.tapDrag = now - lastTap < 320;
      } else {
        freezePan = true;
        g.longTimer = setTimeout(() => {
          if (g && !g.moved && pointers.size === 1) {
            g.consumed = true;
            Conn.send({ t: 'moveto', ...toScreen(g.sx, g.sy) });
            button('right', 'click');
            vibrate(25);
            hint('Clique direito');
          }
        }, 550);
      }
    } else if (g) {
      g.max = Math.max(g.max, pointers.size);
      clearTimeout(g.longTimer);
      if (g.dragging) { button('left', 'up'); g.dragging = false; }
    }
  });

  viewport.addEventListener('pointermove', e => {
    const p = pointers.get(e.pointerId);
    if (!p || !g) return;
    const now = performance.now();
    const dx = e.clientX - p.x, dy = e.clientY - p.y;
    const dt = Math.max(1, now - p.t);
    p.x = e.clientX; p.y = e.clientY; p.t = now;

    if (pointers.size === 1 && g.max === 1) {
      if (!g.moved && Math.hypot(e.clientX - g.sx, e.clientY - g.sy) > 7) {
        g.moved = true;
        clearTimeout(g.longTimer);
      }
      if (!g.moved) return;
      if (settings.mode === 'touchpad') {
        if (g.tapDrag && !g.dragging) { g.dragging = true; button('left', 'down'); hint('Arrastando'); }
        const speed = Math.hypot(dx, dy) / dt;
        const gain = settings.sens * (1 + Math.min(speed, 2.5) * 1.1);
        moveAcc.x += dx * gain;
        moveAcc.y += dy * gain;
      } else {
        if (g.consumed) return;
        if (!g.dragging) {
          g.dragging = true;
          Conn.send({ t: 'moveto', ...toScreen(g.sx, g.sy) });
          button('left', 'down');
        }
        moveTo = toScreen(e.clientX, e.clientY);
      }
      schedule();
    } else if (pointers.size >= 2) {
      const n = pointers.size;
      scrollAcc.x += dx / n;
      scrollAcc.y += dy / n;
      g.scrolled += Math.hypot(dx, dy) / n;
      schedule();
    }
  });

  function endPointer(e) {
    if (!pointers.delete(e.pointerId) || pointers.size > 0 || !g) return;
    clearTimeout(g.longTimer);
    const dur = performance.now() - g.start;
    if (g.max === 1) {
      if (g.dragging) {
        button('left', 'up');
        lastTap = 0;
      } else if (!g.moved && !g.consumed && e.type === 'pointerup') {
        if (settings.mode === 'touchpad') {
          if (dur < 320) { button('left', 'click'); lastTap = performance.now(); }
        } else {
          Conn.send({ t: 'moveto', ...toScreen(g.sx, g.sy) });
          button('left', 'click');
        }
      }
    } else if (g.scrolled < 12 && dur < 400) {
      button(g.max === 2 ? 'right' : 'middle', 'click');
      hint(g.max === 2 ? 'Clique direito' : 'Clique do meio');
    }
    g = null;
    freezePan = false;
    place(true);
  }
  viewport.addEventListener('pointerup', endPointer);
  viewport.addEventListener('pointercancel', endPointer);

  viewport.addEventListener('wheel', e => {
    e.preventDefault();
    const factor = e.deltaMode === 1 ? 40 : 1;
    Conn.send({ t: 'scroll', dy: Math.round(-e.deltaY * factor * 1.2), dx: Math.round(e.deltaX * factor * 1.2) });
  }, { passive: false });

  new ResizeObserver(() => layout()).observe(viewport);

  // --- barra de cima ---

  function renderMode() {
    const tp = settings.mode === 'touchpad';
    const btn = $('#mode-btn');
    btn.replaceChildren(icon(tp ? 'touchpad' : 'hand'), h('span', { text: tp ? 'Touchpad' : 'Toque direto' }));
  }
  renderMode();

  $('#mode-btn').addEventListener('click', () => {
    settings.mode = settings.mode === 'touchpad' ? 'direct' : 'touchpad';
    save();
    renderMode();
    toast(settings.mode === 'touchpad'
      ? 'Touchpad: arraste para mover, toque para clicar, 2 dedos rolam.'
      : 'Toque direto: toque onde quer clicar. Segure para clique direito.');
  });
  $('#zoom-in').addEventListener('click', () => setZoom(zoomIdx + 1));
  $('#zoom-out').addEventListener('click', () => setZoom(zoomIdx - 1));

  $('#screen-settings').addEventListener('click', () => {
    const extra = h('div');
    const group = (label, options, current, onPick) => {
      const row = h('div', { class: 'sheet-options' });
      for (const [value, text] of options) {
        const b = h('button', { class: value === current ? 'on' : '', text });
        b.addEventListener('click', () => {
          for (const x of row.children) x.classList.remove('on');
          b.classList.add('on');
          onPick(value);
        });
        row.append(b);
      }
      extra.append(h('div', { class: 'sheet-label', text: label }), row);
    };
    group('Qualidade da imagem', Object.entries(QUALITY).map(([k, v]) => [k, v.label]), settings.quality, v => { settings.quality = v; save(); sendConfig(); });
    group('Quadros por segundo', [[5, '5'], [10, '10'], [15, '15'], [24, '24'], [30, '30']], settings.fps, v => { settings.fps = v; save(); sendConfig(); });
    group('Velocidade do touchpad', [[1, 'Lenta'], [2, 'Normal'], [3, 'Rápida'], [4.5, 'Muito rápida']], settings.sens, v => { settings.sens = v; save(); });
    if (monitors.length > 1) {
      group('Monitor', monitors.map((m, i) => [i, `${i + 1}${m.primary ? ' (principal)' : ''}`]), settings.monitor, v => {
        settings.monitor = v; save();
        natural = { w: monitors[v].width, h: monitors[v].height };
        sendConfig(); layout();
      });
    }
    extra.append(h('p', { class: 'sheet-msg', text: 'Fora de casa ou no 4G, use "Econômica" para ficar mais rápido.' }));
    sheet({ title: 'Imagem da tela', extra });
  });

  function setImmersive(on) {
    document.body.classList.toggle('immersive', on);
    $('#exit-immersive').hidden = !on;
    if (NATIVE?.setImmersive) NATIVE.setImmersive(on);
    else if (on) document.documentElement.requestFullscreen?.().catch(() => {});
    else if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
  }
  $('#immersive-btn').addEventListener('click', () => setImmersive(true));
  $('#exit-immersive').addEventListener('click', () => setImmersive(false));
  document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement && !NATIVE) setImmersive(false); });

  // --- botões do mouse ---

  for (const b of $$('.mouse-bar [data-btn]')) {
    b.addEventListener('click', () => { button(b.dataset.btn, 'click'); vibrate(); });
  }
  $('#hold-btn').addEventListener('click', () => {
    holding = !holding;
    $('#hold-btn').classList.toggle('on', holding);
    button('left', holding ? 'down' : 'up');
    vibrate();
  });

  // --- teclado ---

  const kin = $('#kbd-input');
  const SENTINEL = ' ';
  const mods = new Set();
  let kPrev = SENTINEL;
  let composing = false;

  function clearMods() {
    mods.clear();
    for (const m of $$('.key.mod')) m.classList.remove('on');
  }
  function pressKey(key) {
    Conn.send({ t: 'key', keys: [...mods, key] });
    clearMods();
    vibrate(8);
  }
  function resetInput() { kin.value = SENTINEL; kPrev = SENTINEL; }

  // Compara o texto do campo com o anterior e manda só a diferença (funciona com
  // corretor automático e teclados que montam a palavra inteira de uma vez).
  function syncInput() {
    const cur = Array.from(kin.value), prev = Array.from(kPrev);
    let i = 0;
    while (i < cur.length && i < prev.length && cur[i] === prev[i]) i++;
    const removed = prev.length - i;
    const added = cur.slice(i).join('');
    if (removed > 0) Conn.send({ t: 'key', keys: ['backspace'], n: removed });
    if (added) {
      if (mods.size && Array.from(added).length === 1) pressKey(added.toLowerCase());
      else Conn.send({ t: 'text', s: added });
    }
    kPrev = kin.value;
    if (!composing && (kin.value.length === 0 || kin.value.length > 40)) resetInput();
  }

  resetInput();
  kin.addEventListener('compositionstart', () => { composing = true; });
  kin.addEventListener('compositionend', () => { composing = false; syncInput(); });
  kin.addEventListener('input', syncInput);
  kin.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); syncInput(); pressKey('enter'); resetInput(); }
    else if (e.key === 'Tab') { e.preventDefault(); pressKey('tab'); }
    else if (e.key === 'Escape') { e.preventDefault(); pressKey('esc'); }
    else if (!composing && e.key && e.key.startsWith('Arrow')) { e.preventDefault(); pressKey(e.key.slice(5).toLowerCase()); }
  });

  for (const m of $$('.key.mod')) {
    m.addEventListener('click', () => {
      const k = m.dataset.mod;
      if (mods.has(k)) mods.delete(k); else mods.add(k);
      m.classList.toggle('on', mods.has(k));
    });
  }
  for (const k of $$('.key[data-key]')) k.addEventListener('click', () => pressKey(k.dataset.key));
  for (const k of $$('.key[data-combo]')) {
    k.addEventListener('click', () => { Conn.send({ t: 'key', keys: k.dataset.combo.split('+') }); clearMods(); vibrate(8); });
  }
  // Evita que os botões roubem o foco do campo (o teclado do celular fecharia).
  for (const k of $$('.kbd-panel .key')) k.addEventListener('pointerdown', e => e.preventDefault());

  $('#kbd-toggle').addEventListener('click', () => {
    const panel = $('#kbd-panel');
    panel.hidden = !panel.hidden;
    $('#kbd-toggle').classList.toggle('on', !panel.hidden);
    if (!panel.hidden) kin.focus();
  });

  return {
    show() { active = true; layout(); requestFrame(); },
    hide() { active = false; },
    onFrame, onMessage, onClose, requestFrame,
  };
})();

// --- Apps --------------------------------------------------------------------

const Apps = (() => {
  let data = null;
  let windowsTimer = 0;
  let editingFavs = false;

  const iconUrl = app => `/api/apps/icon?app=${encodeURIComponent(app.id)}`;
  const fileIconUrl = path => `/api/apps/icon?file=${encodeURIComponent(path)}`;

  function appIcon(src, name) {
    const box = h('div', { class: 'app-icon' });
    const img = h('img', { src, alt: '', loading: 'lazy', decoding: 'async' });
    img.addEventListener('error', () => box.replaceChildren(h('span', { class: 'letter', text: (name[0] || '?').toUpperCase() })));
    box.append(img);
    return box;
  }

  async function launch(body, name) {
    vibrate();
    await attempt(() => post('/api/apps/launch', body), `Abrindo ${name} no PC…`);
  }

  function tile(name, src, onClick) {
    return h('button', { class: 'app-tile', onclick: onClick }, appIcon(src, name), h('span', { class: 'app-name', text: name }));
  }

  function matches(name, q) {
    return !q || name.toLowerCase().normalize('NFD').replace(/\p{M}/gu, '').includes(q);
  }

  function render() {
    if (!data) return;
    const q = $('#apps-search').value.trim().toLowerCase().normalize('NFD').replace(/\p{M}/gu, '');

    const favs = data.favorites.filter(f => matches(f.name, q));
    $('#favorites-wrap').hidden = !favs.length;
    $('#favorites').classList.toggle('favorites-editing', editingFavs);
    $('#favorites').replaceChildren(...favs.map(f => tile(f.name, fileIconUrl(f.path), async () => {
      if (!editingFavs) return launch({ kind: 'file', path: f.path }, f.name);
      if (await confirmSheet(`Remover "${f.name}" dos favoritos?`, 'O arquivo continua no PC.', 'Remover')) {
        const res = await attempt(() => post('/api/apps/favorites', { action: 'remove', id: f.id }));
        if (res) { data.favorites = res.favorites; render(); }
      }
    })));

    const games = data.steam.filter(g => matches(g.name, q));
    $('#steam-wrap').hidden = !games.length;
    $('#steam').replaceChildren(...games.map(game => {
      const img = h('img', { src: `/api/apps/steam/${game.appid}/cover`, alt: '', loading: 'lazy' });
      img.addEventListener('error', () => img.remove());
      return h('button', { class: 'game', onclick: () => launch({ kind: 'steam', id: game.appid }, game.name) },
        img, h('span', { text: game.name }));
    }));

    const apps = data.apps.filter(a => matches(a.name, q));
    $('#apps').replaceChildren(...(apps.length
      ? apps.map(a => tile(a.name, iconUrl(a), () => launch({ kind: 'app', id: a.id }, a.name)))
      : [h('p', { class: 'muted pad', text: q ? 'Nada encontrado.' : 'Nenhum app encontrado.' })]));
  }

  async function load(refresh = false) {
    const res = await attempt(() => api(`/api/apps${refresh ? '?refresh=1' : ''}`));
    if (res) { data = res; render(); }
  }

  async function loadWindows() {
    let wins;
    try { wins = await api('/api/windows'); } catch { return; }
    const strip = $('#open-windows');
    $('#open-windows-wrap').hidden = !wins.length;
    strip.replaceChildren(...wins.map(w => {
      const label = w.process.replace(/\.exe$/i, '') || w.title;
      return h('button', { class: `win-chip${w.active ? ' active' : ''}`, onclick: () => windowMenu(w) },
        icon('window'), h('span', { text: w.title || label }));
    }));
  }

  async function windowMenu(w) {
    const choice = await sheet({
      title: w.title,
      message: w.process,
      actions: [
        { id: 'focus', label: 'Mostrar na tela', icon: 'eye' },
        { id: 'minimize', label: 'Minimizar', icon: 'minimize' },
        { id: 'close', label: 'Fechar janela', icon: 'x' },
        { id: 'kill', label: 'Forçar fechamento', icon: 'trash', danger: true },
      ],
    });
    if (!choice) return;
    if (choice === 'kill') {
      if (!await confirmSheet(`Forçar o fechamento de ${w.process}?`, 'O que não estiver salvo nele será perdido.', 'Forçar fechamento')) return;
      await attempt(() => post('/api/processes/kill', { pids: [w.pid] }), 'Processo encerrado.');
    } else {
      await attempt(() => post('/api/windows/action', { hwnd: w.hwnd, action: choice }));
    }
    setTimeout(loadWindows, 400);
  }

  $('#apps-search').addEventListener('input', render);
  $('#apps-refresh').addEventListener('click', () => { toast('Atualizando lista…'); load(true); loadWindows(); });
  $('#fav-edit').addEventListener('click', () => {
    editingFavs = !editingFavs;
    $('#fav-edit').textContent = editingFavs ? 'Pronto' : 'Editar';
    render();
  });

  return {
    show() {
      if (!data) load();
      loadWindows();
      clearInterval(windowsTimer);
      windowsTimer = setInterval(loadWindows, 4000);
    },
    hide() { clearInterval(windowsTimer); },
    async addFavorite(path, name) {
      const res = await attempt(() => post('/api/apps/favorites', { action: 'add', path, name }), `"${name}" fixado em Apps.`);
      if (res && data) { data.favorites = res.favorites; render(); }
    },
  };
})();

// --- YouTube -----------------------------------------------------------------

const YouTube = (() => {
  const results = $('#yt-results');
  const isLink = q => /(youtube\.com|youtu\.be)\//i.test(q);

  async function play(body, title) {
    vibrate();
    await attempt(() => post('/api/youtube/play', body), title ? `Tocando no PC: ${title}` : 'Abrindo no PC…');
  }

  function render(items) {
    if (!items.length) {
      results.replaceChildren(h('div', { class: 'empty' }, h('p', { text: 'Nenhum vídeo encontrado.' })));
      return;
    }
    results.replaceChildren(...items.map(v => {
      const meta = [v.channel, v.views, v.published].filter(Boolean).join(' · ');
      return h('button', { class: 'yt-item', onclick: () => play({ id: v.id }, v.title) },
        h('div', { class: 'yt-thumb' },
          h('img', { src: `https://i.ytimg.com/vi/${v.id}/mqdefault.jpg`, alt: '', loading: 'lazy' }),
          v.duration ? h('span', { class: 'dur', text: v.duration }) : null),
        h('div', {}, h('div', { class: 'yt-title', text: v.title }), h('div', { class: 'yt-meta', text: meta })));
    }));
    results.scrollTop = 0;
  }

  $('#yt-form').addEventListener('submit', async e => {
    e.preventDefault();
    const q = $('#yt-q').value.trim();
    if (!q) return;
    $('#yt-q').blur();
    if (isLink(q)) {
      await play({ url: q });
      return;
    }
    results.replaceChildren(h('div', { class: 'empty' }, h('p', { text: 'Buscando…' })));
    const res = await attempt(() => api(`/api/youtube/search?q=${encodeURIComponent(q)}`));
    if (!res) return;
    if (res.error) {
      results.replaceChildren(h('div', { class: 'empty' },
        h('p', { text: res.error }),
        h('button', { class: 'btn', text: 'Abrir a busca no PC', onclick: () => attempt(() => post('/api/open', { url: `https://www.youtube.com/results?search_query=${encodeURIComponent(q)}` }), 'Abrindo no PC…') })));
      return;
    }
    render(res.results);
  });

  for (const b of $$('.yt-remote [data-yt]')) {
    b.addEventListener('click', () => {
      vibrate(8);
      attempt(() => post('/api/key', { keys: b.dataset.yt.split('+') }));
    });
  }

  return {};
})();

// --- Controles ---------------------------------------------------------------

const Control = (() => {
  let statsTimer = 0;
  let volTimer = 0;
  let muted = false;

  function renderVolume(v) {
    if (v.level == null) { $('#vol-value').textContent = '–'; return; }
    $('#vol-slider').value = v.level;
    $('#vol-value').textContent = v.level;
    muted = v.muted;
    $('#vol-mute').replaceChildren(icon(muted ? 'mute' : 'volume'));
    $('#vol-mute').classList.toggle('primary', muted);
  }

  async function loadVolume() {
    try { renderVolume(await api('/api/volume')); } catch { /* ignorado */ }
  }

  $('#vol-slider').addEventListener('input', () => {
    const level = Number($('#vol-slider').value);
    $('#vol-value').textContent = level;
    clearTimeout(volTimer);
    volTimer = setTimeout(() => attempt(() => post('/api/volume', { level })), 120);
  });
  $('#vol-mute').addEventListener('click', async () => {
    const v = await attempt(() => post('/api/volume', { muted: !muted }));
    if (v) renderVolume(v);
  });
  for (const b of $$('[data-media]')) {
    b.addEventListener('click', () => { vibrate(); attempt(() => post('/api/key', { keys: [b.dataset.media] })); });
  }

  $('#type-send').addEventListener('click', async () => {
    const text = $('#type-text').value;
    if (!text) return;
    await attempt(() => post('/api/type', { text: $('#type-enter').checked ? `${text}\n` : text }), 'Digitado no PC.');
  });
  $('#clip-send').addEventListener('click', async () => {
    const text = $('#type-text').value;
    if (!text) return;
    await attempt(() => post('/api/clipboard', { text }), 'Copiado no PC. É só dar Ctrl+V lá.');
  });
  $('#clip-get').addEventListener('click', async () => {
    const res = await attempt(() => api('/api/clipboard'));
    if (!res) return;
    $('#type-text').value = res.text;
    $('#type-text').select();
    let copied = false;
    try { await navigator.clipboard.writeText(res.text); copied = true; } catch {
      try { copied = document.execCommand('copy'); } catch { /* sem cópia */ }
    }
    toast(res.text ? (copied ? 'Copiado para o celular.' : 'Texto do PC está no campo.') : 'A área de transferência do PC está vazia.');
  });

  $('#open-form').addEventListener('submit', async e => {
    e.preventDefault();
    const url = $('#open-url').value.trim();
    if (!url) return;
    await attempt(() => post('/api/open', { url }), 'Abrindo no PC…');
  });

  const POWER = {
    lock: { title: 'Bloquear o PC?', msg: 'Depois de bloquear, não dá para desbloquear pelo celular: alguém precisa digitar a senha no PC.', label: 'Bloquear' },
    screen_off: { title: 'Desligar a tela?', msg: 'O monitor apaga, mas o PC continua ligado. Mexer no mouse liga de novo.', label: 'Desligar tela', safe: true },
    sleep: { title: 'Suspender o PC?', msg: 'Ele fica fora do alcance do celular até alguém acordá-lo.', label: 'Suspender' },
    restart: { title: 'Reiniciar o PC?', msg: 'Salve o que estiver aberto. O PControl volta sozinho quando o Windows entrar na sua conta.', label: 'Reiniciar', delay: true },
    shutdown: { title: 'Desligar o PC?', msg: 'Ele só volta se alguém ligar. Salve o que estiver aberto.', label: 'Desligar', delay: true },
  };

  for (const b of $$('[data-power]')) {
    b.addEventListener('click', async () => {
      const action = b.dataset.power;
      if (action === 'cancel') {
        await attempt(() => post('/api/power', { action }), 'Desligamento agendado cancelado.');
        return;
      }
      const p = POWER[action];
      let delay = 0;
      let choice;
      if (p.delay) {
        choice = await sheet({
          title: p.title, message: p.msg,
          actions: [
            { id: '0', label: `${p.label} agora`, danger: true },
            { id: '60', label: 'Daqui a 1 minuto' },
            { id: '600', label: 'Daqui a 10 minutos' },
            { id: '1800', label: 'Daqui a 30 minutos' },
            { id: '3600', label: 'Daqui a 1 hora' },
          ],
        });
        if (choice == null) return;
        delay = Number(choice);
      } else if (!await confirmSheet(p.title, p.msg, p.label, !p.safe)) {
        return;
      }
      await attempt(() => post('/api/power', { action, delay }),
        delay ? `${p.label} agendado. Dá para cancelar aqui.` : 'Feito.');
    });
  }

  $('#keep-awake').addEventListener('change', async e => {
    const on = e.target.checked;
    const res = await attempt(() => post('/api/keep-awake', { on }));
    if (!res) e.target.checked = !on;
  });

  function statBox(label, value, sub, percent) {
    return h('div', { class: 'stat' },
      h('small', { text: label }), h('b', { text: value }),
      sub ? h('small', { text: sub }) : null,
      percent != null ? h('div', { class: `bar${percent > 90 ? ' hot' : ''}` }, h('i', { style: `width:${percent}%` })) : null);
  }

  async function loadStats() {
    let s;
    try { s = await api('/api/stats'); } catch { return; }
    const boxes = [
      statBox('Processador', `${Math.round(s.cpu)}%`, null, s.cpu),
      statBox('Memória', `${Math.round(s.memory.percent)}%`, `${fmtBytes(s.memory.used)} de ${fmtBytes(s.memory.total)}`, s.memory.percent),
      ...s.disks.map(d => statBox(`Disco ${d.name}`, `${Math.round(d.percent)}%`, `${fmtBytes(d.total - d.used)} livres`, d.percent)),
      statBox('Ligado há', fmtDuration(s.uptime)),
    ];
    if (s.battery) boxes.push(statBox('Bateria', `${s.battery.percent}%`, s.battery.plugged ? 'Na tomada' : 'Na bateria', s.battery.percent));
    $('#stats').replaceChildren(...boxes);
  }

  function renderConnInfo() {
    const rows = [];
    const via = { lan: 'Wi-Fi de casa', tailscale: 'Tailscale (de qualquer lugar)', local: 'Neste PC' }[info.via] || info.via;
    rows.push(h('div', {}, 'Conectado por: ', h('b', { text: via })));
    if (info.lan) rows.push(h('div', {}, 'Wi-Fi: ', h('code', { text: info.lan })));
    rows.push(h('div', {}, 'Fora de casa: ', info.tailscale ? h('code', { text: info.tailscale }) : h('span', { class: 'muted', text: 'instale o Tailscale no PC' })));
    $('#conn-info').replaceChildren(...rows);
  }

  $('#logout').addEventListener('click', async () => {
    if (!await confirmSheet('Sair deste aparelho?', 'Vai precisar da senha para entrar de novo.', 'Sair')) return;
    await attempt(() => post('/api/logout'));
    NATIVE?.clearToken?.();
    showLogin();
  });

  $('#open-tasks').addEventListener('click', () => openTasks());

  function openTasks() {
    let timer = 0;
    let list = [];
    const search = h('input', { class: 'field', type: 'search', placeholder: 'Buscar processo' });
    const rows = h('div');
    const page = openPage('Gerenciador de tarefas', { onClose: () => clearInterval(timer) });
    page.body.append(search, rows);

    function render() {
      const q = search.value.trim().toLowerCase();
      rows.replaceChildren(...list.filter(p => !q || p.name.toLowerCase().includes(q)).slice(0, 150).map(p =>
        h('button', { class: 'proc-row', onclick: () => kill(p) },
          h('div', { class: 'file-main' },
            h('div', { class: 'file-name', text: p.name.replace(/\.exe$/i, '') }),
            h('small', { text: p.count > 1 ? `${p.count} processos` : `PID ${p.pids[0]}` })),
          h('div', { class: 'proc-num' }, `${fmtBytes(p.memory)}`, h('small', { text: `${p.cpu}% CPU` })))));
    }
    async function load() {
      try { list = await api('/api/processes'); render(); } catch { /* tenta de novo no próximo ciclo */ }
    }
    async function kill(p) {
      const ok = await confirmSheet(`Encerrar ${p.name}?`,
        `${p.count > 1 ? `São ${p.count} processos. ` : ''}O que não estiver salvo nele será perdido.`, 'Encerrar');
      if (!ok) return;
      const res = await attempt(() => post('/api/processes/kill', { pids: p.pids }));
      if (res) toast(res.denied ? `Encerrados ${res.killed}; ${res.denied} sem permissão.` : 'Encerrado.');
      load();
    }
    search.addEventListener('input', render);
    rows.append(h('p', { class: 'muted', text: 'Carregando…' }));
    load();
    timer = setInterval(load, 3000);
  }

  return {
    show() {
      loadVolume();
      loadStats();
      renderConnInfo();
      $('#keep-awake').checked = !!info.keep_awake;
      clearInterval(statsTimer);
      statsTimer = setInterval(loadStats, 3000);
    },
    hide() { clearInterval(statsTimer); },
  };
})();

// --- Arquivos ------------------------------------------------------------------

const Files = (() => {
  let current = { path: '', parent: null };
  let loaded = false;
  const IMAGE = /\.(png|jpe?g|gif|webp|bmp|svg|avif)$/i;
  const VIDEO = /\.(mp4|webm|mov|m4v|mkv)$/i;
  const AUDIO = /\.(mp3|wav|ogg|m4a|flac|aac|opus)$/i;
  const TEXT = /\.(txt|log|md|json|csv|ini|cfg|xml|yml|yaml|py|js|ts|html|css|bat|ps1)$/i;
  const LAUNCHABLE = /\.(exe|lnk|url|bat|cmd)$/i;

  const join = (dir, name) => (dir.endsWith('\\') ? dir + name : `${dir}\\${name}`);
  const dlUrl = (path, inline) => `/api/files/download?path=${encodeURIComponent(path)}${inline ? '&inline=1' : ''}`;

  function renderCrumbs(path) {
    const box = $('#files-path');
    const crumbs = [h('button', { text: 'Este PC', onclick: () => go('') })];
    if (path) {
      const parts = path.replace(/\\$/, '').split('\\');
      let acc = '';
      parts.forEach((part, i) => {
        acc = i === 0 ? `${part}\\` : join(acc, part);
        const target = acc;
        crumbs.push(h('span', { class: 'sep', text: '›' }), h('button', { text: part, onclick: () => go(target) }));
      });
    }
    box.replaceChildren(...crumbs);
    box.scrollLeft = box.scrollWidth;
  }

  function fileIcon(entry) {
    if (entry.dir) return h('div', { class: 'file-icon folder' }, icon('folder'));
    if (LAUNCHABLE.test(entry.name)) {
      const box = h('div', { class: 'file-icon' });
      const img = h('img', { src: `/api/apps/icon?file=${encodeURIComponent(join(current.path, entry.name))}`, alt: '', loading: 'lazy' });
      img.addEventListener('error', () => box.replaceChildren(icon('file')));
      box.append(img);
      return box;
    }
    const ext = (entry.name.match(/\.([^.]{1,4})$/) || [])[1];
    return h('div', { class: 'file-icon' }, ext || icon('file'));
  }

  async function go(path) {
    const hidden = $('#files-hidden').checked ? '1' : '0';
    const res = await attempt(() => api(`/api/files?path=${encodeURIComponent(path)}&hidden=${hidden}`));
    if (!res) return;
    loaded = true;
    current = res;
    store.set('files.path', res.path);
    renderCrumbs(res.path);
    $('#files-up').disabled = !res.path;
    $('#files-upload').disabled = !res.path;
    $('#files-mkdir').disabled = !res.path;
    const list = $('#files-list');
    if (!res.path) {
      list.replaceChildren(...res.places.map(p =>
        h('button', { class: 'file-row', onclick: () => go(p.path) },
          h('div', { class: `file-icon ${p.kind === 'drive' ? 'drive' : 'folder'}` }, icon(p.kind === 'drive' ? 'drive' : 'folder')),
          h('div', { class: 'file-main' }, h('div', { class: 'file-name', text: p.name }), h('div', { class: 'file-meta', text: p.path })))));
    } else if (!res.entries.length) {
      list.replaceChildren(h('p', { class: 'muted pad', text: 'Pasta vazia.' }));
    } else {
      list.replaceChildren(...res.entries.map(entry => {
        const date = new Date(entry.modified * 1000).toLocaleDateString('pt-BR');
        const meta = entry.dir ? date : `${fmtBytes(entry.size)} · ${date}`;
        return h('button', {
          class: `file-row${entry.hidden ? ' hidden-file' : ''}`,
          onclick: () => (entry.dir ? go(join(res.path, entry.name)) : fileMenu(entry)),
          oncontextmenu: e => { e.preventDefault(); fileMenu(entry); },
        }, fileIcon(entry), h('div', { class: 'file-main' }, h('div', { class: 'file-name', text: entry.name }), h('div', { class: 'file-meta', text: meta })));
      }));
    }
    list.scrollTop = 0;
  }

  async function fileMenu(entry) {
    const path = join(current.path, entry.name);
    const viewable = !entry.dir && (IMAGE.test(entry.name) || VIDEO.test(entry.name) || AUDIO.test(entry.name) || TEXT.test(entry.name));
    const actions = [];
    if (!entry.dir) actions.push({ id: 'open', label: 'Abrir no PC', icon: 'external' });
    if (entry.dir) actions.push({ id: 'enter', label: 'Abrir pasta', icon: 'folder' });
    if (viewable) actions.push({ id: 'view', label: 'Ver no celular', icon: 'eye' });
    if (!entry.dir) actions.push({ id: 'download', label: 'Baixar para o celular', icon: 'download' });
    actions.push({ id: 'pin', label: 'Fixar em Apps', icon: 'star' });
    actions.push({ id: 'rename', label: 'Renomear', icon: 'pencil' });
    actions.push({ id: 'delete', label: 'Mover para a Lixeira', icon: 'trash', danger: true });
    const choice = await sheet({ title: entry.name, message: entry.dir ? 'Pasta' : fmtBytes(entry.size), actions });
    if (choice === 'open') await attempt(() => post('/api/files/open', { path }), `Abrindo ${entry.name} no PC…`);
    else if (choice === 'enter') go(path);
    else if (choice === 'view') view(entry, path);
    else if (choice === 'download') download(path, entry.name);
    else if (choice === 'pin') Apps.addFavorite(path, entry.name.replace(/\.(exe|lnk|url|bat|cmd)$/i, ''));
    else if (choice === 'rename') {
      const name = await promptSheet('Novo nome', entry.name);
      if (name && name !== entry.name && await attempt(() => post('/api/files/rename', { path, name }))) go(current.path);
    } else if (choice === 'delete') {
      if (await confirmSheet(`Mover "${entry.name}" para a Lixeira?`, 'Dá para recuperar pela Lixeira do PC.', 'Mover para a Lixeira')) {
        if (await attempt(() => post('/api/files/delete', { path }), 'Movido para a Lixeira.')) go(current.path);
      }
    }
  }

  function download(path, name) {
    if (NATIVE?.download) {
      NATIVE.download(new URL(dlUrl(path, false), location.href).href, name);
      toast('Baixando… acompanhe nas notificações.');
      return;
    }
    const a = h('a', { href: dlUrl(path, false), download: name });
    document.body.append(a);
    a.click();
    a.remove();
  }

  async function view(entry, path) {
    const page = openPage(entry.name, { center: !TEXT.test(entry.name) });
    const src = dlUrl(path, true);
    if (IMAGE.test(entry.name)) page.body.append(h('img', { src, alt: entry.name }));
    else if (VIDEO.test(entry.name)) page.body.append(h('video', { src, controls: true, autoplay: true, playsinline: true }));
    else if (AUDIO.test(entry.name)) page.body.append(h('audio', { src, controls: true, autoplay: true }));
    else {
      if (entry.size > 2 * 1024 * 1024) { page.body.append(h('p', { class: 'muted', text: 'Arquivo grande demais para ver aqui. Baixe para o celular.' })); return; }
      try {
        const res = await fetch(src, { credentials: 'same-origin' });
        page.body.append(h('pre', { text: await res.text() }));
      } catch {
        page.body.append(h('p', { class: 'muted', text: 'Não foi possível abrir.' }));
      }
    }
  }

  function upload(fileList) {
    if (!fileList.length || !current.path) return;
    const form = new FormData();
    let total = 0;
    for (const f of fileList) { form.append('file', f, f.name); total += f.size; }
    const bar = $('#upload-progress');
    bar.hidden = false;
    const setProgress = (fraction, text) => {
      bar.firstElementChild.style.width = `${Math.round(fraction * 100)}%`;
      bar.lastElementChild.textContent = text;
    };
    setProgress(0, `Enviando ${fileList.length} arquivo(s)…`);
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `/api/files/upload?dir=${encodeURIComponent(current.path)}`);
    xhr.upload.onprogress = e => {
      if (e.lengthComputable) setProgress(e.loaded / e.total, `${fmtBytes(e.loaded)} de ${fmtBytes(e.total || total)}`);
    };
    xhr.onload = () => {
      bar.hidden = true;
      if (xhr.status === 200) { toast('Enviado para o PC.'); go(current.path); }
      else {
        let msg = `Erro ${xhr.status}`;
        try { msg = JSON.parse(xhr.responseText).error || msg; } catch { /* resposta sem JSON */ }
        toast(msg, 'err');
      }
    };
    xhr.onerror = () => { bar.hidden = true; toast('A conexão caiu durante o envio.', 'err'); };
    xhr.send(form);
  }

  $('#files-up').addEventListener('click', () => { if (current.path) go(current.parent || ''); });
  $('#files-refresh').addEventListener('click', () => go(current.path));
  $('#files-hidden').addEventListener('change', () => go(current.path));
  $('#files-upload').addEventListener('click', () => $('#files-input').click());
  $('#files-input').addEventListener('change', e => { upload([...e.target.files]); e.target.value = ''; });
  $('#files-mkdir').addEventListener('click', async () => {
    const name = await promptSheet('Nome da nova pasta', '', 'Nova pasta', 'Criar');
    if (name && await attempt(() => post('/api/files/mkdir', { dir: current.path, name }))) go(current.path);
  });

  return {
    show() { if (!loaded) go(store.get('files.path', '')); },
  };
})();

const Tabs = { screen: Screen, apps: Apps, yt: YouTube, control: Control, files: Files };

// Chamado pelo app Android quando o usuário compartilha um link do YouTube com o PControl.
window.pcontrolShare = async text => {
  const url = (String(text).match(/https?:\/\/\S+/) || [])[0];
  if (!url) return;
  if (/(youtube\.com|youtu\.be)\//i.test(url)) {
    if (loggedIn) showTab('yt');
    await attempt(() => post('/api/youtube/play', { url }), 'Tocando no PC.');
  } else {
    await attempt(() => post('/api/open', { url }), 'Abrindo no PC…');
  }
};

// Botão "voltar" do Android: fecha o que estiver aberto. Retorna false se não havia nada.
window.pcontrolBack = () => {
  const sheetEl = $('#sheet');
  if (!sheetEl.hidden) { $('.sheet-backdrop', sheetEl)?.click(); return true; }
  const page = $('.page');
  if (page) { $('.page-head .icon-btn', page).click(); return true; }
  if (document.body.classList.contains('immersive')) { $('#exit-immersive').click(); return true; }
  if (!$('#kbd-panel').hidden) { $('#kbd-toggle').click(); return true; }
  return false;
};

start();
