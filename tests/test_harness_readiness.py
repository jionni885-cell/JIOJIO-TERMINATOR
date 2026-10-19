import json
import sys

from jio.cli import main
from jio.harness import inspect_harness, run_verification_commands, to_json


def test_inspect_harness_reports_concrete_findings(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Instructions\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n[tool.pytest.ini_options]\ntestpaths = ['tests']\n",
        encoding="utf-8",
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_sample.py").write_text("def test_ok(): pass\n", encoding="utf-8")

    report = inspect_harness(tmp_path)

    assert report["schema_version"] == 1
    assert 0 <= report["score"] <= 100
    assert report["summary"]["warnings"] == sum(
        item["status"] == "warning" for item in report["findings"]
    )
    assert report["summary"]["test_files"] == 1
    assert {item["id"] for item in report["findings"]} == {
        "instructions",
        "tests",
        "project_config",
        "verification_commands",
        "tools",
    }
    assert report["summary"]["verification_commands"] == ["python -m pytest"]
    tools = next(item for item in report["findings"] if item["id"] == "tools")
    assert "pytest=oui" in tools["message"]
    assert json.loads(to_json(report))["score"] == report["score"]


def test_harness_detects_but_never_runs_project_test_scripts(tmp_path):
    marker = tmp_path / "must-not-exist"
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": f"touch {marker}"}}), encoding="utf-8"
    )

    report = inspect_harness(tmp_path)

    assert report["summary"]["verification_commands"] == ["npm test"]
    assert not marker.exists()


def test_opt_in_runtime_checks_use_only_fixed_argv_and_report_failures(
    tmp_path, monkeypatch
):
    from jio import harness
    from jio.verify.executable import SandboxResult

    observed = []

    class FakeSandbox:
        def __init__(self, *, timeout, workdir):
            assert timeout == 7
            assert workdir != tmp_path.resolve()
            assert (workdir / "sentinel").read_text(encoding="utf-8") == "original"
            self.workdir = workdir

        def run_command(self, argv, *, cwd, tag):
            assert cwd == self.workdir
            (cwd / "test-side-effect").write_text("only in copy", encoding="utf-8")
            observed.append((argv[:], cwd, tag))
            return SandboxResult(1, "failed test", "assertion", 0.1)

    (tmp_path / "sentinel").write_text("original", encoding="utf-8")
    monkeypatch.setattr(harness, "Sandbox", FakeSandbox)
    monkeypatch.setattr(harness.shutil, "which", lambda name: f"/fixed/{name}")
    report = {"summary": {"verification_commands": ["python -m pytest"]}}

    results = run_verification_commands(report, tmp_path, timeout=7)

    assert observed[0][0] == [sys.executable, "-m", "pytest"]
    assert observed[0][2] == "harness-check"
    assert results[0]["status"] == "failed"
    assert not (tmp_path / "test-side-effect").exists()
    assert "touch" not in observed[0][0]


def test_runtime_check_refuses_symlinks_to_protect_original_paths(tmp_path):
    import pytest

    outside = tmp_path.parent / "outside-test-target"
    outside.write_text("do not follow", encoding="utf-8")
    try:
        (tmp_path / "escape-link").symlink_to(outside)
    except OSError:
        pytest.skip("creation de lien symbolique non autorisee")

    with pytest.raises(ValueError, match="lien symbolique"):
        run_verification_commands({"summary": {"verification_commands": []}}, tmp_path)


def test_runtime_check_timeout_is_bounded(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="1 et 900"):
        run_verification_commands({"summary": {}}, tmp_path, timeout=901)


def test_cli_run_checks_executes_detected_pytest_and_returns_json(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = ['tests']\n", encoding="utf-8"
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_pass.py").write_text(
        "def test_pass(): assert 2 + 2 == 4\n", encoding="utf-8"
    )

    code = main(
        [
            "harness",
            "--root",
            str(tmp_path),
            "--run-checks",
            "--json",
            "--timeout",
            "20",
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert code == 0
    assert report["verification_runs"][0]["command"] == "python -m pytest"
    assert report["verification_runs"][0]["status"] == "passed"
    assert "n'isole pas le systeme" in report["verification_warning"]


def test_instruction_budget_is_actionable(tmp_path):
    (tmp_path / "AGENTS.md").write_text("ligne\n" * 4, encoding="utf-8")
    report = inspect_harness(tmp_path, instruction_budget=2)
    finding = next(
        item for item in report["findings"] if item["id"] == "instruction_budget"
    )
    assert finding["status"] == "warning"
    assert finding["recommendation"]


def test_cli_harness_json_and_strict_exit(tmp_path, capsys):
    assert main(["harness", "--root", str(tmp_path), "--json"]) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["schema_version"] == 1
    assert main(["harness", "--root", str(tmp_path), "--strict"]) == 1
