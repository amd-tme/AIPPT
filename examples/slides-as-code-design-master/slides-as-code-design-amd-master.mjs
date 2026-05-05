/**
 * slides-as-code-design-amd-master.mjs
 *
 * Master-on variant of the slides-as-code-design example using the AMD theme.
 * Matches the 27-slide outline from slides-as-code-design.js for side-by-side
 * comparison during the slide masters soak period.
 *
 * Usage:
 *   NODE_PATH="$(npm root -g)" node examples/slides-as-code-design-master/slides-as-code-design-amd-master.mjs
 *
 * Output: examples/slides-as-code-design-master/slides-as-code-design-amd-master.pptx
 */

import {
  createDeck, addTitleSlide, addBulletSlide, addSectionDivider,
  addProcessFlow, addTwoColumn, addCardGrid, addStatCallout,
  addCodeSlide, addIconRowsSlide, addClosingSlide, SW, SH
} from '../../lib/pptxgenjs-helpers.mjs';

const deck = createDeck('themes/amd.yaml', { useSlideMaster: true });
let sn = 1;

// ═══ Slide 1: Title ═══
addTitleSlide(deck, 'Slides as Code', 'A Better Way to Build, Edit, and Track Your Presentations', sn++);

// ═══ Slide 2: The Problem Today ═══
addIconRowsSlide(deck, 'The Problem Today', [
  { label: 'Hours of Manual Work', description: 'Building a deck from scratch means dragging shapes, aligning text, and fighting with formatting — slide by slide' },
  { label: 'No Version History', description: 'PowerPoint files are opaque binaries — you can\'t diff, review, or roll back changes meaningfully' },
  { label: 'Inconsistent Results', description: 'Every deck is a one-off. Fonts, spacing, and styling drift between slides and across authors' },
  { label: 'Reuse Is Copy-Paste', description: 'Borrowing slides from old decks means hunting through files and hoping the formatting survives' },
  { label: 'No Collaboration Model', description: 'Sharing a PPTX over email or Teams — who has the latest version? What changed?' },
], null, sn++);

// ═══ Slide 3: What Slides as Code Enables ═══
addCardGrid(deck, 'What If Your Deck Was Code?', [
  { title: 'Readable & Editable', body: 'Your slides defined in a script you can read, understand, and change — not trapped in a binary file format.' },
  { title: 'Version-Controlled', body: 'Track every change with git. See exactly what was modified, when, and by whom — just like source code.' },
  { title: 'Reproducible', body: 'Run the script, get the deck. Same input, same output — every time, on any machine.' },
], sn++);

// ═══ Slide 4: Section — How It Works ═══
addSectionDivider(deck, 1, 'How It Works', sn++);

// ═══ Slide 5: Architecture Overview ═══
addBulletSlide(deck, 'Architecture Overview', [
  'Start with source material — documents, notes, research, or existing slides',
  '**Structured outline** — an AI organizes your content into a clean, editable outline',
  '**Script generation** — the outline becomes human-readable code that defines every slide',
  '**Run to render** — execute the script to produce a finished PPTX; edit the script to make changes',
], sn++, 'Architecture pipeline: Source Material -> Outline -> Script -> PPTX');

// ═══ Slide 6: The Script Is the Source of Truth ═══
addIconRowsSlide(deck, 'The Script Is the Source of Truth', [
  { label: 'Most Precise Representation', description: 'Contains exact positions, colors, fonts, and layout logic for every slide' },
  { label: 'Unlike a PPTX File', description: 'A binary PPTX can\'t be diffed, searched, or merged — a script can do all three' },
  { label: 'Mutable & Trackable', description: 'Scripts can be edited, version-controlled, and diffed like any source code' },
  { label: 'Outline Becomes Lineage', description: 'The outline is tracked as metadata but never mutated after generation' },
], null, sn++);

// ═══ Slide 7: The Closed Loop ═══
addProcessFlow(deck, 'The Closed Loop', [
  'Generate\nAI builds a script and\ninitial PPTX from your outline',
  'Review\nVisual QA — spot text\noverflow and dense slides',
  'Edit\nTell the AI what to fix —\nit updates the script',
  'Regenerate\nRe-run the script to\nproduce an updated PPTX',
  'Repeat\nIterate until the\ndeck is exactly right',
], sn++);

// ═══ Slide 8: Section — Source Tracking ═══
addSectionDivider(deck, 2, 'Source Tracking', sn++);

// ═══ Slide 9: Tracing Decks Back to Code ═══
addBulletSlide(deck, 'Tracing Decks Back to Code', [
  'Every generated deck gets linked to its source script in the catalog',
  'Know which script, engine, theme, and outline produced any deck',
  'Look up source with a single CLI command',
  'Existing decks from arbitrary PPTX files are unaffected — source fields are nullable',
], sn++);

// ═══ Slide 10: What Gets Tracked ═══
addTwoColumn(deck, 'What Gets Tracked', 'Field', 'Purpose', [
  'Script Path — relative path to JS or Python file',
  'Engine — pptxgenjs or python-pptx',
  'Theme — theme name (amd, default, etc.)',
], [
  'Outline Path — the originating markdown outline',
  'Generated At — timestamp of last generation',
  'All fields nullable — only code-generated decks populate them',
], sn++);

// ═══ Slide 11: Auto-Detection ═══
addCardGrid(deck, 'Zero-Configuration Tracking', [
  { title: 'Script Auto-Detection', body: 'The catalog reads your script to determine how it was built — no manual tagging or metadata entry required.' },
  { title: 'Theme Recognition', body: 'Theme settings are read directly from the script so every deck is cataloged with accurate visual context.' },
  { title: 'Works Out of the Box', body: 'Generate a deck with /create-deck and it\'s automatically tracked — nothing to configure, nothing to remember.' },
  { title: 'Always Overridable', body: 'When you need more control, supply explicit source and theme information via the CLI — full flexibility.' },
], sn++);

// ═══ Slide 12: Section — Conversational Editing ═══
addSectionDivider(deck, 3, 'Conversational Editing', sn++);

// ═══ Slide 13: Meet /edit-deck ═══
addIconRowsSlide(deck, 'Meet /edit-deck', [
  { label: 'Natural Language Editing', description: 'Tell an AI what to change in plain English — it modifies the script for you' },
  { label: 'Works from Script or Deck Name', description: 'Point it at a script file or look up a deck by name from the catalog' },
  { label: 'Single-Slide Edits', description: '"make slide 3 a numbered list" — quick, targeted changes' },
  { label: 'Deck-Level Changes', description: '"move compliance section before security" — structural reorganization' },
  { label: 'Batch Operations', description: '"add speaker notes to every slide" — apply changes across all slides at once' },
], null, sn++);

// ═══ Slide 14: Edit Workflow ═══
addProcessFlow(deck, 'Edit Workflow', [
  'Resolve Source\nAccept script path or\nlook up from catalog',
  'Read Context\nScript, PPTX content,\nslide images, theme',
  'LLM Edits\nAI modifies the script\nbased on user request',
  'Diff Preview\nShow changes before\napplying to file',
  'Write & Regenerate\nSave updated script and\nre-run to produce PPTX',
  'Iterate or Review\nAccept more edits or\nhand off to /deck-review',
], sn++);

// ═══ Slide 15: What You Can Edit ═══
addTwoColumn(deck, 'What You Can Edit', 'Single-Slide Edits', 'Deck-Level Edits', [
  'Change layout type (bullet, two-column, numbered)',
  'Rewrite content and bullets',
  'Add or edit speaker notes',
  'Add or swap images',
  'Adjust styling (colors, fonts, spacing)',
], [
  'Add, remove, or duplicate slides',
  'Reorder slides or entire sections',
  'Change theme or global styling',
  'Add section dividers',
  'Batch operations across all slides',
], sn++);

// ═══ Slide 16: Safety and Error Handling ═══
addCardGrid(deck, 'Safety and Error Handling', [
  { title: 'Backup Before Editing', body: 'First edit creates a .bak file preserving the original state — only one backup, always the earliest pre-edit version.' },
  { title: 'Diff Preview', body: 'See exactly what changed in the script before writing. No surprises, full transparency.' },
  { title: 'File Lock Detection', body: 'Warns if the PPTX is open in PowerPoint on Windows before attempting to regenerate.' },
  { title: 'Error Recovery', body: 'If the edited script fails to run, offer to restore from backup or attempt an auto-fix.' },
  { title: 'Git-Friendly', body: 'Edited scripts are plain text that produces clean diffs for version control workflows.' },
], sn++);

// ═══ Slide 17: Section — Change History ═══
addSectionDivider(deck, 4, 'Change History', sn++);

// ═══ Slide 18: Metadata in Speaker Notes ═══
addCodeSlide(deck, 'Metadata in Speaker Notes', `Speaker notes content appears here as normal text.

---aippt-meta---
source: outline → pptxgenjs
created: 2026-03-11
layout: two_column
theme: default
history:
  - 2026-03-11: Created from outline (bullet layout)
  - 2026-03-11: Changed to two_column layout [/edit-deck]
  - 2026-03-12: Rewrote bullets for executive audience [/edit-deck]
---end-aippt-meta---`, sn++);

// ═══ Slide 19: History That Travels With the File ═══
addIconRowsSlide(deck, 'History That Travels With the File', [
  { label: 'Embedded in PPTX', description: 'Change history lives in speaker notes, not locked in an external database' },
  { label: 'Portable by Default', description: 'Share the file via email, Teams, Slack — the history comes along automatically' },
  { label: 'LLM Context', description: 'The AI reads edit history before making changes to understand what\'s been tried' },
  { label: 'Self-Cleaning', description: 'Capped at 10 entries — oldest trimmed on write to keep notes manageable' },
], null, sn++);

// ═══ Slide 20: Section — The Big Picture ═══
addSectionDivider(deck, 5, 'The Big Picture', sn++);

// ═══ Slide 21: User Journey ═══
addProcessFlow(deck, 'User Journey', [
  '/create-outline\nSource material becomes\noutlines/q1-security.md',
  '/create-deck\nGenerates output/\nq1-security.js + .pptx',
  '/deck-review\nFlags text overflow on\nslide 4, density on slide 7',
  '/edit-deck\nFixes slide 4, splits\nslide 7 into two slides',
  '/deck-review\nSlide 7a needs\nspeaker notes',
  '/edit-deck\nAdds notes to\nslides 7-8. Done!',
], sn++);

// ═══ Slide 22: Competitive Landscape ═══
addTwoColumn(deck, 'Competitive Landscape', 'Developer Slide Tools', 'AI Slide Tools', [
  'Slidev, Marp, reveal.js — own markdown-as-source',
  'Excellent developer experience',
  'No PPTX round-trip capability',
  'Cannot produce corporate-ready slide decks',
], [
  'Gamma, Beautiful.ai, PPTAgent — generate polished slides',
  'Impressive visual output from AI',
  'No human-readable source code',
  'No version control or diff-friendly format',
], sn++);

// ═══ Slide 23: What No Other Tool Does ═══
addCardGrid(deck, 'What No Other Tool Does', [
  { title: 'Human-Readable Source', body: 'JS/Python scripts anyone can read, modify, and understand — not opaque binary formats.' },
  { title: 'PPTX Round-Trip', body: 'Generates real PowerPoint files, not HTML or images — opens in PowerPoint, Keynote, Google Slides.' },
  { title: 'Conversational Editing', body: 'Fix slides through natural language against the source code — no manual PPTX surgery.' },
  { title: 'Diff & Version Tracking', body: 'Scripts are plain text, git-ready from day one. Every change produces a clean, reviewable diff.' },
], sn++);

// ═══ Slide 24: Implementation Roadmap ═══
addProcessFlow(deck, 'Implementation Roadmap', [
  'Source Tracking\nLink every deck to its\nscript, theme, and outline',
  'Change History\nEmbed edit history in\nPPTX speaker notes',
  'Deck Generation\nAI creates scripts from\noutlines with full metadata',
  'Conversational Editing\nEdit decks through\nnatural language',
  'Continuous Improvement\nAI reads history to make\nsmarter suggestions',
], sn++);

// ═══ Slide 25: Section — Closing ═══
addSectionDivider(deck, 6, 'Closing', sn++);

// ═══ Slide 26: What's Next ═══
addCardGrid(deck, "What's Next", [
  { title: 'Reliability', body: 'Comprehensive testing of the full create-edit-review loop to ensure consistent, production-quality output.' },
  { title: 'Richer Editing', body: 'Web-based editing UI, smarter AI suggestions from slide analysis, and reference material enrichment.' },
  { title: 'Research-Backed', body: "CMU's AutoPresent confirms: code as an intermediate representation produces higher quality AI slides than direct generation." },
], sn++);

// ═══ Slide 27: Closing ═══
addClosingSlide(deck, sn++, 'Slides as Code — readable, editable, and version-controlled presentations.');

await deck.save('examples/slides-as-code-design-master/slides-as-code-design-amd-master.pptx');
