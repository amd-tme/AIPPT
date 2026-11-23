/**
 * pptxgenjs-helpers.mjs — reusable slide builder library for pptxgenjs engine.
 *
 * Usage from output/ scripts:
 *   import { createDeck, addTitleSlide, addBulletSlide, ... } from '../lib/pptxgenjs-helpers.mjs';
 *
 * All slide builders accept a `deck` object from createDeck() which bundles
 * pptx, theme, and layout so callers don't juggle three args.
 */

import { readFileSync, existsSync, statSync } from "fs";
import { createRequire } from "module";
import { resolve, dirname } from "path";
import { defineMasters, masterNameFor } from './pptxgenjs-masters.mjs';

const require = createRequire(import.meta.url);

// YAML parsing — use js-yaml if available, fall back to simple parser
let yamlParse;
try {
  const jsyaml = require("js-yaml");
  yamlParse = (str) => jsyaml.load(str);
} catch {
  // Minimal YAML parser for theme files (handles flat keys, nested objects, quoted strings)
  yamlParse = (str) => {
    const result = {};
    const lines = str.split("\n");
    let currentSection = null;

    for (const rawLine of lines) {
      const line = rawLine.replace(/\r$/, "");
      // Skip comments and blank lines
      if (/^\s*#/.test(line) || /^\s*$/.test(line)) continue;

      const indent = line.search(/\S/);
      const content = line.trim();

      // Key: value line
      const kvMatch = content.match(/^(\w[\w_]*):\s*(.*)/);
      if (!kvMatch) continue;

      const key = kvMatch[1];
      let value = kvMatch[2].trim();

      if (indent === 0) {
        if (value === "" || value === "|") {
          // Section header
          currentSection = {};
          result[key] = currentSection;
        } else {
          result[key] = parseValue(value);
          currentSection = null;
        }
      } else if (currentSection !== null) {
        currentSection[key] = parseValue(value);
      }
    }
    return result;
  };

  function parseValue(v) {
    // Remove inline comments
    v = v.replace(/\s+#.*$/, "");
    // Quoted string
    if (/^"(.*)"$/.test(v)) return v.slice(1, -1);
    if (/^'(.*)'$/.test(v)) return v.slice(1, -1);
    // Boolean
    if (v === "true") return true;
    if (v === "false") return false;
    // Number
    if (/^-?\d+(\.\d+)?$/.test(v)) return parseFloat(v);
    // Plain string
    return v;
  }
}


// ═══════════════════════════════════════════════════════════════
// Text utility
// ═══════════════════════════════════════════════════════════════

/**
 * Convert a string that may contain \n into a pptxgenjs text-run array so
 * line breaks render correctly. Returns the original string unchanged when
 * there are no newlines (avoids unnecessary array wrapping).
 */
function textRuns(text, extraOpts = {}) {
  if (typeof text !== "string" || !text.includes("\n")) return text;
  return text.split("\n").map((line, i) => ({
    text: line,
    options: i === 0 ? extraOpts : { ...extraOpts, breakLine: true },
  }));
}

// ═══════════════════════════════════════════════════════════════
// Safe-area constants (LAYOUT_WIDE = 13.33" × 7.5")
// ═══════════════════════════════════════════════════════════════

export const SW = 13.33;
export const SH = 7.5;

// Token defaults — every new token has a default matching the current hardcoded value.
export const TOKEN_DEFAULTS = {
  typography: {
    title_size: 36, heading_size: 28, subtitle_size: 18,
    body_size: 18, small_size: 14, eyebrow_size: 8,
    eyebrow_bold: false, eyebrow_char_spacing: 6,
    stat_size: 48, stat_bold: true, stat_label_size: 16,
    stat_desc_size: 13, code_size: 14, footer_size: 10,
  },
  data_colors: {
    series_1: "", series_2: "", series_3: "",
    positive: "1AA01A", negative: "D73D2B", neutral: "",
  },
  shadow: {
    blur: 4, offset: 2, angle: 135, color: "000000", opacity: 0.12,
  },
  eyebrow: {
    show: true, dash_width: 1.2, dash_height: 0.035, label_offset: 1.35,
  },
  // Brand assets (file names in themes/assets/). The defaults are the dark AMD
  // look; a light theme names the black-art versions instead.
  brand: {
    variant: "dark",
    title_background: "amd-arrow-hq.jpg",   // addTitleSlide background
    lockup: "amd-twa-lockup-wht.png",       // "together we advance_" lockup on title slides
    wordmark: "",                           // large logo on closing/alt-title slides; "" = logo.path
    sensitivity_label: "",                  // e.g. "[AMD Official Use Only - General]", top-left
  },
};

function deepMerge(target, source) {
  for (const key of Object.keys(source)) {
    if (
      source[key] !== null &&
      typeof source[key] === "object" &&
      !Array.isArray(source[key]) &&
      typeof target[key] === "object"
    ) {
      deepMerge(target[key], source[key]);
    } else {
      target[key] = source[key];
    }
  }
  return target;
}


// ═══════════════════════════════════════════════════════════════
// Theme & Config
// ═══════════════════════════════════════════════════════════════

/**
 * Load a theme YAML file and return a structured config object.
 * @param {string} yamlPath - Path to themes/*.yaml
 * @returns {{ colors, fonts, logo, slide, footer, name, description }}
 */
export function loadTheme(yamlPath) {
  const raw = readFileSync(yamlPath, "utf8");
  const parsed = yamlParse(raw);
  const themeDir = dirname(dirname(resolve(yamlPath))); // themes/ dir → resolve to repo root

  const theme = {
    name: parsed.name || "",
    description: parsed.description || "",
    colors: {
      background: parsed.colors?.background || "000000",
      background_alt: parsed.colors?.background_alt || parsed.colors?.background || "000000",
      surface: parsed.colors?.surface || "333333",
      text_primary: parsed.colors?.text_primary || "FFFFFF",
      text_secondary: parsed.colors?.text_secondary || "999999",
      text_body: parsed.colors?.text_body || "CCCCCC",
      accent: parsed.colors?.accent || "3B82F6",
      accent_alt: parsed.colors?.accent_alt || "10B981",
      warning: parsed.colors?.warning || "EF4444",
    },
    fonts: {
      heading: parsed.fonts?.heading || "Arial",
      body: parsed.fonts?.body || "Arial",
      mono: parsed.fonts?.mono || "Consolas",
    },
    logo: {
      path: parsed.logo?.path ? resolve(themeDir, parsed.logo.path) : "",
      width: parsed.logo?.width_inches || 0,
      height: parsed.logo?.height_inches || 0,
      x: parsed.logo?.x_inches || 0,
      y: parsed.logo?.y_inches || 0,
    },
    slide: {
      layout: parsed.slide?.layout || "LAYOUT_WIDE",
      margin: parsed.slide?.margin_inches || 0.5,
    },
    footer: {
      show: parsed.footer?.show !== false,
      text: parsed.footer?.text || "",
      showSlideNumbers: parsed.footer?.show_slide_numbers !== false,
      numberPosition: parsed.footer?.number_position || "right",
    },
    master: parsed.master || null,
  };

  // Expanded color slots
  theme.colors.code_bg = parsed.colors?.code_bg || "0D1117";
  theme.colors.code_text = parsed.colors?.code_text || "58A6FF";
  theme.colors.heading_color = parsed.colors?.heading_color ?? "";
  theme.colors.eyebrow_color = parsed.colors?.eyebrow_color ?? "";
  theme.colors.stat_color = parsed.colors?.stat_color ?? "";

  // New token sections
  theme.typography = { ...TOKEN_DEFAULTS.typography, ...parsed.typography };
  theme.data_colors = { ...TOKEN_DEFAULTS.data_colors, ...parsed.data_colors };
  theme.shadow = { ...TOKEN_DEFAULTS.shadow, ...parsed.shadow };
  theme.eyebrow = { ...TOKEN_DEFAULTS.eyebrow, ...parsed.eyebrow };
  theme.brand = { ...TOKEN_DEFAULTS.brand, ...parsed.brand };

  return theme;
}


/**
 * Compute layout geometry from a theme.
 * @param {{ slide: { margin: number } }} theme
 * @returns {{ M, CONTENT_W, CONTENT_Y, FOOTER_Y, CONTENT_H, RIGHT_EDGE }}
 */
export function computeLayout(theme) {
  const M = theme.slide.margin;
  const CONTENT_W = SW - 2 * M;
  const CONTENT_Y = 1.45; // logo bottom ~0.66" + heading 0.55" + gap → content starts here
  const FOOTER_Y = SH - 0.6;
  const CONTENT_H = FOOTER_Y - CONTENT_Y;
  const RIGHT_EDGE = SW - M;
  return { M, CONTENT_W, CONTENT_Y, FOOTER_Y, CONTENT_H, RIGHT_EDGE };
}


// ═══════════════════════════════════════════════════════════════
// Infrastructure
// ═══════════════════════════════════════════════════════════════

/**
 * Detect URLs in text and return a pptxgenjs text array with hyperlinks.
 * Returns the original string if no URLs are found.
 */
function linkifyText(text, baseOptions = {}) {
  if (typeof text !== "string") return text;
  const urlRe = /\b(https?:\/\/[^\s,)]+|(?:www\.|github\.com\/|instinct\.docs\.)[^\s,)]+)/gi;
  const parts = [];
  let last = 0;
  for (const m of text.matchAll(urlRe)) {
    if (m.index > last) {
      parts.push({ text: text.slice(last, m.index), options: { ...baseOptions } });
    }
    const url = m[0].replace(/\.$/,"");
    const href = url.startsWith("http") ? url : `https://${url}`;
    parts.push({
      text: url,
      options: { ...baseOptions, hyperlink: { url: href } },
    });
    last = m.index + m[0].replace(/\.$/,"").length;
    if (m[0].endsWith(".") && !url.endsWith(".")) last++;
  }
  if (last < text.length) {
    parts.push({ text: text.slice(last), options: { ...baseOptions } });
  }
  return parts.length > 1 ? parts : text;
}

/**
 * Fresh shadow object factory — never reuse shadow objects in pptxgenjs.
 * Returns undefined (no shadow) when the theme sets opacity 0, because
 * pptxgenjs treats a 0 opacity as unset and draws its default shadow.
 */
export function cardShadow(theme) {
  const s = theme?.shadow || TOKEN_DEFAULTS.shadow;
  if (!s.opacity) return undefined;
  return {
    type: "outer", blur: s.blur, offset: s.offset,
    angle: s.angle, color: s.color, opacity: s.opacity,
  };
}


/**
 * Render a react-icons component to SVG string.
 * @param {Function} IconComponent - React icon component
 * @param {number} size - Icon size in pixels
 * @param {string} color - Hex color without #
 * @returns {string} SVG markup
 */
export function renderIconSvg(IconComponent, size = 256, color = "FFFFFF") {
  const React = require("react");
  const ReactDOMServer = require("react-dom/server");
  const el = React.createElement(IconComponent, { size, color: `#${color}` });
  return ReactDOMServer.renderToStaticMarkup(el);
}


/**
 * Convert SVG string to base64 PNG data URI via sharp.
 * @param {string} svgString - SVG markup
 * @param {number} size - Output size in pixels
 * @returns {Promise<string>} base64 data URI for pptxgenjs addImage
 */
export async function iconToBase64(svgString, size = 256) {
  const sharp = require("sharp");
  const buf = Buffer.from(svgString);
  const png = await sharp(buf, { density: 300 })
    .resize(size, size)
    .png()
    .toBuffer();
  return `image/png;base64,${png.toString("base64")}`;
}


/**
 * Pre-render a map of named icons to base64 PNGs.
 * @param {Object} iconMap - { name: { component, color } }
 * @returns {Promise<Object>} { name: base64DataUri }
 */
export async function preRenderIcons(iconMap) {
  const result = {};
  for (const [name, { component, color }] of Object.entries(iconMap)) {
    const svg = renderIconSvg(component, 256, color || "FFFFFF");
    result[name] = await iconToBase64(svg);
  }
  return result;
}


const BRAND_ICON_DIR = 'themes/assets/icons/amd';
let brandIconManifest = null;

// The user's own icons and co-brand logo for this deck, from the
// user-assets.json the app writes next to the script (see createDeck).
let userAssets = { icons: {}, cobrand: null };

/** A user icon file as image data; SVG black (and unset fill) becomes *color*. */
function _userIcon(file, color) {
  if (!existsSync(file)) return null;
  if (!file.toLowerCase().endsWith('.svg')) {
    return `image/png;base64,${readFileSync(file).toString('base64')}`;
  }
  const svg = readFileSync(file, 'utf8')
    .replace(/((?:fill|stroke|stop-color|color)\s*[:=]\s*["']?)(?:#000000|#000|black)\b/gi, `$1#${color}`)
    .replace(/<svg\b([^>]*)>/, (tag, attrs) => (/\sfill=/.test(attrs) ? tag : `<svg${attrs} fill="#${color}">`));
  return `image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`;
}

/**
 * The partner co-brand logo, fitted (aspect kept) into *box*: left-aligned,
 * or centred when box.center. Only when the user opted in; returns whether
 * it was drawn.
 */
function _cobrand(slide, box) {
  const logo = userAssets.cobrand;
  if (!logo || !logo.path || !existsSync(logo.path)) return false;
  const ratio = logo.width > 0 && logo.height > 0 ? logo.width / logo.height : 1;
  const w = Math.min(box.w, box.h * ratio);
  const h = w / ratio;
  slide.addImage({
    path: logo.path, w, h,
    x: box.center ? box.x + (box.w - w) / 2 : box.x,
    y: box.y + (box.h - h) / 2,
  });
  return true;
}

/**
 * Load AMD brand icons (themes/assets/icons/amd) as recoloured SVG images.
 * Use the results as a card's `iconImg` or in `iconImages` arrays. SVG keeps
 * icons sharp at any size and needs no native image library, so it works in
 * the sandboxed renderer; the renderer adds PNG fallbacks for old viewers.
 * @param {string[]} ids - Icon ids from the icon bank manifest, e.g. ["gpu", "calendar"],
 *   or the user's own icons ("my-…" ids from user-assets.json)
 * @param {string} color - Hex color without # (white on dark slides, black on light)
 * @returns {Object} { id: base64DataUri } — unknown ids are left out
 */
export function loadIcons(ids, color = "FFFFFF") {
  if (!brandIconManifest) {
    const icons = JSON.parse(readFileSync(`${BRAND_ICON_DIR}/manifest.json`, 'utf8')).icons;
    brandIconManifest = Object.fromEntries(icons.map((icon) => [icon.id, icon]));
  }
  const result = {};
  for (const id of ids) {
    if (userAssets.icons[id]) {
      const data = _userIcon(userAssets.icons[id], color);
      if (data) result[id] = data;
      continue;
    }
    const icon = brandIconManifest[id];
    if (!icon) {
      console.warn(`loadIcons: no icon "${id}" in the icon bank — skipped`);
      continue;
    }
    const file = `${BRAND_ICON_DIR}/${icon.duplicate_of || id}.svg`;
    const svg = readFileSync(file, 'utf8').replaceAll('#000000', `#${color}`);
    result[id] = `image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`;
  }
  return result;
}


// ═══════════════════════════════════════════════════════════════
// Footer
// ═══════════════════════════════════════════════════════════════

/**
 * Add Instinct-style eyebrow label: short teal dash + uppercase spaced label text.
 * Self-contained — draws both the accent dash and the label text.
 * Use sparingly: eyebrows distract from the title on standard content slides.
 * Best suited for section dividers or slides without a prominent heading.
 *
 * Accepts either (slide, label, theme) [legacy] or (slide, label, deck).
 * @param {Object} slide - pptxgenjs slide
 * @param {string} label - Section label (e.g. "PLATFORM OVERVIEW")
 * @param {Object} themeOrDeck - theme config or deck object
 */
export function addEyebrowText(slide, label, themeOrDeck) {
  const theme = themeOrDeck.theme || themeOrDeck;
  const pptx = themeOrDeck.pptx || null;
  const M = theme.slide.margin;
  const C = theme.colors;
  const EB = theme.eyebrow;
  const T = theme.typography;
  const eyebrowColor = C.eyebrow_color || C.accent;
  if (pptx && EB.show) {
    slide.addShape(pptx.ShapeType.rect, {
      x: M, y: 0.22, w: EB.dash_width, h: EB.dash_height,
      fill: { color: eyebrowColor },
    });
  }
  slide.addText(label.toUpperCase(), {
    x: M + EB.label_offset, y: 0.16, w: 8.0, h: 0.14,
    fontSize: T.eyebrow_size, fontFace: theme.fonts.body,
    color: eyebrowColor, charSpacing: T.eyebrow_char_spacing,
    bold: T.eyebrow_bold,
  });
}


/**
 * Add footer (slide number + optional logo) to a slide.
 * @param {Object} slide - pptxgenjs slide
 * @param {number} slideNum - Slide number to display
 * @param {{ colors, fonts, logo }} theme - Theme config
 * @param {{ suppressLogo?, suppressNumber? }} opts
 */
export function addFooter(slide, slideNum, theme, opts = {}) {
  const { suppressLogo = false, suppressNumber = false, deck } = opts;
  if (deck?.useSlideMaster) {
    console.debug('addFooter: skipped — deck uses slide masters');
    return;
  }
  const C = theme.colors;
  const FONT_BODY = theme.fonts.body;

  if (!suppressNumber) {
    // Corporate template: number bottom-left so the lockup can sit bottom-right.
    const left = theme.footer.numberPosition === "left";
    slide.addText(`${slideNum}`, {
      x: left ? 0.21 : SW - 0.7, y: SH - 0.45, w: left ? 0.4 : 0.5, h: 0.3,
      fontSize: theme.typography.footer_size, fontFace: FONT_BODY,
      color: C.text_primary, align: left ? "left" : "right",
    });
  }

  if (theme.brand.sensitivity_label && !(suppressLogo && suppressNumber)) {
    slide.addText(theme.brand.sensitivity_label, {
      x: 0.07, y: 0.07, w: 4, h: 0.25, margin: 0,
      fontSize: 10, fontFace: FONT_BODY, color: "0000FF",
    });
  }

  if (!suppressLogo && theme.logo.path && existsSync(theme.logo.path)) {
    slide.addImage({
      path: theme.logo.path,
      x: theme.logo.x, y: theme.logo.y,
      w: theme.logo.width, h: theme.logo.height,
    });
  }
}


// ═══════════════════════════════════════════════════════════════
// Slide Builders
// ═══════════════════════════════════════════════════════════════

// All slide builders accept a `deck` object: { pptx, theme, layout }

/**
 * Add a title slide (AMD style: logo left, title right, accent bar).
 */
export function addTitleSlide(deck, title, subtitle, slideNum) {
  const { pptx, theme, layout } = deck;
  const C = theme.colors;
  const T = theme.typography;
  const slideOpts = deck.useSlideMaster
    ? { masterName: masterNameFor('title') }
    : {};
  const slide = pptx.addSlide(slideOpts);

  if (!deck.useSlideMaster) {
    // Use the arrow JPG as the slide background (exactly how the corp template does it)
    // — no transparency removal needed, no bounding box artifacts
    const arrowBgPath = _asset(theme, theme.brand.title_background);
    if (existsSync(arrowBgPath)) {
      slide.background = { path: arrowBgPath };
    } else {
      slide.background = { color: C.background };
    }
  }

  slide.addText(textRuns(title, { bold: true, fontSize: T.title_size, fontFace: theme.fonts.heading, color: C.text_primary }), {
    x: 6.8, y: 2.4, w: SW - 7.1, h: 1.5,
    fontSize: T.title_size, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
  });

  slide.addShape(pptx.ShapeType.rect, {
    x: 6.8, y: 4.0, w: 2.0, h: 0.06,
    fill: { color: C.accent },
  });

  if (subtitle) {
  slide.addText(textRuns(subtitle, { fontSize: T.subtitle_size, fontFace: theme.fonts.body, color: C.text_secondary }), {
    x: 6.8, y: 4.2, w: SW - 7.1, h: 0.8,
    fontSize: T.subtitle_size, fontFace: theme.fonts.body,
    color: C.text_secondary,
  });
  }

  // T3: White TWA lockup — corp.potx exact: x=10.27", y=6.31", w=2.58", h=0.73"
  const twaPath = _asset(theme, theme.brand.lockup);
  if (existsSync(twaPath)) {
    slide.addImage({ path: twaPath, x: 10.27, y: 6.31, w: 2.58, h: 0.73 });
  }

  // Opt-in partner co-brand under the subtitle
  _cobrand(slide, { x: 6.8, y: 5.2, w: 2.8, h: 0.8 });

  // No footer on title slide — no slide number, TWA lockup handles branding
  return slide;
}


// --- Bullet slide internals ---

function _pushBulletItem(textItems, text, leadSize, bodySize, spacing, C, hasLeadIn = false) {
  const match = text.match(/^\*\*(.+?)\*\*\s*[—–\-]\s*(.*)/);
  if (match) {
    textItems.push(
      { text: match[1] + " \u2014 ", options: { bold: true, fontSize: leadSize, color: C.text_primary, breakLine: false } },
    );
    const bodyOpts1 = { fontSize: bodySize, color: C.text_body, breakLine: true, paraSpaceAfter: spacing };
    const linked1 = linkifyText(match[2], bodyOpts1);
    if (Array.isArray(linked1)) textItems.push(...linked1);
    else textItems.push({ text: match[2], options: bodyOpts1 });
  } else {
    const match2 = text.match(/^\*\*(.+?)\*\*\s*(.*)/);
    if (match2) {
      textItems.push(
        { text: match2[1] + " ", options: { bold: true, fontSize: leadSize, color: C.text_primary, breakLine: false } },
      );
      const bodyOpts2 = { fontSize: bodySize, color: C.text_body, breakLine: true, paraSpaceAfter: spacing };
      const linked2 = linkifyText(match2[2], bodyOpts2);
      if (Array.isArray(linked2)) textItems.push(...linked2);
      else textItems.push({ text: match2[2], options: bodyOpts2 });
    } else {
      const bodyOpts3 = { fontSize: bodySize, color: C.text_body, bullet: !hasLeadIn, breakLine: true, paraSpaceAfter: spacing };
      const linked3 = linkifyText(text, bodyOpts3);
      if (Array.isArray(linked3)) textItems.push(...linked3);
      else textItems.push({ text, options: bodyOpts3 });
    }
  }
}


/**
 * Add a bullet slide with adaptive font sizing.
 * Bullets support bold lead-in: "**Bold** — rest"
 * Bullets can also be {text, subs: [...]} objects for sub-bullets.
 */
export function addBulletSlide(deck, title, bullets, slideNum, notes) {
  const { pptx, theme, layout } = deck;
  const { M, CONTENT_W, CONTENT_Y, CONTENT_H } = layout;
  const C = theme.colors;
  const T = theme.typography;
  const slideOpts = deck.useSlideMaster
    ? { masterName: masterNameFor('bullet') }
    : {};
  const slide = pptx.addSlide(slideOpts);
  if (!deck.useSlideMaster) {
    slide.background = { color: C.background };
  }

  slide.addText(title, {
    x: M, y: 0.78, w: CONTENT_W, h: 0.55,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.heading_color || C.text_primary, bold: true,
  });

  // Adaptive font size + spacing
  let bodySize, leadSize, spacing;
  if (bullets.length <= 4) {
    bodySize = 22; leadSize = 24; spacing = 20;
  } else if (bullets.length <= 5) {
    bodySize = 20; leadSize = 22; spacing = 16;
  } else if (bullets.length <= 7) {
    bodySize = 18; leadSize = 20; spacing = 12;
  } else {
    bodySize = 16; leadSize = 18; spacing = 10;
  }

  // B1: if any item uses lead-in syntax (**Bold— rest**), suppress bullet markers on all items
  const _LEAD_IN_RE = /^\*\*.+?\*\*\s*[—–\-]/;
  const hasLeadIn = bullets.some(b => {
    const t = typeof b === 'string' ? b : b.text;
    return _LEAD_IN_RE.test(t);
  });

  const textItems = [];
  bullets.forEach((b) => {
    // Support {text, subs} objects for sub-bullets
    if (typeof b === 'object' && b.subs) {
      _pushBulletItem(textItems, b.text, leadSize, bodySize, spacing, C, hasLeadIn);
      b.subs.forEach(sub => {
        textItems.push({
          text: sub,
          options: {
            fontSize: bodySize - 2,
            color: C.text_body,
            bullet: !hasLeadIn,
            indentLevel: hasLeadIn ? 0 : 1,
            breakLine: true,
            paraSpaceAfter: spacing / 2,
          }
        });
      });
    } else {
      const text = typeof b === 'string' ? b : b.text;
      _pushBulletItem(textItems, text, leadSize, bodySize, spacing, C, hasLeadIn);
    }
  });

  slide.addText(textItems, {
    x: M + 0.4, y: CONTENT_Y, w: CONTENT_W - 0.8, h: CONTENT_H,
    valign: "top",
    fontFace: theme.fonts.body,
  });

  if (notes) {
    slide.addNotes(notes);
  }

  if (!deck.useSlideMaster) {
    addFooter(slide, slideNum, theme);
  }
  return slide;
}


/**
 * Pixel size of a PNG, JPEG, GIF or SVG image, read from its header.
 * @param {string} src - File path or data string ("image/png;base64,...")
 * @returns {{w:number,h:number}|null} null when the size can't be read
 */
export function imageSize(src) {
  let buf;
  try {
    if (src && src.startsWith('image/')) buf = Buffer.from(src.slice(src.indexOf(',') + 1), 'base64');
    else if (src && existsSync(src)) buf = readFileSync(src);
    else return null;
  } catch { return null; }
  const ok = (w, h) => (w > 0 && h > 0 ? { w, h } : null);
  if (buf.length >= 24 && buf.readUInt32BE(0) === 0x89504e47) return ok(buf.readUInt32BE(16), buf.readUInt32BE(20));
  if (buf.length >= 10 && buf.toString('latin1', 0, 3) === 'GIF') return ok(buf.readUInt16LE(6), buf.readUInt16LE(8));
  if (buf.length >= 4 && buf[0] === 0xff && buf[1] === 0xd8) {
    // Walk the JPEG segments to the frame header (SOF0-SOF15, not DHT/JPG/DAC)
    let i = 2;
    while (i + 9 < buf.length) {
      if (buf[i] !== 0xff) { i++; continue; }
      const m = buf[i + 1];
      if (m === 0xff) { i++; continue; }
      if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) {
        return ok(buf.readUInt16BE(i + 7), buf.readUInt16BE(i + 5));
      }
      if (m === 0xd8 || m === 0x01 || (m >= 0xd0 && m <= 0xd7)) { i += 2; continue; }
      i += 2 + buf.readUInt16BE(i + 2);
    }
    return null;
  }
  const head = buf.toString('utf8', 0, Math.min(buf.length, 4096));
  const tag = head.match(/<svg\b[^>]*>/i);
  if (!tag) return null;
  const vb = tag[0].match(/viewBox\s*=\s*["']\s*[-\d.e]+[\s,]+[-\d.e]+[\s,]+([\d.e]+)[\s,]+([\d.e]+)/i);
  if (vb) return ok(parseFloat(vb[1]), parseFloat(vb[2]));
  const attr = (n) => { const a = tag[0].match(new RegExp(`\\s${n}\\s*=\\s*["']?\\s*([\\d.]+)(px)?\\s*["']?[\\s/>]`, 'i')); return a ? parseFloat(a[1]) : 0; };
  return ok(attr('width'), attr('height'));
}

// A raster is never enlarged past this many pixels per inch, so a small
// image stays small and sharp instead of blowing up blurry
const MIN_IMAGE_PPI = 72;

/**
 * Add an image to *box* without stretching it. "contain" fits the whole image
 * in the box, centred (or at the top when opts.top); "cover" fills the box
 * and crops the overflow evenly. An image whose size can't be read fills the
 * box as before.
 */
function _addImageFit(slide, src, box, mode = 'contain', opts = {}) {
  const key = src.startsWith('image/') ? { data: src } : { path: src };
  const size = imageSize(src);
  if (!size) {
    slide.addImage({ ...key, x: box.x, y: box.y, w: box.w, h: box.h });
    return;
  }
  const ratio = size.w / size.h;
  if (mode === 'cover') {
    // pptxgenjs crops correctly when w/h carry the image's own proportions
    const w = Math.max(box.w, box.h * ratio);
    slide.addImage({ ...key, x: box.x, y: box.y, w, h: w / ratio, sizing: { type: 'cover', w: box.w, h: box.h } });
    return;
  }
  let w = Math.min(box.w, box.h * ratio);
  const isSvg = src.startsWith('image/') ? src.startsWith('image/svg') : /\.svg$/i.test(src);
  if (!isSvg) {
    w = Math.min(w, size.w / MIN_IMAGE_PPI);
  }
  const h = w / ratio;
  const y = opts.top ? box.y : box.y + (box.h - h) / 2;
  slide.addImage({ ...key, x: box.x + (box.w - w) / 2, y, w, h });
}


/**
 * Add a full-image slide. Image fills the content area with aspect ratio preserved.
 * @param {Object} deck
 * @param {string} title - Slide title
 * @param {string} imagePath - File path or data URI (e.g. "image/png;base64,...")
 * @param {number} slideNum
 * @param {string} [notes] - Optional speaker notes
 * @param {{caption?: string}} [opts] - Optional thin caption strip below the image
 */
export function addImageSlide(deck, title, imagePath, slideNum, notes, opts = {}) {
  const { pptx, theme, layout } = deck;
  const { M, CONTENT_W, CONTENT_Y, CONTENT_H } = layout;
  const C = theme.colors;
  const T = theme.typography;
  const slideOpts = deck.useSlideMaster
    ? { masterName: masterNameFor('image') }
    : {};
  const slide = pptx.addSlide(slideOpts);
  if (!deck.useSlideMaster) {
    slide.background = { color: C.background };
  }

  slide.addText(title, {
    x: M, y: 0.78, w: CONTENT_W, h: 0.55,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.heading_color || C.text_primary, bold: true,
  });

  const captionH = opts.caption ? 0.42 : 0;
  const imgH = CONTENT_H - captionH;

  const isDataUri = imagePath && imagePath.startsWith("image/");

  if (isDataUri || (imagePath && existsSync(imagePath))) {
    _addImageFit(slide, imagePath, { x: M, y: CONTENT_Y, w: CONTENT_W, h: imgH });
  } else {
    // Missing file placeholder
    slide.addShape(pptx.ShapeType.rect, {
      x: M, y: CONTENT_Y, w: CONTENT_W, h: imgH,
      fill: { color: C.surface },
    });
    slide.addText(`[Image: ${imagePath || "unknown"}]`, {
      x: M, y: CONTENT_Y, w: CONTENT_W, h: imgH,
      fontSize: 14, fontFace: theme.fonts.body,
      color: C.text_secondary, align: "center", valign: "middle",
    });
  }

  if (opts.caption) {
    const capY = CONTENT_Y + imgH + 0.04;
    slide.addShape(pptx.ShapeType.rect, {
      x: M, y: capY, w: 0.06, h: captionH - 0.08,
      fill: { color: C.accent },
    });
    slide.addText(opts.caption, {
      x: M + 0.18, y: capY, w: CONTENT_W - 0.2, h: captionH - 0.08,
      fontSize: 12, fontFace: theme.fonts.body,
      color: C.text_secondary, valign: "middle",
    });
  }

  if (notes) slide.addNotes(notes);
  if (!deck.useSlideMaster) {
    addFooter(slide, slideNum, theme);
  }
  return slide;
}


/**
 * Add an image + bullets slide. Image on left (~48%), bullets on right (~52%).
 * @param {Object} deck
 * @param {string} title - Slide title
 * @param {string} imagePath - File path or data URI (e.g. "image/png;base64,...")
 * @param {Array<string|{text,subs}>} bullets - Bullet items (same format as addBulletSlide)
 * @param {number} slideNum
 * @param {string} [notes] - Optional speaker notes
 */
export function addImageBulletsSlide(deck, title, imagePath, bullets, slideNum, notes) {
  const { pptx, theme, layout } = deck;
  const { M, CONTENT_W, CONTENT_Y, CONTENT_H } = layout;
  const C = theme.colors;
  const T = theme.typography;
  const slideOpts = deck.useSlideMaster
    ? { masterName: masterNameFor('imageBullets') }
    : {};
  const slide = pptx.addSlide(slideOpts);
  if (!deck.useSlideMaster) {
    slide.background = { color: C.background };
  }

  slide.addText(title, {
    x: M, y: 0.78, w: CONTENT_W, h: 0.55,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.heading_color || C.text_primary, bold: true,
  });

  // Split layout: image left ~48%, gutter, bullets right ~52%
  const gutter = 0.36;
  const imgW = (CONTENT_W - gutter) * 0.48;
  const bulletW = CONTENT_W - imgW - gutter;
  const imgX = M;
  const bulletX = M + imgW + gutter;

  const isDataUri = imagePath && imagePath.startsWith("image/");

  if (isDataUri || (imagePath && existsSync(imagePath))) {
    _addImageFit(slide, imagePath, { x: imgX, y: CONTENT_Y, w: imgW, h: CONTENT_H }, 'contain', { top: true });
  } else {
    // Missing file placeholder
    slide.addShape(pptx.ShapeType.rect, {
      x: imgX, y: CONTENT_Y, w: imgW, h: CONTENT_H,
      fill: { color: C.surface },
    });
    slide.addText(`[Image: ${imagePath || "unknown"}]`, {
      x: imgX, y: CONTENT_Y, w: imgW, h: CONTENT_H,
      fontSize: 12, fontFace: theme.fonts.body,
      color: C.text_secondary, align: "center", valign: "middle",
    });
  }

  // Adaptive font size + spacing (same thresholds as addBulletSlide)
  let bodySize, leadSize, spacing;
  if (bullets.length <= 4) {
    bodySize = 20; leadSize = 22; spacing = 16;
  } else if (bullets.length <= 6) {
    bodySize = 18; leadSize = 20; spacing = 12;
  } else {
    bodySize = 16; leadSize = 18; spacing = 10;
  }

  const textItems = [];
  bullets.forEach((b) => {
    if (typeof b === "object" && b.subs) {
      _pushBulletItem(textItems, b.text, leadSize, bodySize, spacing, C);
      b.subs.forEach(sub => {
        textItems.push({
          text: sub,
          options: {
            fontSize: bodySize - 2,
            color: C.text_body,
            bullet: true,
            indentLevel: 1,
            breakLine: true,
            paraSpaceAfter: spacing / 2,
          },
        });
      });
    } else {
      const text = typeof b === "string" ? b : b.text;
      _pushBulletItem(textItems, text, leadSize, bodySize, spacing, C);
    }
  });

  slide.addText(textItems, {
    x: bulletX, y: CONTENT_Y, w: bulletW, h: CONTENT_H,
    valign: "top",
    fontFace: theme.fonts.body,
  });

  if (notes) slide.addNotes(notes);
  if (!deck.useSlideMaster) {
    addFooter(slide, slideNum, theme);
  }
  return slide;
}


/**
 * Add an icon rows slide (items with icon circles or accent bars).
 * @param {Object} deck
 * @param {string} title
 * @param {Array<{label, desc}>} items
 * @param {Array<string>|null} iconImages - base64 icon data URIs (or null for accent bars)
 * @param {number} slideNum
 */
export function addIconRowsSlide(deck, title, items, iconImages, slideNum, notes) {
  const { pptx, theme, layout } = deck;
  const { M, CONTENT_W, CONTENT_Y } = layout;
  const C = theme.colors;
  const T = theme.typography;
  const slideOpts = deck.useSlideMaster
    ? { masterName: masterNameFor('iconRows') }
    : {};
  const slide = pptx.addSlide(slideOpts);
  if (!deck.useSlideMaster) {
    slide.background = { color: C.background };
  }

  slide.addText(title, {
    x: M, y: 0.78, w: CONTENT_W, h: 0.55,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.heading_color || C.text_primary, bold: true,
  });

  const rowH = items.length > 3 ? 1.1 : 1.4;

  items.forEach((item, i) => {
    const y = CONTENT_Y + i * rowH;

    if (iconImages && iconImages[i]) {
      slide.addShape(pptx.ShapeType.ellipse, {
        x: M + 0.56, y: y, w: 0.7, h: 0.7,
        fill: { color: C.accent },
      });
      slide.addImage({
        data: iconImages[i],
        x: M + 0.68, y: y + 0.12, w: 0.46, h: 0.46,
      });
    } else {
      slide.addShape(pptx.ShapeType.rect, {
        x: M + 0.56, y: y + 0.05, w: 0.06, h: 0.6,
        fill: { color: C.accent },
      });
    }

    slide.addText(item.label, {
      x: M + 1.56, y: y, w: CONTENT_W - 1.56, h: 0.4,
      fontSize: 20, fontFace: theme.fonts.heading,
      color: C.text_primary, bold: true,
    });

    slide.addText(item.desc, {
      x: M + 1.56, y: y + 0.4, w: CONTENT_W - 1.56, h: rowH - 0.5,
      fontSize: 14, fontFace: theme.fonts.body,
      color: C.text_body,
    });
  });

  if (notes) slide.addNotes(notes);
  if (!deck.useSlideMaster) {
    addFooter(slide, slideNum, theme);
  }
  return slide;
}


// --- Process Flow internals ---

// addProcessFlow's `steps` entries are documented as flat strings
// ("Label\nDescription"), but LLM-generated scripts sometimes pass
// {label, description}-style objects instead (mirroring addCardGrid's
// object-shaped `cards`). Normalize either shape to a string here so a
// malformed entry degrades to a plain label instead of crashing the render.
function _normalizeStep(step) {
  if (typeof step === "string") return step;
  if (step && typeof step === "object") {
    const label = step.label ?? step.title ?? step.name ?? "";
    const description = step.description ?? step.desc ?? step.body ?? step.text ?? "";
    if (label && description) return `${label}\n${description}`;
    if (label || description) return String(label || description);
  }
  return String(step ?? "");
}

function _addStepBox(slide, pptx, theme, step, index, x, y, w, h) {
  const C = theme.colors;
  step = _normalizeStep(step);

  slide.addShape(pptx.ShapeType.rect, {
    x, y, w, h,
    fill: { color: C.surface },
    shadow: cardShadow(theme),
  });

  slide.addText(`${index + 1}`, {
    x, y: y + 0.1, w, h: 0.5,
    fontSize: 24, fontFace: theme.fonts.heading,
    color: C.accent, bold: true, align: "center",
  });

  const nlIndex = step.indexOf("\n");
  if (nlIndex > -1) {
    const label = step.substring(0, nlIndex);
    const desc = step.substring(nlIndex + 1);

    slide.addText(label, {
      x: x + 0.1, y: y + 0.65, w: w - 0.2, h: 0.45,
      fontSize: 16, fontFace: theme.fonts.heading,
      color: C.text_primary, bold: true,
      align: "center", valign: "top",
    });

    slide.addText(desc, {
      x: x + 0.1, y: y + 1.1, w: w - 0.2, h: h - 1.3,
      fontSize: 13, fontFace: theme.fonts.body,
      color: C.text_body, align: "center", valign: "top",
    });
  } else {
    slide.addText(step, {
      x: x + 0.1, y: y + 0.7, w: w - 0.2, h: h - 0.9,
      fontSize: 14, fontFace: theme.fonts.body,
      color: C.text_body, align: "center", valign: "top",
    });
  }
}


/**
 * Add a process flow slide with step boxes and arrows.
 * Supports single-row (≤4 steps) and two-row (5+ steps) layouts.
 * Steps can include a label/description split with \n.
 */
export function addProcessFlow(deck, title, steps, slideNum, notes) {
  const { pptx, theme, layout } = deck;
  const { M, CONTENT_W, CONTENT_Y, CONTENT_H } = layout;
  const C = theme.colors;
  const T = theme.typography;
  const slideOpts = deck.useSlideMaster
    ? { masterName: masterNameFor('processFlow') }
    : {};
  const slide = pptx.addSlide(slideOpts);
  if (!deck.useSlideMaster) {
    slide.background = { color: C.background };
  }

  slide.addText(title, {
    x: M, y: 0.78, w: CONTENT_W, h: 0.55,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.heading_color || C.text_primary, bold: true,
  });

  const n = steps.length;

  if (n <= 4) {
    const gap = n <= 3 ? 0.6 : 0.4;
    const totalGap = (n - 1) * gap;
    const stepW = Math.min(2.8, (CONTENT_W - totalGap) / n);
    const totalW = n * stepW + totalGap;
    const startX = (SW - totalW) / 2;
    const boxH = 2.8;
    const boxY = CONTENT_Y + (CONTENT_H - boxH) / 2;

    steps.forEach((step, i) => {
      const x = startX + i * (stepW + gap);
      _addStepBox(slide, pptx, theme, step, i, x, boxY, stepW, boxH);

      if (i < n - 1) {
        slide.addText("\u2192", {
          x: x + stepW, y: boxY + boxH / 2 - 0.5, w: gap, h: 1.0,
          fontSize: 28, color: C.accent,
          align: "center", valign: "middle",
        });
      }
    });
  } else {
    const topCount = Math.ceil(n / 2);
    const botCount = n - topCount;
    const gap = 0.35;
    const stepW = Math.min(2.4, (CONTENT_W - (topCount - 1) * gap) / topCount);
    const boxH = 2.2;
    const rowGap = 0.5;
    const totalH = 2 * boxH + rowGap;
    const startY = CONTENT_Y + (CONTENT_H - totalH) / 2;

    // Top row
    const topW = topCount * stepW + (topCount - 1) * gap;
    const topStartX = (SW - topW) / 2;
    for (let i = 0; i < topCount; i++) {
      const x = topStartX + i * (stepW + gap);
      _addStepBox(slide, pptx, theme, steps[i], i, x, startY, stepW, boxH);
      if (i < topCount - 1) {
        slide.addText("\u2192", {
          x: x + stepW, y: startY + boxH / 2 - 0.4, w: gap, h: 0.8,
          fontSize: 24, color: C.accent, align: "center", valign: "middle",
        });
      }
    }

    // Bottom row (centered)
    const botW = botCount * stepW + (botCount - 1) * gap;
    const botStartX = (SW - botW) / 2;
    const botY = startY + boxH + rowGap;
    for (let i = 0; i < botCount; i++) {
      const x = botStartX + i * (stepW + gap);
      _addStepBox(slide, pptx, theme, steps[topCount + i], topCount + i, x, botY, stepW, boxH);
      if (i < botCount - 1) {
        slide.addText("\u2192", {
          x: x + stepW, y: botY + boxH / 2 - 0.4, w: gap, h: 0.8,
          fontSize: 24, color: C.accent, align: "center", valign: "middle",
        });
      }
    }
  }

  if (notes) slide.addNotes(notes);
  if (!deck.useSlideMaster) {
    addFooter(slide, slideNum, theme);
  }
  return slide;
}


/**
 * Add a two-column slide with headers and vertical divider.
 */
export function addTwoColumn(deck, title, leftHeader, rightHeader, leftItems, rightItems, slideNum, notes, opts = {}) {
  const { pptx, theme, layout } = deck;
  const { M, CONTENT_W, CONTENT_Y, CONTENT_H } = layout;
  const C = theme.colors;
  const T = theme.typography;
  const slideOpts = deck.useSlideMaster
    ? { masterName: masterNameFor('twoColumn') }
    : {};
  const slide = pptx.addSlide(slideOpts);
  if (!deck.useSlideMaster) {
    slide.background = { color: C.background };
  }

  slide.addText(title, {
    x: M, y: 0.78, w: CONTENT_W, h: 0.55,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.heading_color || C.text_primary, bold: true,
  });

  const col1W = 5.70;
  const gutter = 0.36;
  const col2X = M + col1W + gutter;
  const col2W = CONTENT_W - col1W - gutter;
  const headerY = CONTENT_Y;
  const bodyY = CONTENT_Y + 0.5;
  const bodyH = CONTENT_H - 0.5;

  const leftHeaderColor = opts.leftHeaderColor || C.accent;
  const rightHeaderColor = opts.rightHeaderColor || C.accent;

  if (leftHeader) {
    slide.addText(leftHeader, {
      x: M, y: headerY, w: col1W, h: 0.45,
      fontSize: 20, fontFace: theme.fonts.heading,
      color: leftHeaderColor, bold: true,
    });
  }
  if (rightHeader) {
    slide.addText(rightHeader, {
      x: col2X, y: headerY, w: col2W, h: 0.45,
      fontSize: 20, fontFace: theme.fonts.heading,
      color: rightHeaderColor, bold: true,
    });
  }

  // Vertical divider
  slide.addShape(pptx.ShapeType.rect, {
    x: M + col1W + gutter / 2 - 0.01, y: CONTENT_Y,
    w: 0.02, h: CONTENT_H,
    fill: { color: C.surface },
  });

  const maxItems = Math.max(leftItems.length, rightItems.length);
  // Font size by density
  const fontSize = maxItems <= 3 ? 17 : maxItems <= 5 ? 16 : maxItems <= 7 ? 15 : 14;
  // Item slot height: distribute items evenly across bodyH so content fills the slide.
  // Each slot gets bodyH / maxItems inches; text renders at top of each slot.
  const slotH = bodyH / maxItems;

  const renderColItems = (items, x, w) => {
    items.forEach((item, i) => {
      const y = bodyY + i * slotH;
      const textItems = [];
      const text = typeof item === "string" ? item : item.text;
      _pushBulletItem(textItems, text, fontSize, fontSize, 4, C);
      slide.addText(textItems, {
        x, y, w, h: slotH,
        valign: "top",
        fontFace: theme.fonts.body,
      });
    });
  };

  renderColItems(leftItems, M, col1W);
  renderColItems(rightItems, col2X, col2W);

  if (notes) slide.addNotes(notes);
  if (!deck.useSlideMaster) {
    addFooter(slide, slideNum, theme);
  }
  return slide;
}


/**
 * Add a card grid slide (2x2 or 2x3 layout).
 */
export function addCardGrid(deck, title, cards, slideNum, notes) {
  const { pptx, theme, layout } = deck;
  const { M, CONTENT_W, CONTENT_Y, CONTENT_H } = layout;
  const C = theme.colors;
  const T = theme.typography;
  const slideOpts = deck.useSlideMaster
    ? { masterName: masterNameFor('cardGrid') }
    : {};
  const slide = pptx.addSlide(slideOpts);
  if (!deck.useSlideMaster) {
    slide.background = { color: C.background };
  }

  slide.addText(title, {
    x: M, y: 0.78, w: CONTENT_W, h: 0.55,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.heading_color || C.text_primary, bold: true,
  });

  const n = cards.length;
  const cols = n === 3 ? 3 : n <= 4 ? 2 : 3;
  const rows = Math.ceil(n / cols);
  const gap = 0.4;
  const cardW = (CONTENT_W - (cols - 1) * gap) / cols;
  const cardH = (CONTENT_H - (rows - 1) * gap) / rows;

  const lastRowCount = n % cols || cols;
  const lastRowOffset = lastRowCount < cols
    ? (CONTENT_W - lastRowCount * (cardW + gap) + gap) / 2
    : 0;

  cards.forEach((card, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    const isLastRow = row === rows - 1;
    const x = M + col * (cardW + gap) + (isLastRow ? lastRowOffset : 0);
    const y = CONTENT_Y + row * (cardH + gap);
    const accentColor = card.accent || C.accent;

    slide.addShape(pptx.ShapeType.rect, {
      x, y, w: cardW, h: cardH,
      fill: { color: C.surface },
      shadow: cardShadow(theme),
    });

    slide.addShape(pptx.ShapeType.rect, {
      x, y, w: 0.06, h: cardH,
      fill: { color: accentColor },
    });

    if (card.iconImg) {
      slide.addShape(pptx.ShapeType.ellipse, {
        x: x + 0.25, y: y + 0.25, w: 0.55, h: 0.55,
        fill: { color: C.background },
      });
      slide.addImage({
        data: card.iconImg,
        x: x + 0.33, y: y + 0.33, w: 0.39, h: 0.39,
      });
    }

    const titleX = card.iconImg ? x + 0.95 : x + 0.25;
    const titleW = card.iconImg ? cardW - 1.1 : cardW - 0.45;
    slide.addText(card.title, {
      x: titleX, y: y + 0.2, w: titleW, h: 0.55,
      fontSize: 18, fontFace: theme.fonts.heading,
      color: C.text_primary, bold: true,
      valign: "middle",
    });

    slide.addText(card.body, {
      x: x + 0.25, y: y + 0.85, w: cardW - 0.45, h: cardH - 1.1,
      fontSize: 14, fontFace: theme.fonts.body,
      color: C.text_body, valign: "top",
    });
  });

  if (notes) slide.addNotes(notes);
  if (!deck.useSlideMaster) {
    addFooter(slide, slideNum, theme);
  }
  return slide;
}


/**
 * Add a logo grid slide for technology stack slides (4–8 named tools).
 * Each cell: brand-colored top bar, logo circle, tool name, one-line description.
 * Rich mode only — corporate-match mode should use addIconRowsSlide instead.
 *
 * @param {object} deck        - Deck bundle from createDeck()
 * @param {string} title       - Slide title
 * @param {Array}  items       - Array of { name, description } objects
 * @param {Array}  iconImages  - Array of base64 data URIs (from iconToBase64)
 * @param {Array}  brandColors - Array of hex color strings (no #) per item
 * @param {number} slideNum    - Slide number for footer
 * @param {string} [notes]     - Optional speaker notes
 */
export function addLogoGridSlide(deck, title, items, iconImages, brandColors, slideNum, notes) {
  const { pptx, theme, layout } = deck;
  const { M, CONTENT_W, CONTENT_Y, CONTENT_H } = layout;
  const C = theme.colors;
  const T = theme.typography;

  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  slide.addText(title, {
    x: M, y: 0.3, w: CONTENT_W, h: 0.7,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.heading_color || C.text_primary, bold: true,
  });

  const n = items.length;
  const cols = n <= 4 ? n : (n <= 6 ? 3 : 4);
  const rows = Math.ceil(n / cols);
  const gap = 0.3;
  const cardW = (CONTENT_W - (cols - 1) * gap) / cols;
  const cardH = (CONTENT_H - (rows - 1) * gap) / rows;
  const circleSize = Math.min(0.8, cardH * 0.35);

  items.forEach((item, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    const x = M + col * (cardW + gap);
    const y = CONTENT_Y + row * (cardH + gap);

    // Card
    slide.addShape(pptx.ShapeType.rect, {
      x, y, w: cardW, h: cardH,
      fill: { color: C.surface },
      shadow: cardShadow(theme),
    });

    // Brand color top bar
    const brandColor = (brandColors && brandColors[i]) || C.accent;
    slide.addShape(pptx.ShapeType.rect, {
      x, y, w: cardW, h: 0.06,
      fill: { color: brandColor },
    });

    // Logo circle on dark background so colored icons pop
    const circleX = x + (cardW - circleSize) / 2;
    const circleY = y + 0.2;
    slide.addShape(pptx.ShapeType.ellipse, {
      x: circleX, y: circleY, w: circleSize, h: circleSize,
      fill: { color: C.background },
    });

    if (iconImages && iconImages[i]) {
      const inset = circleSize * 0.15;
      slide.addImage({
        data: iconImages[i],
        x: circleX + inset, y: circleY + inset,
        w: circleSize - 2 * inset, h: circleSize - 2 * inset,
      });
    }

    // Tool name
    slide.addText(item.name, {
      x: x + 0.1, y: circleY + circleSize + 0.1, w: cardW - 0.2, h: 0.35,
      fontSize: 15, fontFace: theme.fonts.heading,
      color: C.text_primary, bold: true, align: "center",
    });

    // Description
    slide.addText(item.description, {
      x: x + 0.1, y: circleY + circleSize + 0.45, w: cardW - 0.2,
      h: cardH - circleSize - 0.75,
      fontSize: 12, fontFace: theme.fonts.body,
      color: C.text_body, align: "center", valign: "top",
    });
  });

  if (notes) slide.addNotes(notes);
  addFooter(slide, slideNum, theme);
  return slide;
}


/**
 * Add a stat/callout slide with large numbers.
 */
export function addStatCallout(deck, title, stats, slideNum, notes) {
  const { pptx, theme, layout } = deck;
  const { M, CONTENT_W, CONTENT_Y, CONTENT_H } = layout;
  const C = theme.colors;
  const T = theme.typography;
  const slideOpts = deck.useSlideMaster
    ? { masterName: masterNameFor('statCallout') }
    : {};
  const slide = pptx.addSlide(slideOpts);
  if (!deck.useSlideMaster) {
    slide.background = { color: C.background };
  }

  slide.addText(title, {
    x: M, y: 0.78, w: CONTENT_W, h: 0.55,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.heading_color || C.text_primary, bold: true,
  });

  const n = stats.length;
  const gap = 0.5;
  const statW = (CONTENT_W - (n - 1) * gap) / n;

  stats.forEach((stat, i) => {
    const x = M + i * (statW + gap);
    const y = CONTENT_Y + CONTENT_H * 0.15;

    slide.addShape(pptx.ShapeType.rect, {
      x: x + 0.1, y: y - 0.15, w: statW - 0.2, h: 3.1,
      fill: { color: C.surface },
      rectRadius: 0.1,
      shadow: cardShadow(theme),
    });

    slide.addText(stat.value, {
      x, y, w: statW, h: 1.2,
      fontSize: T.stat_size, fontFace: theme.fonts.heading,
      color: stat.color || C.stat_color || C.accent, bold: T.stat_bold,
      align: "center",
    });

    slide.addText(stat.label, {
      x, y: y + 1.3, w: statW, h: 0.6,
      fontSize: T.stat_label_size, fontFace: theme.fonts.body,
      color: C.text_body,
      align: "center",
    });

    if (stat.desc) {
      const descOpts = {
        fontSize: T.stat_desc_size, fontFace: theme.fonts.body,
        color: C.text_secondary, align: "center",
      };
      const descContent = linkifyText(stat.desc, descOpts);
      if (Array.isArray(descContent)) {
        slide.addText(descContent, {
          x, y: y + 2.0, w: statW, h: 0.8,
          align: "center",
        });
      } else {
        slide.addText(stat.desc, {
          x, y: y + 2.0, w: statW, h: 0.8,
          ...descOpts,
        });
      }
    }
  });

  if (notes) slide.addNotes(notes);
  if (!deck.useSlideMaster) {
    addFooter(slide, slideNum, theme);
  }
  return slide;
}


/**
 * Add a code block slide.
 */
export function addCodeSlide(deck, title, code, slideNum, notes) {
  const { pptx, theme, layout } = deck;
  const { M, CONTENT_W, CONTENT_Y, CONTENT_H } = layout;
  const C = theme.colors;
  const T = theme.typography;
  const slideOpts = deck.useSlideMaster
    ? { masterName: masterNameFor('code') }
    : {};
  const slide = pptx.addSlide(slideOpts);
  if (!deck.useSlideMaster) {
    slide.background = { color: C.background };
  }

  slide.addText(title, {
    x: M, y: 0.78, w: CONTENT_W, h: 0.55,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.heading_color || C.text_primary, bold: true,
  });

  slide.addShape(pptx.ShapeType.rect, {
    x: M, y: CONTENT_Y, w: CONTENT_W, h: CONTENT_H,
    fill: { color: C.code_bg },
  });

  slide.addShape(pptx.ShapeType.rect, {
    x: M, y: CONTENT_Y, w: CONTENT_W, h: 0.05,
    fill: { color: C.accent },
  });

  slide.addText(code, {
    x: M + 0.3, y: CONTENT_Y + 0.25, w: CONTENT_W - 0.6, h: CONTENT_H - 0.4,
    fontSize: T.code_size, fontFace: theme.fonts.mono,
    color: C.code_text,
    valign: "top",
    paraSpaceAfter: 6,
  });

  if (notes) slide.addNotes(notes);
  if (!deck.useSlideMaster) {
    addFooter(slide, slideNum, theme);
  }
  return slide;
}


/**
 * Add a section divider slide (numbered panel on left, title right).
 */
export function addSectionDivider(deck, sectionNumber, title, slideNum) {
  const { pptx, theme, layout } = deck;
  const { M } = layout;
  const C = theme.colors;
  const slideOpts = deck.useSlideMaster
    ? { masterName: masterNameFor('sectionDivider') }
    : {};
  const slide = pptx.addSlide(slideOpts);

  const panelW = SW * 0.18;

  if (!deck.useSlideMaster) {
    slide.background = { color: C.background };
    slide.addShape(pptx.ShapeType.rect, {
      x: 0, y: 0, w: panelW, h: SH,
      fill: { color: C.background_alt },
    });
  }

  const numStr = String(sectionNumber).padStart(2, "0");
  slide.addText(numStr, {
    x: 0, y: SH * 0.3, w: panelW, h: 1.5,
    fontSize: 96, fontFace: theme.fonts.heading,
    color: C.text_secondary, bold: true,
    align: "center", valign: "middle",
    transparency: 70,
  });

  if (!deck.useSlideMaster) {
    slide.addShape(pptx.ShapeType.rect, {
      x: panelW - 0.04, y: 0, w: 0.04, h: SH,
      fill: { color: C.accent },
    });
  }

  const rightX = panelW + 0.6;
  const rightW = SW - rightX - M;

  slide.addText("SECTION", {
    x: rightX, y: SH * 0.35, w: rightW, h: 0.4,
    fontSize: 12, fontFace: theme.fonts.body,
    color: C.text_secondary,
    charSpacing: 6,
  });

  slide.addText(title, {
    x: rightX, y: SH * 0.42, w: rightW, h: 1.2,
    fontSize: 42, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
  });

  slide.addShape(pptx.ShapeType.rect, {
    x: rightX, y: SH * 0.42 + 1.25, w: 2.0, h: 0.06,
    fill: { color: C.accent },
  });

  if (!deck.useSlideMaster) {
    addFooter(slide, slideNum, theme);
  }
  return slide;
}


/**
 * Start a PowerPoint section: every slide added after this call belongs to
 * it until the next startSection. Call it before the first slide so no slide
 * is left outside a section.
 * @param {object} deck
 * @param {string} title  — section name shown in PowerPoint's slide sorter
 */
export function startSection(deck, title) {
  const { pptx } = deck;
  pptx.addSection({ title });
  if (!deck._sectionAware) {
    // pptxgenjs puts slides added without a sectionTitle into a new
    // "Default" section, so tag every slide with the current section
    const addSlide = pptx.addSlide.bind(pptx);
    pptx.addSlide = (opts = {}) => addSlide({ ...opts, sectionTitle: deck._section });
    deck._sectionAware = true;
  }
  deck._section = title;
}


/**
 * Add a 30-3-30 tier divider: the tier name centered, with an optional
 * subtitle (e.g. the deck title) underneath.
 * @param {object} deck
 * @param {string} title     — e.g. "Executive Overview (30 Sec)"
 * @param {string} subtitle  — small accent line under the title ('' for none)
 * @param {number} slideNum
 * @param {string} [notes]
 */
export function addTierDivider(deck, title, subtitle, slideNum, notes) {
  const { pptx, theme } = deck;
  const C = theme.colors;
  const slideOpts = deck.useSlideMaster
    ? { masterName: masterNameFor('sectionDivider') }
    : {};
  const slide = pptx.addSlide(slideOpts);
  if (!deck.useSlideMaster) {
    slide.background = { color: C.background };
  }

  slide.addText(title, {
    x: 1, y: SH * 0.36, w: SW - 2, h: 1.2,
    fontSize: 40, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
    align: "center", valign: "middle",
  });
  slide.addShape(pptx.ShapeType.rect, {
    x: (SW - 1.6) / 2, y: SH * 0.36 + 1.3, w: 1.6, h: 0.05,
    fill: { color: C.accent },
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 1, y: SH * 0.36 + 1.5, w: SW - 2, h: 0.5,
      fontSize: 16, fontFace: theme.fonts.body,
      color: C.accent, italic: true,
      align: "center", valign: "middle",
    });
  }

  if (notes) slide.addNotes(notes);
  if (!deck.useSlideMaster) {
    addFooter(slide, slideNum, theme);
  }
  return slide;
}


/**
 * Add a closing slide (AMD style: centered wordmark, no footer).
 * With an opt-in partner co-brand: AMD wordmark | divider | partner logo.
 */
export function addClosingSlide(deck, slideNum, notes) {
  const { pptx, theme, layout } = deck;
  const C = theme.colors;
  const slideOpts = deck.useSlideMaster
    ? { masterName: masterNameFor('closing') }
    : {};
  const slide = pptx.addSlide(slideOpts);
  if (!deck.useSlideMaster) {
    slide.background = { color: C.background };
  }

  const bigLogo = _bigLogo(theme);
  if (userAssets.cobrand) {
    // Co-brand: AMD | divider | partner, both centred in their half
    const half = SW / 2;
    if (bigLogo) {
      slide.addImage({ path: bigLogo, x: half - 0.7 - 4.6, y: (SH - 1.09) / 2, w: 4.6, h: 1.09 });
    }
    slide.addShape(pptx.ShapeType.line, {
      x: half, y: SH / 2 - 1.1, w: 0, h: 2.2,
      line: { color: C.text_secondary || C.text_primary, width: 1 },
    });
    _cobrand(slide, { x: half + 0.7, y: SH / 2 - 0.8, w: 4.6, h: 1.6, center: true });
  } else if (bigLogo) {
    // corp.potx exact: x=3.97", y=3.11", w=5.39", h=1.28" — perfectly centered
    slide.addImage({
      path: bigLogo,
      x: 3.97, y: 3.11, w: 5.39, h: 1.28,
    });
  } else {
    slide.addText("Thank You", {
      x: 1, y: (SH - 1.2) / 2, w: SW - 2, h: 1.2,
      fontSize: 48, fontFace: theme.fonts.heading,
      color: theme.colors.text_primary, bold: true,
      align: "center", valign: "middle",
    });
  }

  if (notes) slide.addNotes(notes);
  if (!deck.useSlideMaster) {
    addFooter(slide, slideNum, theme, { suppressLogo: true, suppressNumber: true });
  }
  return slide;
}


// ═══════════════════════════════════════════════════════════════
// Matt's Master Layout Library
// ═══════════════════════════════════════════════════════════════

/**
 * Layout 1 — Title Alt: text left-center, large AMD wordmark right.
 * No arrow background. Use when the title slide needs a clean black look.
 * @param {object} deck
 * @param {string} title
 * @param {string} subtitle
 * @param {number} slideNum
 */
export function addTitleAlt(deck, title, subtitle, slideNum) {
  const { pptx, theme } = deck;
  const C = theme.colors;
  const T = theme.typography;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  slide.addText(title, {
    x: 0.46, y: 2.6, w: 5.5, h: 1.2,
    fontSize: T.title_size, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.46, y: 3.9, w: 5.5, h: 0.5,
      fontSize: T.subtitle_size, fontFace: theme.fonts.body,
      color: C.text_secondary,
    });
  }
  // Large AMD wordmark right (~40% of slide width, vertically centered)
  const bigLogo = _bigLogo(theme);
  if (bigLogo) {
    slide.addImage({ path: bigLogo, x: 6.5, y: 2.9, w: 5.8, h: 1.38 });
  }
  _cobrand(slide, { x: 0.46, y: 4.8, w: 2.8, h: 0.8 });
  addFooter(slide, slideNum, theme, { suppressLogo: true });
  return slide;
}

/**
 * Layout 3 — Section + Content: tall left column with section title,
 * vertical divider line, large right content area. No header logo.
 * @param {object} deck
 * @param {string} sectionTitle  — displayed vertically anchored bottom-left
 * @param {string[]} bullets
 * @param {number} slideNum
 */
export function addSectionContent(deck, sectionTitle, bullets, slideNum, notes) {
  const { pptx, theme } = deck;
  const C = theme.colors;
  const T = theme.typography;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  // Left panel — section title anchored to bottom
  slide.addText(sectionTitle, {
    x: 0.3, y: 1.0, w: 2.8, h: 5.8,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
    valign: 'bottom',
  });

  // Vertical divider
  slide.addShape(pptx.ShapeType.line, {
    x: 3.3, y: 0.2, w: 0, h: 6.8,
    line: { color: C.surface, width: 1 },
  });

  // Right content area — bullets may be an array or a plain string
  const bulletArr = Array.isArray(bullets)
    ? bullets
    : (bullets ? String(bullets).split('\n').filter(Boolean) : []);
  const textItems = [];
  bulletArr.forEach(b => {
    textItems.push({
      text: typeof b === 'string' ? b : b.text,
      options: { fontSize: T.body_size, color: C.text_body, bullet: true, breakLine: true,
                 fontFace: theme.fonts.body, paraSpaceBefore: 6 },
    });
  });
  if (textItems.length) {
    slide.addText(textItems, {
      x: 3.55, y: 0.5, w: 9.4, h: 6.5, valign: 'top',
    });
  }

  addFooter(slide, slideNum, theme, { suppressLogo: true });
  if (notes) slide.addNotes(notes);
  return slide;
}

/**
 * Layout 4 — Two-Col Numbered: white decorative bar across top,
 * left: section title, right: numbered list.
 * @param {object} deck
 * @param {string} sectionTitle
 * @param {string[]} items  — numbered on the right
 * @param {number} slideNum
 */
export function addTwoColNumbered(deck, sectionTitle, items, slideNum, notes) {
  const { pptx, theme } = deck;
  const C = theme.colors;
  const T = theme.typography;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  // Horizontal accent bar
  slide.addShape(pptx.ShapeType.rect, {
    x: 0.46, y: 0.9, w: 3.1, h: 0.06, fill: { color: C.text_primary },
  });
  slide.addShape(pptx.ShapeType.rect, {
    x: 3.7, y: 0.9, w: 9.0, h: 0.06, fill: { color: C.surface },
  });

  // Left: section title
  slide.addText(sectionTitle, {
    x: 0.46, y: 1.1, w: 3.0, h: 5.5,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true, valign: 'top',
  });

  // Right: numbered list
  const textItems = (items || []).flatMap((item, i) => [
    {
      text: `${String(i + 1).padStart(2, '0')}  ${typeof item === 'string' ? item : item.text}`,
      options: {
        fontSize: T.body_size, fontFace: theme.fonts.body,
        color: C.text_body, bullet: false, breakLine: true, paraSpaceBefore: 14,
      },
    },
  ]);
  if (textItems.length) {
    slide.addText(textItems, { x: 3.7, y: 1.1, w: 9.0, h: 5.8, valign: 'top' });
  }

  addFooter(slide, slideNum, theme, { suppressLogo: true });
  if (notes) slide.addNotes(notes);
  return slide;
}

/**
 * Layout 5 — Picture + Caption: full-width title, large image left ~60%,
 * caption text box right.
 * @param {object} deck
 * @param {string} title
 * @param {string} imagePath
 * @param {string} caption
 * @param {number} slideNum
 */
export function addPictureCaption(deck, title, imagePath, caption, slideNum, notes) {
  const { pptx, theme } = deck;
  const C = theme.colors;
  const T = theme.typography;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  // Title bar across full width
  slide.addText(title, {
    x: 0.46, y: 0.3, w: SW - 0.92, h: 0.55,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
  });

  // Image placeholder or actual image — left ~60%
  if (imagePath && existsSync(imagePath)) {
    slide.addImage({ path: imagePath, x: 0.46, y: 1.05, w: 7.6, h: 5.55 });
  } else {
    slide.addShape(pptx.ShapeType.rect, {
      x: 0.46, y: 1.05, w: 7.6, h: 5.55,
      fill: { color: C.surface }, line: { color: C.surface },
    });
    slide.addText('[ Image ]', {
      x: 0.46, y: 1.05, w: 7.6, h: 5.55,
      fontSize: T.small_size, color: C.text_secondary, align: 'center', valign: 'middle',
    });
  }

  // Caption right column
  if (caption) {
    slide.addText(caption, {
      x: 8.3, y: 1.05, w: 4.6, h: 5.55,
      fontSize: T.body_size, fontFace: theme.fonts.body,
      color: C.text_body, valign: 'top', wrap: true,
    });
  }

  addFooter(slide, slideNum, theme, { suppressLogo: true });
  if (notes) slide.addNotes(notes);
  return slide;
}

/**
 * Layout 7 — 4-Image Gallery: title across top, 4 image cells in a row,
 * caption text below each image.
 * @param {object} deck
 * @param {string} title
 * @param {Array<{imagePath?:string, caption:string}>} items  — exactly 4
 * @param {number} slideNum
 */
export function addFourImageGallery(deck, title, items, slideNum, notes) {
  const { pptx, theme } = deck;
  const C = theme.colors;
  const T = theme.typography;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  slide.addText(title, {
    x: 0.46, y: 0.3, w: SW - 0.92, h: 0.55,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
  });

  const cols = 4;
  const imgW = (SW - 0.92 - (cols - 1) * 0.18) / cols;
  const imgH = 3.7;
  const capH = 0.9;
  const startX = 0.46;
  const imgY = 1.05;
  const capY = imgY + imgH + 0.1;

  (items || []).slice(0, 4).forEach((item, i) => {
    const x = startX + i * (imgW + 0.18);
    if (item.imagePath && existsSync(item.imagePath)) {
      slide.addImage({ path: item.imagePath, x, y: imgY, w: imgW, h: imgH });
    } else {
      slide.addShape(pptx.ShapeType.rect, {
        x, y: imgY, w: imgW, h: imgH,
        fill: { color: C.surface }, line: { color: C.surface },
      });
    }
    if (item.caption) {
      slide.addText(item.caption, {
        x, y: capY, w: imgW, h: capH,
        fontSize: T.small_size, fontFace: theme.fonts.body,
        color: C.text_body, align: 'center', valign: 'top', wrap: true,
      });
    }
  });

  addFooter(slide, slideNum, theme, { suppressLogo: true });
  if (notes) slide.addNotes(notes);
  return slide;
}

/**
 * Layout 9 — 3-Col Content: title across top, 3 equal columns each with
 * a heading, teal accent bar, and body text.
 * @param {object} deck
 * @param {string} title
 * @param {Array<{heading:string, body:string}>} columns  — exactly 3
 * @param {number} slideNum
 */
export function addThreeColContent(deck, title, columns, slideNum, notes) {
  const { pptx, theme } = deck;
  const C = theme.colors;
  const T = theme.typography;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  slide.addText(title, {
    x: 0.46, y: 0.3, w: SW - 0.92, h: 0.55,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
  });

  const colW = (SW - 0.92 - 2 * 0.22) / 3;
  const gap = 0.22;
  const startX = 0.46;
  const headY = 1.1;
  const barY = 1.68;
  const bodyY = 1.82;

  (columns || []).slice(0, 3).forEach((col, i) => {
    const x = startX + i * (colW + gap);
    slide.addText(col.heading || '', {
      x, y: headY, w: colW, h: 0.5,
      fontSize: T.subtitle_size, fontFace: theme.fonts.heading,
      color: C.text_primary, bold: true,
    });
    slide.addShape(pptx.ShapeType.rect, {
      x, y: barY, w: colW, h: 0.04, fill: { color: C.accent },
    });
    slide.addText(col.body || '', {
      x, y: bodyY, w: colW, h: 4.8,
      fontSize: T.body_size, fontFace: theme.fonts.body,
      color: C.text_body, valign: 'top', wrap: true,
    });
  });

  addFooter(slide, slideNum, theme, { suppressLogo: true });
  if (notes) slide.addNotes(notes);
  return slide;
}

/**
 * Layout 8 — 3-Col Image+Text: title across top, 3 equal columns each with
 * a heading, image placeholder, and body text below.
 * @param {object} deck
 * @param {string} title
 * @param {Array<{heading:string, imagePath?:string, body:string}>} columns
 * @param {number} slideNum
 */
export function addThreeColImageText(deck, title, columns, slideNum, notes) {
  const { pptx, theme } = deck;
  const C = theme.colors;
  const T = theme.typography;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  slide.addText(title, {
    x: 0.46, y: 0.3, w: SW - 0.92, h: 0.55,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
  });

  const colW = (SW - 0.92 - 2 * 0.22) / 3;
  const gap = 0.22;
  const startX = 0.46;
  const headY = 1.1;
  const imgY = 1.65;
  const imgH = 2.5;
  const bodyY = imgY + imgH + 0.1;
  const bodyH = SH - bodyY - 0.55;

  (columns || []).slice(0, 3).forEach((col, i) => {
    const x = startX + i * (colW + gap);
    slide.addText(col.heading || '', {
      x, y: headY, w: colW, h: 0.48,
      fontSize: T.subtitle_size, fontFace: theme.fonts.heading,
      color: C.text_primary, bold: true,
    });
    if (col.imagePath && existsSync(col.imagePath)) {
      slide.addImage({ path: col.imagePath, x, y: imgY, w: colW, h: imgH });
    } else {
      slide.addShape(pptx.ShapeType.rect, {
        x, y: imgY, w: colW, h: imgH,
        fill: { color: C.surface }, line: { color: C.surface },
      });
    }
    if (col.body) {
      slide.addText(col.body, {
        x, y: bodyY, w: colW, h: bodyH,
        fontSize: T.body_size, fontFace: theme.fonts.body,
        color: C.text_body, valign: 'top', wrap: true,
      });
    }
  });

  addFooter(slide, slideNum, theme, { suppressLogo: true });
  if (notes) slide.addNotes(notes);
  return slide;
}

/**
 * Layout 10 — 3-Image Gallery: title, 3 large images in row, caption below each.
 * @param {object} deck
 * @param {string} title
 * @param {Array<{imagePath?:string, caption:string}>} items
 * @param {number} slideNum
 */
export function addThreeImageGallery(deck, title, items, slideNum, notes) {
  const { pptx, theme } = deck;
  const C = theme.colors;
  const T = theme.typography;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  slide.addText(title, {
    x: 0.46, y: 0.3, w: SW - 0.92, h: 0.55,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
  });

  const cols = 3;
  const imgW = (SW - 0.92 - (cols - 1) * 0.22) / cols;
  const imgH = 4.1;
  const capH = 0.75;
  const imgY = 1.05;
  const capY = imgY + imgH + 0.1;

  (items || []).slice(0, 3).forEach((item, i) => {
    const x = 0.46 + i * (imgW + 0.22);
    if (item.imagePath && existsSync(item.imagePath)) {
      slide.addImage({ path: item.imagePath, x, y: imgY, w: imgW, h: imgH });
    } else {
      slide.addShape(pptx.ShapeType.rect, {
        x, y: imgY, w: imgW, h: imgH,
        fill: { color: C.surface }, line: { color: C.surface },
      });
    }
    if (item.caption) {
      slide.addText(item.caption, {
        x, y: capY, w: imgW, h: capH,
        fontSize: T.small_size, fontFace: theme.fonts.body,
        color: C.text_body, align: 'center', wrap: true,
      });
    }
  });

  addFooter(slide, slideNum, theme, { suppressLogo: true });
  if (notes) slide.addNotes(notes);
  return slide;
}

/**
 * Layout 11 — 2-Image Gallery: title, 2 large images side by side, caption below each.
 * @param {object} deck
 * @param {string} title
 * @param {Array<{imagePath?:string, caption:string}>} items  — exactly 2
 * @param {number} slideNum
 */
export function addTwoImageGallery(deck, title, items, slideNum, notes) {
  const { pptx, theme } = deck;
  const C = theme.colors;
  const T = theme.typography;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  slide.addText(title, {
    x: 0.46, y: 0.3, w: SW - 0.92, h: 0.55,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
  });

  const imgW = (SW - 0.92 - 0.3) / 2;
  const imgH = 4.4;
  const capH = 0.75;
  const imgY = 1.05;
  const capY = imgY + imgH + 0.1;

  (items || []).slice(0, 2).forEach((item, i) => {
    const x = 0.46 + i * (imgW + 0.3);
    if (item.imagePath && existsSync(item.imagePath)) {
      slide.addImage({ path: item.imagePath, x, y: imgY, w: imgW, h: imgH });
    } else {
      slide.addShape(pptx.ShapeType.rect, {
        x, y: imgY, w: imgW, h: imgH,
        fill: { color: C.surface }, line: { color: C.surface },
      });
    }
    if (item.caption) {
      slide.addText(item.caption, {
        x, y: capY, w: imgW, h: capH,
        fontSize: T.small_size, fontFace: theme.fonts.body,
        color: C.text_body, align: 'center', wrap: true,
      });
    }
  });

  addFooter(slide, slideNum, theme, { suppressLogo: true });
  if (notes) slide.addNotes(notes);
  return slide;
}

/**
 * Layout 12 — Cinematic: full-bleed image covers top ~68%, black bar at bottom
 * with AMD wordmark left, vertical rule, large title right.
 * @param {object} deck
 * @param {string} title
 * @param {string} imagePath
 * @param {number} slideNum
 */
export function addCinematicSlide(deck, title, imagePath, slideNum, notes) {
  const { pptx, theme } = deck;
  const C = theme.colors;
  const T = theme.typography;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  const imgH = SH * 0.68;
  const barY = imgH;
  const barH = SH - barY;

  if (imagePath && existsSync(imagePath)) {
    _addImageFit(slide, imagePath, { x: 0, y: 0, w: SW, h: imgH }, 'cover');
  } else {
    slide.addShape(pptx.ShapeType.rect, {
      x: 0, y: 0, w: SW, h: imgH,
      fill: { color: C.surface }, line: { color: C.surface },
    });
  }

  // Black bar
  slide.addShape(pptx.ShapeType.rect, {
    x: 0, y: barY, w: SW, h: barH,
    fill: { color: C.background }, line: { color: C.background },
  });

  // AMD wordmark in bar
  if (theme.logo.path && existsSync(theme.logo.path)) {
    const logoW = 1.6;
    const logoH = logoW / (6597 / 1574);
    slide.addImage({ path: theme.logo.path, x: 0.46, y: barY + (barH - logoH) / 2, w: logoW, h: logoH });
  }

  // Vertical rule
  slide.addShape(pptx.ShapeType.line, {
    x: 2.3, y: barY + 0.12, w: 0, h: barH - 0.24,
    line: { color: C.surface, width: 1 },
  });

  // Title in bar
  slide.addText(title, {
    x: 2.55, y: barY, w: SW - 3.0, h: barH,
    fontSize: T.heading_size, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true, valign: 'middle',
  });

  if (notes) slide.addNotes(notes);
  return slide;
}

/**
 * Layout 13 — Split Image + Content: left half image, right half title + body.
 * @param {object} deck
 * @param {string} title
 * @param {string[]} bullets
 * @param {string} imagePath
 * @param {number} slideNum
 */
export function addSplitImageContent(deck, title, bullets, imagePath, slideNum, notes) {
  const { pptx, theme } = deck;
  const C = theme.colors;
  const T = theme.typography;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  const splitX = SW / 2;

  // Left: image
  if (imagePath && existsSync(imagePath)) {
    slide.addImage({ path: imagePath, x: 0, y: 0, w: splitX, h: SH });
  } else {
    slide.addShape(pptx.ShapeType.rect, {
      x: 0, y: 0, w: splitX, h: SH,
      fill: { color: C.surface }, line: { color: C.surface },
    });
  }

  // Right: teal title bar
  slide.addShape(pptx.ShapeType.rect, {
    x: splitX, y: 0.78, w: splitX, h: 0.65,
    fill: { color: C.accent }, line: { color: C.accent },
  });
  slide.addText(title, {
    x: splitX + 0.3, y: 0.78, w: splitX - 0.4, h: 0.65,
    fontSize: T.subtitle_size, fontFace: theme.fonts.heading,
    color: '000000', bold: true, valign: 'middle',
  });

  // Right: body
  const textItems = (bullets || []).map(b => ({
    text: typeof b === 'string' ? b : b.text,
    options: { fontSize: T.body_size, color: C.text_body, bullet: true, breakLine: true,
               fontFace: theme.fonts.body, paraSpaceBefore: 6 },
  }));
  if (textItems.length) {
    slide.addText(textItems, {
      x: splitX + 0.3, y: 1.55, w: splitX - 0.4, h: SH - 2.1, valign: 'top',
    });
  }

  addFooter(slide, slideNum, theme, { suppressLogo: true });
  if (notes) slide.addNotes(notes);
  return slide;
}

/**
 * Layout 14 — Title with Image: title slide variant, left ~55% black with
 * AMD logo + title + subtitle, right ~45% image placeholder.
 * @param {object} deck
 * @param {string} title
 * @param {string} subtitle
 * @param {string} imagePath
 * @param {number} slideNum
 */
export function addTitleWithImage(deck, title, subtitle, imagePath, slideNum) {
  const { pptx, theme } = deck;
  const C = theme.colors;
  const T = theme.typography;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };

  const splitX = SW * 0.55;

  // Right: image
  if (imagePath && existsSync(imagePath)) {
    slide.addImage({ path: imagePath, x: splitX, y: 0, w: SW - splitX, h: SH });
  } else {
    slide.addShape(pptx.ShapeType.rect, {
      x: splitX, y: 0, w: SW - splitX, h: SH,
      fill: { color: C.surface }, line: { color: C.surface },
    });
  }

  // Left: AMD logo top-left
  if (theme.logo.path && existsSync(theme.logo.path)) {
    const logoW = 0.9;
    const logoH = logoW / (6597 / 1574);
    slide.addImage({ path: theme.logo.path, x: 0.46, y: 0.38, w: logoW, h: logoH });
  }

  // Left: title
  slide.addText(title, {
    x: 0.46, y: 2.1, w: splitX - 0.7, h: 1.6,
    fontSize: T.title_size, fontFace: theme.fonts.heading,
    color: C.text_primary, bold: true,
  });

  // Left: subtitle
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.46, y: 3.8, w: splitX - 0.7, h: 0.6,
      fontSize: T.subtitle_size, fontFace: theme.fonts.body,
      color: C.text_secondary,
    });
  }
  _cobrand(slide, { x: 0.46, y: 4.8, w: 2.8, h: 0.8 });

  addFooter(slide, slideNum, theme, { suppressLogo: true, suppressNumber: true });
  return slide;
}

// ═══════════════════════════════════════════════════════════════
// Shared slide patterns (additive)
//
// Newer layouts used by both the LLM engines and the deterministic
// pptxgenjs-direct engine. They only read theme values, so they follow
// whatever theme the deck was created with. Existing builders above are
// untouched — tests/test_amd_layouts_golden.py guards them.
// ═══════════════════════════════════════════════════════════════

const TAKEAWAY_H = 0.5;

/** New content slide with background + standard title. */
function _patternSlide(deck, title) {
  const { pptx, theme, layout } = deck;
  const C = theme.colors;
  const slide = pptx.addSlide(deck.useSlideMaster ? { masterName: masterNameFor('bullet') } : {});
  if (!deck.useSlideMaster) {
    slide.background = { color: C.background };
  }
  if (title) {
    slide.addText(title, {
      x: layout.M, y: 0.78, w: layout.CONTENT_W, h: 0.55,
      fontSize: theme.typography.heading_size, fontFace: theme.fonts.heading,
      color: C.heading_color || C.text_primary, bold: true,
    });
  }
  return slide;
}

/**
 * One-sentence takeaway under the title (the "so what" of the slide).
 * Returns the y where content should start.
 */
function _addTakeaway(deck, slide, takeaway) {
  const { theme, layout } = deck;
  if (!takeaway) return layout.CONTENT_Y;
  slide.addText(takeaway, {
    x: layout.M, y: 1.33, w: layout.CONTENT_W, h: TAKEAWAY_H,
    fontSize: theme.typography.subtitle_size, fontFace: theme.fonts.body,
    color: theme.colors.accent, valign: 'top',
  });
  return layout.CONTENT_Y + TAKEAWAY_H;
}

function _finishPatternSlide(deck, slide, slideNum, notes, footerOpts = {}) {
  if (notes) slide.addNotes(notes);
  if (!deck.useSlideMaster) {
    addFooter(slide, slideNum, deck.theme, footerOpts);
  }
  return slide;
}


/**
 * Title + one-sentence takeaway + supporting points (the 30-3-30 slide).
 * @param {Array<string|{text,subs}>} points - same format as addBulletSlide
 */
export function addTakeawaySlide(deck, title, takeaway, points, slideNum, notes) {
  const { theme, layout } = deck;
  const C = theme.colors;
  const slide = _patternSlide(deck, title);
  const top = _addTakeaway(deck, slide, takeaway);
  const items = points || [];
  const n = items.length;
  const bodySize = n <= 4 ? 20 : n <= 6 ? 18 : 16;
  const spacing = n <= 4 ? 16 : 10;
  const textItems = [];
  items.forEach((b) => {
    const text = typeof b === 'string' ? b : b.text;
    _pushBulletItem(textItems, text, bodySize + 2, bodySize, spacing, C);
    if (typeof b === 'object' && b.subs) {
      b.subs.forEach((sub) => textItems.push({
        text: sub,
        options: { fontSize: bodySize - 2, color: C.text_body, bullet: true, indentLevel: 1,
                   breakLine: true, paraSpaceAfter: spacing / 2 },
      }));
    }
  });
  if (textItems.length) {
    slide.addText(textItems, {
      x: layout.M + 0.4, y: top + 0.1, w: layout.CONTENT_W - 0.8, h: layout.FOOTER_Y - top - 0.2,
      valign: 'top', fontFace: theme.fonts.body,
    });
  }
  return _finishPatternSlide(deck, slide, slideNum, notes);
}


const _NUMERIC_CELL = /^[\s$~≈<>+\-–]*[\d.,]+\s*(?:[%x×]|[KMGTP]B|[KMB]|ms|µs|s)?\s*$/;

/**
 * Native (editable) table.
 * @param {string[]} header - column headings
 * @param {string[][]} rows - body rows
 * @param {{ takeaway?: string, source?: string }} [opts]
 */
export function addTableSlide(deck, title, header, rows, slideNum, notes, opts = {}) {
  const { theme, layout } = deck;
  const C = theme.colors;
  const slide = _patternSlide(deck, title);
  const top = _addTakeaway(deck, slide, opts.takeaway);
  const bodyRows = rows || [];
  const cols = Math.max(header?.length || 0, ...bodyRows.map(r => r.length), 1);
  const n = bodyRows.length;
  const fontSize = n <= 4 ? 16 : n <= 6 ? 14 : n <= 10 ? 12 : 10;
  const border = { type: 'solid', pt: 0.75, color: C.surface };
  const numeric = Array.from({ length: cols }, (_, c) =>
    n > 0 && bodyRows.every(r => !r[c] || _NUMERIC_CELL.test(r[c])));
  const cell = (text, c, opts2) => ({
    text: text ?? '',
    options: { align: numeric[c] ? 'right' : 'left', valign: 'middle', border, ...opts2 },
  });
  const tableRows = [];
  if (header && header.length) {
    tableRows.push(Array.from({ length: cols }, (_, c) => cell(header[c], c, {
      bold: true, color: C.text_primary, fill: { color: C.surface }, fontFace: theme.fonts.heading,
    })));
  }
  bodyRows.forEach((r) => {
    tableRows.push(Array.from({ length: cols }, (_, c) => cell(r[c], c, {
      color: c === 0 ? C.text_primary : C.text_body, bold: c === 0,
    })));
  });
  const sourceH = opts.source ? 0.35 : 0;
  slide.addTable(tableRows, {
    x: layout.M, y: top + 0.1, w: layout.CONTENT_W,
    fontSize, fontFace: theme.fonts.body,
    rowH: fontSize / 72 * 2.2, autoPage: false,
  });
  if (opts.source) {
    slide.addText(opts.source, {
      x: layout.M, y: layout.FOOTER_Y - sourceH, w: layout.CONTENT_W - 1.0, h: sourceH,
      fontSize: theme.typography.small_size, fontFace: theme.fonts.body,
      color: C.text_secondary, valign: 'bottom',
    });
  }
  return _finishPatternSlide(deck, slide, slideNum, notes);
}


/**
 * Agenda — numbered sections; opts.current (1-based) highlights one item.
 * @param {string[]} items
 * @param {{ current?: number, image?: string, label?: string }} [opts] - image: photo variant (string path, or "" for the default photo); label: deck name shown on the photo
 */
export function addAgendaSlide(deck, title, items, slideNum, notes, opts = {}) {
  const { pptx, theme, layout } = deck;
  const C = theme.colors;
  const T = theme.typography;
  const slide = _patternSlide(deck, null);
  const list = items || [];
  let x = 4.6;
  let top = 1.1;
  // image '' = the bundled agenda photo
  const photo = opts.image !== undefined && opts.image !== null;
  if (photo) {
    // Photo variant (AMD exec agenda): full-bleed dimmed photo, deck label in a
    // panel on the left, the list in a translucent panel on the right
    _coverImage(deck, slide, opts.image, 'agenda-bg.png', { x: 0, y: 0, w: SW, h: SH });
    slide.addShape(pptx.ShapeType.rect, {
      x: 0, y: 0, w: SW, h: SH, fill: { color: '000000', transparency: 45 }, line: { type: 'none' },
    });
    if (opts.label) {
      slide.addShape(pptx.ShapeType.rect, {
        x: 0.65, y: 1.8, w: 3.8, h: 1.85, fill: { color: '000000', transparency: 35 }, line: { type: 'none' },
      });
      slide.addShape(pptx.ShapeType.rect, {
        x: 0.65, y: 1.8, w: 3.8, h: 0.05, fill: { color: 'A6A6A6' }, line: { type: 'none' },
      });
      const parts = String(opts.label).split('\n');
      const head = parts.length > 1 ? parts.slice(0, -1).join('\n') : '';
      const last = parts[parts.length - 1];
      slide.addText([
        ...(head ? [{ text: head, options: { fontSize: 18, breakLine: true } }] : []),
        { text: last, options: { fontSize: last.length > 40 ? 20 : 24 } },
      ], {
        x: 0.75, y: 1.95, w: 3.55, h: 1.6, fontFace: theme.fonts.body,
        color: C.text_primary, bold: true, align: 'right', valign: 'middle', margin: 0,
      });
    }
    const rows = Math.max(list.length, 1);
    const panelH = Math.min(5.3, 1.0 + rows * Math.min(0.6, (6.15 - 1.95) / rows) + 0.3);
    slide.addShape(pptx.ShapeType.rect, {
      x: 5.1, y: 0.95, w: SW - 5.1, h: panelH, fill: { color: '000000', transparency: 30 }, line: { type: 'none' },
    });
    x = 5.3;
    slide.addText(String(title || 'Agenda').toUpperCase(), {
      x, y: 1.1, w: layout.RIGHT_EDGE - x, h: 0.65,
      fontSize: 28, fontFace: theme.fonts.body, color: C.text_primary, bold: true, margin: 0,
    });
    slide.addShape(pptx.ShapeType.rect, {
      x: 5.1, y: 1.85, w: layout.RIGHT_EDGE - 5.1, h: 0.04, fill: { color: 'A6A6A6' }, line: { type: 'none' },
    });
    top = 1.95;
    x = 5.7; // number column inset from the panel edge
  } else {
    slide.addText(title || 'Agenda', {
      x: layout.M, y: 1.1, w: 3.6, h: 1.2,
      fontSize: T.title_size, fontFace: theme.fonts.heading,
      color: C.text_primary, bold: true, valign: 'top',
    });
    slide.addShape(pptx.ShapeType.rect, {
      x: layout.M, y: 2.35, w: 1.2, h: 0.05, fill: { color: C.accent },
    });
  }
  const w = layout.RIGHT_EDGE - x;
  const bottom = photo ? 6.15 : layout.FOOTER_Y;
  const rowH = Math.min(photo ? 0.6 : 0.85, (bottom - top) / Math.max(list.length, 1));
  const size = photo ? (rowH >= 0.5 ? 18 : 15) : (rowH >= 0.7 ? 22 : rowH >= 0.55 ? 18 : 15);
  list.forEach((item, i) => {
    const y = top + i * rowH;
    const active = !opts.current || opts.current === i + 1;
    slide.addText(String(i + 1).padStart(2, '0'), {
      x, y, w: 0.9, h: rowH,
      fontSize: size, fontFace: photo ? theme.fonts.body : theme.fonts.heading, bold: true, valign: 'middle',
      align: photo ? 'right' : 'left',
      color: active ? (photo ? C.text_primary : C.accent) : C.text_secondary,
    });
    slide.addText(item, {
      x: x + 0.9, y, w: w - 0.9, h: rowH,
      fontSize: size, fontFace: theme.fonts.body, valign: 'middle',
      color: active ? C.text_primary : C.text_secondary, bold: opts.current === i + 1,
    });
    if (i < list.length - 1) {
      slide.addShape(pptx.ShapeType.rect, {
        x: photo ? 5.1 : x, y: y + rowH - 0.01, w: photo ? layout.RIGHT_EDGE - 5.1 : w, h: 0.01,
        fill: { color: photo ? '7F7F7F' : C.surface },
      });
    }
  });
  if (photo) {
    const twa = _asset(theme, 'amd-twa-lockup-wht.png');
    if (existsSync(twa)) slide.addImage({ path: twa, x: 11.6, y: 6.95, w: 1.51, h: 1.51 * 750 / 2636 });
    // Number bottom-left, clear of the lockup
    slide.addText(String(slideNum), {
      x: 0.3, y: 7.05, w: 0.5, h: 0.3, fontSize: 9, fontFace: theme.fonts.body,
      color: C.text_secondary, margin: 0,
    });
  }
  return _finishPatternSlide(deck, slide, slideNum, notes,
    photo ? { suppressLogo: true, suppressNumber: true } : {});
}


/**
 * Pull quote with attribution.
 */
export function addQuoteSlide(deck, quote, attribution, slideNum, notes) {
  const { theme, layout } = deck;
  const C = theme.colors;
  const slide = _patternSlide(deck, null);
  slide.addText('“', {
    x: layout.M + 0.4, y: 1.0, w: 1.2, h: 1.4,
    fontSize: 120, fontFace: theme.fonts.heading, color: C.accent, bold: true,
  });
  const size = quote.length <= 120 ? 32 : quote.length <= 240 ? 26 : 20;
  slide.addText(quote, {
    x: layout.M + 1.4, y: 1.6, w: layout.CONTENT_W - 2.4, h: 3.6,
    fontSize: size, fontFace: theme.fonts.heading, color: C.text_primary,
    valign: 'middle', italic: true,
  });
  if (attribution) {
    slide.addText(`— ${attribution}`, {
      x: layout.M + 1.4, y: 5.35, w: layout.CONTENT_W - 2.4, h: 0.5,
      fontSize: theme.typography.subtitle_size, fontFace: theme.fonts.body,
      color: C.text_secondary,
    });
  }
  return _finishPatternSlide(deck, slide, slideNum, notes);
}


/**
 * Roadmap — timeline columns (e.g. quarters) with items under each.
 * @param {Array<{heading: string, items: string[]}>} columns
 * @param {{ takeaway?: string }} [opts]
 */
export function addRoadmapSlide(deck, title, columns, slideNum, notes, opts = {}) {
  const { pptx, theme, layout } = deck;
  const C = theme.colors;
  const slide = _patternSlide(deck, title);
  const top = _addTakeaway(deck, slide, opts.takeaway);
  const cols = columns || [];
  const n = Math.max(cols.length, 1);
  const gap = 0.25;
  const colW = (layout.CONTENT_W - (n - 1) * gap) / n;
  const lineY = top + 0.75;
  slide.addShape(pptx.ShapeType.rect, {
    x: layout.M, y: lineY - 0.015, w: layout.CONTENT_W, h: 0.03, fill: { color: C.surface },
  });
  const maxItems = Math.max(...cols.map(c => (c.items || []).length), 1);
  const size = maxItems <= 3 ? 14 : maxItems <= 5 ? 13 : 11;
  cols.forEach((col, i) => {
    const x = layout.M + i * (colW + gap);
    slide.addText(col.heading || '', {
      x, y: top, w: colW, h: 0.5,
      fontSize: 18, fontFace: theme.fonts.heading, bold: true, color: C.accent, valign: 'bottom',
    });
    slide.addShape(pptx.ShapeType.ellipse, {
      x: x, y: lineY - 0.11, w: 0.22, h: 0.22, fill: { color: C.accent },
    });
    const items = (col.items || []).map((it) => ({
      text: it,
      options: { bullet: true, breakLine: true, paraSpaceAfter: 8, fontSize: size, color: C.text_body },
    }));
    if (items.length) {
      slide.addText(items, {
        x, y: lineY + 0.25, w: colW, h: layout.FOOTER_Y - lineY - 0.35,
        fontFace: theme.fonts.body, valign: 'top',
      });
    }
  });
  return _finishPatternSlide(deck, slide, slideNum, notes);
}


/** Estimated height (in) of paragraphs at *size* pt wrapped to *w* inches (Arial). */
function _paraHeight(paras, w, size) {
  const perLine = Math.max(1, Math.floor(w * 72 / (0.45 * size)));
  const lines = paras.reduce((n, p) => n + Math.max(1, Math.ceil(p.length / perLine)), 0);
  return (lines * size * 1.15 + paras.length * 6) / 72;
}

/** Largest size from max down to min (pt) whose wrapped paragraphs fit in w × h. */
function _fitParagraphs(paras, w, h, max, min) {
  for (let size = max; size > min; size--) {
    if (_paraHeight(paras, w, size) <= h) return size;
  }
  return min;
}

/** Split paragraphs (or sentences of a single paragraph) into two halves of similar length. */
function _balancedHalves(paras) {
  const parts = paras.length > 1 ? paras : paras[0].split(/(?<=[.;])\s+/);
  const total = parts.reduce((n, p) => n + p.length, 0);
  let acc = 0, cut = 1;
  for (let i = 0; i < parts.length - 1; i++) {
    acc += parts[i].length;
    cut = i + 1;
    if (acc >= total / 2) break;
  }
  const join = paras.length > 1 ? (a) => a : (a) => [a.join(' ')];
  return [join(parts.slice(0, cut)), join(parts.slice(cut))];
}

/**
 * Legal / disclaimer text, sized to fill the slide: short notices get large
 * readable type (up to 18pt); long legal text shrinks to fit and flows into
 * two columns when that keeps it larger.
 */
export function addDisclaimerSlide(deck, title, text, slideNum, notes) {
  const { theme, layout } = deck;
  const slide = _patternSlide(deck, title || 'Disclaimer');
  const paras = String(text || '').split('\n').map(p => p.trim()).filter(Boolean);
  const h = layout.CONTENT_H - 0.2;
  const [MAX, MIN] = [18, 9];
  const style = (size) => ({
    fontSize: size, fontFace: theme.fonts.body, color: theme.colors.text_secondary,
    valign: 'top', paraSpaceAfter: 6,
  });
  const runs = (ps) => ps.map((p, i) => ({ text: p, options: { breakLine: i < ps.length - 1 } }));

  const oneSize = paras.length ? _fitParagraphs(paras, layout.CONTENT_W, h, MAX, MIN) : MAX;
  const gap = 0.5, colW = (layout.CONTENT_W - gap) / 2;
  const halves = paras.length && oneSize < 12 ? _balancedHalves(paras) : null;
  const twoSize = halves && halves[1].length
    ? Math.min(...halves.map(half => _fitParagraphs(half, colW, h, MAX, MIN))) : 0;

  if (twoSize > oneSize) {
    halves.forEach((half, c) => slide.addText(runs(half), {
      x: layout.M + c * (colW + gap), y: layout.CONTENT_Y, w: colW, h, ...style(twoSize),
    }));
  } else {
    slide.addText(runs(paras), {
      x: layout.M, y: layout.CONTENT_Y, w: layout.CONTENT_W, h, ...style(oneSize),
    });
  }
  return _finishPatternSlide(deck, slide, slideNum, notes);
}

// ═══════════════════════════════════════════════════════════════
// Brand slides (additive) — title, section and message layouts modelled on
// AMD exec / product decks: photo backgrounds that fade to black, product
// lockups, and big two-tone statements.
// ═══════════════════════════════════════════════════════════════

/** The large AMD logo for closing and alt-title slides, or "" if there is none. */
function _bigLogo(theme) {
  const path = theme.brand.wordmark ? _asset(theme, theme.brand.wordmark) : theme.logo.path;
  return path && existsSync(path) ? path : "";
}

/** Path of a file next to the theme logo (themes/assets/ by default). */
function _asset(theme, name) {
  return theme.logo.path ? theme.logo.path.replace(/[^/]+$/, name) : `themes/assets/${name}`;
}

/** Image covering a box; falls back to the bundled default, then to nothing. */
function _coverImage(deck, slide, imagePath, fallback, box) {
  const path = imagePath && existsSync(imagePath) ? imagePath : _asset(deck.theme, fallback);
  if (existsSync(path)) _addImageFit(slide, path, box, 'cover');
}

/** Largest font (pt) between min and max that fits *text* on one line in *w* inches (Arial bold). */
function _fitSize(text, w, max, min) {
  const longest = Math.max(...String(text).split('\n').map(l => l.length), 1);
  return Math.max(min, Math.min(max, Math.floor(w * 72 / (0.56 * longest))));
}

/** Black fade over a photo; side = the edge that ends fully black. */
function _fade(deck, slide, box, side) {
  const path = _asset(deck.theme, 'fade-black.png');
  if (existsSync(path)) slide.addImage({ path, ...box, flipH: side === 'right' });
}

/**
 * AMD wordmark with a product name under it (e.g. "ROCm", "Instinct").
 * ROCm uses the real lockup artwork.
 */
function _productLockup(deck, slide, product, x, y, w) {
  const { theme } = deck;
  if (product && /^rocm$/i.test(product.trim())) {
    const rocm = _asset(theme, 'title-wordmark-small.png');
    if (existsSync(rocm)) {
      slide.addImage({ path: rocm, x, y, w, h: w * 398 / 844 });
      return;
    }
  }
  const mark = _asset(theme, 'amd-wordmark.png');
  const markH = w / (6597 / 1574);
  if (existsSync(mark)) slide.addImage({ path: mark, x, y, w, h: markH });
  if (product) {
    slide.addText(product, {
      x: x - 0.05, y: y + markH + 0.02, w: w * 1.6, h: markH * 1.1,
      fontSize: Math.round(w * 15), fontFace: theme.fonts.heading,
      color: theme.colors.text_primary, valign: 'top', margin: 0,
    });
  }
}

/**
 * Executive / keynote title: full-bleed photo fading to black on the right,
 * title + "together we advance" lockup + date on the right.
 * @param {{image?: string, date?: string, footnote?: string}} [opts]
 */
export function addHeroTitleSlide(deck, title, subtitle, slideNum, opts = {}) {
  const { pptx, theme } = deck;
  const C = theme.colors;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };
  _coverImage(deck, slide, opts.image, 'chart-frame.jpeg', { x: 0, y: 0, w: SW * 0.7, h: SH });
  _fade(deck, slide, { x: SW * 0.38, y: 0, w: SW * 0.32, h: SH }, 'right');
  // Geometry follows the AMD exec title layout: text column at x 7.2"
  const x = 7.2;
  const w = SW - x - 0.3;
  slide.addText(title, {
    x, y: 1.5, w, h: 2.0, fontSize: _fitSize(title, w, 36, 26), fontFace: theme.fonts.body,
    color: C.text_primary, bold: true, valign: 'bottom', margin: 0,
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x, y: 3.6, w, h: 0.8, fontSize: 18, fontFace: theme.fonts.body,
      color: C.text_secondary, valign: 'top', margin: 0,
    });
  }
  const twa = _asset(theme, 'amd-twa-lockup-wht.png');
  if (existsSync(twa)) slide.addImage({ path: twa, x, y: 4.65, w: 3.1, h: 3.1 * 750 / 2636 });
  _cobrand(slide, { x: x + 3.45, y: 4.65, w: SW - x - 3.75, h: 3.1 * 750 / 2636 });
  if (opts.date) {
    slide.addText(opts.date, {
      x, y: 5.75, w, h: 0.45, fontSize: 18, fontFace: theme.fonts.body,
      color: C.text_primary, margin: 0,
    });
  }
  if (opts.footnote) {
    slide.addText(opts.footnote, {
      x: 0.1, y: 7.22, w: 10.2, h: 0.25, fontSize: 7, fontFace: theme.fonts.body,
      color: C.text_primary, valign: 'middle', margin: 0,
    });
  }
  return slide;
}

/**
 * Product title: product render top-left over a streak background, product
 * lockup bottom-left, title + presenter on the right.
 * @param {{product?: string, image?: string, presenter?: string, background?: string}} [opts]
 */
export function addProductTitleSlide(deck, title, subtitle, slideNum, opts = {}) {
  const { pptx, theme } = deck;
  const C = theme.colors;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };
  _coverImage(deck, slide, opts.background, 'title-bg.jpeg', { x: 0, y: 0, w: SW, h: SH });
  // Geometry follows the AMD product title layout: large render top left,
  // product lockup under it, two-tone title right
  const product = opts.image && existsSync(opts.image) ? opts.image : _asset(theme, 'title-graphic.png');
  if (existsSync(product)) slide.addImage({ path: product, x: 0.03, y: -0.06, w: 7.0, h: 7.0 * 1650 / 2933 });
  _productLockup(deck, slide, opts.product, 2.17, 4.1, 2.94);
  const x = 6.62;
  const w = SW - x - 0.4;
  // "Lead – Main" / "Lead: Main" / a line break → smaller lead line, larger main line
  const m = String(title).match(/^(.*?(?:\s[–—-]|:))\s+(.+)$/) || String(title).match(/^(.*)\n(.*)$/);
  const lines = m ? [m[1].trim(), m[2].trim()] : [String(title)];
  // Main line may wrap to two lines; the lead sits at ~3/4 of its size (ref 40 / 54)
  const main = lines[lines.length - 1];
  const oneLine = _fitSize(main, w, 54, 24);
  const mainSize = oneLine >= 40 || !main.includes(' ')
    ? oneLine : _fitSize(main.slice(0, Math.ceil(main.length / 2) + 4), w, 54, 28);
  const leadSize = Math.min(_fitSize(lines[0], w, 40, 20), Math.round(mainSize * 0.74));
  const runs = lines.map((t, i) => ({
    text: t,
    options: { fontSize: i === lines.length - 1 ? mainSize : leadSize, breakLine: i < lines.length - 1 },
  }));
  slide.addText(runs, {
    x, y: 1.3, w, h: 2.45, fontFace: theme.fonts.body,
    color: C.text_primary, bold: true, valign: 'bottom', margin: 0,
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: x + 0.05, y: 3.95, w, h: 0.45, fontSize: 20, fontFace: theme.fonts.body,
      color: C.text_primary, valign: 'top', margin: 0,
    });
  }
  if (opts.presenter) {
    slide.addText(opts.presenter, {
      x: x + 0.05, y: subtitle ? 4.5 : 4.1, w, h: 0.45, fontSize: subtitle ? 18 : 24,
      fontFace: theme.fonts.body, color: subtitle ? C.text_secondary : C.text_primary, valign: 'top', margin: 0,
    });
  }
  const twa = _asset(theme, 'amd-twa-lockup-wht.png');
  if (existsSync(twa)) slide.addImage({ path: twa, x: 11.6, y: 6.95, w: 1.51, h: 1.51 * 750 / 2636 });
  _cobrand(slide, { x: x + 0.05, y: 5.3, w: 2.8, h: 0.8 });
  return slide;
}

/**
 * Section opener with a short description: text on the left, photo fading in
 * from the right. Use addSectionDivider for a bare numbered divider.
 * @param {{image?: string}} [opts]
 */
export function addSectionIntroSlide(deck, title, body, slideNum, notes, opts = {}) {
  const { pptx, theme, layout } = deck;
  const C = theme.colors;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };
  _coverImage(deck, slide, opts.image, 'section-divider-bg.jpeg', { x: SW * 0.45, y: 0, w: SW * 0.55, h: SH });
  _fade(deck, slide, { x: SW * 0.45, y: 0, w: SW * 0.2, h: SH }, 'left');
  slide.addText(title, {
    x: layout.M, y: 2.6, w: 5.2, h: 0.8, fontSize: theme.typography.heading_size,
    fontFace: theme.fonts.heading, color: C.text_primary, bold: true, valign: 'bottom', margin: 0,
  });
  if (body) {
    slide.addText(body, {
      x: layout.M, y: 3.55, w: 5.0, h: 2.0, fontSize: 16, fontFace: theme.fonts.body,
      color: C.text_body, valign: 'top', margin: 0, paraSpaceAfter: 10,
    });
  }
  return _finishPatternSlide(deck, slide, slideNum, notes);
}

/**
 * Big two-tone statement on the left (accent headline + white subline),
 * cited evidence on the right — the "why now / market context" slide.
 * @param {Array<{text: string, source?: string}>} evidence - 1-4 items
 */
export function addStatementSlide(deck, headline, subline, evidence, slideNum, notes) {
  const { pptx, theme, layout } = deck;
  const C = theme.colors;
  const slide = _patternSlide(deck, null);
  const leftW = 4.6;
  slide.addText([
    { text: headline, options: { color: C.accent, bold: true, breakLine: !!subline } },
    ...(subline ? [{ text: subline, options: { color: C.text_primary } }] : []),
  ], {
    x: layout.M, y: 1.2, w: leftW, h: 4.8, fontSize: 30, fontFace: theme.fonts.heading,
    align: 'right', valign: 'middle', margin: 0,
  });
  const divX = layout.M + leftW + 0.35;
  slide.addShape(pptx.ShapeType.line, {
    x: divX, y: 2.0, w: 0, h: 3.2, line: { color: C.text_secondary, width: 1 },
  });
  const items = (evidence || []).slice(0, 4);
  const x = divX + 0.4;
  const w = layout.RIGHT_EDGE - x;
  const rowH = Math.min(1.6, 5.0 / Math.max(items.length, 1));
  items.forEach((item, i) => {
    const runs = [{ text: item.text, options: { color: C.text_primary, fontSize: 16, breakLine: !!item.source } }];
    if (item.source) runs.push({ text: item.source, options: { color: C.text_secondary, fontSize: 10 } });
    slide.addText(runs, {
      x, y: 1.25 + i * rowH, w, h: rowH - 0.15, fontFace: theme.fonts.body,
      valign: 'middle', margin: 0, paraSpaceAfter: 4,
    });
  });
  return _finishPatternSlide(deck, slide, slideNum, notes);
}

function _metric(value) {
  const n = parseFloat(String(value).replace(/,/g, '').replace(/[^\d.\-]/g, ''));
  return Number.isFinite(n) ? n : null;
}

/**
 * One proof point: label + accent headline + subline on the left, a
 * before/after pair of bars with the improvement multiple on the right.
 * @param {{before: {value, label}, after: {value, label}, multiple?: string, caption?: string}} proof
 * @param {{label?: string}} [opts] - small label above the headline (default "Key Takeaway")
 */
export function addProofPointSlide(deck, headline, subline, proof, slideNum, notes, opts = {}) {
  const { pptx, theme, layout } = deck;
  const C = theme.colors;
  const slide = _patternSlide(deck, null);
  slide.addText(opts.label ?? 'Key Takeaway', {
    x: layout.M, y: 0.9, w: 5, h: 0.5, fontSize: 22, fontFace: theme.fonts.heading,
    color: C.text_primary, margin: 0,
  });
  slide.addText([
    { text: headline, options: { color: C.accent, bold: true, fontSize: 28, breakLine: !!subline } },
    ...(subline ? [{ text: subline, options: { color: C.text_primary, fontSize: 20 } }] : []),
  ], {
    x: layout.M, y: 1.8, w: 4.6, h: 3.6, fontFace: theme.fonts.heading,
    align: 'right', valign: 'middle', margin: 0, paraSpaceAfter: 8,
  });
  slide.addShape(pptx.ShapeType.line, {
    x: layout.M + 4.95, y: 2.2, w: 0, h: 2.8, line: { color: C.text_secondary, width: 1 },
  });
  const p = proof || {};
  const bars = [p.before, p.after].filter(Boolean);
  const nums = bars.map((b) => _metric(b.value));
  const max = Math.max(...nums.map((n) => n ?? 0), 1);
  const baseY = 5.0;
  const maxH = 2.6;
  const barW = 1.3;
  bars.forEach((b, i) => {
    const h = nums[i] == null ? maxH * 0.5 : Math.max(0.35, maxH * nums[i] / max);
    const x = 7.0 + i * 2.9;
    slide.addShape(pptx.ShapeType.rect, {
      x, y: baseY - h, w: barW, h, fill: { color: C.accent, transparency: i === 0 ? 45 : 0 },
      line: { color: C.accent },
    });
    slide.addText(String(b.value), {
      x, y: baseY - h, w: barW, h: 0.4, fontSize: 14, fontFace: theme.fonts.body,
      color: C.text_primary, align: 'center', margin: 0,
    });
    slide.addText(b.label || '', {
      x: x - 0.4, y: baseY + 0.08, w: barW + 0.8, h: 0.4, fontSize: 14, fontFace: theme.fonts.body,
      color: C.text_primary, align: 'center', margin: 0,
    });
  });
  slide.addShape(pptx.ShapeType.line, {
    x: 6.6, y: baseY, w: 5.4, h: 0, line: { color: C.text_secondary, width: 1 },
  });
  if (p.multiple) {
    slide.addText(p.multiple, {
      x: 8.2, y: baseY - maxH - 0.75, w: 3.0, h: 0.7, fontSize: 32, fontFace: theme.fonts.heading,
      color: C.text_primary, bold: true, align: 'right', margin: 0,
    });
  }
  if (p.caption) {
    slide.addText(p.caption, {
      x: 6.6, y: baseY + 0.6, w: 5.4, h: 0.6, fontSize: 13, fontFace: theme.fonts.body,
      color: C.text_body, align: 'center', valign: 'top', margin: 0,
    });
  }
  return _finishPatternSlide(deck, slide, slideNum, notes);
}

/**
 * Product-branded feature list: lockup | title + accent tagline header,
 * optional visual on the left, features with underlined headings on the right.
 * @param {Array<{heading: string, lines: string[]}>} features - 2-4 items
 * @param {{product?: string, image?: string}} [opts]
 */
export function addFeatureListSlide(deck, title, tagline, features, slideNum, notes, opts = {}) {
  const { pptx, theme, layout } = deck;
  const C = theme.colors;
  const slide = pptx.addSlide();
  slide.background = { color: C.background };
  _productLockup(deck, slide, opts.product, layout.M, 0.42, 1.7);
  slide.addShape(pptx.ShapeType.line, {
    x: 2.55, y: 0.35, w: 0, h: 1.1, line: { color: C.text_secondary, width: 1 },
  });
  slide.addText(title, {
    x: 2.75, y: 0.3, w: SW - 3.3, h: 0.75, fontSize: theme.typography.title_size,
    fontFace: theme.fonts.heading, color: C.text_primary, bold: true, valign: 'bottom', margin: 0,
  });
  if (tagline) {
    slide.addText(tagline, {
      x: 2.75, y: 1.05, w: SW - 3.3, h: 0.4, fontSize: 15, fontFace: theme.fonts.body,
      color: C.accent, bold: true, valign: 'top', margin: 0,
    });
  }
  const hasImage = opts.image && existsSync(opts.image);
  if (hasImage) {
    _addImageFit(slide, opts.image, { x: layout.M, y: 2.2, w: 3.6, h: 3.4 });
  }
  const x = hasImage ? 5.0 : 2.75;
  const w = layout.RIGHT_EDGE - x;
  const items = (features || []).slice(0, 4);
  const top = 1.85;
  const rowH = Math.min(1.55, (layout.FOOTER_Y - top) / Math.max(items.length, 1));
  items.forEach((f, i) => {
    const y = top + i * rowH;
    slide.addText(f.heading, {
      x, y, w, h: 0.4, fontSize: 18, fontFace: theme.fonts.heading,
      color: C.text_primary, bold: true, margin: 0,
    });
    slide.addShape(pptx.ShapeType.rect, {
      x, y: y + 0.42, w: Math.min(w, 3.6), h: 0.03, fill: { color: C.accent },
    });
    const lines = (f.lines || []).slice(0, 3);
    if (lines.length) {
      slide.addText(lines.map((t, j) => ({ text: t, options: { breakLine: j < lines.length - 1 } })), {
        x, y: y + 0.5, w, h: rowH - 0.6, fontSize: 14, fontFace: theme.fonts.body,
        color: C.text_body, valign: 'top', margin: 0, paraSpaceAfter: 2,
      });
    }
  });
  return _finishPatternSlide(deck, slide, slideNum, notes, { suppressLogo: true });
}


/**
 * Icon feature grid: 3-6 features, each an icon over a short bold label and a
 * one-line description. Icons sit on the slide with no circle or card behind
 * them (AMD brand rule) in the title colour; highlighted items use the accent.
 * Layout: up to 4 in one row, 5 as 3 + 2 (centred), 6 as 3 x 2.
 * @param {Array<{icon?: string, label: string, desc?: string, highlight?: boolean}>} items
 *   icon - a brand icon id (see loadIcons) or an image data string ("image/svg+xml;base64,...")
 * @param {{ takeaway?: string }} [opts]
 */
export function addIconFeatureGrid(deck, title, items, slideNum, notes, opts = {}) {
  const { theme, layout } = deck;
  const C = theme.colors;
  const slide = _patternSlide(deck, title);
  const top = _addTakeaway(deck, slide, opts.takeaway);
  const list = (items || []).slice(0, 6);
  const n = list.length;
  if (!n) return _finishPatternSlide(deck, slide, slideNum, notes);

  const rows = n <= 4 ? [n] : [3, n - 3];
  const cols = rows[0];
  const twoRows = rows.length > 1;
  const gutter = 0.45;
  const colW = (layout.CONTENT_W - (cols - 1) * gutter) / cols;
  const iconSize = twoRows ? 0.6 : n <= 3 ? 0.9 : 0.8;
  const labelSize = twoRows ? 18 : n <= 3 ? 22 : 20;
  const descSize = twoRows ? 13 : n <= 3 ? 16 : 14;
  // Room for a two-line label when the longest one won't fit on one line
  // (Arial bold averages ~0.55 em per character)
  const longest = Math.max(...list.map(it => (it.label || '').length));
  const labelLines = longest * labelSize * 0.55 / 72 > colW ? 2 : 1;
  const labelH = labelLines * labelSize * 1.2 / 72 + 0.12;
  const descH = twoRows ? 0.85 : 1.3;
  const blockH = iconSize + 0.2 + labelH + descH;
  const rowGap = 0.35;
  const gridH = rows.length * blockH + (rows.length - 1) * rowGap;
  // Sit slightly above centre of the space between the title and the footer
  const y0 = top + Math.max(0.1, (layout.FOOTER_Y - top - gridH) * 0.45);

  const iconColor = (item) => (item.highlight ? C.accent : (C.heading_color || C.text_primary));
  const iconData = (item) => {
    const icon = item.icon || '';
    if (!icon) return null;
    if (icon.startsWith('image/') || icon.startsWith('data:')) return icon;
    return loadIcons([icon], iconColor(item))[icon] || null;
  };

  let i = 0;
  rows.forEach((count, r) => {
    const rowW = count * colW + (count - 1) * gutter;
    const x0 = layout.M + (layout.CONTENT_W - rowW) / 2;
    const y = y0 + r * (blockH + rowGap);
    for (let c = 0; c < count; c++, i++) {
      const item = list[i];
      const x = x0 + c * (colW + gutter);
      const data = iconData(item);
      if (data) slide.addImage({ data, x, y, w: iconSize, h: iconSize });
      slide.addText(item.label || '', {
        x, y: y + iconSize + 0.2, w: colW, h: labelH, margin: 0, valign: 'top',
        fontSize: labelSize, fontFace: theme.fonts.heading, bold: true,
        color: item.highlight ? C.accent : (C.heading_color || C.text_primary),
      });
      if (item.desc) {
        slide.addText(item.desc, {
          x, y: y + iconSize + 0.2 + labelH, w: colW, h: descH, margin: 0, valign: 'top',
          fontSize: descSize, fontFace: theme.fonts.body, color: C.text_body,
        });
      }
    }
  });
  return _finishPatternSlide(deck, slide, slideNum, notes);
}


/** Icon id or image data string → addImage data (null when unknown). */
function _iconData(icon, color) {
  if (!icon) return null;
  if (icon.startsWith('image/') || icon.startsWith('data:')) return icon;
  return loadIcons([icon], color)[icon] || null;
}

/**
 * Small source line at the bottom left, above the footer, plus an optional
 * endnote pointer at the bottom right of the same row.
 */
function _addSourceLine(deck, slide, source, endnote) {
  const { theme, layout } = deck;
  const hasSource = Array.isArray(source) ? source.length > 0 : !!source;
  if (hasSource) {
    slide.addText(source, {
      x: layout.M, y: layout.FOOTER_Y - 0.35, w: layout.CONTENT_W - (endnote ? 2.6 : 1.0), h: 0.35,
      fontSize: 10, fontFace: theme.fonts.body, color: theme.colors.text_secondary,
      valign: 'bottom', margin: 0,
    });
  }
  if (endnote) addEndnoteRef(deck, slide, endnote);
}

/**
 * "See endnote XX-nn" pointer at the bottom right of a slide, above the
 * footer, for performance claims backed by an endnote. Works on any slide.
 * @param {string|string[]} ref - endnote id(s), or full text starting with "See"
 */
export function addEndnoteRef(deck, slide, ref) {
  const { theme, layout } = deck;
  const ids = (Array.isArray(ref) ? ref : [ref]).map(r => String(r || '').trim()).filter(Boolean);
  if (!ids.length) return slide;
  const text = /^see\b/i.test(ids[0]) ? ids.join(', ')
    : `See endnote${ids.length > 1 ? 's' : ''} ${ids.join(', ')}`;
  slide.addText(text, {
    x: layout.M + layout.CONTENT_W - 2.4, y: layout.FOOTER_Y - 0.35, w: 2.4, h: 0.35,
    fontSize: 10, fontFace: theme.fonts.body, color: theme.colors.text_secondary,
    align: 'right', valign: 'bottom', margin: 0,
  });
  return slide;
}


/**
 * KPI tiles: 2-4 headline numbers, each with a short label and an optional
 * "vs. what" context line and icon. Flat tiles with a thin accent bar on top;
 * only highlighted values use the accent colour (highlight one, not all).
 * @param {Array<{value: string, label: string, context?: string, icon?: string, highlight?: boolean}>} tiles
 *   icon - brand icon id (see loadIcons) or an image data string
 * @param {{ takeaway?: string, source?: string, endnote?: string|string[] }} [opts]
 */
export function addKpiTiles(deck, title, tiles, slideNum, notes, opts = {}) {
  const { pptx, theme, layout } = deck;
  const C = theme.colors;
  const ink = C.heading_color || C.text_primary;
  const slide = _patternSlide(deck, title);
  const top = _addTakeaway(deck, slide, opts.takeaway);
  const list = (tiles || []).slice(0, 4);
  const n = list.length;
  if (!n) return _finishPatternSlide(deck, slide, slideNum, notes);

  const gap = 0.3;
  const tileW = (layout.CONTENT_W - (n - 1) * gap) / n;
  const pad = 0.3;
  const innerW = tileW - 2 * pad;
  const hasIcon = list.some(t => t.icon);
  const iconSize = 0.5;
  // One size for every value so the row reads evenly
  const valueSize = Math.min(...list.map(t => _fitSize(t.value || '', innerW, 48, 28)));
  const valueH = valueSize * 1.25 / 72;
  const labelSize = n <= 3 ? 18 : 16;
  // Size the tiles to the longest label / context (~0.5 em per character)
  const lines = (text, size) => Math.ceil(String(text || '').length * size * 0.5 / 72 / innerW) || 0;
  const labelH = Math.max(1, ...list.map(t => lines(t.label, labelSize))) * labelSize * 1.2 / 72 + 0.05;
  const ctxLines = Math.max(0, ...list.map(t => lines(t.context, 12)));
  const ctxH = ctxLines ? ctxLines * 12 * 1.2 / 72 + 0.05 : 0;
  const tileH = 0.3 + (hasIcon ? iconSize + 0.2 : 0) + valueH + 0.05 + labelH + (ctxH ? 0.15 + ctxH : 0) + 0.3;
  const bottom = layout.FOOTER_Y - (opts.source || opts.endnote ? 0.45 : 0.1);
  const y = top + Math.max(0.15, (bottom - top - tileH) * 0.4);

  list.forEach((t, i) => {
    const x = layout.M + i * (tileW + gap);
    slide.addShape(pptx.ShapeType.rect, {
      x, y, w: tileW, h: tileH, fill: { color: C.surface }, line: { color: C.surface, width: 0 },
    });
    slide.addShape(pptx.ShapeType.rect, {
      x, y, w: tileW, h: 0.06, fill: { color: C.accent }, line: { color: C.accent, width: 0 },
    });
    let ty = y + 0.3;
    const data = _iconData(t.icon, t.highlight ? C.accent : ink);
    if (hasIcon) {
      if (data) slide.addImage({ data, x: x + pad, y: ty, w: iconSize, h: iconSize });
      ty += iconSize + 0.2;
    }
    slide.addText(t.value || '', {
      x: x + pad, y: ty, w: innerW, h: valueH, margin: 0, valign: 'bottom', fit: 'none',
      fontSize: valueSize, fontFace: theme.fonts.heading, bold: true,
      color: t.highlight ? C.accent : ink,
    });
    ty += valueH + 0.05;
    slide.addText(t.label || '', {
      x: x + pad, y: ty, w: innerW, h: labelH, margin: 0, valign: 'top',
      fontSize: labelSize, fontFace: theme.fonts.body, color: ink,
    });
    if (t.context) {
      slide.addText(t.context, {
        x: x + pad, y: ty + labelH + 0.15, w: innerW, h: ctxH, margin: 0, valign: 'top',
        fontSize: 12, fontFace: theme.fonts.body, color: C.text_secondary,
      });
    }
  });
  _addSourceLine(deck, slide, opts.source, opts.endnote);
  return _finishPatternSlide(deck, slide, slideNum, notes);
}


/**
 * Hero number: one statistic, very large, left-aligned and vertically
 * centred, with a label and an optional baseline/context line. Use for the
 * one or two numbers a deck hinges on.
 * @param {{ title?: string, context?: string, source?: string, endnote?: string|string[] }} [opts]
 */
export function addHeroNumber(deck, value, label, slideNum, notes, opts = {}) {
  const { theme, layout } = deck;
  const C = theme.colors;
  const ink = C.heading_color || C.text_primary;
  const slide = _patternSlide(deck, opts.title || null);
  const valueSize = _fitSize(value || '', layout.CONTENT_W, 110, 60);
  const valueH = valueSize * 1.15 / 72;
  const blockH = valueH + 0.2 + 0.9 + (opts.context ? 0.6 : 0);
  const top = opts.title ? layout.CONTENT_Y : 0.5;
  const y = top + Math.max(0, (layout.FOOTER_Y - top - blockH) / 2);
  slide.addText(value || '', {
    x: layout.M, y, w: layout.CONTENT_W, h: valueH, margin: 0, valign: 'bottom', fit: 'none',
    fontSize: valueSize, fontFace: theme.fonts.heading, bold: true, color: C.accent,
  });
  slide.addText(label || '', {
    x: layout.M, y: y + valueH + 0.2, w: layout.CONTENT_W * 0.75, h: 0.9, margin: 0, valign: 'top',
    fontSize: 24, fontFace: theme.fonts.body, color: ink,
  });
  if (opts.context) {
    slide.addText(opts.context, {
      x: layout.M, y: y + valueH + 1.1, w: layout.CONTENT_W * 0.75, h: 0.5, margin: 0, valign: 'top',
      fontSize: 16, fontFace: theme.fonts.body, color: C.text_secondary,
    });
  }
  _addSourceLine(deck, slide, opts.source, opts.endnote);
  return _finishPatternSlide(deck, slide, slideNum, notes);
}


/**
 * Metric comparison table (AMD vs. competitor): grey bold metric names, a
 * large accent value column (e.g. "1.3x") and a short "why it matters"
 * column. Horizontal rules only. Optional product image on the left.
 * @param {Array<{label: string, value: string, why?: string}>} rows - up to 6
 * @param {{ header?: string[], image?: string, takeaway?: string, source?: string, endnote?: string|string[] }} [opts]
 *   header - three column headings, e.g. ["Metric", "MI355X vs. B200", "Why it matters"]
 */
export function addMetricTable(deck, title, rows, slideNum, notes, opts = {}) {
  const { theme, layout } = deck;
  const C = theme.colors;
  const ink = C.heading_color || C.text_primary;
  const slide = _patternSlide(deck, title);
  const top = _addTakeaway(deck, slide, opts.takeaway);
  const list = (rows || []).slice(0, 6);
  const n = list.length;
  if (!n) return _finishPatternSlide(deck, slide, slideNum, notes);

  let x = layout.M;
  let w = layout.CONTENT_W;
  const bottom = layout.FOOTER_Y - (opts.source || opts.endnote ? 0.45 : 0.1);
  if (opts.image && existsSync(opts.image)) {
    const imgW = 3.6;
    _addImageFit(slide, opts.image, { x, y: top + 0.2, w: imgW, h: bottom - top - 0.4 });
    x += imgW + 0.4;
    w -= imgW + 0.4;
  }
  const hasWhy = list.some(r => r.why);
  const colW = hasWhy ? [w * 0.38, w * 0.24, w * 0.38] : [w * 0.6, w * 0.4];
  const valueSize = n <= 4 ? 36 : 30;
  const labelSize = n <= 4 ? 20 : 18;
  const rowH = n <= 4 ? 0.8 : 0.66;
  const rule = { type: 'solid', pt: 2.25, color: C.surface };
  const none = { type: 'none' };
  const border = [none, none, rule, none];   // top, right, bottom, left
  const tableRows = [];
  const header = (opts.header || []).slice(0, colW.length);
  if (header.length) {
    tableRows.push(colW.map((_, c) => ({
      text: header[c] || '',
      options: {
        bold: true, fontSize: 16, color: ink, fill: { color: C.surface },
        align: c === 0 ? 'left' : 'center', valign: 'middle', border: [none, none, none, none],
      },
    })));
  }
  list.forEach((r) => {
    const cells = [
      { text: r.label || '', options: { bold: true, fontSize: labelSize, color: C.text_secondary, align: 'left' } },
      { text: r.value || '', options: { bold: true, fontSize: valueSize, color: C.accent, align: 'center' } },
    ];
    if (hasWhy) {
      cells.push({ text: r.why || '', options: { bold: true, fontSize: n <= 4 ? 16 : 14, color: ink, align: 'center' } });
    }
    cells.forEach(cell => Object.assign(cell.options, { valign: 'middle', border }));
    tableRows.push(cells);
  });
  const tableH = (header.length ? 0.5 : 0) + n * rowH;
  slide.addTable(tableRows, {
    x, y: top + Math.max(0.15, (bottom - top - tableH) * 0.4), w, colW,
    rowH: header.length ? [0.5, ...Array(n).fill(rowH)] : rowH,
    fontFace: theme.fonts.body, margin: [0.05, 0.12, 0.05, 0.12], autoPage: false,
  });
  _addSourceLine(deck, slide, opts.source, opts.endnote);
  return _finishPatternSlide(deck, slide, slideNum, notes);
}


/** Blend hex colour `a` into `b` (t = share of a). */
function _mix(a, b, t) {
  const ch = (hex, i) => parseInt(hex.slice(i, i + 2), 16);
  return [0, 2, 4].map(i => Math.round(ch(a, i) * t + ch(b, i) * (1 - t))
    .toString(16).padStart(2, '0')).join('').toUpperCase();
}

function _isDark(hex) {
  const [r, g, b] = [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16));
  return 0.299 * r + 0.587 * g + 0.114 * b < 128;
}

const _AMD_PRODUCT = /\b(AMD|Instinct|MI\d{3}[A-Z]*|EPYC|Ryzen|Radeon|ROCm|Pensando|Versal)\b/i;

/**
 * Spec table: rows are specs, columns are 1-3 products. The AMD column (found
 * from its header, or opts.highlight) gets an accent header, a tinted fill and
 * bold values; other products stay muted. With one product it is a borderless
 * two-column spec sheet (accent labels, plain values).
 * @param {string[]} header - ["Spec", "MI355X", "B200", ...]
 * @param {string[][]} rows - [["HBM", "288 GB", "192 GB"], ...] (up to 12)
 * @param {{ highlight?: number|false, takeaway?: string, source?: string, endnote?: string|string[] }} [opts]
 *   highlight - column index to highlight (default: first AMD-looking header), false for none
 */
export function addSpecTable(deck, title, header, rows, slideNum, notes, opts = {}) {
  const { theme, layout } = deck;
  const C = theme.colors;
  const ink = C.heading_color || C.text_primary;
  const slide = _patternSlide(deck, title);
  const top = _addTakeaway(deck, slide, opts.takeaway);
  const head = header || [];
  const body = (rows || []).slice(0, 12);
  const cols = Math.min(4, Math.max(head.length, ...body.map(r => r.length), 2));
  const n = body.length;
  if (!n) return _finishPatternSlide(deck, slide, slideNum, notes);

  const fontSize = n <= 6 ? 16 : n <= 9 ? 14 : 12;
  const rowH = fontSize / 72 * 2.4;
  const none = { type: 'none' };
  const hairline = { type: 'solid', pt: 0.75, color: _mix(C.text_primary, C.background, 0.2) };
  const bottom = layout.FOOTER_Y - (opts.source || opts.endnote ? 0.45 : 0.1);
  const tableRows = [];
  let x = layout.M;
  let w = layout.CONTENT_W;
  let colW;

  if (cols === 2) {
    // One product: borderless spec sheet
    w = Math.min(w, 9.0);
    colW = [w * 0.32, w * 0.68];
    if (head.some(h => h)) {
      tableRows.push(head.slice(0, 2).map((h) => ({
        text: h || '', options: { bold: true, color: ink, border: [none, none, hairline, none] },
      })));
    }
    body.forEach((r) => tableRows.push([
      { text: r[0] || '', options: { bold: true, color: C.accent, border: [none, none, none, none] } },
      { text: r[1] || '', options: { color: ink, border: [none, none, none, none] } },
    ]));
  } else {
    let hi = opts.highlight;
    if (hi === undefined) {
      hi = head.findIndex((h, c) => c > 0 && _AMD_PRODUCT.test(h || ''));
    }
    if (hi === false || hi === null || hi < 1 || hi >= cols) hi = -1;
    // Accent tint: ~0A3A42 on black, a pale cyan on white
    const tint = _mix(C.accent, C.background, _isDark(C.background) ? 0.25 : 0.15);
    const labelW = w * (cols === 3 ? 0.36 : 0.31);
    colW = [labelW, ...Array(cols - 1).fill((w - labelW) / (cols - 1))];
    const border = [none, none, hairline, none];
    tableRows.push(Array.from({ length: cols }, (_, c) => ({
      text: head[c] || '',
      options: c === hi
        ? { bold: true, color: '000000', fill: { color: C.accent }, align: 'center', border }
        : { bold: true, color: ink, align: c ? 'center' : 'left', border },
    })));
    body.forEach((r) => tableRows.push(Array.from({ length: cols }, (_, c) => ({
      text: r[c] || '',
      options: c === 0
        ? { bold: true, color: ink, border }
        : c === hi
          ? { bold: true, color: ink, fill: { color: tint }, align: 'center', border }
          : { color: C.text_secondary, align: 'center', border },
    }))));
  }
  const tableH = tableRows.length * rowH;
  slide.addTable(tableRows, {
    x, y: top + Math.max(0.15, (bottom - top - tableH) * 0.4), w, colW, rowH,
    fontSize, fontFace: theme.fonts.body, valign: 'middle',
    margin: [0.04, 0.12, 0.04, 0.12], autoPage: false,
  });
  _addSourceLine(deck, slide, opts.source, opts.endnote);
  return _finishPatternSlide(deck, slide, slideNum, notes);
}


/**
 * Competitive column chart: a native (editable) clustered column chart with
 * the AMD series in the accent colour and competitors in greys. No gridlines,
 * value axis or chart legend; values sit on the bars, "1.3×" ratio labels sit
 * above the AMD bars, and chip legends sit under the plot. Bars start at zero.
 * @param {string[]} categories - x-axis groups (models, workloads), up to 8
 * @param {Array<{name: string, values: number[], amd?: boolean}>} series - 1-4 series
 *   The AMD series is the one with amd: true, else the first AMD-looking name,
 *   else the last series.
 * @param {{ takeaway?: string, ratios?: boolean|string[], lowerIsBetter?: boolean,
 *   metric?: string, valueFormat?: string, date?: string, source?: string, endnote?: string|string[] }} [opts]
 *   ratios - false to hide, or one label per category (default: AMD / best competitor)
 *   metric - unit note shown beside the legend, e.g. "Tokens/s (higher is better)"
 *   valueFormat - Excel number format for the bar values (default "#,##0", or
 *     "#,##0.0" / "#,##0.00" when the values have decimals, so 1.3 is not shown as 1)
 */
export function addCompetitiveChart(deck, title, categories, series, slideNum, notes, opts = {}) {
  const { pptx, theme, layout } = deck;
  const C = theme.colors;
  const ink = C.heading_color || C.text_primary;
  const slide = _patternSlide(deck, title);
  const top = _addTakeaway(deck, slide, opts.takeaway);
  const cats = (categories || []).slice(0, 8);
  const sers = (series || []).slice(0, 4);
  if (!cats.length || !sers.length) return _finishPatternSlide(deck, slide, slideNum, notes);

  let amd = sers.findIndex(s => s.amd);
  if (amd < 0) amd = sers.findIndex(s => _AMD_PRODUCT.test(s.name || ''));
  if (amd < 0) amd = sers.length - 1;
  // Competitor greys keep >= 3:1 contrast on black and on white
  const greys = [0.62, 0.45, 0.78].map(t => _mix(C.text_primary, C.background, t));
  let g = 0;
  const colors = sers.map((s, i) => (i === amd ? C.accent : greys[g++ % greys.length]));
  const vals = sers.map(s => cats.map((_, c) => Math.max(0, Number(s.values?.[c]) || 0)));
  const maxVal = Math.max(...vals.flat()) || 1;
  // Decimal places the data needs (0-2), unless a format was given
  const places = Math.min(2, Math.max(0, ...vals.flat().map(v => {
    const frac = String(+v.toFixed(2)).split('.')[1];
    return frac ? frac.length : 0;
  })));
  const valueFormat = opts.valueFormat || (places ? `#,##0.${'0'.repeat(places)}` : '#,##0');

  // Frame: chart, then a chip legend row, then the Date / Data Source block
  const hasSource = !!(opts.date || opts.source || opts.endnote);
  const legendH = sers.length > 1 || opts.metric ? 0.45 : 0;
  const bottom = layout.FOOTER_Y - (hasSource ? 0.45 : 0.1);
  const legendY = bottom - legendH;
  const cx = layout.M;
  const cy = top + 0.1;
  const cw = layout.CONTENT_W;
  const ch = legendY - 0.15 - cy;
  // Inner plot area pinned (fractions of the frame) so the bars can be located
  const headroom = 0.65;
  const catRoom = 0.45;
  const plot = { x: 0.01, y: headroom / ch, w: 0.98, h: (ch - headroom - catRoom) / ch };
  const gapPct = sers.length <= 2 ? 60 : 40;
  const valueFont = sers.length * cats.length > 12 ? 11 : 14;

  slide.addChart(pptx.charts.BAR, sers.map((s, i) => ({ name: s.name, labels: cats, values: vals[i] })), {
    x: cx, y: cy, w: cw, h: ch,
    barDir: 'col', barGrouping: 'clustered', barGapWidthPct: gapPct,
    chartColors: colors.slice(),
    layout: { ...plot },
    showLegend: false, showTitle: false,
    valAxisHidden: true, valAxisMinVal: 0, valAxisMaxVal: maxVal,
    valGridLine: { style: 'none' }, catGridLine: { style: 'none' },
    catAxisLabelColor: C.text_secondary, catAxisLabelFontSize: 14,
    catAxisLabelFontFace: theme.fonts.body,
    catAxisLineShow: true, catAxisLineColor: _mix(C.text_primary, C.background, 0.3),
    showValue: true, dataLabelPosition: 'outEnd', dataLabelColor: ink,
    dataLabelFontSize: valueFont, dataLabelFontFace: theme.fonts.body,
    dataLabelFormatCode: valueFormat,
  });

  // Ratio labels above the AMD bars
  if (opts.ratios !== false && sers.length > 1) {
    const plotX = cx + plot.x * cw;
    const plotY = cy + plot.y * ch;
    const plotW = plot.w * cw;
    const plotH = plot.h * ch;
    const catW = plotW / cats.length;
    const barW = catW / (sers.length + gapPct / 100);
    cats.forEach((_, c) => {
      let label = Array.isArray(opts.ratios) ? opts.ratios[c] : null;
      if (!Array.isArray(opts.ratios)) {
        const rivals = vals.filter((_, i) => i !== amd).map(v => v[c]).filter(v => v > 0);
        const a = vals[amd][c];
        if (!rivals.length || !a) return;
        const best = opts.lowerIsBetter ? Math.min(...rivals) : Math.max(...rivals);
        const r = opts.lowerIsBetter ? best / a : a / best;
        label = `${r >= 10 ? Math.round(r) : r.toFixed(1)}×`;
      }
      if (!label) return;
      const barX = plotX + c * catW + (gapPct / 100) * barW / 2 + amd * barW;
      const barTop = plotY + plotH * (1 - vals[amd][c] / maxVal);
      const w = Math.max(barW, 0.9);
      slide.addText(label, {
        x: barX + barW / 2 - w / 2, y: barTop - valueFont / 72 * 1.5 - 0.34, w, h: 0.34,
        fontSize: 16, bold: true, fontFace: theme.fonts.body, color: C.accent,
        align: 'center', valign: 'bottom', margin: 0,
      });
    });
  }

  // Chip legend: dark tile with a colour stripe on the left
  if (legendH) {
    let x = cx;
    if (sers.length > 1) {
      sers.forEach((s, i) => {
        const w = Math.min(3.0, Math.max(1.6, (s.name || '').length * 12 * 0.5 / 72 + 0.5));
        slide.addShape(pptx.shapes.RECTANGLE, {
          x, y: legendY, w, h: 0.4, fill: { color: C.surface }, line: { type: 'none' },
        });
        slide.addShape(pptx.shapes.RECTANGLE, {
          x, y: legendY, w: 0.08, h: 0.4, fill: { color: colors[i] }, line: { type: 'none' },
        });
        slide.addText(s.name || '', {
          x: x + 0.18, y: legendY, w: w - 0.24, h: 0.4,
          fontSize: 12, fontFace: theme.fonts.body, color: ink, valign: 'middle', margin: 0,
        });
        x += w + 0.2;
      });
    }
    if (opts.metric) {
      slide.addText(opts.metric, {
        x, y: legendY, w: cx + cw - x, h: 0.4,
        fontSize: 12, fontFace: theme.fonts.body, color: C.text_secondary,
        align: 'right', valign: 'middle', margin: 0,
      });
    }
  }

  const runs = [];
  if (opts.date) runs.push({ text: 'Date: ', options: { bold: true } }, { text: opts.date });
  if (opts.date && opts.source) runs.push({ text: '    ' });
  if (opts.source) runs.push({ text: 'Data Source: ', options: { bold: true } }, { text: opts.source });
  _addSourceLine(deck, slide, runs, opts.endnote);
  return _finishPatternSlide(deck, slide, slideNum, notes);
}


/**
 * Check / partial / none comparison matrix: features down the side, 1-4
 * products across. The AMD column (first AMD-looking header, or
 * opts.highlight) gets an accent header and a tinted body, as in
 * addSpecTable. Marks stay quiet: ✓ is accent in the highlighted column and
 * ink elsewhere, "Partial" and ✗ (none) are muted grey. Any other string is
 * shown as-is. Optional group rows split the features into sections.
 * @param {string[]} header - ["Capability", "AMD Instinct MI355X", "H200", ...]
 * @param {Array<{label: string, values: string[], group?: string}>} rows - up to 14
 *   values - per product: "check"/"yes"/"✓", "partial"/"◐", "none"/"no"/"✗", or text
 *   group - section heading, drawn when it changes from the previous row
 * @param {{ highlight?: number|false, takeaway?: string, source?: string, endnote?: string|string[] }} [opts]
 *   highlight - column index to highlight (default: first AMD-looking header), false for none
 */
export function addCheckMatrix(deck, title, header, rows, slideNum, notes, opts = {}) {
  const { theme, layout } = deck;
  const C = theme.colors;
  const ink = C.heading_color || C.text_primary;
  const slide = _patternSlide(deck, title);
  const top = _addTakeaway(deck, slide, opts.takeaway);
  const head = header || [];
  const body = (rows || []).slice(0, 14);
  const prods = Math.min(4, Math.max(1, head.length - 1, ...body.map(r => (r.values || []).length)));
  const cols = prods + 1;
  if (!body.length) return _finishPatternSlide(deck, slide, slideNum, notes);

  let hi = opts.highlight;
  if (hi === undefined) {
    hi = head.findIndex((h, c) => c > 0 && _AMD_PRODUCT.test(h || ''));
  }
  if (hi === false || hi === null || hi < 1 || hi >= cols) hi = -1;
  const dark = _isDark(C.background);
  const tint = _mix(C.accent, C.background, dark ? 0.25 : 0.15);
  const none = { type: 'none' };
  const border = [none, none, { type: 'solid', pt: 0.75, color: _mix(C.text_primary, C.background, 0.2) }, none];

  const mark = (raw, c) => {
    const v = String(raw ?? '').trim();
    const k = v.toLowerCase();
    if (['check', 'yes', '✓', '✔'].includes(k)) {
      return { text: '✓', color: c === hi || hi < 0 ? C.accent : ink, bold: true, sym: true };
    }
    if (['partial', 'half', '◐', '~'].includes(k)) return { text: 'Partial', color: C.text_secondary };
    if (['none', 'no', 'x', '✗', '✘', '-', '—'].includes(k)) return { text: '✗', color: C.text_secondary, sym: true };
    return { text: v, color: c === hi ? ink : C.text_secondary, bold: c === hi };
  };

  // Rows to draw: header, then features with a group row wherever the group changes
  const lines = [];
  let group = null;
  body.forEach((r) => {
    if (r.group && r.group !== group) lines.push({ heading: r.group });
    group = r.group || group;
    lines.push(r);
  });
  const n = lines.length + 1;
  const bottom = layout.FOOTER_Y - (opts.source || opts.endnote ? 0.45 : 0.1);
  const avail = bottom - top - 0.15;
  // Largest size whose rows fit: row height = 2.4 x font size
  const fontSize = [16, 14, 12, 11].find(s => n * s / 72 * 2.4 <= avail) || 11;
  const rowH = Math.min(fontSize / 72 * 2.4, avail / n);
  const symSize = fontSize + 4;

  const tableRows = [Array.from({ length: cols }, (_, c) => ({
    text: head[c] || '',
    options: c === hi
      ? { bold: true, color: '000000', fill: { color: C.accent }, align: 'center', border }
      : { bold: true, color: ink, align: c ? 'center' : 'left', border },
  }))];
  lines.forEach((r) => {
    if (r.heading) {
      tableRows.push([{
        text: r.heading,
        options: { colspan: cols, bold: true, color: C.accent, fontSize: fontSize - 2, border },
      }]);
      return;
    }
    tableRows.push(Array.from({ length: cols }, (_, c) => {
      if (c === 0) return { text: r.label || '', options: { bold: true, color: ink, border } };
      const m = mark((r.values || [])[c - 1], c);
      const options = { color: m.color, bold: !!m.bold, align: 'center', border };
      if (m.sym) options.fontSize = symSize;
      if (c === hi) options.fill = { color: tint };
      return { text: m.text, options };
    }));
  });

  const w = layout.CONTENT_W;
  const labelW = w * [0.55, 0.42, 0.36, 0.31][prods - 1];
  const colW = [labelW, ...Array(prods).fill((w - labelW) / prods)];
  slide.addTable(tableRows, {
    x: layout.M, y: top + Math.max(0.15, (bottom - top - n * rowH) * 0.4), w, colW, rowH,
    fontSize, fontFace: theme.fonts.body, valign: 'middle',
    margin: [0.02, 0.12, 0.02, 0.12], autoPage: false,
  });
  _addSourceLine(deck, slide, opts.source, opts.endnote);
  return _finishPatternSlide(deck, slide, slideNum, notes);
}


/** Rough line count for *text* at *size* pt in a box *w* inches wide. */
function _lines(text, w, size) {
  return Math.max(1, Math.ceil(String(text || '').length * size * 0.5 / 72 / w));
}

/**
 * Timeline / roadmap: 3-7 milestones on a horizontal rule. Milestones before
 * the current one are solid dots, the current one is an accent dot with a
 * ring, later ones are outlined. Up to 5 milestones sit in one row under the
 * line; 6-7 alternate above and below it.
 * @param {Array<{date: string, label: string, desc?: string, current?: boolean}>} milestones
 * @param {{ takeaway?: string, source?: string, endnote?: string|string[], caveat?: boolean|string }} [opts]
 *   caveat - true for "Roadmap subject to change.", or custom text (forward-looking items)
 */
export function addTimeline(deck, title, milestones, slideNum, notes, opts = {}) {
  const { pptx, theme, layout } = deck;
  const C = theme.colors;
  const ink = C.heading_color || C.text_primary;
  const slide = _patternSlide(deck, title);
  const top = _addTakeaway(deck, slide, opts.takeaway);
  const items = (milestones || []).slice(0, 7);
  const n = items.length;
  const caveat = opts.caveat === true ? 'Roadmap subject to change.' : opts.caveat || '';
  const note = [opts.source, caveat].filter(Boolean).join('  ');
  if (!n) return _finishPatternSlide(deck, slide, slideNum, notes);

  const bottom = layout.FOOTER_Y - (note || opts.endnote ? 0.45 : 0.1);
  const alternate = n > 5;
  const pitch = layout.CONTENT_W / n;
  const blockW = alternate ? Math.min(2 * pitch - 0.2, 2.6) : pitch - 0.2;
  const dateSize = n <= 4 ? 22 : 18;
  const labelSize = n <= 4 ? 20 : n <= 5 ? 18 : 14;
  const descSize = n <= 4 ? 16 : n <= 5 ? 14 : 12;
  // One row: centre date + line + label + 2-line description in the space
  const rowH = dateSize / 72 * 1.4 + 0.65 + labelSize / 72 * 2.4 + descSize / 72 * 2.5;
  const lineY = alternate
    ? (top + bottom) / 2
    : top + Math.max(0.2, (bottom - top - rowH) * 0.45) + dateSize / 72 * 1.4 + 0.3;
  const cur = items.findIndex(m => m.current);

  slide.addShape(pptx.shapes.LINE, {
    x: layout.M, y: lineY, w: layout.CONTENT_W, h: 0,
    line: { color: _mix(C.text_primary, C.background, 0.35), width: 2 },
  });
  items.forEach((m, i) => {
    const cx = layout.M + pitch * (i + 0.5);
    const isCur = i === cur;
    const future = cur >= 0 && i > cur;
    const d = 0.22;
    if (isCur) {
      slide.addShape(pptx.shapes.OVAL, {
        x: cx - 0.2, y: lineY - 0.2, w: 0.4, h: 0.4,
        fill: { type: 'none' }, line: { color: C.accent, width: 1.5 },
      });
    }
    slide.addShape(pptx.shapes.OVAL, {
      x: cx - d / 2, y: lineY - d / 2, w: d, h: d,
      fill: { color: isCur ? C.accent : future ? C.background : ink },
      line: future ? { color: C.text_secondary, width: 1.5 } : { type: 'none' },
    });

    // Date next to the line; label + description on the far side of it
    const above = alternate && i % 2 === 1;
    const dateH = dateSize / 72 * 1.4;
    const labelH = Math.min(2, _lines(m.label, blockW, labelSize)) * labelSize / 72 * 1.2 + 0.05;
    const descH = m.desc ? Math.min(3, _lines(m.desc, blockW, descSize)) * descSize / 72 * 1.25 + 0.05 : 0;
    const x = cx - blockW / 2;
    const textOpts = { x, w: blockW, fontFace: theme.fonts.body, align: 'center', margin: 0 };
    let y;
    if (above) {
      slide.addText(m.date || '', { ...textOpts, y: lineY + 0.3, h: dateH, fontSize: dateSize, bold: true,
        color: isCur ? C.accent : ink, valign: 'top' });
      y = lineY - 0.35 - labelH - descH;
    } else {
      slide.addText(m.date || '', { ...textOpts, y: lineY - 0.3 - dateH, h: dateH, fontSize: dateSize, bold: true,
        color: isCur ? C.accent : ink, valign: 'bottom' });
      y = lineY + 0.35;
    }
    slide.addText(m.label || '', { ...textOpts, y, h: labelH, fontSize: labelSize, bold: true,
      color: future ? C.text_secondary : ink, valign: 'top' });
    if (m.desc) {
      slide.addText(m.desc, { ...textOpts, y: y + labelH, h: descH, fontSize: descSize,
        color: C.text_secondary, valign: 'top' });
    }
  });
  _addSourceLine(deck, slide, note, opts.endnote);
  return _finishPatternSlide(deck, slide, slideNum, notes);
}


/**
 * Stage flow: 3-4 stages left to right. Each stage has a header tile (accent
 * bar on top; accent text on dark themes, ink on light ones), accent arrows
 * between tiles, an optional screenshot, an accent sub-head and a few
 * bullets; an optional closing line sits at the bottom.
 * @param {Array<{title: string, image?: string, subhead?: string, bullets?: string[]}>} stages
 * @param {{ takeaway?: string, closing?: string, source?: string, endnote?: string|string[] }} [opts]
 */
export function addStageFlow(deck, title, stages, slideNum, notes, opts = {}) {
  const { pptx, theme, layout } = deck;
  const C = theme.colors;
  const ink = C.heading_color || C.text_primary;
  const slide = _patternSlide(deck, title);
  const top = _addTakeaway(deck, slide, opts.takeaway);
  const list = (stages || []).slice(0, 4);
  const k = list.length;
  if (!k) return _finishPatternSlide(deck, slide, slideNum, notes);

  const bottom = layout.FOOTER_Y - (opts.source || opts.endnote ? 0.45 : 0.1);
  const closingH = opts.closing ? 0.6 : 0;
  const gap = 0.64;                                   // arrow 0.4 + 0.12 either side
  const tileW = (layout.CONTENT_W - (k - 1) * gap) / k;
  const tileY = top + 0.15;
  const tileH = 0.8;
  const headSize = k <= 3 ? 18 : 16;
  const images = list.map(s => (s.image && existsSync(s.image) ? s.image : null));
  const imgH = images.some(Boolean) ? Math.min(tileW * 9 / 16, 1.8) : 0;
  const dark = _isDark(C.background);
  // Larger text when there are no screenshots to fill the space
  const bodySize = imgH ? (k <= 3 ? 14 : 13) : (k <= 3 ? 18 : 16);
  const subSize = imgH ? 16 : (k <= 3 ? 20 : 18);

  list.forEach((s, i) => {
    const x = layout.M + i * (tileW + gap);
    slide.addShape(pptx.shapes.RECTANGLE, {
      x, y: tileY, w: tileW, h: tileH, fill: { color: C.surface }, line: { type: 'none' },
    });
    slide.addShape(pptx.shapes.RECTANGLE, {
      x, y: tileY, w: tileW, h: 0.06, fill: { color: C.accent }, line: { type: 'none' },
    });
    // Accent text on dark tiles; ink on light tiles (cyan on light grey is too faint)
    slide.addText(s.title || '', {
      x, y: tileY, w: tileW, h: tileH, fontSize: headSize, bold: true, fontFace: theme.fonts.body,
      color: dark ? C.accent : ink, align: 'center', valign: 'middle', margin: [0, 0.12, 0, 0.12],
    });
    if (i < k - 1) {
      slide.addShape(pptx.shapes.RIGHT_ARROW, {
        x: x + tileW + 0.12, y: tileY + tileH / 2 - 0.1, w: 0.4, h: 0.2,
        fill: { color: C.accent }, line: { type: 'none' },
      });
    }
    let y = tileY + tileH + 0.2;
    if (imgH) {
      if (images[i]) {
        _addImageFit(slide, images[i], { x, y, w: tileW, h: imgH });
      }
      y += imgH + 0.2;
    }
    if (s.subhead) {
      const h = Math.min(2, _lines(s.subhead, tileW, subSize)) * subSize / 72 * 1.2 + 0.05;
      slide.addText(s.subhead, {
        x, y, w: tileW, h, fontSize: subSize, bold: true, underline: { style: 'sng' },
        fontFace: theme.fonts.body, color: C.accent, valign: 'top', margin: 0,
      });
      y += h + 0.08;
    }
    const pts = (s.bullets || []).slice(0, 5);
    if (pts.length) {
      slide.addText(pts.map(t => ({ text: t, options: { bullet: { indent: 14 }, breakLine: true } })), {
        x, y, w: tileW, h: Math.max(0.4, bottom - closingH - 0.1 - y), fontSize: bodySize,
        fontFace: theme.fonts.body, color: C.text_body || ink, valign: 'top', margin: 0,
        paraSpaceAfter: 4,
      });
    }
  });
  if (opts.closing) {
    slide.addText(opts.closing, {
      x: layout.M, y: bottom - closingH, w: layout.CONTENT_W, h: closingH,
      fontSize: _fitSize(opts.closing, layout.CONTENT_W, 28, 18), bold: true,
      fontFace: theme.fonts.body, color: C.accent, valign: 'middle', margin: 0,
    });
  }
  _addSourceLine(deck, slide, opts.source, opts.endnote);
  return _finishPatternSlide(deck, slide, slideNum, notes);
}

/**
 * Endnotes back-matter slide: the full text behind "See endnote" pointers,
 * in a muted panel. Each note leads with its id in bold. Text is sized to fill
 * the slide (16pt down to 8pt), flows into two columns when that keeps it
 * larger, and the panel shrinks to fit short lists.
 * @param {Array<string|{id: string, text: string}>} endnotes
 */
export function addEndnotesSlide(deck, title, endnotes, slideNum, notes) {
  const { pptx, theme, layout } = deck;
  const C = theme.colors;
  const ink = C.heading_color || C.text_primary;
  const slide = _patternSlide(deck, title || 'Endnotes');
  const items = (endnotes || [])
    .map(e => (typeof e === 'string' ? { id: '', text: e } : { id: e.id || '', text: e.text || '' }))
    .filter(e => e.id || e.text);
  if (!items.length) return _finishPatternSlide(deck, slide, slideNum, notes);

  const pad = 0.2;
  const y = layout.CONTENT_Y, maxH = layout.CONTENT_H - 0.1;
  const innerW = layout.CONTENT_W - 2 * pad, innerH = maxH - 2 * pad;
  const [MAX, MIN] = [16, 8];
  const plain = items.map(e => (e.id ? `${e.id}  ${e.text}` : e.text));
  const runs = (list, size) => list.flatMap((e, i) => {
    const last = i === list.length - 1;
    const body = { text: e.text, options: { color: C.text_secondary, breakLine: !last } };
    return e.id
      ? [{ text: `${e.id}  `, options: { bold: true, color: ink } }, body]
      : [body];
  });
  const style = (size) => ({
    fontSize: size, fontFace: theme.fonts.body, valign: 'top', margin: 0, paraSpaceAfter: 6,
  });

  const oneSize = _fitParagraphs(plain, innerW, innerH, MAX, MIN);
  const gap = 0.4, colW = (innerW - gap) / 2;
  const cut = items.length > 1 && oneSize < 11 ? _balancedHalves(plain)[0].length : 0;
  const halves = cut ? [items.slice(0, cut), items.slice(cut)] : null;
  const flat = (list) => list.map(e => `${e.id}  ${e.text}`);
  const twoSize = halves
    ? Math.min(...halves.map(half => _fitParagraphs(flat(half), colW, innerH, MAX, MIN)))
    : 0;
  const two = twoSize > oneSize;
  const textH = two
    ? Math.max(...halves.map(half => _paraHeight(flat(half), colW, twoSize)))
    : _paraHeight(plain, innerW, oneSize);
  const h = Math.min(maxH, textH + 2 * pad + 0.15);
  slide.addShape(pptx.shapes.RECTANGLE, {
    x: layout.M, y, w: layout.CONTENT_W, h, fill: { color: C.surface }, line: { type: 'none' },
  });

  if (two) {
    halves.forEach((half, c) => slide.addText(runs(half), {
      x: layout.M + pad + c * (colW + gap), y: y + pad, w: colW, h: h - 2 * pad, ...style(twoSize),
    }));
  } else {
    slide.addText(runs(items), {
      x: layout.M + pad, y: y + pad, w: innerW, h: h - 2 * pad, ...style(oneSize),
    });
  }
  return _finishPatternSlide(deck, slide, slideNum, notes);
}

// ═══════════════════════════════════════════════════════════════
// Deck Lifecycle
// ═══════════════════════════════════════════════════════════════

/** user-assets.json next to the running script, if the app wrote one. */
function _readUserAssets() {
  const file = process.argv[1] && resolve(dirname(process.argv[1]), 'user-assets.json');
  if (!file || !existsSync(file)) return { icons: {}, cobrand: null };
  const parsed = JSON.parse(readFileSync(file, 'utf8'));
  return { icons: parsed.icons || {}, cobrand: parsed.cobrand || null };
}

/**
 * Create a new deck with theme and layout computed.
 * @param {string} themePath - Path to themes/*.yaml
 * @param {{ useSlideMaster?: boolean, userAssets?: object }} [opts] - Options.
 *   userAssets defaults to user-assets.json next to the running script:
 *   { icons: { "my-…": path }, cobrand: { path, width, height } | null }
 * @returns {{ pptx, theme, layout, useSlideMaster, save(path) }}
 */
export function createDeck(themePath, opts = {}) {
  const pptxgen = require("pptxgenjs");
  const theme = loadTheme(themePath);
  if (opts.overrides) {
    deepMerge(theme, opts.overrides);
  }
  const layout = computeLayout(theme);
  const useSlideMaster = opts.useSlideMaster ?? false;
  userAssets = opts.userAssets || _readUserAssets();

  const pptx = new pptxgen();
  pptx.layout = theme.slide.layout;

  const deck = {
    pptx,
    theme,
    layout,
    useSlideMaster,
    async save(outputPath) {
      await pptx.writeFile({ fileName: outputPath });
      if (existsSync(outputPath)) {
        const stats = statSync(outputPath);
        console.log(`Deck saved: ${outputPath} (${(stats.size / 1024).toFixed(0)} KB)`);
      }
    },
  };

  if (useSlideMaster) {
    defineMasters(deck);
  }

  return deck;
}

export { masterNameFor } from './pptxgenjs-masters.mjs';
