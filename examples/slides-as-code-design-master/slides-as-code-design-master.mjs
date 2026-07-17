/**
 * slides-as-code-design-master.mjs
 *
 * Master-on variant of the slides-as-code-design example.
 * Demonstrates slide masters via createDeck({ useSlideMaster: true }).
 *
 * Usage:
 *   NODE_PATH="$(npm root -g)" node examples/slides-as-code-design-master/slides-as-code-design-master.mjs
 *
 * Output: examples/slides-as-code-design-master/slides-as-code-design-master.pptx
 */

import {
  createDeck, addTitleSlide, addBulletSlide, addImageSlide,
  addProcessFlow, addTwoColumn, addCardGrid, addStatCallout,
  addCodeSlide, addIconRowsSlide, addSectionDivider, addClosingSlide,
  SW, SH
} from '../../lib/pptxgenjs-helpers.mjs';

const deck = createDeck('themes/default.yaml', { useSlideMaster: true });
let sn = 1;

// ═══ Slide 1: Title ═══
addTitleSlide(deck, 'Slides as Code', 'Master-enabled pptxgenjs example', sn++);

// ═══ Slide 2: Section Divider ═══
addSectionDivider(deck, 1, 'Why Slides as Code?', sn++);

// ═══ Slide 3: Bullet Slide ═══
addBulletSlide(deck, 'Benefits of Code-Driven Decks', [
  '**Version control** — track every change in git',
  '**Reproducible** — same input always produces same output',
  '**Programmable** — loops, conditionals, data-driven slides',
  '**Themeable** — swap YAML, regenerate entire deck',
  '**Reviewable** — code review catches layout bugs',
], sn++, 'Key selling points for the slides-as-code approach.');

// ═══ Slide 4: Process Flow ═══
addProcessFlow(deck, 'The Generation Pipeline', [
  'Outline\nMarkdown with directives',
  'Layout Selection\nAI picks best layout per slide',
  'Script Generation\nNode.js ESM using helpers',
  'Render\npptxgenjs → .pptx file',
], sn++, 'Four-step pipeline from outline to deck.');

// ═══ Slide 5: Section Divider ═══
addSectionDivider(deck, 2, 'Layout Variety', sn++);

// ═══ Slide 6: Two-Column ═══
addTwoColumn(deck, 'Engines Compared', 'pptxgenjs', 'python-pptx', [
  'Full programmatic control',
  'Rich visual layouts',
  'Icon rendering via react-icons',
  'No template dependency',
], [
  'Template-based inheritance',
  'Corporate master slides built-in',
  'Placeholder-driven layouts',
  'Smaller output files',
], sn++, 'Trade-offs between the two generation engines.');

// ═══ Slide 7: Card Grid ═══
addCardGrid(deck, 'Available Layouts', [
  { title: 'Bullets', body: 'Adaptive font sizing, bold lead-ins, sub-bullets' },
  { title: 'Process Flow', body: 'Numbered step boxes with arrows, 1-row or 2-row' },
  { title: 'Two-Column', body: 'Headers, vertical divider, bullet lists' },
  { title: 'Card Grid', body: '2×2 or 3×N cards with accent bars and icons' },
  { title: 'Icon Rows', body: 'Labeled rows with icon circles or accent bars' },
  { title: 'Code Block', body: 'Dark background, mono font, accent bar' },
], sn++, 'Six core layout types available in the helper library.');

// ═══ Slide 8: Stat Callout ═══
addStatCallout(deck, 'By the Numbers', [
  { value: '12', label: 'Layout helpers', desc: 'Covering all common slide types' },
  { value: '2', label: 'Themes', desc: 'AMD Corporate + Default dark' },
  { value: '27', label: 'Example slides', desc: 'In the reference deck' },
], sn++, 'Quick stats about the helper library.');

// ═══ Slide 9: Code Slide ═══
addCodeSlide(deck, 'Creating a Master-Enabled Deck', `
import { createDeck, addBulletSlide } from '../lib/pptxgenjs-helpers.mjs';

// Enable slide masters — chrome inherits from master, not baked per-slide
const deck = createDeck('themes/amd.yaml', { useSlideMaster: true });

addBulletSlide(deck, 'My Slide', ['Point 1', 'Point 2'], 1, 'notes');

await deck.save('output/my-deck.pptx');
`, sn++, 'Minimal example showing the useSlideMaster flag.');

// ═══ Slide 10: Closing ═══
addClosingSlide(deck, sn++, 'Generated with slide masters enabled.');

// Honor AIPPT_PREVIEW_OUT (set by the live-preview renderer) so the deck lands
// on a writable path under a read-only root filesystem; fall back to the
// repo-relative path for standalone CLI runs.
const _outDir = process.env.AIPPT_PREVIEW_OUT || 'examples/slides-as-code-design-master';
await deck.save(`${_outDir}/slides-as-code-design-master.pptx`);
