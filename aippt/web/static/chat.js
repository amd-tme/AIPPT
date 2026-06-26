/**
 * Chat-with-a-Deck — slide-scoped chat panel.
 *
 * Renders inside #slide-dialog as a collapsible panel beneath the existing
 * AI actions row.  Uses the SSE streaming endpoint.
 *
 * Exposed on window as window.__chatModule so index.html can call:
 *   chatOpenForSlide(slideId, deckId)  — called when slide dialog opens
 *   chatClose()                        — called when slide dialog closes
 */

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------
let _slideId = null;
let _deckId = null;
let _convId = null;
let _streaming = false;
let _cancelFn = null;   // AbortController.abort bound fn
let _streamBuf = '';    // accumulated streaming text
let _streamEl = null;   // DOM element being built during stream

// ---------------------------------------------------------------------------
// Entry points called from index.html
// ---------------------------------------------------------------------------

export async function chatOpenForSlide(slideId, deckId) {
    _slideId = slideId;
    _deckId = deckId;
    _ensurePanel();
    await _loadConversations();
}

export function chatClose() {
    if (_streaming && _cancelFn) _cancelFn();
    _slideId = null;
    _deckId = null;
    _convId = null;
    _streaming = false;
}

// ---------------------------------------------------------------------------
// Panel bootstrap
// ---------------------------------------------------------------------------

function _ensurePanel() {
    let panel = document.getElementById('slide-chat-panel');
    if (!panel) {
        panel = _buildPanel();
        const dialog = document.getElementById('slide-dialog');
        const article = dialog?.querySelector('article');
        if (article) article.appendChild(panel);
    }
    panel.style.display = 'flex';
}

function _buildPanel() {
    const panel = document.createElement('div');
    panel.id = 'slide-chat-panel';

    panel.innerHTML = `
      <div class="chat-conv-bar">
        <select id="chat-conv-select" onchange="window.__chatModule._onConvChange()">
          <option value="">— select or start conversation —</option>
        </select>
        <button class="outline chat-tab-btn" onclick="window.__chatModule._newConv()">+ New</button>
        <button class="outline chat-tab-btn" id="chat-del-btn" onclick="window.__chatModule._deleteConv()" style="display:none;">Delete</button>
      </div>
      <div class="chat-history" id="chat-history"></div>
      <div class="chat-input-row" id="chat-input-row" style="display:none;">
        <textarea id="chat-input" rows="2" placeholder="Ask about this slide…"
                  onkeydown="window.__chatModule._onKeydown(event)"></textarea>
        <button id="chat-send-btn" onclick="window.__chatModule._sendMessage()">Send</button>
        <button id="chat-stop-btn" style="display:none;" onclick="window.__chatModule._stopStream()">Stop</button>
      </div>
    `;
    return panel;
}

// ---------------------------------------------------------------------------
// Conversation management
// ---------------------------------------------------------------------------

async function _loadConversations() {
    if (!_deckId) return;
    const resp = await fetch(`api/chat/conversations?deck_id=${_deckId}`);
    if (!resp.ok) return;
    const convs = await resp.json();

    const sel = document.getElementById('chat-conv-select');
    sel.innerHTML = '<option value="">— select or start conversation —</option>';
    for (const c of convs) {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = c.title;
        sel.appendChild(opt);
    }

    // Auto-select first if only one
    if (convs.length === 1) {
        sel.value = convs[0].id;
        await _onConvChange();
    }
}

async function _onConvChange() {
    const sel = document.getElementById('chat-conv-select');
    const id = parseInt(sel.value);
    document.getElementById('chat-del-btn').style.display = id ? '' : 'none';
    document.getElementById('chat-input-row').style.display = id ? '' : 'none';
    if (!id) { _convId = null; document.getElementById('chat-history').innerHTML = ''; return; }

    _convId = id;
    const resp = await fetch(`api/chat/conversations/${id}`);
    if (!resp.ok) return;
    const data = await resp.json();
    _renderHistory(data.messages);
}

async function _newConv() {
    if (!_deckId) return;
    const title = prompt('Conversation title (or leave blank):', `Slide ${_slideId} chat`);
    if (title === null) return;   // cancelled
    const resp = await fetch('api/chat/conversations', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({deck_id: _deckId, title: title || `Slide ${_slideId} chat`}),
    });
    if (!resp.ok) { alert('Failed to create conversation'); return; }
    const conv = await resp.json();
    _convId = conv.id;
    await _loadConversations();
    document.getElementById('chat-conv-select').value = _convId;
    document.getElementById('chat-del-btn').style.display = '';
    document.getElementById('chat-input-row').style.display = '';
    document.getElementById('chat-history').innerHTML = '';
}

async function _deleteConv() {
    if (!_convId || !confirm('Delete this conversation?')) return;
    const resp = await fetch(`api/chat/conversations/${_convId}`, {method: 'DELETE'});
    if (!resp.ok) { alert('Failed to delete'); return; }
    _convId = null;
    document.getElementById('chat-history').innerHTML = '';
    document.getElementById('chat-input-row').style.display = 'none';
    document.getElementById('chat-del-btn').style.display = 'none';
    await _loadConversations();
}

// ---------------------------------------------------------------------------
// Message rendering
// ---------------------------------------------------------------------------

function _renderHistory(messages) {
    const el = document.getElementById('chat-history');
    el.innerHTML = '';
    for (const m of messages) {
        _appendMsg(m.role, m.content);
    }
    el.scrollTop = el.scrollHeight;
}

function _appendMsg(role, content) {
    const el = document.getElementById('chat-history');
    const div = document.createElement('div');
    div.className = `chat-msg chat-msg--${role}`;
    div.textContent = content;
    el.appendChild(div);
    el.scrollTop = el.scrollHeight;
    return div;
}

// ---------------------------------------------------------------------------
// Sending messages and SSE streaming
// ---------------------------------------------------------------------------

async function _sendMessage() {
    if (!_convId || _streaming) return;
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text) return;

    input.value = '';
    input.disabled = true;
    document.getElementById('chat-send-btn').style.display = 'none';
    document.getElementById('chat-stop-btn').style.display = '';

    _appendMsg('user', text);

    // Start streaming assistant bubble
    const histEl = document.getElementById('chat-history');
    _streamBuf = '';
    _streamEl = document.createElement('div');
    _streamEl.className = 'chat-msg chat-msg--assistant chat-msg--streaming';
    _streamEl.textContent = '…';
    histEl.appendChild(_streamEl);
    histEl.scrollTop = histEl.scrollHeight;

    const ctrl = new AbortController();
    _cancelFn = () => {
        ctrl.abort();
        _cancelStream();
    };
    _streaming = true;

    const ntid = (localStorage.getItem('aippt_ntid') || '').trim();
    try {
        const resp = await fetch(`api/chat/conversations/${_convId}/messages`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: text, slide_id: _slideId, ntid: ntid || undefined}),
            signal: ctrl.signal,
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({error: 'Unknown error'}));
            _streamEl.textContent = `Error: ${err.error || resp.status}`;
            _streamEl.classList.remove('chat-msg--streaming');
            _finishStream();
            return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let partial = '';

        while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            partial += decoder.decode(value, {stream: true});
            const lines = partial.split('\n');
            partial = lines.pop();
            for (const line of lines) {
                if (!line.startsWith('data:')) continue;
                const raw = line.slice(5).trim();
                if (!raw) continue;
                let evt;
                try { evt = JSON.parse(raw); } catch { continue; }
                _handleSseEvent(evt);
            }
        }
    } catch (e) {
        if (e.name !== 'AbortError') {
            _streamEl.textContent = `Connection error: ${e.message}`;
        }
    }
    _finishStream();
}

function _handleSseEvent(evt) {
    if (evt.type === 'chunk') {
        _streamBuf += evt.text;
        _streamEl.textContent = _streamBuf;
        document.getElementById('chat-history').scrollTop = document.getElementById('chat-history').scrollHeight;
    } else if (evt.type === 'patch_applied') {
        _onPatchApplied(evt.slide_id, evt.field);
    } else if (evt.type === 'patch_failed') {
        _onPatchFailed(evt.slide_id, evt.field, evt.reason);
    } else if (evt.type === 'cancelled') {
        _streamEl.classList.remove('chat-msg--streaming');
        _finishStream();
    } else if (evt.type === 'done') {
        _streamEl.classList.remove('chat-msg--streaming');
    } else if (evt.type === 'error') {
        _streamEl.textContent = `Error: ${evt.message}`;
        _streamEl.classList.remove('chat-msg--streaming');
    }
}

function _onPatchApplied(slideId, field) {
    const histEl = document.getElementById('chat-history');
    const note = document.createElement('div');
    note.className = 'chat-msg chat-msg--patch';
    note.innerHTML =
        `<span class="chat-patch-badge chat-patch-badge--applied">&#x2713; Applied: ${field}</span>` +
        `<button class="chat-undo-btn" onclick="window.__chatModule._undoPatch(${slideId},'${field}',this)">Undo</button>`;
    histEl.appendChild(note);
    histEl.scrollTop = histEl.scrollHeight;
}

function _onPatchFailed(slideId, field, reason) {
    const histEl = document.getElementById('chat-history');
    const note = document.createElement('div');
    note.className = 'chat-msg chat-msg--patch';
    note.innerHTML = `<span class="chat-patch-badge chat-patch-badge--failed">&#x2717; Failed: ${field} — ${reason}</span>`;
    histEl.appendChild(note);
    histEl.scrollTop = histEl.scrollHeight;
}

async function _undoPatch(slideId, field, btn) {
    btn.disabled = true;
    const resp = await fetch(`api/chat/slides/${slideId}/revert`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({field}),
    });
    if (resp.ok) {
        btn.textContent = 'Undone';
        btn.style.opacity = '0.5';
    } else {
        const err = await resp.json().catch(() => ({error: 'failed'}));
        btn.textContent = 'Failed';
        btn.title = err.error || 'revert failed';
        btn.disabled = false;
    }
}

function _stopStream() {
    if (_cancelFn) {
        fetch(`api/chat/conversations/${_convId}/cancel`, {method: 'POST'}).catch(() => {});
        _cancelFn();
    }
}

function _cancelStream() {
    if (_streamEl) {
        _streamEl.classList.remove('chat-msg--streaming');
        _streamEl.textContent += ' [cancelled]';
    }
    _finishStream();
}

function _finishStream() {
    _streaming = false;
    _cancelFn = null;
    _streamEl = null;
    _streamBuf = '';
    const input = document.getElementById('chat-input');
    if (input) {
        input.disabled = false;
        input.focus();
    }
    const sendBtn = document.getElementById('chat-send-btn');
    if (sendBtn) sendBtn.style.display = '';
    const stopBtn = document.getElementById('chat-stop-btn');
    if (stopBtn) stopBtn.style.display = 'none';
}

// ---------------------------------------------------------------------------
// Keyboard shortcut: Ctrl+Enter / Cmd+Enter sends
// ---------------------------------------------------------------------------

function _onKeydown(evt) {
    if (evt.key === 'Enter' && (evt.ctrlKey || evt.metaKey)) {
        evt.preventDefault();
        _sendMessage();
    }
}

// ---------------------------------------------------------------------------
// Expose internals for onclick handlers (since we're an ES module)
// ---------------------------------------------------------------------------
export {
    _onConvChange,
    _newConv,
    _deleteConv,
    _onKeydown,
    _sendMessage,
    _stopStream,
    _undoPatch,
};
