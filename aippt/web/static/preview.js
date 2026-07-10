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
let lastGoodTs = null;
let reconnectTimer = null;
let reconnectDelay = 1000;   // ms, doubles each attempt, capped at 10 000
let pptxViewer = null;       // PPTXViewer instance (pptxviewjs)

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
    const saveBtn  = el('preview-save-btn');
    if (forceBtn) forceBtn.disabled = !hasSession;
    if (stopBtn)  stopBtn.disabled  = !hasSession;
    if (saveBtn)  saveBtn.disabled  = !hasSession;
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
    _clearViewer();

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
    _clearViewer();
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
}

async function onRenderComplete(data) {
    clearError();
    lastGoodTs = data.ts;

    if (!data.pptx_url) {
        setStatus('updated', `Updated ${relativeTime(lastGoodTs)}`);
        return;
    }

    const canvas = el('preview-canvas');
    if (!canvas) return;

    // The browser-side renderer must be present. If the PptxViewJS bundle
    // failed to load (e.g. CDN blocked on an air-gapped network), don't leave
    // a misleading green "Updated" badge over a blank viewer — surface it.
    if (!window.PptxViewJS) {
        setStatus('error');
        showError({
            stage: 'viewer',
            stderr_tail: 'PptxViewJS failed to load — the deck rendered on the '
                + 'server but cannot be displayed. Check that '
                + 'static/vendor/PptxViewJS.min.js is reachable.',
        });
        return;
    }

    setStatus('updated', `Updated ${relativeTime(lastGoodTs)}`);

    // Destroy previous viewer before loading new deck
    if (pptxViewer) {
        try { pptxViewer.destroy?.(); } catch { /* ignore */ }
        pptxViewer = null;
    }

    // Show viewer first so clientWidth is non-zero when we measure the container.
    // (If viewer is display:none, clientWidth returns 0 and PptxViewJS renders
    // to a 0x0 canvas, producing a blank result on first Open.)
    el('preview-viewer').style.display = '';

    // Set canvas pixel dimensions before PPTXViewer initialises — it reads
    // CSS width as a raw number so "100%" becomes 100px. Setting attributes
    // explicitly and removing all CSS width avoids the misread entirely.
    const wrap = el('preview-canvas-wrap');
    const displayW = (wrap && wrap.clientWidth > 0) ? wrap.clientWidth : 960;
    const displayH = Math.round(displayW * 9 / 16);
    canvas.width  = displayW;
    canvas.height = displayH;
    canvas.style.width  = '';
    canvas.style.height = '';

    const { PPTXViewer } = window.PptxViewJS;
    pptxViewer = new PPTXViewer({ canvas, fitMode: 'contain' });

    pptxViewer.on('loadComplete', ({ slideCount }) => {
        _updateCounter(pptxViewer.currentSlideIndex ?? 0, slideCount);
        _buildThumbStrip(slideCount);
        pptxViewer.render();
    });

    pptxViewer.on('slideChanged', (index) => {
        _updateCounter(index, pptxViewer.slideCount);
        _highlightThumb(index);
    });

    try {
        await pptxViewer.loadFromUrl(data.pptx_url + `?t=${Date.now()}`);
    } catch (e) {
        setStatus('error');
        showError({ stage: 'viewer', stderr_tail: 'Failed to render the deck in the browser: ' + String(e) });
    }
}

function onRenderFailed(data) {
    setStatus('error');
    showError(data);
}

// ── PptxViewJS helpers ────────────────────────────────────────────────────────

function _updateCounter(index, total) {
    const counter = el('preview-slide-counter');
    if (counter) counter.textContent = `Slide ${index + 1} of ${total}`;
}

function _buildThumbStrip(slideCount) {
    const strip = el('preview-thumb-strip');
    if (!strip) return;
    strip.innerHTML = '';
    for (let i = 0; i < slideCount; i++) {
        const btn = document.createElement('button');
        btn.className = 'preview-thumb-btn' + (i === 0 ? ' active' : '');
        btn.dataset.index = i;
        btn.textContent = `${i + 1}`;
        btn.style.cssText = 'min-width:2rem; padding:0.2rem 0.4rem; font-size:0.75rem;';
        btn.onclick = () => pptxViewer?.goToSlide(i);
        strip.appendChild(btn);
    }
}

function _highlightThumb(index) {
    const strip = el('preview-thumb-strip');
    if (!strip) return;
    strip.querySelectorAll('.preview-thumb-btn').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.index) === index);
    });
}

function _clearViewer() {
    if (pptxViewer) {
        try { pptxViewer.destroy?.(); } catch { /* ignore */ }
        pptxViewer = null;
    }
    const viewer = el('preview-viewer');
    if (viewer) viewer.style.display = 'none';
    const strip = el('preview-thumb-strip');
    if (strip) strip.innerHTML = '';
    lastGoodTs = null;
}

export function prevSlide() { pptxViewer?.previousSlide?.(); }
export function nextSlide() { pptxViewer?.nextSlide?.(); }
export function getSessionToken() { return session?.token ?? null; }

/**
 * Capture each rendered slide as a PNG data URL for Save-to-Library.
 *
 * Renders every slide to an offscreen canvas via PptxViewJS
 * `renderSlide(index, canvas)` and reads it back with `toBlob`. Returns
 * `[{position, data}]` where `data` is a base64 data URL, ready to POST to the
 * catalog endpoint. Best-effort: any per-slide failure is skipped; if the
 * viewer isn't ready or the API is missing, returns [] so the caller falls back
 * to cataloging with placeholder cards (current behavior).
 *
 * PptxViewJS `render` mutates `currentSlideIndex` even when drawing to an
 * offscreen canvas, so the visible viewer is restored to its prior slide after
 * capture to avoid a surprise jump in the panel.
 *
 * @param {number} width  Target capture width in px (default 1280).
 */
export async function captureSlideImages(width = 1280) {
    try {
        if (!pptxViewer || typeof pptxViewer.renderSlide !== 'function') return [];
        const count = pptxViewer.slideCount || 0;
        if (!count) return [];

        const height = Math.round(width * 9 / 16);
        const offscreen = document.createElement('canvas');
        offscreen.width = width;
        offscreen.height = height;

        const restoreIndex = pptxViewer.currentSlideIndex ?? 0;
        const images = [];
        try {
            for (let i = 0; i < count; i++) {
                try {
                    // renderSlide(index, canvas, opts) — draw slide `i` to the
                    // offscreen canvas.
                    await pptxViewer.renderSlide(i, offscreen);
                    const blob = await new Promise((resolve) => {
                        offscreen.toBlob(resolve, 'image/png');
                    });
                    if (!blob) continue;
                    // Blob → base64 without FileReader (which is unavailable in
                    // some embedded/webview contexts). The server accepts a bare
                    // base64 string or a data URL.
                    const buf = new Uint8Array(await blob.arrayBuffer());
                    let bin = '';
                    for (let b = 0; b < buf.length; b++) bin += String.fromCharCode(buf[b]);
                    const b64 = btoa(bin);
                    images.push({ position: i + 1, data: b64 });
                } catch (e) {
                    console.warn(`Slide ${i + 1} thumbnail capture failed:`, e);
                }
            }
        } finally {
            // Restore the visible viewer to the slide the user was on.
            try { await pptxViewer.goToSlide(restoreIndex); } catch { /* ignore */ }
        }
        return images;
    } catch (e) {
        console.warn('captureSlideImages failed:', e);
        return [];
    }
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
