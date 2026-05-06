"""Tests for theme token schema v2 — typography, shadow, eyebrow, data_colors, overrides."""

import subprocess
import json
import os
import pytest

HELPERS_DIR = os.path.join(os.path.dirname(__file__), "..")

def run_node(script):
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True, text=True, cwd=HELPERS_DIR, timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Node failed: {result.stderr}")
    return json.loads(result.stdout)


class TestLoadThemeDefaults:
    """When a theme YAML omits new token sections, loadTheme() fills defaults."""

    def test_typography_defaults(self):
        theme = run_node("""
            import { loadTheme } from './lib/pptxgenjs-helpers.mjs';
            const t = loadTheme('themes/default.yaml');
            console.log(JSON.stringify(t.typography));
        """)
        assert theme["title_size"] == 36
        assert theme["heading_size"] == 28
        assert theme["subtitle_size"] == 18
        assert theme["body_size"] == 18
        assert theme["small_size"] == 14
        assert theme["eyebrow_size"] == 8
        assert theme["eyebrow_bold"] == False
        assert theme["eyebrow_char_spacing"] == 6
        assert theme["stat_size"] == 48
        assert theme["stat_bold"] == True
        assert theme["stat_label_size"] == 16
        assert theme["stat_desc_size"] == 13
        assert theme["code_size"] == 14
        assert theme["footer_size"] == 10

    def test_shadow_defaults(self):
        theme = run_node("""
            import { loadTheme } from './lib/pptxgenjs-helpers.mjs';
            const t = loadTheme('themes/default.yaml');
            console.log(JSON.stringify(t.shadow));
        """)
        assert theme["blur"] == 4
        assert theme["offset"] == 2
        assert theme["angle"] == 135
        assert theme["color"] == "000000"
        assert theme["opacity"] == 0.12

    def test_eyebrow_defaults(self):
        theme = run_node("""
            import { loadTheme } from './lib/pptxgenjs-helpers.mjs';
            const t = loadTheme('themes/default.yaml');
            console.log(JSON.stringify(t.eyebrow));
        """)
        assert theme["show"] == True
        assert theme["dash_width"] == 1.2
        assert theme["dash_height"] == 0.035
        assert theme["label_offset"] == 1.35

    def test_data_colors_defaults(self):
        theme = run_node("""
            import { loadTheme } from './lib/pptxgenjs-helpers.mjs';
            const t = loadTheme('themes/default.yaml');
            console.log(JSON.stringify(t.data_colors));
        """)
        assert theme["series_1"] == ""
        assert theme["series_2"] == ""
        assert theme["series_3"] == ""
        assert theme["positive"] == "1AA01A"
        assert theme["negative"] == "D73D2B"
        assert theme["neutral"] == ""

    def test_expanded_color_defaults(self):
        theme = run_node("""
            import { loadTheme } from './lib/pptxgenjs-helpers.mjs';
            const t = loadTheme('themes/default.yaml');
            console.log(JSON.stringify({
                code_bg: t.colors.code_bg,
                code_text: t.colors.code_text,
                heading_color: t.colors.heading_color,
                eyebrow_color: t.colors.eyebrow_color,
                stat_color: t.colors.stat_color,
            }));
        """)
        assert theme["code_bg"] == "0D1117"
        assert theme["code_text"] == "58A6FF"
        assert theme["heading_color"] == ""
        assert theme["eyebrow_color"] == ""
        assert theme["stat_color"] == ""


class TestLoadThemeOverrides:
    """When a theme YAML specifies new token values, they override defaults."""

    def test_typography_override(self):
        theme = run_node("""
            import { loadTheme } from './lib/pptxgenjs-helpers.mjs';
            const t = loadTheme('themes/instinct.yaml');
            console.log(JSON.stringify(t.typography));
        """)
        assert theme["body_size"] == 16
        assert theme["heading_size"] == 28
        assert theme["title_size"] == 36

    def test_shadow_override(self):
        theme = run_node("""
            import { loadTheme } from './lib/pptxgenjs-helpers.mjs';
            const t = loadTheme('themes/instinct.yaml');
            console.log(JSON.stringify(t.shadow));
        """)
        assert theme["color"] == "003040"
        assert theme["opacity"] == 0.15
        assert theme["blur"] == 4

    def test_expanded_color_override(self):
        theme = run_node("""
            import { loadTheme } from './lib/pptxgenjs-helpers.mjs';
            const t = loadTheme('themes/instinct.yaml');
            console.log(JSON.stringify({
                code_bg: t.colors.code_bg,
                code_text: t.colors.code_text,
            }));
        """)
        assert theme["code_bg"] == "131416"
        assert theme["code_text"] == "00C2DE"


class TestCreateDeckOverrides:
    """createDeck() overrides deep-merge over the loaded theme."""

    def test_typography_override_via_create_deck(self):
        result = run_node("""
            import { createDeck } from './lib/pptxgenjs-helpers.mjs';
            const deck = createDeck('themes/default.yaml', {
                overrides: { typography: { heading_size: 24 } },
            });
            console.log(JSON.stringify({
                heading_size: deck.theme.typography.heading_size,
                title_size: deck.theme.typography.title_size,
            }));
        """)
        assert result["heading_size"] == 24
        assert result["title_size"] == 36

    def test_color_override_via_create_deck(self):
        result = run_node("""
            import { createDeck } from './lib/pptxgenjs-helpers.mjs';
            const deck = createDeck('themes/default.yaml', {
                overrides: { colors: { accent: "FF5733" } },
            });
            console.log(JSON.stringify({
                accent: deck.theme.colors.accent,
                background: deck.theme.colors.background,
            }));
        """)
        assert result["accent"] == "FF5733"
        assert result["background"] == "1E293B"


class TestBackwardCompatibility:
    """Existing themes without new sections produce identical base token objects."""

    def test_existing_colors_unchanged(self):
        theme = run_node("""
            import { loadTheme } from './lib/pptxgenjs-helpers.mjs';
            const t = loadTheme('themes/amd.yaml');
            console.log(JSON.stringify(t.colors));
        """)
        assert theme["background"] == "000000"
        assert theme["accent"] == "00C2DE"
        assert theme["text_primary"] == "FFFFFF"
        assert theme["surface"] == "636466"

    def test_existing_fonts_unchanged(self):
        theme = run_node("""
            import { loadTheme } from './lib/pptxgenjs-helpers.mjs';
            const t = loadTheme('themes/amd.yaml');
            console.log(JSON.stringify(t.fonts));
        """)
        assert theme["heading"] == "Arial"
        assert theme["body"] == "Arial"
        assert theme["mono"] == "Consolas"
