"""Tests for the fast AI engine (LLM layout plan → deterministic script)."""
import json
import re

import pytest

from aippt.pptxgenjs_plan import build_prompt, generate_script, parse_plan
from aippt.pptxgenjs_direct import plan_slides

OUTLINE = """# AMD Instinct MI355X: Measured Performance
Inference results — Q4 2026

# Agenda
- Inference
- Training

# Throughput
- **MI300X** — 1,000 tok/s
- **MI355X** — 2,100 tok/s

# Steps
- Install ROCm
- Pull the container
- Run the benchmark
"""


class FakeLLM:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def generate_text(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.reply


def _plan(*layouts):
    return json.dumps({'slides': [{'i': i, 'layout': l} for i, l in enumerate(layouts)]})


def _helpers(script):
    return re.findall(r'^(add[A-Z]\w+)\(deck', script, re.M)


def test_prompt_lists_every_slide_and_layout():
    slides = plan_slides(OUTLINE)
    prompt = build_prompt(slides)
    for i, s in enumerate(slides):
        assert f'[{i}] {s["title"]}' in prompt
    assert 'hero_title' in prompt and 'proof_point' in prompt


def test_parse_plan_drops_invalid_entries():
    raw = 'Sure! ' + json.dumps({'slides': [
        {'i': 0, 'layout': 'product_title'},
        {'i': 1, 'layout': 'agenda'},
        {'i': 2, 'layout': 'made_up'},
        {'i': 3, 'layout': 'hero_title'},     # title layout off slide 0
        {'i': 9, 'layout': 'bullet'},         # out of range
        {'i': 'x', 'layout': 'bullet'},
    ]})
    plan, dropped = parse_plan(raw, 4)
    assert plan == {0: 'product_title', 1: 'agenda'}
    assert len(dropped) == 4


def test_parse_plan_keeps_two_column_headers_and_skips_auto():
    plan, _ = parse_plan(_plan('title_alt', 'auto', 'two_column | Before | After'), 3)
    assert plan == {0: 'title_alt', 2: 'two_column | Before | After'}


def test_parse_plan_blocks_brand_layouts_without_brand_title():
    plan, dropped = parse_plan(_plan('title_alt', 'proof_point'), 2)
    assert plan == {0: 'title_alt'}
    assert dropped == [{'i': 1, 'layout': 'proof_point'}]


@pytest.mark.parametrize('raw', ['', 'not json', '{"slides": "nope"}', '{bad json}'])
def test_parse_plan_survives_garbage(raw):
    assert parse_plan(raw, 3)[0] == {}


def test_generate_uses_plan(tmp_path):
    llm = FakeLLM(_plan('product_title', 'agenda', 'proof_point', 'numbered'))
    script = generate_script(OUTLINE, str(tmp_path / 'deck.mjs'), llm_client=llm)
    assert _helpers(script)[:4] == [
        'addProductTitleSlide', 'addAgendaSlide', 'addProofPointSlide', 'addProcessFlow']
    assert len(llm.calls) == 1
    assert (tmp_path / 'deck.mjs').read_text() == script


def test_author_layout_directive_wins(tmp_path):
    outline = OUTLINE.replace('# Steps\n', '# Steps\nLAYOUT: bullet\n')
    llm = FakeLLM(_plan('title_alt', 'agenda', 'auto', 'numbered'))
    script = generate_script(outline, str(tmp_path / 'deck.mjs'), llm_client=llm)
    assert _helpers(script)[3] == 'addBulletSlide'


def test_llm_failure_falls_back_to_rule_based(tmp_path):
    from aippt.pptxgenjs_direct import generate_script as direct
    events = []
    script = generate_script(OUTLINE, str(tmp_path / 'a.mjs'),
                             llm_client=FakeLLM(error=RuntimeError('gateway down')),
                             progress_callback=lambda s, d: events.append(d))
    assert script == direct(OUTLINE, str(tmp_path / 'b.mjs'))
    assert any('rule-based' in e for e in events)


def test_plan_can_restyle_synthetic_deck_title(tmp_path):
    outline = "# Deck Title\n## First\n- a\n- b\n## Second\n- c\n"
    llm = FakeLLM(_plan('hero_title'))
    script = generate_script(outline, str(tmp_path / 'deck.mjs'), llm_client=llm)
    assert _helpers(script)[0] == 'addHeroTitleSlide'


def test_tier_outline_builds_30_3_30_deck(tmp_path):
    outline = ("# Widgets\n\n## Widgets\nA tour\n\n# 30 Seconds\n\n## Summary\n- a\n- b\n\n"
               "# 3 Minutes\n\n## Detail\n- c\n- d\n")
    slides = plan_slides(outline)
    llm = FakeLLM(_plan(*['auto'] * len(slides)))
    script = generate_script(outline, str(tmp_path / 'deck.mjs'), llm_client=llm)
    assert re.findall(r'^startSection\(deck, `([^`]*)`', script, re.M) == [
        'Intro', '30 Seconds', '3 Minutes']
    assert _helpers(script).count('addTierDivider') == 2
    assert _helpers(script).count('addClosingSlide') == 2


# ---------------------------------------------------------------------------
# Brand recipes (aippt/brand/recipes.json)
# ---------------------------------------------------------------------------

RECIPE_OUTLINE = """# Instinct
Sub

# Headline results
- 3x — faster training
- 40% — lower cost per token

# Specs
| Spec | MI355X | B200 |
|---|---|---|
| HBM | 288 GB | 192 GB |

# Not a table
- HBM: 288 GB
- FP4: 10 PF
"""


def test_prompt_lists_every_recipe():
    from aippt import recipes
    prompt = build_prompt(plan_slides(OUTLINE))
    for rid in recipes.ids():
        assert f'- {rid}: ' in prompt
    assert prompt.index('- endnotes: ') < prompt.index('- auto: ')


def test_parse_plan_accepts_recipes_on_any_title():
    plan, dropped = parse_plan(_plan('title_alt', 'kpi_tiles', 'hero_number'), 3)
    assert plan == {0: 'title_alt', 1: 'kpi_tiles', 2: 'hero_number'} and not dropped


def test_parse_plan_drops_table_recipe_without_table():
    slides = plan_slides(RECIPE_OUTLINE)
    plan, dropped = parse_plan(_plan('title_alt', 'kpi_tiles', 'spec_table', 'check_matrix'), 4, slides)
    assert plan == {0: 'title_alt', 1: 'kpi_tiles', 2: 'spec_table'}
    assert dropped == [{'i': 3, 'layout': 'check_matrix'}]


@pytest.mark.parametrize('theme', ['amd', 'corp_black'])
def test_generate_uses_recipe_plan(tmp_path, theme):
    llm = FakeLLM(_plan('title_alt', 'kpi_tiles', 'spec_table', 'icon_grid'))
    script = generate_script(RECIPE_OUTLINE, str(tmp_path / 'deck.mjs'), llm_client=llm, theme=theme)
    assert _helpers(script)[:4] == ['addTitleSlide', 'addKpiTiles', 'addSpecTable', 'addIconFeatureGrid']
