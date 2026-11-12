/* =====================================================================
   FORJA DE IMPRESSORAS — RPG / GAMER LOGIC & INTERACTION ENGINE
   Web Audio Synthesizer • Dynamic HUD • Inventory Grid & Tactical Table
   ===================================================================== */
'use strict';

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

/* ------------------------------------------------------------------ STATE */
const S = {
  printers: [],
  checked: new Set(),
  filterText: '',
  filterCategory: 'all',
  selected: null,
  busy: false,
  admin: false,
  networks: [],
  installed: [],
  viewMode: 'grid', // 'grid' | 'table'
  soundEnabled: true,
};

/* ------------------------------------------------------------------ UTILS */
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

async function api(path, body) {
  const opt = {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
  };
  if (body !== undefined) opt.body = JSON.stringify(body);
  const r = await fetch(path, opt);
  let data = {};
  try { data = await r.json(); } catch (e) { /* silent */ }
  if (!r.ok || data.error) throw new Error(data.error || ('HTTP ' + r.status));
  return data;
}

/* ------------------------------------------------------------------ MUSICA MEDIEVAL (arquivos) */
const SoundFx = (() => {
  // Musica medieval de verdade: arquivos em /static/audio (vendorizados).
  //   Loops:   "Minstrel Guild", "Lord of the Land", "Celtic Impulse"
  //   Fanfarra:"The Rule", "Mighty and Meek"   (todos: Kevin MacLeod, CC-BY 3.0)
  //   Sino:    bronze, dominio publico (PDSounds)
  // Ver atribuicoes no README. Sorteio sem repeticao em sequencia.
  const BASE = '/static/audio/';
  const lastPlay = {};
  const live = new Set();
  let loopEl = null;
  S.wantLoop = false;

  function oneShot(name, opts) {
    opts = opts || {};
    if (!S.soundEnabled) return;
    const now = performance.now();
    const gap = opts.debounce == null ? 800 : opts.debounce;
    const key = name + '|' + (opts.rate || 1);
    if (now - (lastPlay[key] || 0) < gap) return;
    lastPlay[key] = now;
    try {
      const el = new Audio(BASE + name);
      el.volume = opts.vol == null ? 0.6 : opts.vol;
      if (opts.rate) el.playbackRate = opts.rate;
      live.add(el);
      el.onended = () => live.delete(el);
      const p = el.play();
      if (p && p.then) {
        p.then(() => {
          if (opts.stopAfter) setTimeout(() => {
            try { el.pause(); } catch (e) {}
            live.delete(el);
          }, opts.stopAfter);
        }).catch(() => { live.delete(el); });
      }
    } catch (e) {}
  }

  function stopLoopEl() {
    try { if (loopEl) loopEl.pause(); } catch (e) {}
    loopEl = null;
  }

  // Rádio menestrel: sorteia faixas sem repetir em sequência.
  //   loops:    minstrel.mp3, lord.mp3, celtic.mp3
  //   fanfarra: fanfare.mp3, mighty.mp3
  //   sino:     bell.ogg (cliques + dobrado fúnebre)
  const POOL = {
    loop: ['minstrel.mp3', 'lord.mp3', 'celtic.mp3'],
    fanfare: ['fanfare.mp3', 'mighty.mp3'],
  };
  let lastTrack = '';
  let lastFanfare = '';

  function pick(pool, avoid) {
    const opts = pool.filter(t => t !== avoid);
    const arr = opts.length ? opts : pool;
    return arr[(Math.random() * arr.length) | 0];
  }

  function playLoopTrack() {
    stopLoopEl();
    lastTrack = pick(POOL.loop, lastTrack);
    try {
      loopEl = new Audio(BASE + lastTrack);
      loopEl.volume = 0.42;
      loopEl.onended = () => { if (S.wantLoop && S.soundEnabled) playLoopTrack(); };
      const p = loopEl.play();
      if (p && p.then) p.catch(() => { loopEl = null; });
    } catch (e) { loopEl = null; }
  }

  function startLoop() {
    S.wantLoop = true;
    if (!S.soundEnabled) return;
    if (loopEl && !loopEl.paused) return;
    playLoopTrack();
  }

  function stopLoop() {
    S.wantLoop = false;
    stopLoopEl();
  }

  function silence() {
    // Mudo imediato: pausa o loop e tudo que estiver tocando.
    // Nao mexe em wantLoop (desmutar retoma de onde parou).
    stopLoopEl();
    live.forEach((el) => { try { el.pause(); } catch (e) {} });
    live.clear();
  }

  function setSoundEnabled(on) {
    S.soundEnabled = !!on;
    $('#soundIcon').className = S.soundEnabled ? 'bi bi-volume-up-fill' : 'bi bi-volume-mute-fill';
    $('#btnSound').classList.toggle('is-active', S.soundEnabled);
    try { localStorage.setItem('rpg-sound', S.soundEnabled ? '1' : '0'); } catch (e) {}
    if (!S.soundEnabled) {
      silence();
    } else if (S.wantLoop && !loopEl) {
      startLoop();
    }
  }

  // Autoplay: navegador pode bloquear audio fora de gesto; tenta de novo
  // no proximo clique/tecla se o loop ficou pendente.
  window.addEventListener('pointerdown', () => { if (S.wantLoop && !loopEl) startLoop(); });
  window.addEventListener('keydown', () => { if (S.wantLoop && !loopEl) startLoop(); });

  return {
    stopLoop,
    startLoop,
    setSoundEnabled,
    click() {
      // Silencioso de proposito: badalar a cada clique vira sineta constante.
    },
    coin() {
      oneShot('bell.ogg', { vol: 0.4, rate: 0.95 + Math.random() * 0.15 });
    },
    select(on) {
      // Silencioso de proposito: marcar caixas nao pode badalar.
    },
    radar() {
      startLoop();
    },
    forge() {
      startLoop();
    },
    scanLoop() {
      startLoop();
    },
    found() {
      // Uma badalada suave por descoberta (debounce longo: varredura com
      // dezenas de impressoras nao pode virar carrilhao).
      oneShot('bell.ogg', { vol: 0.4, rate: 1.2 + Math.random() * 0.15, debounce: 4000 });
    },
    fanfare() {
      stopLoopEl();
      lastFanfare = pick(POOL.fanfare, lastFanfare);
      oneShot(lastFanfare, { vol: 0.8, debounce: 2500, stopAfter: 12000 });
    },
    gameOver() {
      // Dobrado funebre: 2-3 badaladas graves, ritmo irregular.
      stopLoopEl();
      const n = 2 + ((Math.random() * 2) | 0);
      const base = 0.42 + Math.random() * 0.18;
      let t = 0;
      for (let k = 0; k < n; k++) {
        const rate = base - k * 0.05;
        const vol = 0.7 - k * 0.05;
        setTimeout(() => oneShot('bell.ogg', { vol, rate, debounce: 0 }), t);
        t += 800 + Math.random() * 450;
      }
    },
    victory() {
      try { this.fanfare(); } catch (e) {}
    },
    error() {
      try { this.gameOver(); } catch (e) {}
    }
  };
})();


/* ------------------------------------------------------------------ TOASTS */
function toast(kind, title, message) {
  const map = {
    success: 'toast-success',
    danger:  'toast-danger',
    warning: 'toast-warning',
    info:    'toast-info',
  };
  const iconMap = {
    success: 'bi-check2-circle text-success',
    danger:  'bi-exclamation-octagon text-danger',
    warning: 'bi-exclamation-triangle text-warning',
    info:    'bi-info-circle text-info',
  };

  const el = document.createElement('div');
  el.className = `toast align-items-center border-0 ${map[kind] || 'toast-info'}`;
  el.setAttribute('role', 'alert');
  el.innerHTML = `
    <div class="d-flex p-2">
      <div class="toast-body d-flex gap-2 align-items-start">
        <i class="bi ${iconMap[kind] || 'bi-gem'} fs-5"></i>
        <div>
          <strong class="d-block text-white" style="font-family:var(--rpg-font-display);font-size:0.86rem;letter-spacing:0.04em;">
            ${esc(title)}
          </strong>
          ${message ? `<span class="d-block small text-muted mt-1">${esc(message)}</span>` : ''}
        </div>
      </div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
    </div>`;

  $('#toasts').appendChild(el);
  const t = new bootstrap.Toast(el, { delay: 5500 });
  el.addEventListener('hidden.bs.toast', () => el.remove());
  t.show();

  if (kind === 'danger') SoundFx.error();
  else if (kind === 'success') SoundFx.victory();
  else if (kind === 'info') SoundFx.coin();
}

/* ------------------------------------------------------------------ RARITY & BADGES */
function getRarity(p) {
  const d = p.driver || {};
  const orig = d.origem || 'pendente';
  const conf = (p.confianca_modelo || 'baixa').toLowerCase();

  if (orig === 'pendente' || !d.driver_name) return 'pending';
  if (conf === 'alta' && (orig === 'local' || orig === 'inbox-exato')) return 'legendary';
  if (orig === 'download' || orig === 'inbox') return 'epic';
  if (p.conexao === 'usb') return 'uncommon';
  return 'rare';
}

const RARITY_LABELS = {
  legendary: { label: 'Lendário',   icon: 'bi-stars',             class: 'badge-rarity-legendary' },
  epic:      { label: 'Épico',      icon: 'bi-lightning-charge',  class: 'badge-rarity-epic' },
  rare:      { label: 'Raro',       icon: 'bi-gem',               class: 'badge-rarity-rare' },
  uncommon:  { label: 'Incomum',    icon: 'bi-shield-shaded',     class: 'badge-rarity-uncommon' },
  pending:   { label: 'Sem Runa',   icon: 'bi-slash-circle',      class: 'badge-rarity-pending' },
};

const ORIGIN_LABELS = {
  local:         { label: 'Runa Local (.inf)',      icon: 'bi-folder-check' },
  'inbox-exato': { label: 'Runa Windows (Exata)',   icon: 'bi-check-all' },
  download:      { label: 'Runa Nuvem (Download)',  icon: 'bi-cloud-arrow-down-fill' },
  inbox:         { label: 'Runa Fabricante',        icon: 'bi-hdd-network-fill' },
  instalado:     { label: 'Já Vinculada',           icon: 'bi-check-circle-fill' },
  pendente:      { label: 'Driver não encontrado',  icon: 'bi-exclamation-triangle-fill' },
};

function getVendorIcon(vendor) {
  const v = (vendor || '').toLowerCase();
  if (v.includes('hp') || v.includes('hewlett')) return 'bi-printer-fill';
  if (v.includes('epson')) return 'bi-card-image';
  if (v.includes('brother')) return 'bi-cpu-fill';
  if (v.includes('canon')) return 'bi-camera-fill';
  if (v.includes('samsung')) return 'bi-phone-landscape';
  if (v.includes('kyocera') || v.includes('lexmark') || v.includes('ricoh')) return 'bi-building-fill';
  return 'bi-printer';
}

/* ------------------------------------------------------------------ THEME & SOUND */
function applyTheme(theme) {
  if (theme === 'steampunk' || theme === 'arcane' || theme === 'cyber') theme = 'industrial'; // temas removidos: virou Oficina
  document.documentElement.setAttribute('data-rpg-theme', theme);
  const bsTheme = theme === 'paladin' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-bs-theme', bsTheme);

  $$('.theme-dropdown .dropdown-item').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.setTheme === theme);
  });

  try { localStorage.setItem('rpg-theme', theme); } catch (e) {}
}

$$('.theme-dropdown .dropdown-item').forEach((btn) => {
  btn.addEventListener('click', () => {
    applyTheme(btn.dataset.setTheme);
    SoundFx.click();
  });
});

$('#btnSound').addEventListener('click', () => {
  SoundFx.setSoundEnabled(!S.soundEnabled);
  if (S.soundEnabled) SoundFx.click();
});

/* ------------------------------------------------------------------ VIEW TOGGLE (GRID / TABLE) */
function setViewMode(mode) {
  S.viewMode = mode;
  $('#viewIcon').className = mode === 'grid' ? 'bi bi-grid-fill' : 'bi bi-list-task';
  $('#btnViewToggle').title = mode === 'grid'
    ? 'Alternar para Tabela Tática'
    : 'Alternar para Grade de Inventário';
  try { localStorage.setItem('rpg-view', mode); } catch (e) {}
  renderList();
}

$('#btnViewToggle').addEventListener('click', () => {
  setViewMode(S.viewMode === 'grid' ? 'table' : 'grid');
  SoundFx.click();
});

/* ------------------------------------------------------------------ LOG & STATUS */
function addLog(text, level) {
  const box = $('#logBox');
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 50;
  const div = document.createElement('div');
  div.className = level ? `l-${level}` : '';
  div.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
  box.appendChild(div);
  while (box.childElementCount > 800) box.removeChild(box.firstChild);
  if (atBottom) box.scrollTop = box.scrollHeight;
}
$('#btnClearLog').addEventListener('click', () => {
  $('#logBox').innerHTML = '';
  SoundFx.click();
});

function setStatus(text, pct) {
  $('#statusText').textContent = text;
  if (typeof pct === 'number') {
    $('#statusPct').textContent = pct + '%';
    $('#progressBar').style.width = pct + '%';
    const track = $('#progressTrack');
    if (track) track.setAttribute('aria-valuenow', String(pct));
  }
}

function updateQuestStepper(step) {
  $('#qstep1').classList.toggle('is-active', step === 1);
  $('#qstep2').classList.toggle('is-active', step === 2);
  $('#qstep3').classList.toggle('is-active', step === 3);
}

function setBusy(busy) {
  S.busy = !!busy;
  ['#btnScan', '#btnInstall', '#btnResolve', '#btnTestIp', '#btnTestPage'].forEach((s) => {
    const el = $(s);
    if (el) el.disabled = !!busy;
  });
  const cancelBtn = $('#btnCancel');
  if (cancelBtn) cancelBtn.hidden = !busy;

  const scanIcon = $('#scanBtnIcon');
  if (scanIcon) {
    scanIcon.className = busy ? 'bi bi-arrow-repeat spin-anim' : 'bi bi-radar';
  }

  $('#statusIcon').className = busy
    ? 'bi bi-hourglass-split text-accent'
    : 'bi bi-shield-shaded status-icon';

  if (busy === 'scan') {
    updateQuestStepper(1);
    SoundFx.radar();
  } else if (busy === 'install' || busy === 'remove' || busy === 'resolve') {
    updateQuestStepper(3);
    SoundFx.forge();
  } else if (!busy) {
    SoundFx.stopLoop();
  }
}

/* ------------------------------------------------------------------ FILTERING */
function visiblePrinters() {
  const q = S.filterText.trim().toLowerCase();
  const cat = S.filterCategory;

  return S.printers.filter((p) => {
    const d = p.driver || {};
    const rarity = getRarity(p);
    const usb = p.conexao === 'usb';

    // Category filter
    if (cat === 'ready' && rarity === 'pending') return false;
    if (cat === 'pending' && rarity !== 'pending') return false;
    if (cat === 'net' && usb) return false;
    if (cat === 'usb' && !usb) return false;

    // Search query
    if (!q) return true;
    const haystack = [
      p.ip, p.fabricante, p.modelo, p.modelo_canonico,
      d.driver_name, d.detalhe, p.hostname, p.mac, p.serial, p.usb_device_id
    ].join(' ').toLowerCase();

    return haystack.includes(q);
  });
}

$$('.pill-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    $$('.pill-btn').forEach((b) => b.classList.remove('is-active'));
    btn.classList.add('is-active');
    S.filterCategory = btn.dataset.filter;
    renderList();
    SoundFx.click();
  });
});

$('#filter').addEventListener('input', (ev) => {
  S.filterText = ev.target.value;
  renderList();
});

/* ------------------------------------------------------------------ RENDER LIST / GRID */
function renderList() {
  const rows = visiblePrinters();
  const box = $('#printerRows');
  const scroll = $('#listBody').scrollTop;

  box.className = S.viewMode === 'grid' ? 'rpg-grid-view' : 'rpg-table-view';
  box.innerHTML = '';

  rows.forEach((p) => {
    const d = p.driver || {};
    const uid = p.uid || p.ip;
    const isChecked = S.checked.has(uid);
    const isSelected = S.selected === uid;
    const usb = p.conexao === 'usb';
    const rarityKey = getRarity(p);
    const rarity = RARITY_LABELS[rarityKey] || RARITY_LABELS.rare;
    const origKey = d.origem || 'pendente';
    const origin = ORIGIN_LABELS[origKey] || ORIGIN_LABELS.pendente;
    const vendorIcon = getVendorIcon(p.fabricante);

    const modelDisplay = p.modelo_canonico || p.modelo || (usb ? 'Dispositivo USB' : 'Impressora de Rede');
    const targetDisplay = usb
      ? `<i class="bi bi-usb-plug-fill me-1"></i>${p.usb_port || 'USB PnP'}`
      : `<i class="bi bi-wifi me-1"></i>${p.ip || 'Sem IP'}`;

    if (S.viewMode === 'grid') {
      // -------------------------------- GRID CARD
      const card = document.createElement('div');
      card.className = `rpg-card-item rarity-${rarityKey} ${isChecked ? 'is-selected' : ''} ${isSelected ? 'is-active' : ''}`;
      card.dataset.uid = uid;
      card.tabIndex = 0;
      card.setAttribute('role', 'checkbox');
      card.setAttribute('aria-checked', isChecked ? 'true' : 'false');
      card.setAttribute('aria-label', modelDisplay);
      card.innerHTML = `
        <div class="card-top">
          <div class="card-identity">
            <div class="vendor-emblem" title="${esc(p.fabricante || 'Desconhecido')}">
              <i class="bi ${vendorIcon}"></i>
            </div>
            <div class="identity-meta">
              <div class="card-title" title="${esc(modelDisplay)}">${esc(modelDisplay)}</div>
              <div class="card-target">${targetDisplay}</div>
            </div>
          </div>
          <input class="form-check-input rpg-checkbox pr-check" type="checkbox" ${isChecked ? 'checked' : ''} title="Vincular este artefato">
        </div>

        <div class="card-badges">
          <span class="rpg-badge ${usb ? 'badge-conn-usb' : 'badge-conn-net'}">
            ${usb ? '<i class="bi bi-usb me-1"></i>USB' : '<i class="bi bi-broadcast me-1"></i>REDE'}
          </span>
          <span class="rpg-badge ${rarity.class}">
            <i class="bi ${rarity.icon} me-1"></i>${rarity.label}
          </span>
          ${!usb && p.snmp_ok ? '<span class="rpg-badge badge-rarity-uncommon"><i class="bi bi-cpu me-1"></i>SNMP</span>' : ''}
          <span class="rpg-badge text-muted" style="border:1px solid var(--rpg-border);">
            ${esc(p.fabricante || 'GENÉRICO')}
          </span>
        </div>

        <div class="driver-rune-box">
          <div class="rune-header">
            <span><i class="bi ${origin.icon} me-1 text-gold"></i>${esc(origin.label)}</span>
            <span class="mono small">${p.confianca_modelo ? `conf. ${p.confianca_modelo}` : ''}</span>
          </div>
          <div class="rune-driver-name" title="${esc(d.driver_name || 'Sem driver específico')}">
            ${esc(d.driver_name || 'Nenhuma runa PCL compatível')}
          </div>
          ${d.detalhe ? `<div class="rune-desc" title="${esc(d.detalhe)}">${esc(d.detalhe)}</div>` : ''}
        </div>

        <div class="card-footer-stats">
          <span class="mono">${usb ? (p.usb_device_id ? p.usb_device_id.slice(0, 24) + '…' : 'PnP') : `portas: ${(p.portas || []).join(',') || '9100'}`}</span>
          <button class="rpg-btn-sm rpg-btn-subtle btn-inspect" type="button" title="Inspecionar atributos">
            <i class="bi bi-info-circle me-1"></i>Atributos
          </button>
        </div>`;
      box.appendChild(card);
    } else {
      // -------------------------------- TACTICAL TABLE ROW
      const row = document.createElement('div');
      row.className = `rpg-table-row rarity-${rarityKey} ${isChecked ? 'is-selected' : ''} ${isSelected ? 'is-active' : ''}`;
      row.dataset.uid = uid;
      row.tabIndex = 0;
      row.setAttribute('role', 'checkbox');
      row.setAttribute('aria-checked', isChecked ? 'true' : 'false');
      row.setAttribute('aria-label', modelDisplay);
      row.innerHTML = `
        <div class="tbl-cell-check">
          <input class="form-check-input rpg-checkbox pr-check" type="checkbox" ${isChecked ? 'checked' : ''}>
        </div>
        <div class="tbl-cell-icon">
          <i class="bi ${vendorIcon}"></i>
        </div>
        <div class="tbl-cell-main">
          <div class="fw-bold text-white text-truncate">${esc(modelDisplay)}</div>
          <div class="mono small text-muted">${targetDisplay} · ${esc(p.fabricante || '')}</div>
        </div>
        <div class="tbl-cell-driver">
          <div class="small fw-semibold text-truncate text-white">
            <i class="bi ${origin.icon} me-1 text-gold"></i>${esc(d.driver_name || 'Sem driver PCL')}
          </div>
          <div class="small text-muted text-truncate">${esc(origin.label)}</div>
        </div>
        <div class="tbl-cell-badges">
          <span class="rpg-badge ${rarity.class}">${rarity.label}</span>
        </div>
        <div class="tbl-cell-actions">
          <button class="rpg-btn-icon-sm btn-inspect" type="button" title="Inspecionar atributos">
            <i class="bi bi-chevron-right"></i>
          </button>
        </div>`;
      box.appendChild(row);
    }
  });

  const emptyEl = $('#emptyState');
  if (emptyEl) {
    emptyEl.style.display = rows.length ? 'none' : '';
  }

  const countBadge = $('#countBadge');
  if (countBadge) {
    countBadge.textContent = rows.length;
  }

  $('#listBody').scrollTop = scroll;
  updateCheckAll();
  updateSummary();

  if (rows.length > 0 && !S.busy) {
    updateQuestStepper(2);
  }
}

function updateCheckAll() {
  const rows = visiblePrinters();
  const on = rows.filter((p) => S.checked.has(p.uid || p.ip)).length;
  const all = $('#checkAll');
  if (all) {
    all.checked = rows.length > 0 && on === rows.length;
    all.indeterminate = on > 0 && on < rows.length;
  }
}

function updateSummary() {
  const total = S.printers.length;
  const sel = S.checked.size;
  const infoEl = $('#selInfo');
  if (infoEl) {
    infoEl.textContent = total ? `${sel} de ${total} artefatos marcados` : '0 selecionadas';
  }
}

/* ------------------------------------------------------------------ LIST INTERACTIONS */
$('#printerRows').addEventListener('keydown', (ev) => {
  if (ev.key !== 'Enter' && ev.key !== ' ') return;
  const item = ev.target.closest('.rpg-card-item, .rpg-table-row');
  if (!item) return;
  ev.preventDefault();
  item.click();
});
$('#printerRows').addEventListener('click', (ev) => {
  const item = ev.target.closest('.rpg-card-item, .rpg-table-row');
  if (!item) return;
  const uid = item.dataset.uid;
  const p = S.printers.find((x) => (x.uid || x.ip) === uid);
  if (!p) return;

  // Inspect button clicked -> open offcanvas
  if (ev.target.closest('.btn-inspect')) {
    S.selected = uid;
    renderDetails(p);
    bootstrap.Offcanvas.getOrCreateInstance($('#detailsPanel')).show();
    SoundFx.click();
    renderList();
    return;
  }

  // Checkbox clicked
  if (ev.target.classList.contains('pr-check')) {
    if (ev.target.checked) {
      S.checked.add(uid);
      SoundFx.select(true);
    } else {
      S.checked.delete(uid);
      SoundFx.select(false);
    }
    updateSummary();
    updateCheckAll();
    renderList();
    return;
  }

  // Card body clicked -> toggle check & update details
  S.selected = uid;
  renderDetails(p);
  if (S.checked.has(uid)) {
    S.checked.delete(uid);
    SoundFx.select(false);
  } else {
    S.checked.add(uid);
    SoundFx.select(true);
  }
  updateSummary();
  updateCheckAll();
  renderList();
});

$('#printerRows').addEventListener('dblclick', (ev) => {
  const item = ev.target.closest('.rpg-card-item, .rpg-table-row');
  if (!item || ev.target.classList.contains('pr-check')) return;
  const uid = item.dataset.uid;
  const p = S.printers.find((x) => (x.uid || x.ip) === uid);
  if (p) {
    S.selected = uid;
    renderDetails(p);
    bootstrap.Offcanvas.getOrCreateInstance($('#detailsPanel')).show();
    SoundFx.click();
    renderList();
  }
});

$('#checkAll').addEventListener('change', (ev) => {
  const check = ev.target.checked;
  visiblePrinters().forEach((p) => {
    const uid = p.uid || p.ip;
    if (check) S.checked.add(uid); else S.checked.delete(uid);
  });
  SoundFx.select(check);
  renderList();
  updateSummary();
});

$('#btnSelectAll').addEventListener('click', () => {
  S.printers.forEach((p) => S.checked.add(p.uid || p.ip));
  SoundFx.select(true);
  renderList();
  updateSummary();
});

$('#btnSelectNone').addEventListener('click', () => {
  S.checked.clear();
  SoundFx.select(false);
  renderList();
  updateSummary();
});

/* ------------------------------------------------------------------ DETALHES DO ARTEFATO */
function renderDetails(p) {
  const d = p.driver || {};
  const usb = p.conexao === 'usb';
  const rarityKey = getRarity(p);
  const rarity = RARITY_LABELS[rarityKey] || RARITY_LABELS.rare;
  const origKey = d.origem || 'pendente';
  const origin = ORIGIN_LABELS[origKey] || ORIGIN_LABELS.pendente;

  const statRow = (lbl, val, isMono = false) => `
    <div class="stat-row">
      <span class="stat-lbl">${esc(lbl)}</span>
      <span class="stat-val ${isMono ? 'mono' : ''}">${esc(val || '—')}</span>
    </div>`;

  $('#detailsBody').innerHTML = `
    <!-- Top Identity -->
    <div class="d-flex align-items-center gap-3 mb-3 pb-3 border-bottom border-secondary-subtle">
      <div class="vendor-emblem fs-2" style="width:48px;height:48px;">
        <i class="bi ${getVendorIcon(p.fabricante)}"></i>
      </div>
      <div class="min-w-0">
        <h5 class="fw-bold mb-1 text-white">${esc(p.modelo_canonico || p.modelo || 'Artefato Místico')}</h5>
        <div class="d-flex gap-2">
          <span class="rpg-badge ${rarity.class}">${rarity.label}</span>
          <span class="rpg-badge ${usb ? 'badge-conn-usb' : 'badge-conn-net'}">${usb ? 'USB' : 'REDE'}</span>
          <span class="rpg-badge text-muted" style="border:1px solid var(--rpg-border);">${esc(p.fabricante || 'Desconhecido')}</span>
        </div>
      </div>
    </div>

    <!-- Bloco de Runas / Driver -->
    <div class="rpg-stat-block">
      <div class="stat-block-title">
        <i class="bi bi-lightning-charge me-1"></i>Runa do Driver PCL
      </div>
      <div class="d-flex align-items-center gap-2 mb-2">
        <span class="rpg-badge ${rarity.class}"><i class="bi ${origin.icon} me-1"></i>${esc(origin.label)}</span>
        <span class="mono small text-muted">conf. ${esc(p.confianca_modelo || 'baixa')}</span>
      </div>
      <div class="fw-bold text-white mb-1">${esc(d.driver_name || 'Driver PCL não encontrado')}</div>
      ${d.detalhe ? `<div class="small text-muted mb-2">${esc(d.detalhe)}</div>` : ''}
      ${statRow('Arquivo .INF', d.inf, true)}
      ${statRow('Origem Runa', d.origem)}
    </div>

    <!-- Bloco de Conexão & Hardware -->
    <div class="rpg-stat-block">
      <div class="stat-block-title">
        <i class="bi bi-cpu me-1"></i>Parâmetros de Hardware
      </div>
      ${usb ? `
        ${statRow('Dispositivo PnP', p.usb_device_id, true)}
        ${statRow('Porta USB', p.usb_port || 'USB', true)}
        ${statRow('Estado no Windows', p.usb_instalada ? 'Já instalada' : 'Não instalada')}
        ${statRow('Hardware IDs', (p.usb_hardware_ids || []).slice(0, 2).join('; '), true)}
      ` : `
        ${statRow('Endereço IP', p.ip, true)}
        ${statRow('Hostname', p.hostname, true)}
        ${statRow('Endereço MAC', p.mac, true)}
        ${statRow('Número de Série', p.serial, true)}
        ${statRow('Portas Abertas', (p.portas || []).join(', '), true)}
        ${statRow('Suporte SNMP', p.snmp_ok ? 'Ativo (v1/v2c)' : 'Inativo')}
      `}
    </div>

    <!-- Bloco de Evidências & Descoberta -->
    <div class="rpg-stat-block">
      <div class="stat-block-title">
        <i class="bi bi-journal-check me-1"></i>Crônica de Descoberta
      </div>
      ${p.motivo ? `<div class="small text-muted mb-2" style="line-height:1.5;">${esc(p.motivo)}</div>` : ''}
      ${p.ews_modelo ? statRow('Identificador EWS', p.ews_modelo) : ''}
      ${p.ipp_modelo ? statRow('Identificador IPP', p.ipp_modelo) : ''}
      ${p.sys_descr ? statRow('Descrição SNMP', p.sys_descr) : ''}
    </div>`;
}

/* ------------------------------------------------------------------ AÇÕES (SCAN, INSTALL, TEST) */
function getSelectedCidrs() {
  const sel = $('#netSelect').value;
  const extra = $('#netExtra').value.trim();
  const parts = [];
  if (sel && !sel.startsWith('(auto')) parts.push(sel);
  if (extra) parts.push(extra);
  return parts.join(', ') || null;
}

$('#btnScan').addEventListener('click', async () => {
  SoundFx.click();
  try {
    await api('/api/scan', { cidrs: getSelectedCidrs() });
    toast('info', 'Exploração Iniciada', 'Sondando sub-redes e portas USB em busca de artefatos...');
  } catch (e) {
    toast('danger', 'Falha ao Iniciar Varredura', e.message);
  }
});

$('#btnCancel').addEventListener('click', async () => {
  SoundFx.click();
  try {
    await api('/api/cancel', {});
    toast('warning', 'Cancelamento', 'Operação cancelada. Parando a música...');
    SoundFx.stopLoop();
  } catch (e) {
    toast('danger', 'Falha ao cancelar', e.message);
  }
});

$('#btnTestIp').addEventListener('click', async () => {
  const ip = $('#ipManual').value.trim();
  if (!ip) {
    toast('warning', 'Alvo Ausente', 'Informe um endereço IP válido (ex.: 192.168.15.50)');
    return;
  }
  SoundFx.click();
  try {
    await api('/api/test-ip', { ip });
    toast('info', 'Sondagem de Alvo', `Enviando sondas arcanas para ${ip}...`);
  } catch (e) {
    toast('danger', 'Falha ao Sondar Alvo', e.message);
  }
});

$('#btnResolve').addEventListener('click', async () => {
  SoundFx.click();
  try {
    await api('/api/resolve', {});
    toast('info', 'Re-resolvendo Runas', 'Reavaliando catálogo de drivers PCL...');
  } catch (e) {
    toast('danger', 'Falha', e.message);
  }
});

$('#btnInstall').addEventListener('click', async () => {
  const uids = Array.from(S.checked);
  if (!uids.length) {
    toast('warning', 'Nenhum Artefato Selecionado', 'Marque as caixas de seleção das impressoras a equipar.');
    return;
  }
  if (!S.admin) {
    toast('danger', 'Privilégio Insuficiente',
      'A forja exige privilégio de Grão-Mestre (Administrador do Windows). Execute o app via run.bat.');
    return;
  }
  SoundFx.click();
  try {
    await api('/api/install', { uids });
    toast('info', 'Forja em Andamento', `Instalando ${uids.length} impressora(s) no Windows...`);
  } catch (e) {
    toast('danger', 'Falha na Forja', e.message);
  }
});

$('#btnTestPage').addEventListener('click', async () => {
  const uids = Array.from(S.checked);
  if (!uids.length) {
    toast('warning', 'Nenhum Artefato Selecionado', 'Selecione as impressoras instaladas para o disparo de teste.');
    return;
  }
  SoundFx.click();
  try {
    await api('/api/test-page', { uids });
    toast('info', 'Prova de Fogo', 'Enviando página de teste para as filas selecionadas...');
  } catch (e) {
    toast('danger', 'Falha', e.message);
  }
});

$('#btnOpenDrivers').addEventListener('click', async () => {
  SoundFx.click();
  try {
    await api('/api/open-drivers', {});
  } catch (e) {
    toast('danger', 'Não foi possível abrir o alforje', e.message);
  }
});

$('#autoDownload').addEventListener('change', async (ev) => {
  SoundFx.click();
  try {
    await api('/api/settings', { auto_download: ev.target.checked });
  } catch (e) {}
});

$('#btnLog').addEventListener('click', () => {
  bootstrap.Offcanvas.getOrCreateInstance($('#logPanel')).show();
  SoundFx.click();
});

/* ------------------------------------------------------------------ EXPURGAMENTO (REMOVER) */
const removeModal = new bootstrap.Modal($('#removeModal'));

async function loadInstalled() {
  $('#installedList').innerHTML =
    '<div class="text-center py-4 text-muted small"><i class="bi bi-hourglass-split me-1"></i>Consultando o reino do Windows…</div>';
  try {
    const r = await api('/api/installed');
    S.installed = r.printers || [];
  } catch (e) {
    S.installed = [];
  }
  renderInstalled();
}

function renderInstalled() {
  const box = $('#installedList');
  $('#installedCount').textContent = S.installed.length;
  if (!S.installed.length) {
    box.innerHTML = '<div class="text-center py-4 text-muted small">Nenhuma impressora encontrada no Windows.</div>';
    return;
  }
  box.innerHTML = S.installed.map((p, i) => `
    <div class="rpg-inst-row">
      <input class="form-check-input rpg-checkbox inst-check" type="checkbox" data-i="${i}" checked>
      <div class="flex-grow-1 min-w-0">
        <div class="inst-name text-truncate">${esc(p.name)}</div>
        <div class="inst-meta text-truncate">${esc(p.driver || '')}${p.port ? ' · ' + esc(p.port) : ''}</div>
      </div>
      ${p.virtual ? '<span class="rpg-badge text-muted" style="border:1px solid var(--rpg-border);">VIRTUAL</span>' : ''}
    </div>`).join('');
}

function selectedInstalled() {
  return $$('.inst-check').filter((c) => c.checked)
    .map((c) => S.installed[Number(c.dataset.i)])
    .filter(Boolean)
    .map((p) => p.name);
}

$('#btnInstAll').addEventListener('click', () => {
  $$('.inst-check').forEach((c) => { c.checked = true; });
  SoundFx.click();
});
$('#btnInstNone').addEventListener('click', () => {
  $$('.inst-check').forEach((c) => { c.checked = false; });
  SoundFx.click();
});
$('#btnRefreshInstalled').addEventListener('click', () => {
  loadInstalled();
  SoundFx.click();
});

$('#btnRemove').addEventListener('click', () => {
  removeModal.show();
  loadInstalled();
  SoundFx.click();
});

$('#btnRemoveSel').addEventListener('click', () => doRemove(false));
$('#btnRemoveAll').addEventListener('click', () => doRemove(true));

async function doRemove(all) {
  const names = all ? S.installed.map((p) => p.name) : selectedInstalled();
  if (!names.length) {
    toast('warning', 'Nada Selecionado', 'Marque ao menos um equipamento para expurgar.');
    return;
  }
  if (!confirm(`Expurgar e banir ${names.length} impressora(s) do sistema operacional?\n\n` +
      names.slice(0, 10).join('\n') + (names.length > 10 ? '\n…' : ''))) {
    return;
  }
  SoundFx.click();
  try {
    await api('/api/remove', {
      names,
      keep_virtual: $('#optKeepVirtual').checked,
      remove_ports: $('#optRemovePorts').checked,
      remove_drivers: $('#optRemoveDrivers').checked,
    });
    removeModal.hide();
    toast('info', 'Expurgando', 'Removendo filas e portas selecionadas...');
  } catch (e) {
    toast('danger', 'Falha no Expurgamento', e.message);
  }
}

/* ------------------------------------------------------------------ SSE (EVENTOS AO VIVO) */
function handleEvent(type, data) {
  switch (type) {
    case 'log':
      addLog(data.text, data.level);
      break;

    case 'status':
      setStatus(data.text, data.pct);
      break;

    case 'printers': {
      const prevCount = S.printers.length;
      S.printers = data.printers || [];
      S.checked = new Set(data.checked || []);
      renderList();
      if (S.printers.length > prevCount) {
        SoundFx.found();
      }
      break;
    }

    case 'printer': {
      const uid = data.uid || data.ip;
      const i = S.printers.findIndex((x) => (x.uid || x.ip) === uid);
      if (i >= 0) S.printers[i] = data; else {
        S.printers.push(data);
        SoundFx.found();
      }
      renderList();
      break;
    }

    case 'busy':
      setBusy(data.busy);
      break;

    case 'done':
      if (data.action === 'install') {
        if (data.fail) {
          toast('danger', 'Forja Parcial', `${data.ok} instalada(s), ${data.fail} falha(s). Verifique o log.`);
          SoundFx.stopLoop();
          SoundFx.gameOver();
        } else {
          toast('success', 'Grande Vitória!', `${data.ok} impressora(s) forjada(s) e instaladas com sucesso!`);
          SoundFx.stopLoop();
          SoundFx.victory();
        }
      } else if (data.action === 'remove') {
        toast('success', 'Expurgamento Concluído', `${data.ok} impressora(s) removida(s).`);
        SoundFx.stopLoop();
      }
      break;
  }
}

function connectEvents() {
  const es = new EventSource('/api/events');
  es.onmessage = (ev) => {
    try {
      const m = JSON.parse(ev.data);
      handleEvent(m.type, m.data);
    } catch (e) {}
  };
  es.onerror = () => {
    setStatus('Conexão arcana com o servidor perdida — reconectando…');
    es.close();
    setTimeout(connectEvents, 2500);
  };
}

/* ------------------------------------------------------------------ INICIALIZAÇÃO */
(async function init() {
  // Sound preference
  try {
    SoundFx.setSoundEnabled(localStorage.getItem('rpg-sound') !== '0');
  } catch (e) {}

  // View mode preference
  try {
    const savedView = localStorage.getItem('rpg-view') || 'grid';
    setViewMode(savedView);
  } catch (e) {
    setViewMode('grid');
  }

  // Theme preference
  try {
    const savedTheme = localStorage.getItem('rpg-theme') || 'industrial';
    applyTheme(savedTheme);
  } catch (e) {
    applyTheme('industrial');
  }

  // Fetch initial state
  try {
    const st = await api('/api/state');
    S.printers = st.printers || [];
    S.checked = new Set(st.checked || []);
    S.admin = !!st.admin;
    S.networks = st.networks || [];
    $('#autoDownload').checked = st.auto_download !== false;

    const badge = $('#adminBadge');
    if (badge) {
      badge.className = 'rpg-rank-badge ' + (S.admin ? 'rank-admin' : 'rank-nonadmin');
      badge.innerHTML = S.admin
        ? '<i class="bi bi-shield-fill-check me-1"></i>Grão-Mestre'
        : '<i class="bi bi-shield-fill-exclamation me-1"></i>Aprendiz (Sem Admin)';
    }

    if (st.networks) {
      $('#netSelect').innerHTML = ['(auto: todas as sub-redes)', ...st.networks]
        .map((o) => `<option value="${esc(o)}">${esc(o)}</option>`).join('');
    }
  } catch (e) {
    toast('danger', 'Falha ao Iniciar', e.message);
  }

  renderList();
  connectEvents();
})();
