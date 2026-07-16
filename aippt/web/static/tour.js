/**
 * AIPPT Onboarding Tours — vanilla JS
 * Ported from zsyed-amd/rocm-rag-assistant (amd-ui-reskin branch)
 * Spotlight + clip-path overlay, no dependencies.
 *
 * Two tours share the same overlay/spotlight/tooltip DOM nodes:
 *   window.__tour   — main onboarding (5 steps + create-panel step)
 *   window.__lpTour — Live Preview mini-tour (triggered on first LP visit)
 */
(function () {
    'use strict';

    const PAD          = 10;
    const TOOLTIP_W    = 300;
    const TOOLTIP_H_EST = 190;

    // ── Shared DOM ────────────────────────────────────────────────────────────

    let overlay, spotlight, tooltip;
    let activeTour = null;

    function mountShared() {
        overlay = mk('div', 'tour-overlay');
        overlay.style.display = 'none';
        overlay.addEventListener('click', () => activeTour?.dismiss());

        spotlight = mk('div', 'tour-spotlight');
        spotlight.style.display = 'none';

        tooltip = mk('div', 'tour-tooltip');
        tooltip.style.display = 'none';

        document.body.append(overlay, spotlight, tooltip);

        window.addEventListener('resize',  () => { if (activeTour) activeTour._render(); });
        window.addEventListener('keydown', (e) => {
            if (!activeTour) return;
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') activeTour.next();
            if (e.key === 'ArrowLeft'  || e.key === 'ArrowUp')   activeTour.prev();
            if (e.key === 'Escape') activeTour.dismiss();
        });
    }

    function mk(tag, cls) {
        const d = document.createElement(tag);
        if (cls) d.className = cls;
        return d;
    }

    // ── Global relay helpers (inline onclick can't reach closures) ───────────

    window.__tourNext    = () => activeTour?.next();
    window.__tourPrev    = () => activeTour?.prev();
    window.__tourDismiss = () => activeTour?.dismiss();

    // ── Tour factory ──────────────────────────────────────────────────────────

    function createTour({ steps, storageKey, pillLabel, onDismiss }) {
        let step    = 0;
        let visible = false;
        let pill;

        // Pill button
        pill = mk('button', 'tour-pill');
        pill.innerHTML = `<span>?</span> ${pillLabel}`;
        pill.addEventListener('click', start);
        pill.style.display = 'none';
        document.body.appendChild(pill);

        function start() {
            if (activeTour && activeTour !== api) activeTour.dismiss();
            activeTour = api;
            step = 0;
            visible = true;
            pill.style.display = 'none';
            overlay.style.display   = '';
            spotlight.style.display = '';
            tooltip.style.display   = '';
            _render();
        }

        function dismiss() {
            visible = false;
            activeTour = null;
            overlay.style.display   = 'none';
            spotlight.style.display = 'none';
            tooltip.style.display   = 'none';
            pill.style.display = '';
            localStorage.setItem(storageKey, '1');
            onDismiss?.();
        }

        function prev() { if (step > 0) { step--; _render(); } }
        function next() { if (step < steps.length - 1) { step++; _render(); } else dismiss(); }
        function showPill() { pill.style.display = ''; }
        function hidePill() { pill.style.display = 'none'; }

        function _render() {
            const s = steps[step];

            // Run any onEnter callback (e.g. open a panel)
            if (s.onEnter) s.onEnter();

            const delay = s.onEnter ? 320 : 60;
            setTimeout(() => {
                const target = document.querySelector(`[data-tour="${s.target}"]`);
                if (!target) { next(); return; }

                target.scrollIntoView({ behavior: 'smooth', block: 'center' });

                setTimeout(() => {
                    const r       = target.getBoundingClientRect();
                    const x       = r.left   - PAD;
                    const y       = r.top    - PAD;
                    const right   = r.right  + PAD;
                    const bottom  = r.bottom + PAD;
                    const w       = r.width  + PAD * 2;
                    const h       = r.height + PAD * 2;

                    // Spotlight
                    Object.assign(spotlight.style, {
                        left: `${x}px`, top: `${y}px`,
                        width: `${w}px`, height: `${h}px`,
                    });

                    // Overlay clip-path cutout
                    overlay.style.clipPath = `polygon(
                        0px 0px,
                        0px ${bottom}px,
                        ${x}px ${bottom}px,
                        ${x}px ${y}px,
                        ${right}px ${y}px,
                        ${right}px ${bottom}px,
                        0px ${bottom}px,
                        0px 100vh,
                        100vw 100vh,
                        100vw 0px
                    )`;

                    // Tooltip position
                    const pos = _tooltipPos(r);
                    Object.assign(tooltip.style, { top: `${pos.top}px`, left: `${pos.left}px` });

                    // Tooltip HTML
                    const isLast = step === steps.length - 1;
                    const dots   = steps.map((_, i) =>
                        `<span class="tour-dot${i === step ? ' active' : ''}"></span>`).join('');

                    tooltip.innerHTML = `
                        <div class="tour-tt-header">
                            <span class="tour-step-label">${step + 1} / ${steps.length}</span>
                            <button class="tour-skip-btn" onclick="window.__tourDismiss()">Skip</button>
                        </div>
                        <div class="tour-tt-title">${s.title}</div>
                        <div class="tour-tt-body">${s.body}</div>
                        <div class="tour-tt-footer">
                            <button class="tour-prev-btn" ${step === 0 ? 'disabled' : ''}
                                onclick="window.__tourPrev()">← Prev</button>
                            <div style="display:flex;align-items:center;gap:0.3rem;">${dots}</div>
                            <button class="tour-next-btn"
                                onclick="window.__tourNext()">
                                ${isLast ? 'Get Started ✓' : 'Next →'}
                            </button>
                        </div>`;
                }, 80);
            }, delay);
        }

        function _tooltipPos(r) {
            const vw  = window.innerWidth;
            const vh  = window.innerHeight;
            const gap = PAD + 12;
            let top, left;

            if (r.bottom + gap + TOOLTIP_H_EST < vh) {
                top = r.bottom + gap;
            } else {
                top = r.top - gap - TOOLTIP_H_EST;
            }
            left = r.left + r.width / 2 - TOOLTIP_W / 2;
            left = Math.max(16, Math.min(left, vw - TOOLTIP_W - 16));
            top  = Math.max(16, top);
            return { top, left };
        }

        const api = { start, dismiss, prev, next, showPill, hidePill, _render,
                      get visible() { return visible; } };
        return api;
    }

    // ── Main tour steps ───────────────────────────────────────────────────────

    const MAIN_STEPS = [
        {
            target: 'tour-nav',
            title: 'Welcome to AIPPT',
            body: 'Navigate between your Slide Library, Search, Settings, and Live Preview using the top nav bar.',
        },
        {
            target: 'tour-library',
            title: 'Your Slide Library',
            body: 'All your cataloged decks appear here as cards. Click any card to browse slides, chat with AI, and make edits.',
        },
        {
            target: 'tour-create',
            title: 'Create from Outline',
            body: 'Click this card to open the deck builder — write a markdown outline and AIPPT generates a full PowerPoint.',
        },
        {
            target: 'tour-create-form',
            title: 'Write Your Outline',
            body: 'Use ## for slide titles and — for bullet points. Toggle AI enhancement to auto-improve your content before generating.',
            onEnter: () => { if (typeof openCreatePanel === 'function') openCreatePanel(); },
        },
        {
            target: 'tour-search',
            title: 'Search Slides',
            body: 'Find any slide across all your decks by title or tag, then remix results into a brand-new deck.',
        },
        {
            target: 'tour-preview',
            title: 'Live Preview',
            body: 'Open a slides-as-code script and watch your deck render in real time. Click Live Preview to explore it further.',
        },
    ];

    // ── Live Preview mini-tour steps ──────────────────────────────────────────

    const LP_STEPS = [
        {
            target: 'tour-lp-script',
            title: 'Pick a Script',
            body: 'Select a recent script from the dropdown or paste an absolute path to any .js deck script on disk.',
        },
        {
            target: 'tour-lp-open',
            title: 'Open & Watch',
            body: 'Click Open to start a live session. AIPPT watches the file for changes and re-renders automatically.',
        },
        {
            target: 'tour-lp-viewer',
            title: 'Slide Viewer',
            body: 'Once a script is open, your rendered deck appears below. Use the ← → arrows or the number strip to navigate between slides.',
        },
        {
            target: 'tour-lp-grid',
            title: 'Render Status & Grid',
            body: 'The status badge shows Idle / Rendering / Ready. After opening, switch to Grid view to see all slides as thumbnails at once.',
        },
        {
            target: 'tour-lp-save',
            title: 'Save to Library',
            body: 'Happy with the result? Save the rendered deck to your Slide Library to browse, tag, and share it.',
        },
    ];

    // ── Init ──────────────────────────────────────────────────────────────────

    document.addEventListener('DOMContentLoaded', () => {
        mountShared();

        window.__tour = createTour({
            steps: MAIN_STEPS,
            storageKey: 'aippt_tour_done',
            pillLabel: 'Tour',
        });

        window.__lpTour = createTour({
            steps: LP_STEPS,
            storageKey: 'aippt_lp_tour_done',
            pillLabel: 'LP Tour',
        });

        // Main tour: auto-start on first visit
        if (!localStorage.getItem('aippt_tour_done')) {
            setTimeout(window.__tour.start, 900);
        } else {
            window.__tour.showPill();
        }

        // LP tour pill only shown when on preview view (wired via showPreview hook below)
    });

    // Hook into showPreview — called from index.html
    // Wrapped so it fires after the original showPreview runs
    document.addEventListener('DOMContentLoaded', () => {
        const _orig = window.showPreview;
        if (typeof _orig === 'function') {
            window.showPreview = function (...args) {
                _orig.apply(this, args);
                window.__lpTour?.showPill();
                if (!localStorage.getItem('aippt_lp_tour_done')) {
                    setTimeout(window.__lpTour.start, 400);
                }
            };
        }
    });

})();
