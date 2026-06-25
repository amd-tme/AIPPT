/**
 * Live Preview panel — ES Module
 *
 * Manages the session lifecycle, WebSocket connection, and thumbnail grid
 * for the Live Preview view in the AIPPT SPA.
 *
 * Public API (attached to window.* by the inline module script in index.html):
 *   loadScriptPicker()  — populate the script dropdown
 *   openFromUI()        — called by the Open button
 *   forceRender()       — send force_render action over WS
 *   closeSession()      — DELETE session and close WS
 */

// ── Module state ──────────────────────────────────────────────────────────────

let session = null;          // { token, wsUrl, script }
let ws = null;
let slideHashes = {};        // { n: shortHash }  — for per-slide diff
let lastGoodTs = null;
let reconnectTimer = null;
let reconnectDelay = 1000;   // ms, doubles each attempt, capped at 10 000
let detailIndex = 0;         // currently shown slide in detail dialog
let detailSlides = [];       // [{n, url}] from last render_complete

const RECENT_KEY = 'aippt_preview_recent';
const MAX_RECENT = 5;

// ── Helpers ───────────────────────────────────────────────────────────────────

function el(id) { return document.getElementById(id); }

function setStatus(state, detail) {
    const badge = el('preview-status');
    if (!badge) return;
    const labels = {
        idle: 'Idle',
        watching: 'Watching',
        rendering: 'Rendering…',
        updated: detail || 'Updated',
        error: 'Error',
        disconnected: 'Disconnected, retrying…',
        stopped: 'Stopped',
    };
    badge.textContent = labels[state] || state;
    badge.className = `preview-status preview-status--${state}`;
}

function setButtons(hasSession) {
    const forceBtn = el('preview-force-btn');
    const stopBtn  = el('preview-stop-btn');
    if (forceBtn) forceBtn.disabled = !hasSession;
    if (stopBtn)  stopBtn.disabled  = !hasSession;
}

function logEvent(data) {
    const log = el('preview-log');
    if (!log) return;
    const line = JSON.stringify(data);
    log.textContent = log.textContent
        ? log.textContent + '\n' + line
        : line;
    log.scrollTop = log.scrollHeight;
}

function showReconnectBanner(visible) {
    let banner = el('preview-reconnect-banner');
    if (!banner) {
        if (!visible) return;
        banner = document.createElement('div');
        banner.id = 'preview-reconnect-banner';
        banner.textContent = 'WebSocket disconnected — reconnecting…';
        const section = el('preview-view');
        if (section) section.insertBefore(banner, section.querySelector('.preview-toolbar')?.nextSibling || section.firstChild);
    }
    banner.style.display = visible ? '' : 'none';
}

// ── Recent scripts (localStorage) ────────────────────────────────────────────

function getRecent() {
    try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); } catch { return []; }
}

function addRecent(path) {
    const list = getRecent().filter(p => p !== path);
    list.unshift(path);
    try { localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, MAX_RECENT))); } catch { /* ignore */ }
}

// ── Script picker ─────────────────────────────────────────────────────────────

export async function loadScriptPicker() {
    const select = el('preview-script-select');
    if (!select) return;
    select.innerHTML = '<option value="">— pick a script —</option>';

    // Recent entries
    const recent = getRecent();
    if (recent.length) {
        const grp = document.createElement('optgroup');
        grp.label = 'Recent';
        recent.forEach(p => {
            const o = document.createElement('option');
            o.value = p;
            o.textContent = p.split('/').pop() + '  (' + p + ')';
            grp.appendChild(o);
        });
        select.appendChild(grp);
    }

    // Discovered scripts
    try {
        const resp = await fetch('api/preview/scripts');
        if (resp.ok) {
            const scripts = await resp.json();
            if (scripts.length) {
                const grp = document.createElement('optgroup');
                grp.label = 'Discovered';
                scripts.forEach(s => {
                    if (recent.includes(s.path)) return; // already in recent
                    const o = document.createElement('option');
                    o.value = s.path;
                    o.textContent = s.name + '  (' + s.path + ')';
                    grp.appendChild(o);
                });
                select.appendChild(grp);
            }
        }
    } catch { /* server unreachable */ }

    // Sync picker → text input
    select.onchange = () => {
        const input = el('preview-script-path');
        if (input && select.value) input.value = select.value;
    };
}

// ── Session lifecycle ─────────────────────────────────────────────────────────

export async function openFromUI() {
    const pathInput = el('preview-script-path');
    const selectEl  = el('preview-script-select');
    const script = (pathInput?.value || '').trim() || selectEl?.value || '';
    if (!script) { alert('Choose or paste a script path first.'); return; }
    await openSession(script);
}

async function openSession(script) {
    if (session) await closeSession();

    setStatus('watching');
    clearError();
    clearGrid();

    try {
        const resp = await fetch('api/preview/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ script }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            showError({ stage: 'session', exit_code: resp.status, stderr_tail: err.error || err.detail || 'Failed to create session.' });
            setStatus('error');
            return;
        }
        const data = await resp.json();
        session = { token: data.token, wsUrl: data.ws_url, script: data.script };
        setButtons(true);
        addRecent(data.script);
        reconnectDelay = 1000;
        connectWs();
    } catch (e) {
        showError({ stage: 'network', stderr_tail: String(e) });
        setStatus('error');
    }
}

export async function closeSession() {
    clearReconnectTimer();
    if (ws) { ws.onclose = null; ws.close(); ws = null; }
    if (session) {
        const token = session.token;
        session = null;
        try { await fetch(`api/preview/sessions/${token}`, { method: 'DELETE' }); } catch { /* ignore */ }
    }
    setStatus('stopped');
    setButtons(false);
    showReconnectBanner(false);
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

function connectWs() {
    if (!session) return;
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${location.host}${session.wsUrl}`;
    ws = new WebSocket(url);

    ws.onopen = () => {
        showReconnectBanner(false);
        reconnectDelay = 1000;
    };

    ws.onmessage = (evt) => {
        let data;
        try { data = JSON.parse(evt.data); } catch { return; }
        logEvent(data);
        switch (data.event) {
            case 'render_started':  onRenderStarted(data);  break;
            case 'render_complete': onRenderComplete(data); break;
            case 'render_failed':   onRenderFailed(data);   break;
            case 'idle':
                setStatus('watching');
                break;
        }
    };

    ws.onclose = () => {
        ws = null;
        if (session) scheduleReconnect();
    };

    ws.onerror = () => { /* onclose will fire next */ };
}

function scheduleReconnect() {
    clearReconnectTimer();
    setStatus('disconnected');
    showReconnectBanner(true);
    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        if (session) connectWs();
    }, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 10000);
}

function clearReconnectTimer() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
}

export function forceRender() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'force_render' }));
    }
}

// ── Event handlers ────────────────────────────────────────────────────────────

function onRenderStarted(data) {
    setStatus('rendering');
    clearError();
    // Dim existing thumbnails while rendering
    document.querySelectorAll('.preview-thumb img').forEach(img => img.classList.add('dimmed'));
}

function onRenderComplete(data) {
    clearError();
    lastGoodTs = data.ts;
    const elapsed = lastGoodTs ? relativeTime(lastGoodTs) : '';
    setStatus('updated', elapsed ? `Updated ${elapsed}` : 'Updated');

    const slides = data.slides || [];
    detailSlides = slides.map(s => ({ n: s.n, url: s.url }));

    if (!el('preview-grid').children.length) {
        buildGrid(slides);
    } else {
        slides.forEach(s => {
            const shortHash = (s.hash || '').slice(0, 8);
            if (shortHash && slideHashes[s.n] === shortHash) return; // unchanged
            slideHashes[s.n] = shortHash;
            updateThumb(s.n, s.url, shortHash);
        });
    }

    // Un-dim all
    document.querySelectorAll('.preview-thumb img').forEach(img => img.classList.remove('dimmed'));
}

function onRenderFailed(data) {
    setStatus('error');
    showError(data);
    // Dim thumbnails to indicate stale
    document.querySelectorAll('.preview-thumb img').forEach(img => img.classList.add('dimmed'));
}

// ── Thumbnail grid ────────────────────────────────────────────────────────────

function clearGrid() {
    const grid = el('preview-grid');
    if (grid) grid.innerHTML = '';
    slideHashes = {};
    detailSlides = [];
    lastGoodTs = null;
}

function buildGrid(slides) {
    const grid = el('preview-grid');
    if (!grid) return;
    grid.innerHTML = '';
    slides.forEach(s => {
        const shortHash = (s.hash || '').slice(0, 8);
        slideHashes[s.n] = shortHash;
        grid.appendChild(makeThumb(s.n, s.url, shortHash));
    });
}

function makeThumb(n, url, shortHash) {
    const div = document.createElement('div');
    div.className = 'preview-thumb';
    div.dataset.n = n;
    div.onclick = () => openDetail(n - 1);

    const fig = document.createElement('figure');
    const img = document.createElement('img');
    img.src = url + (shortHash ? `?h=${shortHash}` : '');
    img.alt = `Slide ${n}`;
    img.loading = 'lazy';

    const cap = document.createElement('figcaption');
    cap.textContent = `Slide ${n}`;

    fig.appendChild(img);
    fig.appendChild(cap);
    div.appendChild(fig);
    return div;
}

function updateThumb(n, url, shortHash) {
    let thumb = document.querySelector(`.preview-thumb[data-n="${n}"]`);
    if (!thumb) {
        // New slide appeared (e.g. deck grew) — append
        const grid = el('preview-grid');
        if (grid) { thumb = makeThumb(n, url, shortHash); grid.appendChild(thumb); }
        return;
    }
    const img = thumb.querySelector('img');
    if (img) {
        img.src = url + (shortHash ? `?h=${shortHash}` : '');
        img.classList.remove('dimmed');
    }
    // Pulse animation
    thumb.classList.remove('changed');
    void thumb.offsetWidth; // reflow
    thumb.classList.add('changed');
    setTimeout(() => thumb.classList.remove('changed'), 700);
}

// ── Detail view ───────────────────────────────────────────────────────────────

function openDetail(idx) {
    if (!detailSlides.length) return;
    detailIndex = Math.max(0, Math.min(idx, detailSlides.length - 1));

    let dlg = el('preview-detail-dialog');
    if (!dlg) {
        dlg = document.createElement('dialog');
        dlg.id = 'preview-detail-dialog';
        dlg.innerHTML = `
            <img id="preview-detail-img" alt="">
            <div id="preview-detail-nav">
                <button id="preview-detail-prev" onclick="window.__previewModule.detailPrev()">&#8592; Prev</button>
                <span id="preview-detail-label"></span>
                <button id="preview-detail-next" onclick="window.__previewModule.detailNext()">Next &#8594;</button>
                <button onclick="this.closest('dialog').close()" style="margin-left:1rem;">Close</button>
            </div>`;
        document.body.appendChild(dlg);
        dlg.addEventListener('keydown', e => {
            if (e.key === 'ArrowLeft')  { e.preventDefault(); detailPrev(); }
            if (e.key === 'ArrowRight') { e.preventDefault(); detailNext(); }
            if (e.key === 'Escape')     { dlg.close(); }
        });
    }
    renderDetail();
    dlg.showModal();
}

function renderDetail() {
    const slide = detailSlides[detailIndex];
    if (!slide) return;
    const img   = el('preview-detail-img');
    const label = el('preview-detail-label');
    if (img)   img.src = slide.url;
    if (label) label.textContent = `Slide ${slide.n} of ${detailSlides.length}`;
    el('preview-detail-prev').disabled = detailIndex === 0;
    el('preview-detail-next').disabled = detailIndex === detailSlides.length - 1;
}

export function detailPrev() {
    if (detailIndex > 0) { detailIndex--; renderDetail(); }
}

export function detailNext() {
    if (detailIndex < detailSlides.length - 1) { detailIndex++; renderDetail(); }
}

// ── Error display ─────────────────────────────────────────────────────────────

function showError(data) {
    const box = el('preview-error');
    if (!box) return;
    const stage    = data.stage    ? ` at stage: <strong>${data.stage}</strong>` : '';
    const exitCode = data.exit_code != null ? ` (exit ${data.exit_code})` : '';
    const stderr   = data.stderr_tail || '';
    box.innerHTML = `
        <div class="preview-error-title">&#x2717; Render failed${stage}${exitCode}</div>
        ${stderr ? `<pre class="preview-error-stderr">${escHtml(stderr)}</pre>` : ''}`;
    box.style.display = '';
}

function clearError() {
    const box = el('preview-error');
    if (box) { box.innerHTML = ''; box.style.display = 'none'; }
}

function escHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function relativeTime(ts) {
    const diff = Math.round((Date.now() / 1000) - ts);
    if (diff < 5)   return 'just now';
    if (diff < 60)  return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
}
