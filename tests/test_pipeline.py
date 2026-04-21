"""Tests for aippt.pipeline module."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from pptx import Presentation

from aippt.pipeline import PipelineConfig, PipelineResult


class TestPipelineConfig:
    def test_required_fields(self):
        config = PipelineConfig(
            outline_text="# Test\n## Slide 1\n- Bullet",
            template_path="template.pptx",
            output_path="output.pptx",
        )
        assert config.outline_text == "# Test\n## Slide 1\n- Bullet"
        assert config.template_path == "template.pptx"
        assert config.output_path == "output.pptx"

    def test_defaults(self):
        config = PipelineConfig(
            outline_text="x", template_path="t.pptx", output_path="o.pptx"
        )
        assert config.enhance is False
        assert config.model is None
        assert config.audience is None
        assert config.show_plan is False
        assert config.no_plan is False
        assert config.gateway_config is None
        assert config.api_key is None
        assert config.api_base is None
        assert config.image_gen == "none"
        assert config.mcp_config == "mcp_servers.json"
        assert config.mcp_server == "txt2img"
        assert config.classification == "internal"
        assert config.outline_path is None
        assert config.progress_callback is None

    def test_all_fields(self):
        cb = lambda step, detail: None
        config = PipelineConfig(
            outline_text="x",
            template_path="t.pptx",
            output_path="o.pptx",
            enhance=True,
            model="claude-sonnet-4-6",
            audience="engineers",
            show_plan=True,
            no_plan=False,
            gateway_config="gateway.yaml",
            api_key="sk-test",
            api_base="https://api.example.com",
            image_gen="mcp",
            mcp_config="mcp.json",
            mcp_server="imgserver",
            classification="external",
            outline_path="outline.md",
            progress_callback=cb,
        )
        assert config.enhance is True
        assert config.model == "claude-sonnet-4-6"
        assert config.audience == "engineers"
        assert config.progress_callback is cb


class TestPipelineResult:
    def test_fields(self):
        result = PipelineResult(
            output_path="out.pptx", slide_count=5, title="Test"
        )
        assert result.output_path == "out.pptx"
        assert result.slide_count == 5
        assert result.title == "Test"


class TestRunPipeline:
    def _make_template(self, tmp_path):
        path = str(tmp_path / "template.pptx")
        Presentation().save(path)
        return path

    def test_basic_pipeline_no_enhance(self, tmp_path):
        """Non-enhanced pipeline produces slides from markdown."""
        from aippt.pipeline import PipelineConfig, run_pipeline

        template = self._make_template(tmp_path)
        output = str(tmp_path / "output.pptx")

        config = PipelineConfig(
            outline_text="## Slide One\n- Point A\n- Point B\n\n## Slide Two\n- Point C\n",
            template_path=template,
            output_path=output,
        )
        result = run_pipeline(config)

        assert result.slide_count == 2
        assert result.output_path == output
        assert os.path.exists(output)

    def test_pipeline_calls_progress_callback(self, tmp_path):
        """Progress callback is invoked during pipeline execution."""
        from aippt.pipeline import PipelineConfig, run_pipeline

        template = self._make_template(tmp_path)
        output = str(tmp_path / "output.pptx")
        steps = []

        config = PipelineConfig(
            outline_text="## Slide\n- Bullet\n",
            template_path=template,
            output_path=output,
            progress_callback=lambda step, detail: steps.append(step),
        )
        run_pipeline(config)

        assert "parse" in steps
        assert "build" in steps

    def test_pipeline_raises_on_missing_template(self, tmp_path):
        """Pipeline raises FileNotFoundError for missing template."""
        from aippt.pipeline import PipelineConfig, run_pipeline

        config = PipelineConfig(
            outline_text="## Slide\n- Bullet\n",
            template_path=str(tmp_path / "nonexistent.pptx"),
            output_path=str(tmp_path / "output.pptx"),
        )
        with pytest.raises(FileNotFoundError):
            run_pipeline(config)

    def test_pipeline_result_title(self, tmp_path):
        """Pipeline result contains the first slide title."""
        from aippt.pipeline import PipelineConfig, run_pipeline

        template = self._make_template(tmp_path)
        output = str(tmp_path / "output.pptx")

        config = PipelineConfig(
            outline_text="## My Great Slide\n- Content\n",
            template_path=template,
            output_path=output,
        )
        result = run_pipeline(config)
        assert result.title == "My Great Slide"


class TestFunctionalSlideSkipping:
    """Functional slides (≤2 bullets, no LAYOUT) skip enhancement."""

    def _make_template(self, tmp_path):
        path = str(tmp_path / "template.pptx")
        Presentation().save(path)
        return path

    def _mock_client(self):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "NARRATIVE: x\nLAYOUT: bullet"
        mock_client.model_config = MagicMock()
        mock_client.model_config.provider = "anthropic"
        return mock_client

    @patch('aippt.enhancer.enhance_with_llm')
    @patch('aippt.llm.LLMClient')
    @patch('aippt.config.get_model_default', return_value='test-model')
    def test_title_slide_skips_enhancement(self, mock_default, mock_llm_cls,
                                            mock_enhance, tmp_path):
        """A 2-bullet title slide should NOT call enhance_with_llm."""
        from aippt.pipeline import PipelineConfig, run_pipeline

        mock_client = self._mock_client()
        # plan_deck response (empty plan)
        mock_client.generate_text.return_value = (
            '{"narrative_arc":"unknown","arc_assessment":"","slides":[]}'
        )
        mock_llm_cls.return_value = mock_client
        mock_enhance.return_value = "NARRATIVE: x\nLAYOUT: bullet"

        template = self._make_template(tmp_path)
        output = str(tmp_path / "output.pptx")

        # Title slide has only 2 bullets and no LAYOUT directive
        outline = (
            "## GPU Monitoring\n"
            "- Matt Elliott\n"
            "  - Technical Marketing Engineer\n"
            "\n"
            "## Real Content Slide\n"
            "- Point A\n"
            "- Point B\n"
            "- Point C\n"
            "- Point D\n"
        )
        config = PipelineConfig(
            outline_text=outline,
            template_path=template,
            output_path=output,
            enhance=True,
        )
        run_pipeline(config)

        # enhance_with_llm should be called only for the content-rich slide
        assert mock_enhance.call_count == 1
        enhanced_slide = mock_enhance.call_args[0][0]
        assert enhanced_slide['title'] == 'Real Content Slide'

    @patch('aippt.enhancer.enhance_with_llm')
    @patch('aippt.llm.LLMClient')
    @patch('aippt.config.get_model_default', return_value='test-model')
    def test_slide_with_layout_directive_always_enhanced(self, mock_default,
                                                          mock_llm_cls,
                                                          mock_enhance, tmp_path):
        """Even a sparse slide with a LAYOUT directive should be enhanced."""
        from aippt.pipeline import PipelineConfig, run_pipeline

        mock_client = self._mock_client()
        mock_client.generate_text.return_value = (
            '{"narrative_arc":"unknown","arc_assessment":"","slides":[]}'
        )
        mock_llm_cls.return_value = mock_client
        mock_enhance.return_value = "NARRATIVE: x\nLAYOUT: basic"

        template = self._make_template(tmp_path)
        output = str(tmp_path / "output.pptx")

        # Slide has LAYOUT directive despite only 1 bullet
        outline = (
            "## Overview\n"
            "LAYOUT: basic\n"
            "- Single point\n"
        )
        config = PipelineConfig(
            outline_text=outline,
            template_path=template,
            output_path=output,
            enhance=True,
        )
        run_pipeline(config)

        # Should still be enhanced because of LAYOUT directive
        assert mock_enhance.call_count == 1

    @patch('aippt.enhancer.enhance_with_llm')
    @patch('aippt.llm.LLMClient')
    @patch('aippt.config.get_model_default', return_value='test-model')
    def test_three_bullet_slide_always_enhanced(self, mock_default, mock_llm_cls,
                                                 mock_enhance, tmp_path):
        """A slide with 3+ bullets should always be enhanced."""
        from aippt.pipeline import PipelineConfig, run_pipeline

        mock_client = self._mock_client()
        mock_client.generate_text.return_value = (
            '{"narrative_arc":"unknown","arc_assessment":"","slides":[]}'
        )
        mock_llm_cls.return_value = mock_client
        mock_enhance.return_value = "NARRATIVE: x\nLAYOUT: bullet"

        template = self._make_template(tmp_path)
        output = str(tmp_path / "output.pptx")

        outline = "## Slide\n- A\n- B\n- C\n"
        config = PipelineConfig(
            outline_text=outline,
            template_path=template,
            output_path=output,
            enhance=True,
        )
        run_pipeline(config)
        assert mock_enhance.call_count == 1
