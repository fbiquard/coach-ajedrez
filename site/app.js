import { Chessground } from './vendor/chessground.js';
import { Chess } from './vendor/chess.js';

const app = document.getElementById('app');
const state = { index: null, puzzles: null, games: {}, filter: 'todas', diag: 'rapid', bestTc: 'rapid', planTc: 'rapid' };

// ---------- utilidades ----------
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtDate = (t) => new Date(t * 1000).toLocaleDateString('es-AR', { day: 'numeric', month: 'short' });
const fmtDateLong = (t) => new Date(t * 1000).toLocaleDateString('es-AR', { day: 'numeric', month: 'long', year: 'numeric' });
const dec = (n, d = 1) => (n == null ? '–' : Number(n).toFixed(d).replace('.', ','));
const clock = (c) => (c == null ? '' : `${Math.floor(c / 60)}:${String(Math.floor(c % 60)).padStart(2, '0')}`);
const RES = { W: 'G', D: 'T', L: 'P' };
const RES_TXT = { W: 'Ganaste', D: 'Tablas', L: 'Perdiste' };
const TC = { rapid: 'Rapid', blitz: 'Blitz' };
const DAY = 86400000;

async function getJSON(path) {
  const r = await fetch(path, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`No pude cargar ${path} (${r.status})`);
  return r.json();
}

// ---------- repaso espaciado (en este navegador) ----------
const SRS_KEY = 'coach.srs.v1';
const INTERVALS = [1, 3, 7, 21, 60];
const NEW_PER_DAY = 5;
function loadSrs() { try { return JSON.parse(localStorage.getItem(SRS_KEY)) || {}; } catch { return {}; } }
function saveSrs(s) { try { localStorage.setItem(SRS_KEY, JSON.stringify(s)); } catch { /* sin almacenamiento */ } }
function grade(id, ok) {
  const s = loadSrs();
  const cur = s[id] || { box: -1, seen: 0, right: 0 };
  cur.seen += 1;
  if (ok) { cur.right += 1; cur.box = Math.min(cur.box + 1, INTERVALS.length - 1); } else { cur.box = 0; }
  cur.due = Date.now() + (ok ? INTERVALS[cur.box] : 1) * DAY;
  cur.last = Date.now();
  if (!s._new) s._new = {};
  s[id] = cur;
  saveSrs(s);
}
function noteNew(id) {
  const s = loadSrs();
  const today = new Date().toDateString();
  if (!s._new || s._new.day !== today) s._new = { day: today, ids: [] };
  if (!s._new.ids.includes(id)) s._new.ids.push(id);
  saveSrs(s);
}
function queue() {
  const s = loadSrs();
  const now = Date.now();
  const due = state.puzzles.filter((p) => s[p.id] && s[p.id].due <= now);
  const today = new Date().toDateString();
  const usedNew = s._new && s._new.day === today ? s._new.ids.length : 0;
  const fresh = state.puzzles.filter((p) => !s[p.id]).slice(0, Math.max(0, NEW_PER_DAY - usedNew));
  return { due, fresh, list: [...due, ...fresh], total: state.puzzles.length, learned: Object.keys(s).filter((k) => k[0] !== '_' && s[k].box >= 2).length };
}

// ---------- tablero ----------
function destsOf(chess) {
  const d = new Map();
  for (const m of chess.moves({ verbose: true })) {
    if (!d.has(m.from)) d.set(m.from, []);
    d.get(m.from).push(m.to);
  }
  return d;
}

function mountPuzzle(container, p, onDone) {
  const chess = new Chess(p.fen);
  const color = chess.turn() === 'w' ? 'white' : 'black';
  const boardEl = container.querySelector('.board');
  const res = container.querySelector('.result');
  let done = false;
  const cg = Chessground(boardEl, {
    fen: p.fen, orientation: color, turnColor: color, coordinates: true,
    movable: { free: false, color, dests: destsOf(chess), showDests: true, events: { after: onMove } },
    draggable: { showGhost: true }, highlight: { lastMove: true, check: true }, premovable: { enabled: false },
  });
  function onMove(from, to) {
    if (done) return;
    const want = p.solution.find((u) => u.slice(0, 4) === from + to);
    const promo = want && want.length > 4 ? want[4] : 'q';
    let mv;
    try { mv = chess.move({ from, to, promotion: promo }); } catch { mv = null; }
    if (!mv) return;
    done = true;
    const ok = Boolean(want);
    cg.set({ fen: chess.fen(), turnColor: chess.turn() === 'w' ? 'white' : 'black', movable: { color: undefined, dests: new Map() }, check: chess.inCheck() });
    if (!ok) {
      const sol = p.solution[0];
      setTimeout(() => {
        chess.undo();
        cg.set({ fen: chess.fen(), lastMove: undefined, check: false });
        cg.setAutoShapes([
          { orig: sol.slice(0, 2), dest: sol.slice(2, 4), brush: 'green' },
          ...(p.played_uci ? [{ orig: p.played_uci.slice(0, 2), dest: p.played_uci.slice(2, 4), brush: 'red' }] : []),
        ]);
      }, 700);
    } else {
      cg.setAutoShapes([]);
    }
    const verdict = ok ? (want === p.solution[0] ? 'Bien. Era esa.' : 'Bien. Esa también sirve.') : `No. La jugada era ${p.solution_san}.`;
    res.innerHTML = `
      <p class="verdict ${ok ? 'ok' : 'bad'}">${esc(verdict)}</p>
      <p class="line">${esc(p.line)}</p>
      <p>${esc(p.text)}</p>
      ${ok ? '' : '<p class="muted" style="font-size:.85rem">En verde la mejor jugada, en rojo la que jugaste en la partida.</p>'}
      <p class="muted" style="font-size:.85rem">Tus chances: ${p.wb}% → ${p.wa}% en la partida.</p>`;
    res.hidden = false;
    onDone && onDone(ok);
  }
  return cg;
}

function puzzleHTML(p, extra = '') {
  const side = new Chess(p.fen).turn() === 'w' ? 'blancas' : 'negras';
  return `
  <article class="card puzzle" data-id="${esc(p.id)}">
    <div class="board"></div>
    <div class="pz-side">
      <div class="pz-meta"><span class="tag">${esc(p.label)}</span><span class="mono">Jugada ${p.move_no} · ${esc(p.phase)}</span>${p.date ? `<span>${fmtDate(p.date)}${p.opp ? ' vs ' + esc(p.opp) : ''}</span>` : ''}</div>
      <p class="pz-q">${esc(p.question)}</p>
      <p class="pz-hint">Juegan las ${side}. Mové la pieza en el tablero.</p>
      <div class="result" hidden></div>
      ${extra}
    </div>
  </article>`;
}

// ---------- vistas ----------
function setTab(name) {
  document.querySelectorAll('.tabs a').forEach((a) => a.classList.toggle('on', a.dataset.tab === name));
}

function viewRepaso() {
  setTab('repaso');
  const q = queue();
  const last = state.index.games[0];
  const header = `
    <section class="head">
      <p class="eyebrow">Repaso de hoy</p>
      <h1>${q.list.length ? `Tenés ${q.list.length} ${q.list.length === 1 ? 'ejercicio' : 'ejercicios'} para hoy` : 'Repaso al día'}</h1>
      <p class="lede">Son posiciones de tus partidas, justo antes de un error tuyo. Los que fallás vuelven mañana; los que acertás, cada vez más espaciados.</p>
    </section>
    <div class="sheet">
      <div><span class="v">${q.due.length}</span><span class="l">para repasar</span></div>
      <div><span class="v">${q.fresh.length}</span><span class="l">nuevos de hoy</span></div>
      <div><span class="v">${q.learned}</span><span class="l">ya aprendidos</span></div>
      <div><span class="v">${q.total}</span><span class="l">ejercicios en total</span></div>
    </div>`;
  if (!q.list.length) {
    app.innerHTML = header + `
      <div class="card empty"><h2>No hay nada pendiente</h2><p class="muted">Mañana entran ${NEW_PER_DAY} ejercicios nuevos. Mientras tanto podés mirar tu última partida.</p>
      ${last ? `<a class="btn" href="#partida/${last.id}">Ver la última partida</a>` : ''}</div>`;
    return;
  }
  let i = 0, right = 0;
  const list = q.list;
  app.innerHTML = header + `<div class="progress" aria-hidden="true"><div style="width:0%"></div></div><div id="slot"></div>`;
  const slot = document.getElementById('slot');
  const bar = app.querySelector('.progress div');
  function show() {
    if (i >= list.length) {
      bar.style.width = '100%';
      slot.innerHTML = `<div class="card empty"><h2>Listo por hoy: ${right} de ${list.length}</h2><p class="muted">${right === list.length ? 'Todos bien. ' : 'Los que fallaste vuelven mañana. '}La próxima partida que juegues aparece acá en un par de horas.</p><a class="btn" href="#partidas">Ver tus partidas</a></div>`;
      return;
    }
    const p = list[i];
    slot.innerHTML = puzzleHTML(p, `<div class="actions" hidden><button class="btn" type="button" id="next">${i + 1 < list.length ? 'Siguiente' : 'Terminar'}</button><a class="btn ghost" href="#partida/${p.game}">Ver la partida</a></div>`);
    const el = slot.querySelector('.puzzle');
    mountPuzzle(el, p, (ok) => {
      if (!loadSrs()[p.id]) noteNew(p.id);
      grade(p.id, ok);
      right += ok ? 1 : 0;
      el.querySelector('.actions').hidden = false;
      el.querySelector('#next').addEventListener('click', () => { i += 1; bar.style.width = `${(100 * i) / list.length}%`; show(); });
      el.querySelector('#next').focus();
    });
  }
  show();
}

function gameRow(g) {
  const tags = [];
  if (g.blown) tags.push('<span class="tag warn">Se te escapó</span>');
  if (g.n_puzzles) tags.push(`<span class="tag">${g.n_puzzles} ${g.n_puzzles === 1 ? 'ejercicio' : 'ejercicios'}</span>`);
  return `
  <a class="card game" href="#partida/${g.id}">
    <span class="res ${g.outcome}" aria-label="${RES_TXT[g.outcome]}">${RES[g.outcome]}</span>
    <span class="g-main">
      <span class="g-title">vs ${esc(g.opp || 'rival')} <span class="muted mono" style="font-weight:400">${g.opp_rating}</span> ${tags.join(' ')}</span>
      <span class="g-sub">${fmtDate(g.date)} · ${TC[g.time_class] || g.time_class} ${esc(g.tc)} · ${g.color === 'white' ? 'blancas' : 'negras'} · ${esc(g.opening)}</span>
      ${g.advice ? `<span class="g-adv">${esc(g.advice)}</span>` : ''}
    </span>
    <span class="g-right"><span class="n">${g.n_blunders}</span>blunders</span>
  </a>`;
}

function viewPartidas() {
  setTab('partidas');
  const all = state.index.games;
  const gs = state.filter === 'todas' ? all : all.filter((g) => g.time_class === state.filter);
  const shown = gs.slice(0, 60);
  app.innerHTML = `
    <section class="head"><p class="eyebrow">Partidas</p><h1>Tus últimas partidas</h1>
      <p class="lede">Cada una con su momento clave, un consejo y los errores convertidos en ejercicios.</p></section>
    <div class="chips" role="group" aria-label="Filtrar por ritmo">
      ${['todas', 'rapid', 'blitz'].map((f) => `<button type="button" class="chip ${state.filter === f ? 'on' : ''}" data-f="${f}">${f === 'todas' ? 'Todas' : TC[f]}</button>`).join('')}
    </div>
    <div class="list">${shown.map(gameRow).join('') || '<p class="muted">No hay partidas de este ritmo todavía.</p>'}</div>
    ${gs.length > shown.length ? `<p class="muted">Mostrando las ${shown.length} más recientes de ${gs.length}.</p>` : ''}`;
  app.querySelectorAll('.chip').forEach((b) => b.addEventListener('click', () => { state.filter = b.dataset.f; viewPartidas(); }));
}

function curveSVG(g) {
  const W = 640, H = 150, n = g.curve.length;
  if (n < 2) return '';
  const x = (i) => (i / (n - 1)) * W;
  const y = (v) => H - (v / 100) * H;
  const pts = g.curve.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const area = `0,${H} ${pts} ${W},${H}`;
  const dots = g.errors.map((e) => `<circle cx="${x(e.ply).toFixed(1)}" cy="${y(e.wa).toFixed(1)}" r="4.5" fill="var(--${e.sev === 'blunder' ? 'blunder' : 'mistake'})" stroke="var(--surface)" stroke-width="1.5"><title>${esc(e.played)}: ${e.wb}% → ${e.wa}%</title></circle>`).join('');
  return `<svg class="curve" viewBox="-4 -6 ${W + 8} ${H + 22}" role="img" aria-label="Tus chances de ganar a lo largo de la partida">
    <line x1="0" y1="${y(50)}" x2="${W}" y2="${y(50)}" stroke="var(--line)" stroke-dasharray="4 4"/>
    <polygon points="${area}" fill="var(--accent-soft)"/>
    <polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="2"/>
    ${dots}
    <text x="0" y="${H + 14}" font-size="11" fill="var(--muted)" font-family="var(--font-mono)">inicio</text>
    <text x="${W}" y="${H + 14}" font-size="11" fill="var(--muted)" text-anchor="end" font-family="var(--font-mono)">jugada ${Math.ceil(n / 2)}</text>
  </svg>`;
}

async function viewPartida(id) {
  setTab('partidas');
  app.innerHTML = '<p class="loading">Cargando la partida…</p>';
  let g = state.games[id];
  if (!g) {
    try { g = state.games[id] = await getJSON(`data/games/${id}.json`); } catch (e) { app.innerHTML = `<p>${esc(e.message)}</p>`; return; }
  }
  const adv = g.advice || {};
  const errs = [...g.errors].sort((a, b) => a.ply - b.ply);
  app.innerHTML = `
    <section class="head">
      <p class="eyebrow"><a href="#partidas">← Partidas</a> · ${fmtDateLong(g.date)} · ${TC[g.time_class] || ''} ${esc(g.tc)}</p>
      <h1>${RES_TXT[g.outcome]} con ${g.color === 'white' ? 'blancas' : 'negras'} vs ${esc(g.opp || 'rival')} (${g.opp_rating})</h1>
      <p class="lede">${esc(g.opening)} · tu rating ${g.rating}${g.accuracy ? ` · precisión chess.com ${dec(g.accuracy)}%` : ''} · <a href="${esc(g.url)}" target="_blank" rel="noopener">Abrir en chess.com ↗</a></p>
    </section>
    <section class="card advice">
      <p class="eyebrow">${adv.source === 'claude' ? 'Consejo de Claude' : 'Consejo'}</p>
      <p>${esc(adv.text || 'Sin consejo todavía.')}</p>
    </section>
    <section class="card curve-wrap">
      <h3>Tus chances de ganar, jugada a jugada</h3>
      ${curveSVG(g)}
      <p class="muted" style="font-size:.85rem">Los puntos son tus errores: rojo para blunders (??), ámbar para errores (?).</p>
    </section>
    ${g.puzzles.length ? `<section class="head"><h2>Ejercicios de esta partida</h2><p class="muted">Las posiciones justo antes de tus errores. Buscá lo que no viste.</p></section>
      <div class="list" id="pzs">${g.puzzles.map((p) => puzzleHTML(p)).join('')}</div>` : ''}
    <section class="card" style="padding:6px 18px">
      <div class="head" style="padding:12px 0 4px"><h2>Tus errores</h2></div>
      <div class="errs">${errs.length ? errs.map((e) => `
        <div class="err"><span class="nag ${e.sev}">${e.sev === 'blunder' ? '??' : '?'}</span>
          <div><p class="t">${esc(e.played)} <span class="muted mono" style="font-weight:400">${e.wb}% → ${e.wa}% · reloj ${clock(e.clk)}</span></p>
          <p>${esc(e.text)} Mejor: <span class="mono">${esc(e.best_line)}</span></p></div></div>`).join('') : '<p class="muted" style="padding:12px 0">Ningún error grave. Bien jugada.</p>'}</div>
    </section>`;
  app.querySelectorAll('#pzs .puzzle').forEach((el) => {
    const p = g.puzzles.find((x) => x.id === el.dataset.id);
    mountPuzzle(el, p, (ok) => grade(p.id, ok));
  });
}

function bars(rows, { fmt = (v) => v, hot = () => false, max } = {}) {
  const mx = max || Math.max(...rows.map((r) => r.v), 1);
  return `<div class="bars">${rows.map((r) => `
    <div class="brow"><span>${esc(r.label)}</span><span class="btrack"><span class="bar ${hot(r) ? 'hot' : ''}" style="display:block;width:${((100 * r.v) / mx).toFixed(1)}%"></span></span>
    <span class="bval">${fmt(r.v)}<span class="bsub">${esc(r.sub || '')}</span></span></div>`).join('')}</div>`;
}

function spark(series) {
  if (series.length < 2) return '';
  const W = 640, H = 80;
  const vs = series.map((s) => s[1]);
  const lo = Math.min(...vs) - 10, hi = Math.max(...vs) + 10;
  const x = (i) => (i / (series.length - 1)) * W;
  const y = (v) => H - ((v - lo) / (hi - lo)) * H;
  const pts = series.map((s, i) => `${x(i).toFixed(1)},${y(s[1]).toFixed(1)}`).join(' ');
  const last = series[series.length - 1];
  return `<svg class="spark" viewBox="-4 -4 ${W + 8} ${H + 8}" preserveAspectRatio="none" role="img" aria-label="Evolución del rating">
    <polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="2" vector-effect="non-scaling-stroke"/>
    <circle cx="${x(series.length - 1)}" cy="${y(last[1])}" r="4" fill="var(--accent)"/></svg>`;
}

function viewDiag() {
  setTab('diagnostico');
  const S = state.index.stats;
  const tcs = Object.keys(S);
  if (!tcs.includes(state.diag)) state.diag = tcs[0];
  const s = S[state.diag];
  if (!s) { app.innerHTML = '<p class="muted">Todavía no hay datos para el diagnóstico.</p>'; return; }
  const trend = s.bpg_recent != null && s.bpg_older != null ? s.bpg_recent - s.bpg_older : null;
  const hotKinds = new Set(['Colgaste la pieza que acabás de mover', 'Dejaste otra pieza sin defensa', 'Te comiste un ataque doble', 'No viste un mate']);
  const maxPhase = Math.max(...s.phase.map((r) => r.rate));
  const maxClk = Math.max(...s.clock.map((r) => r.rate));
  const maxSp = Math.max(...s.spent.map((r) => r.rate));
  const r0 = s.rating[0][1], r1 = s.rating[s.rating.length - 1][1];
  app.innerHTML = `
    <section class="head"><p class="eyebrow">Diagnóstico · últimas ${s.n_games} partidas</p>
      <h1>Dónde se te van las partidas</h1>
      <p class="lede">Del ${fmtDateLong(s.first)} al ${fmtDateLong(s.last)}. Se recalcula con cada partida nueva.</p></section>
    <div class="chips" role="group" aria-label="Ritmo">${tcs.map((t) => `<button type="button" class="chip ${t === state.diag ? 'on' : ''}" data-t="${t}">${TC[t]}</button>`).join('')}</div>
    <div class="sheet">
      <div><span class="v">${dec(s.blunders_per_game, 2)}</span><span class="l">blunders por partida</span></div>
      <div><span class="v ${trend == null ? '' : trend <= 0 ? 'up' : 'down'}">${s.bpg_recent == null ? '–' : dec(s.bpg_recent, 2)}</span><span class="l">últimos 30 días (${s.n_recent} partidas)</span></div>
      <div><span class="v">${s.conv.n ? Math.round((100 * s.conv.won) / s.conv.n) + '%' : '–'}</span><span class="l">ganadas de las que tuviste ganadas</span></div>
      <div><span class="v">${s.median_spent == null ? '–' : dec(s.median_spent, 0) + 's'}</span><span class="l">mediana por jugada</span></div>
    </div>
    <section class="card" style="padding:14px 16px;display:grid;gap:6px">
      <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap"><h3>Rating ${TC[state.diag]}</h3><span class="mono muted">${r0} → ${r1}</span></div>
      ${spark(s.rating)}
      <p class="muted" style="font-size:.85rem">${s.results.W} ganadas, ${s.results.D} tablas, ${s.results.L} perdidas. ${s.missed} veces no castigaste un error del rival.</p>
    </section>
    <div class="charts">
      <div class="chart wide"><h3>Qué tipo de blunder cometés</h3>
        ${bars(s.kinds.map((k) => ({ label: k.label, v: k.n, sub: `${Math.round((100 * k.n) / s.n_blunders)}%` })), { hot: (r) => hotKinds.has(r.label) })}
        <p class="note">En rojo, los que se evitan con el chequeo de jaques, capturas y amenazas antes de soltar la pieza.</p></div>
      <div class="chart"><h3>Blunders cada 100 jugadas, por fase</h3>
        ${bars(s.phase.map((r) => ({ label: r.label, v: r.rate, sub: `${r.blunders} en ${r.moves}` })), { fmt: (v) => dec(v) + '%', hot: (r) => r.v === maxPhase })}</div>
      <div class="chart"><h3>Según tu reloj</h3>
        ${bars(s.clock.map((r) => ({ label: r.label, v: r.rate, sub: `${r.blunders} en ${r.moves}` })), { fmt: (v) => dec(v) + '%', hot: (r) => r.v === maxClk && r.sub.split(' en ')[1] > 50 })}
        <p class="note">Con menos de 50 jugadas en un tramo, el número es poco confiable.</p></div>
      <div class="chart"><h3>Según cuánto pensaste la jugada</h3>
        ${bars(s.spent.map((r) => ({ label: r.label, v: r.rate, sub: `${r.blunders} en ${r.moves}` })), { fmt: (v) => dec(v) + '%', hot: (r) => r.v === maxSp })}
        <p class="note">Desde la jugada 9.</p></div>
      <div class="chart"><h3>Aperturas</h3>
        <div class="tbl"><table><thead><tr><th>Color</th><th>Apertura</th><th class="num">Partidas</th><th class="num">Puntos</th></tr></thead>
        <tbody>${s.openings.map((o) => `<tr><td>${o.color === 'white' ? 'Blancas' : 'Negras'}</td><td>${esc(o.name)}</td><td class="num">${o.n}</td><td class="num" style="color:var(--${o.pct >= 55 ? 'good' : o.pct < 45 ? 'blunder' : 'ink'})">${o.pct}%</td></tr>`).join('')}</tbody></table></div>
        <p class="note">El color es el tuyo. Puntos: victorias más medio punto por tablas.</p></div>
    </div>`;
  app.querySelectorAll('.chip').forEach((b) => b.addEventListener('click', () => { state.diag = b.dataset.t; viewDiag(); }));
}

// ---------- mejores partidas ----------
function miniBoard(el, fen, uci) {
  const turn = new Chess(fen).turn() === 'w' ? 'white' : 'black';
  const cg = Chessground(el, { fen, orientation: turn, viewOnly: true, coordinates: false });
  if (uci) cg.setAutoShapes([{ orig: uci.slice(0, 2), dest: uci.slice(2, 4), brush: 'green' }]);
}

function viewMejores() {
  setTab('mejores');
  const B = state.index.best || {};
  const tcs = Object.keys(B).filter((t) => B[t].length);
  if (!tcs.length) { app.innerHTML = '<div class="card empty"><h2>Todavía no hay mejores partidas</h2><p class="muted">Aparecen cuando el análisis termina de revisar tus partidas candidatas.</p></div>'; return; }
  if (!tcs.includes(state.bestTc)) state.bestTc = tcs[0];
  const list = B[state.bestTc];
  app.innerHTML = `
    <section class="head"><p class="eyebrow">Mejores partidas</p><h1>Lo que hacés bien</h1>
      <p class="lede">Ordenadas por precisión, nivel del rival y jugadas difíciles encontradas: sacrificios correctos y jugadas únicas. Una victoria fácil contra alguien que regaló todo no entra.</p></section>
    <div class="chips" role="group" aria-label="Ritmo">${tcs.map((t) => `<button type="button" class="chip ${t === state.bestTc ? 'on' : ''}" data-t="${t}">${TC[t]}</button>`).join('')}</div>
    <div class="list">${list.map((g, i) => {
      const h = g.highlights[0];
      return `
      <article class="card best">
        <div class="mini-board" data-i="${i}"></div>
        <div class="best-side">
          <span class="rank">#${i + 1} · ${fmtDateLong(g.date)} · ${esc(g.tc)}</span>
          <a class="best-title" href="#partida/${g.id}" style="color:var(--ink);text-decoration:none">${RES_TXT[g.outcome]} con ${g.color === 'white' ? 'blancas' : 'negras'} vs ${esc(g.opp || 'rival')} (${g.opp_rating})</a>
          <div class="chips">${g.tags.map((t) => `<span class="tag good">${esc(t)}</span>`).join('')}</div>
          <p class="best-why">${esc(g.why)}</p>
          ${g.highlights.length ? `<div class="hl-list">${g.highlights.map((x) => `<span>${x.type === 'sacrificio' ? 'Sacrificio' : 'Jugada única'}: <b>${x.move_no}${g.color === 'white' ? '.' : '…'}${esc(x.san)}</b> · ${esc(x.line)}</span>`).join('')}</div>` : ''}
          <p style="font-size:.85rem"><a href="#partida/${g.id}">Ver la partida</a> · <a href="${esc(g.url)}" target="_blank" rel="noopener">chess.com ↗</a></p>
        </div>
      </article>`; }).join('')}</div>`;
  app.querySelectorAll('.mini-board').forEach((el) => {
    const g = list[+el.dataset.i];
    const h = g.highlights[0];
    if (h) miniBoard(el, h.fen, h.uci);
    else el.remove();
  });
  app.querySelectorAll('.chip').forEach((b) => b.addEventListener('click', () => { state.bestTc = b.dataset.t; viewMejores(); }));
}

// ---------- plan ----------
function fmtMetric(v, unit) {
  if (v == null) return '–';
  const s = Number.isInteger(v) ? String(v) : dec(v, v < 1 ? 2 : 1);
  return s + (unit || '');
}

function recCard(r) {
  const m = r.metric;
  const trend = m.before == null ? '' : (m.better === 'lower' ? (m.now < m.before ? 'up' : m.now > m.before ? 'down' : '') : (m.now > m.before ? 'up' : m.now < m.before ? 'down' : ''));
  return `
  <article class="card rec">
    <div class="rec-head"><h2>${esc(r.title)}</h2><span class="tag">${esc(r.area)}</span></div>
    <p class="why">${esc(r.why)}</p>
    <p class="rule">${esc(r.rule)}</p>
    <ul class="reslist">${r.resources.map((x) => `<li><span>${x.url ? `<a href="${esc(x.url)}"${x.url.startsWith('#') ? '' : ' target="_blank" rel="noopener"'}>${esc(x.name)}${x.url.startsWith('#') ? '' : ' ↗'}</a>` : esc(x.name)}</span><span class="dose">${esc(x.dose)}</span></li>`).join('')}</ul>
    <div class="meter">
      <div><span class="v">${fmtMetric(m.before, m.unit)}</span><span class="l">30 partidas anteriores</span></div>
      <div><span class="v ${trend}">${fmtMetric(m.now, m.unit)}</span><span class="l">últimas 30 partidas</span></div>
      <div><span class="v">${m.better === 'lower' ? '≤ ' : '≥ '}${fmtMetric(m.target, m.unit)}</span><span class="l">objetivo</span></div>
    </div>
    <p class="muted" style="font-size:.8rem">${esc(m.label[0].toUpperCase() + m.label.slice(1))}. Se recalcula con cada partida nueva.</p>
  </article>`;
}

function viewPlan() {
  setTab('plan');
  const P = state.index.plan || {};
  const tcs = Object.keys(P);
  if (!tcs.length) { app.innerHTML = '<div class="card empty"><h2>Todavía no hay plan</h2><p class="muted">Hacen falta al menos 10 partidas de un ritmo.</p></div>'; return; }
  if (!tcs.includes(state.planTc)) state.planTc = tcs[0];
  const p = P[state.planTc];
  app.innerHTML = `
    <section class="head"><p class="eyebrow">Plan de entrenamiento · ${TC[state.planTc]}</p>
      <h1>${p.focus.length ? (p.focus.length === 1 ? 'Tu foco para las próximas 4 semanas' : `Tus ${p.focus.length} focos para las próximas 4 semanas`) : 'Nada urgente para entrenar'}</h1>
      <p class="lede">Sale de tus errores reales. Cada foco trae una regla para aplicar en la partida, recursos concretos y una métrica: si en 30 partidas no mejora, el plan cambia.</p></section>
    <div class="chips" role="group" aria-label="Ritmo">${tcs.map((t) => `<button type="button" class="chip ${t === state.planTc ? 'on' : ''}" data-t="${t}">${TC[t]}</button>`).join('')}</div>
    <div class="list">${p.focus.map(recCard).join('')}</div>
    ${p.later.length ? `<section class="head"><h2>Después</h2><p class="muted">También aparecen en tus datos, con menos peso. Encaralos cuando los de arriba lleguen al objetivo.</p></section>
      <div class="later">${p.later.map((r) => `<div class="card later-row"><span><b>${esc(r.title)}</b> <span class="muted">· ${esc(r.why)}</span></span><span class="tag">${esc(r.area)}</span></div>`).join('')}</div>` : ''}`;
  app.querySelectorAll('.chip').forEach((b) => b.addEventListener('click', () => { state.planTc = b.dataset.t; viewPlan(); }));
}

// ---------- ruteo ----------
function route() {
  const h = location.hash.replace('#', '') || 'repaso';
  window.scrollTo(0, 0);
  if (h.startsWith('partida/')) return viewPartida(h.slice(8));
  if (h === 'partidas') return viewPartidas();
  if (h === 'mejores') return viewMejores();
  if (h === 'plan') return viewPlan();
  if (h === 'diagnostico') return viewDiag();
  return viewRepaso();
}

async function boot() {
  try {
    [state.index, state.puzzles] = await Promise.all([getJSON('data/index.json'), getJSON('data/puzzles.json')]);
  } catch (e) {
    app.innerHTML = `<div class="card empty"><h2>No pude cargar los datos</h2><p class="muted">${esc(e.message)}</p></div>`;
    return;
  }
  document.getElementById('updated').textContent = `Actualizado: ${new Date(state.index.updated * 1000).toLocaleString('es-AR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}`;
  window.addEventListener('hashchange', route);
  route();
}
boot();
