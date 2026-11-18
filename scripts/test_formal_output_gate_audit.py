"""The audit must detect real bypasses without accepting documentary tokens."""
from pathlib import Path

import pytest

import formal_output_gate_audit as audit


def inspect_writer(tmp_path, monkeypatch, source, *, function="main", ui=False):
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    path = tmp_path / "Luz-Dev" / "scripts" / "writer.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    entry = audit.EntryPoint("luz-dev", "scripts/writer.py", function,
                             "reading-html", ui=ui, source_audit=ui)
    return audit._audit_entry(entry)


def test_missing_gates_are_reported(tmp_path, monkeypatch):
    result = inspect_writer(tmp_path, monkeypatch, "def main():\n    target.write_text('report')\n")
    assert not result["crawl_gate"]
    assert not result["template_gate"]
    assert result["write_before_gate"]


def test_executed_local_helpers_count_as_gates(tmp_path, monkeypatch):
    result = inspect_writer(tmp_path, monkeypatch, """def preflight():
    require_session_preflight(session)
    require_selected(session, caller, stage, target, 'reading-html')

def main():
    preflight()
    target.write_text('report')
""")
    assert result["crawl_gate"] and result["template_gate"]
    assert not result["write_before_gate"]
    assert not result["errors"]


@pytest.mark.parametrize("source", [
    """def main():
    require_session_preflight(session)
    target.write_text('report')
    require_selected(session, caller, stage, target, 'reading-html')
""",
    """def main():
    require_selected(session, caller, stage, target, 'reading-html')
    target.write_text('report')
    require_session_preflight(session)
""",
    """def preflight():
    target.write_text('report')
    require_session_preflight(session)
    require_selected(session, caller, stage, target, 'reading-html')

def main():
    preflight()
""",
])
def test_writing_before_either_required_gate_is_reported(tmp_path, monkeypatch, source):
    assert inspect_writer(tmp_path, monkeypatch, source)["write_before_gate"]


def test_comments_strings_and_deferred_bodies_do_not_pass(tmp_path, monkeypatch):
    result = inspect_writer(tmp_path, monkeypatch, """def main():
    # require_session_preflight and require_selected were considered.
    note = 'template_library source_ui require_audit'
    def unused():
        require_session_preflight(session)
        require_selected(session, caller, stage, target, 'reading-html')
    target.write_text('report')
""")
    assert not result["crawl_gate"] and not result["template_gate"]


def test_post_write_receipt_cannot_replace_template_preflight(tmp_path, monkeypatch):
    result = inspect_writer(tmp_path, monkeypatch, """def main():
    require_session_preflight(session)
    target.write_text('report')
    record_output(session, caller, stage, target, 'reading-html')
""")
    assert not result["template_gate"]


def test_missing_inventory_function_is_an_error(tmp_path, monkeypatch):
    result = inspect_writer(tmp_path, monkeypatch, """def some_other_function():
    require_session_preflight(session)
    require_selected(session, caller, stage, target, 'reading-html')
""")
    assert any("不存在" in error and "main" in error for error in result["errors"])


@pytest.mark.parametrize("require_audit, accepted", [("False", False), ("True", True)])
def test_ui_export_requires_browser_audit(tmp_path, monkeypatch, require_audit, accepted):
    result = inspect_writer(tmp_path, monkeypatch, f"""def main():
    require_session_preflight(session)
    require_selected(session, caller, stage, target, 'ui-source-output')
    verify_package(package, session=session, require_audit={require_audit})
    target.write_bytes(b'ui')
""", ui=True)
    assert result["source_audit_detected"] is accepted


def test_disabled_legacy_writer_is_not_a_generation_bypass(tmp_path, monkeypatch):
    result = inspect_writer(tmp_path, monkeypatch, """def main():
    reject_legacy_ui_generation('writer.py')
    target.write_text('unreachable')
""", ui=True)
    assert result["disabled"]
    assert not result["errors"]


def test_local_imported_gate_is_resolved(tmp_path, monkeypatch):
    scripts = tmp_path / "Luz-Dev" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "design_gate.py").write_text("""def gate(target):
    require_session_preflight(session)
    require_selected(session, caller, stage, target, 'reading-html')
""", encoding="utf-8")
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    (scripts / "writer.py").write_text("""from design_gate import gate as checked

def main():
    checked(target)
    target.write_text('report')
""", encoding="utf-8")
    result = audit._audit_entry(audit.EntryPoint("luz-dev", "scripts/writer.py", "main", "reading-html"))
    assert result["crawl_gate"] and result["template_gate"]
    assert not result["errors"]


def test_design_combined_gate_requires_its_template_argument(tmp_path, monkeypatch):
    result = inspect_writer(tmp_path, monkeypatch, """def main():
    require_session_preflight(session, target, template_id='docx')
    target.write_bytes(b'docx')
""")
    assert result["crawl_gate"] and result["template_gate"]
    assert not result["errors"]


def test_raw_json_writes_do_not_require_a_document_template(tmp_path, monkeypatch):
    result = inspect_writer(tmp_path, monkeypatch, """def main():
    require_session_preflight(session)
    spec_path = raw / 'report.spec.json'
    spec_path.write_text(json.dumps(spec))
    (raw / 'build-report.json').write_text(json.dumps(report))
    require_selected(session, caller, stage, target, 'reading-html')
    target.write_text('report')
""")
    assert not result["write_before_gate"]
    assert len(result["process_writes"]) == 2


def test_in_memory_image_encoding_is_not_a_file_write(tmp_path, monkeypatch):
    result = inspect_writer(tmp_path, monkeypatch, """def main():
    require_session_preflight(session)
    buffer = io.BytesIO()
    image.save(buffer, 'JPEG')
    require_selected(session, caller, stage, target, 'reading-html')
    target.write_text('report')
""")
    assert not result["write_before_gate"]


def test_internal_reference_maintenance_is_explicitly_excluded():
    excluded = {entry.file for entry in audit.ENTRY_POINTS if not entry.formal}
    assert {"scripts/build_checklist.py", "scripts/build_standards.py",
            "scripts/build_function_catalog.py", "scripts/knowledge.py"}.issubset(excluded)
    assert all(entry.exclusion_reason for entry in audit.ENTRY_POINTS if not entry.formal)


@pytest.mark.parametrize("code,written,diagnostic,expected", [
    (1, False, "缺少 Luz-Design 模板选择记录", True),
    (1, False, "ModuleNotFoundError: optional_library", False),
    (0, False, "缺少 Luz-Design 模板选择记录", False),
    (1, True, "缺少 Luz-Design 模板选择记录", False),
])
def test_runtime_refusal_needs_the_expected_gate_reason(code, written, diagnostic, expected):
    assert audit._probe_outcome("missing_template", code, written, diagnostic)["passed"] is expected


def test_reviewed_machine_index_still_requires_exact_template(tmp_path, monkeypatch):
    scripts = tmp_path / "Luz-Project" / "scripts"
    scripts.mkdir(parents=True)
    target = scripts / "project_summary.py"
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    entry = audit.EntryPoint("luz-project", "scripts/project_summary.py", "render_summary", "reading-html",
                             research_required=False, research_exemption_reason="machine ledger only")
    target.write_text("def render_summary():\n    target.write_text('index')\n", encoding="utf-8")
    result = audit._audit_entry(entry)
    assert not result["crawl_gate"] and result["write_before_gate"]
    assert any("模板" in error for error in result["errors"])
    target.write_text("def render_summary():\n    require_selected(session, caller, stage, target, 'reading-html')\n    target.write_text('index')\n", encoding="utf-8")
    result = audit._audit_entry(entry)
    assert not result["errors"]


def test_research_exemption_cannot_be_undocumented(tmp_path, monkeypatch):
    scripts = tmp_path / "Luz-Project" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "project_summary.py").write_text("def render_summary():\n    require_selected(session, caller, stage, target, 'reading-html')\n    target.write_text('index')\n", encoding="utf-8")
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    result = audit._audit_entry(audit.EntryPoint("luz-project", "scripts/project_summary.py", "render_summary",
                                                "reading-html", research_required=False))
    assert any("研究豁免" in error for error in result["errors"])


def test_unreviewed_same_named_ui_wrapper_cannot_count(tmp_path, monkeypatch):
    result = inspect_writer(tmp_path, monkeypatch, """def verify_ui_source(package):
    return {'passed': True}

def main():
    require_session_preflight(session)
    require_selected(session, caller, stage, target, 'ui-source-output')
    verify_ui_source(package)
    target.write_bytes(b'ui')
""", ui=True)
    assert not result["source_audit_detected"]


def test_only_reviewed_machine_index_has_research_exemption():
    exempt = [entry for entry in audit.ENTRY_POINTS if entry.formal and not entry.research_required]
    assert [(entry.skill, entry.file, entry.function) for entry in exempt] == [
        ("luz-project", "scripts/project_summary.py", "render_summary")]
    assert all(entry.research_exemption_reason for entry in exempt)
