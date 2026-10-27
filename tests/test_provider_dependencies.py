"""Vertex AI and Bedrock support ship with every install, not as extras."""

from __future__ import annotations

import importlib
import importlib.util
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
PYINSTALLER_SPEC = ROOT / "strix.spec"


def _pyproject() -> dict[str, object]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


@pytest.mark.skipif(not PYPROJECT.exists(), reason="this fork ships no pyproject.toml")
@pytest.mark.parametrize("package", ["google-auth", "boto3"])
def test_provider_packages_are_regular_dependencies(package: str) -> None:
    project = _pyproject()["project"]
    assert isinstance(project, dict)
    assert any(req.startswith(package) for req in project["dependencies"])
    assert "optional-dependencies" not in project


@pytest.mark.parametrize(
    "module",
    [
        "google.auth",
        "google.auth.transport.requests",
        "google.oauth2.service_account",
        "boto3",
        "litellm.llms.vertex_ai.vertex_llm_base",
        "litellm.llms.bedrock.base_aws_llm",
    ],
)
def test_provider_modules_import(module: str) -> None:
    if module.startswith("google") and importlib.util.find_spec("google") is None:
        pytest.skip("google-auth is not installed in this deployment")
    importlib.import_module(module)


@pytest.mark.skipif(not PYINSTALLER_SPEC.exists(), reason="this fork ships no strix.spec")
def test_pyinstaller_spec_bundles_google_auth() -> None:
    spec = PYINSTALLER_SPEC.read_text(encoding="utf-8")
    assert "collect_submodules('google.auth')" in spec
    assert "'google.auth'," not in spec
    assert "'google.oauth2'," not in spec
