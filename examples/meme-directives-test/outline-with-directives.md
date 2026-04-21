# Outline Directives
- Control slide layout and embed images directly in your markdown outline
- LAYOUT: and IMAGE: directives are written as plain text lines before bullet content
- Directives are stripped from the final slide body -- they only affect rendering

# What Are Directives?
LAYOUT: bullet
- Directives are special lines in a slide's content block
- LAYOUT: sets the slide layout type (bullet, two_column, numbered, basic, diagram)
- IMAGE: sets a pre-made image to embed on the slide
- Both directives are optional -- omit them to use the default layout
- Directive keywords are case-sensitive and must appear in UPPERCASE

# Layout Types Side by Side
LAYOUT: two_column | Without Directives | With Directives
- Default layout chosen automatically
- Content formatted as simple bullets
- No column structure
- Works for most slides
- Specify LAYOUT: two_column
- Content splits at the midpoint into two columns
- Add column headers after pipe separators
- Ideal for comparisons and pros/cons

# Generating a Deck: Step by Step
LAYOUT: numbered
- Write your markdown outline with H1 headers as slide titles
- Add LAYOUT: or IMAGE: directives on lines before your bullet content
- Run: outline2ppt.py create outline.md template.pptx output.pptx
- Open the generated deck and review the results
- Re-run with --enhance to layer in AI-generated speaker notes and narrative

# System Architecture Diagram
LAYOUT: diagram
IMAGE: images/architecture.png
- The IMAGE: directive loads a pre-made image onto the slide
- LAYOUT: diagram reserves the full content area for the image
- Use this combination when you want a full-image slide with text in speaker notes
- The image path is relative to the outline file's directory

# Before You Start
IMAGE: images/screenshot.png
- IMAGE: without LAYOUT: diagram shows image and text side-by-side
- The template's picture+text layout places the image left and bullets right
- Use LAYOUT: diagram with IMAGE: if you want the image to fill the entire slide
- Supported formats: PNG, JPG, GIF, BMP, TIFF
- Relative paths are resolved from the outline file's location
- Missing images log a warning but do not abort deck generation
