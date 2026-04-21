# Screenshot Capture Guide

This guide consolidates and extends the screenshot guidance from the `deck-reviewer` skill. It covers Playwright-based capture workflows for use as `IMAGE:` directives in presentation outlines.

---

## Browser Setup

Before capturing any screenshot, resize the browser to 1920x1080. This produces images with a 16:9 aspect ratio that matches slide dimensions, ensuring captured content fills the slide cleanly without letterboxing or pillarboxing.

```
browser_resize: width=1920, height=1080
```

For element-specific captures (cropping to a single UI component, chart, or panel), pass the `ref` parameter from a `browser_snapshot` to `browser_take_screenshot`. The screenshot will be cropped to that element's bounding box rather than the full viewport.

Maintain a consistent viewport size across all captures in a session. Changing the window size mid-session can produce images at different resolutions that look inconsistent when placed on adjacent slides.

---

## Capture Workflow

Follow these steps in order for reliable, clean screenshots:

1. **Confirm the URL is accessible** — navigate with `browser_navigate`, check for error pages or redirect loops before proceeding.
2. **Resize browser to 1920x1080** — call `browser_resize` with `width: 1920, height: 1080`.
3. **Navigate to the target URL** — if you redirected to a different page in step 1, navigate explicitly to the intended URL now.
4. **Wait for content to load** — use `browser_wait_for` with a key piece of text that appears only after the page finishes rendering (e.g., a heading, a data value, or a UI label).
5. **Dismiss modals and welcome screens** — press Escape or click the dismiss button. Many apps show onboarding overlays on first load; these will obscure the content you want.
6. **Hide overlays that would clutter the image** — dismiss cookie consent banners, close dev tools panels, hide browser extension overlays, and collapse any sidebar that is not part of the target content.
7. **Interact as needed** — click tabs to show the right panel, expand collapsed sections, scroll to the content of interest, or toggle between views (e.g., light/dark mode).
8. **Capture the screenshot** — call `browser_take_screenshot` with `type: "png"`. For element-specific captures, include the `ref` parameter.
9. **Save to the outline's images directory** — use the naming convention below and place the file in `images/{outline-stem}/`.

---

## Capturing from Different Sources

### From a Generic Web Page

```
1. browser_navigate to the target URL
2. browser_wait_for with a heading or content landmark
3. Dismiss cookie banners (look for "Accept", "Got it", or "I agree" buttons)
4. browser_resize to 1920x1080 if not already done
5. browser_take_screenshot, type: "png"
6. Save to images/{outline-stem}/web-{NN}-{description}.png
```

If the page has a sticky header or footer that intrudes on the content area, use an element-specific capture (browser_snapshot to find the main content ref, then pass ref to browser_take_screenshot).

### From a Running Web App (Localhost)

```
1. Confirm the app is running before navigating:
   curl -s http://localhost:{port}/ or check logs
2. browser_navigate to http://localhost:{port}
3. browser_wait_for with a known UI label (e.g., deck name, dashboard heading)
4. Navigate to the specific view (click deck, slide, or panel)
5. Allow any async data fetches to complete (browser_wait_for with loaded content)
6. browser_resize to 1920x1080
7. browser_take_screenshot, type: "png"
```

For the aippt web UI specifically: start the server first (`$VENV_PYTHON aippt.py serve --port 8000`), then navigate to `http://localhost:8000`. Use `browser_snapshot` to find element refs for navigating to specific decks or slides.

### From Excalidraw

The self-hosted Excalidraw instance is at `https://excalidraw.lab.shamsway.net/`.

```
1. browser_navigate to https://excalidraw.lab.shamsway.net/
2. browser_wait_for — wait for the canvas to appear
3. Dismiss the welcome screen by pressing Escape (browser_press_key: "Escape")
4. Load or create the diagram:
   - To paste existing elements: use browser_evaluate to write clipboard data,
     then press Ctrl+V
   - To create inline: use mcp__excalidraw__create_view, then export
5. browser_resize to 1920x1080
6. Take the screenshot — the canvas fills the viewport
7. Save to images/{outline-stem}/web-{NN}-{description}.png
```

To paste diagram elements via clipboard in Excalidraw:

```javascript
// In browser_evaluate:
navigator.clipboard.writeText(JSON.stringify({
  type: "excalidraw/clipboard",
  elements: [/* your elements */],
  files: {}
}))
```

Then call `browser_press_key` with `"Control+v"` to paste. Use `browser_press_key` with `"Control+a"` first to clear the canvas if updating an existing diagram.

---

## Naming Convention

Use this pattern for all Playwright-captured images:

```
web-{NN}-{description}.png
```

- `web-` prefix distinguishes Playwright captures from auto-exported slide images (which use the `Slide{N}.PNG` convention)
- `{NN}` is the slide number, zero-padded to two digits
- `{description}` is a short lowercase slug describing the content, with hyphens for spaces

**Examples:**

```
web-04-dashboard-overview.png
web-07-api-docs.png
web-12-settings-page.png
web-01-architecture-diagram.png
web-09-comparison-table.png
```

Always use lowercase and hyphens. Never use spaces, underscores, or mixed case in image filenames.

Place files in `images/{outline-stem}/` where `{outline-stem}` is the base name of the outline file (e.g., an outline at `decks/cloud-migration.md` uses `images/cloud-migration/`).

---

## File Format Guidance

**PNG** (`type: "png"`) — use for:
- UI screenshots with crisp text and sharp edges
- Diagrams and charts
- Any content where text legibility matters
- App interfaces (buttons, panels, forms)

**JPEG** (`type: "jpeg"`) — use for:
- Photographs and photographic-style images
- Complex images with smooth gradients and many colors
- Cases where file size is a priority over lossless reproduction

Always use PNG for app screenshots. JPEG compression introduces artifacts around text and UI edges that degrade readability on slides.

---

## Tips for Clean Screenshots

**Before capturing:**
- Dismiss cookie consent banners before taking any screenshot — they sit above the content and obscure it
- Close browser dev tools (F12 toggles them; or check that the viewport was not resized with tools open)
- Close any browser sidebar extensions that may overlay the page content
- Expand collapsed sections if they contain key content for the slide
- Set the consistent 1920x1080 viewport before each capture session

**Content considerations:**
- For dark-themed apps, verify that the captured content will have adequate contrast against slide backgrounds — dark-on-dark combinations can disappear on slide templates with dark fills
- Consider capturing both light and dark mode screenshots if the app supports theming, then choose the one with better slide contrast
- If the page has a busy background or distracting decorative elements, use an element-specific ref capture to isolate the relevant component
- For multi-page captures across a session, maintain the same browser size throughout so all images have the same dimensions

**After capturing:**
- Read the saved PNG immediately to verify it captured the intended content and the filename is correct
- Reference it in the outline using `IMAGE: images/{outline-stem}/web-{NN}-{description}.png` — paths are relative to the outline file

---

## Reference in Outlines

Once captured, reference the image in the outline with an `IMAGE:` directive:

```markdown
# Dashboard Overview
LAYOUT: diagram
IMAGE: images/cloud-migration/web-04-dashboard-overview.png
- Walk through the main monitoring dashboard
- Highlight the alert threshold configuration panel
- Point out the cost breakdown by service
```

When `IMAGE:` is present, slide content moves to speaker notes automatically. The image occupies the full content area of the slide.
