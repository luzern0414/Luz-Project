"""Machine-state summaries use a real template without opening business research."""
from pathlib import Path
import importlib.util

import pytest

import project_summary as summary
from client_fixture import new_project
import project_core as pc


def library():
    source = Path(__file__).resolve().parents[2] / "Luz-Design/scripts/template_library.py"
    spec = importlib.util.spec_from_file_location("_summary_contract_test_library", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("model", ["stage", "document"])
def test_initial_summary_uses_real_template_and_records_its_final_bytes(tmp_path, model):
    root = new_project("状态索引", tmp_path, model=model)
    page = pc.summary_path(root)
    assert page is not None and page.is_file()
    item = library().require_selected(root.parent, "luz-project", "internal-summary", page,
                                      "reading-html", phase="post")
    assert item["snapshots"]
    assert item["output"]["generator"] == "Luz-Project/scripts/project_summary.py:render_summary"
    assert not (root / "00-crawl").exists()  # a state index is not a new business stage
    assert "项目总览" in page.read_text(encoding="utf-8")


def test_summary_refuses_a_broken_template_before_overwriting_the_page(tmp_path, monkeypatch):
    root = new_project("拒绝写入", tmp_path)
    page = pc.summary_path(root)
    before = page.read_bytes()
    real = library()
    calls = []

    def refuse(*args, **kwargs):
        calls.append((args, kwargs))
        raise ValueError("actual template preflight failed")

    monkeypatch.setattr(real, "require_selected", refuse)
    monkeypatch.setattr(summary, "design_library", lambda: real)
    with pytest.raises(pc.ProjectError, match="actual template preflight failed"):
        summary.render_summary(root)
    assert calls and page.read_bytes() == before


def test_summary_hash_detects_later_edits_and_cannot_cover_another_file(tmp_path):
    root = new_project("哈希绑定", tmp_path)
    page = pc.summary_path(root)
    real = library()
    other = page.parent / "other.html"
    other.write_bytes(page.read_bytes())
    with pytest.raises(ValueError, match="准确输出位置"):
        real.require_selected(root.parent, "luz-project", "internal-summary", other,
                              "reading-html", phase="post")
    page.write_text(page.read_text(encoding="utf-8") + "<!-- edited -->", encoding="utf-8")
    with pytest.raises(ValueError, match="哈希不符"):
        real.require_selected(root.parent, "luz-project", "internal-summary", page,
                              "reading-html", phase="post")
