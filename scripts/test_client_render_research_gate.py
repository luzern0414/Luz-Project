"""Public document renderers retain the stage-specific research contract."""
from __future__ import annotations

import pytest

import client_fixture as fx
import client_render as render
from project_core import ProjectError
from project_paths import locate


@pytest.mark.parametrize("other_stage", [False, True])
def test_showcase_api_requires_its_own_crawl_before_creating_staging(tmp_path, other_stage):
    root = fx.new_project("public showcase research gate", tmp_path, model="stage")
    if other_stage:
        fx.crawled(root, "proposal")  # Explicit OFFLINE evidence cannot cover requirements.
    render.design_modules()
    import template_library

    target = locate(root, "docs/01-需求对接/01-需求说明书.pdf")
    template_library.select(root, "luz-project", "requirements", "showcase", str(target))
    template_library.require_selected(root, "luz-project", "requirements", target, "showcase")
    spec = render.expand_auto(fx.requirements(), fx.features(), "fitness-gym")
    work = locate(root, "client-docs")
    assert not work.exists()

    with pytest.raises(ProjectError, match="Crawl|crawl"):
        render.build_showcase(root, "requirements", spec)

    assert not work.exists()
    assert not target.exists()
