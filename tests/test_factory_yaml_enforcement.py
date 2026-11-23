"""Mandatory YAML and pipeline switches are enforced, not decorative."""
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from word_parser.application.factory import create_default_parser
from word_parser.config.loader import ConfigLoader
from word_parser.document.word.simple_docx_loader import SimpleDocxLoader
from word_parser.primary.validator import PassThroughValidator, Validator


ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs"


def test_production_yaml_validator_flag_matches_original_behavior():
    pipeline = yaml.safe_load((CFG / "pipeline.yaml").read_text(encoding="utf-8-sig"))
    assert pipeline["modules"]["validator"]["enabled"] is True
    parser = create_default_parser(CFG)
    assert isinstance(parser.pipeline.validator, Validator)
    assert parser.pipeline.exporter.result_builder.strict_domain_literals is True


def test_disabling_supported_modules_selects_real_python_operators(monkeypatch):
    original = ConfigLoader.load_required_yaml
    def override(self, path):
        data = original(self, path)
        if path == "pipeline.yaml":
            data = deepcopy(data)
            data["modules"]["validator"]["enabled"] = False
            data["modules"]["aspose_loader"]["enabled"] = False
        return data
    monkeypatch.setattr(ConfigLoader, "load_required_yaml", override)
    parser = create_default_parser(CFG)
    assert isinstance(parser.pipeline.validator, PassThroughValidator)
    assert isinstance(parser.pipeline.loader.word_loader, SimpleDocxLoader)
    fields = {"x": object()}
    assert parser.pipeline.validator.validate(fields) is fields


def test_unsupported_disabled_module_fails_instead_of_being_ignored(monkeypatch):
    original = ConfigLoader.load_required_yaml
    def override(self, path):
        data = original(self, path)
        if path == "pipeline.yaml":
            data = deepcopy(data)
            data["modules"]["alias_matcher"]["enabled"] = False
        return data
    monkeypatch.setattr(ConfigLoader, "load_required_yaml", override)
    with pytest.raises(ValueError, match="alias_matcher"):
        create_default_parser(CFG)


def test_empty_or_missing_required_yaml_fails_loudly(tmp_path):
    loader = ConfigLoader(tmp_path)
    with pytest.raises(FileNotFoundError):
        loader.load_required_yaml("output_schema.yaml")
    (tmp_path / "output_schema.yaml").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="非空对象"):
        loader.load_required_yaml("output_schema.yaml")
