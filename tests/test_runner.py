"""Unit tests — runner module, with bumblebee subprocess mocked."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


runner = _load("bb_runner", _PLUGIN_ROOT / "lib" / "runner.py")
findings = _load("bb_findings", _PLUGIN_ROOT / "lib" / "findings.py")


def test_find_binary_returns_path_or_none():
    result = runner.find_binary()
    assert result is None or isinstance(result, str)


def test_run_scan_raises_when_binary_missing():
    with mock.patch.object(runner, "find_binary", return_value=None):
        with pytest.raises(runner.BumblebeeNotInstalled):
            runner.run_scan(profile="baseline", exposure_catalog="/tmp/cat")


def test_run_scan_findings_only_requires_catalog():
    with mock.patch.object(runner, "find_binary", return_value="/fake/bumblebee"):
        with pytest.raises(ValueError, match="exposure_catalog"):
            runner.run_scan(profile="baseline", findings_only=True)


def test_run_scan_parses_ndjson_stdout():
    fake_stdout = (
        '{"record_type":"finding","ecosystem":"npm","package_name":"evil"}\n'
        '{"record_type":"finding","ecosystem":"pypi","package_name":"badpkg"}\n'
        '{"record_type":"scan_summary","status":"complete","files_considered":100}\n'
    )
    fake_result = mock.MagicMock(stdout=fake_stdout, stderr="", returncode=0)

    with mock.patch.object(runner, "find_binary", return_value="/fake/bumblebee"), \
         mock.patch.object(runner.subprocess, "run", return_value=fake_result):
        records, summary, _ = runner.run_scan(
            profile="baseline",
            exposure_catalog="/tmp/cat",
            findings_only=True,
        )

    assert len(records) == 2
    assert all(r["record_type"] == "finding" for r in records)
    assert summary["status"] == "complete"
    assert summary["files_considered"] == 100


def test_run_scan_command_construction():
    fake_result = mock.MagicMock(stdout="", stderr="", returncode=0)

    with mock.patch.object(runner, "find_binary", return_value="/fake/bumblebee"), \
         mock.patch.object(runner.subprocess, "run", return_value=fake_result) as mock_run:
        runner.run_scan(
            profile="project",
            roots=["/home/x/code", "/home/x/work"],
            ecosystems=["npm", "pypi"],
            exposure_catalog="/tmp/catalogs",
            findings_only=True,
            max_duration="10m",
        )

    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "/fake/bumblebee"
    assert "scan" in cmd
    assert "--profile" in cmd and "project" in cmd
    assert "--findings-only" in cmd
    assert "--exposure-catalog" in cmd and "/tmp/catalogs" in cmd
    assert cmd.count("--root") == 2
    assert "/home/x/code" in cmd and "/home/x/work" in cmd
    assert "npm,pypi" in cmd
    assert "--max-duration" in cmd and "10m" in cmd


def test_summarize_findings_empty():
    assert findings.summarize_findings([]) == {
        "count": 0, "by_ecosystem": {}, "by_advisory": {}, "examples": [],
    }


def test_summarize_findings_groups_by_ecosystem_and_advisory():
    recs = [
        {"record_type": "finding", "ecosystem": "npm", "package_name": "a",
         "exposure": {"advisory_id": "GHSA-1"}},
        {"record_type": "finding", "ecosystem": "npm", "package_name": "b",
         "exposure": {"advisory_id": "GHSA-1"}},
        {"record_type": "finding", "ecosystem": "pypi", "package_name": "c",
         "exposure": {"advisory_id": "GHSA-2"}},
        {"record_type": "package", "ecosystem": "npm"},  # non-finding, ignored
    ]
    s = findings.summarize_findings(recs)
    assert s["count"] == 3
    assert s["by_ecosystem"] == {"npm": 2, "pypi": 1}
    assert s["by_advisory"] == {"GHSA-1": 2, "GHSA-2": 1}
    assert len(s["examples"]) == 3


def test_summarize_findings_truncates_examples_at_10():
    recs = [
        {"record_type": "finding", "ecosystem": "npm", "package_name": f"p{i}",
         "exposure": {"advisory_id": "GHSA-X"}}
        for i in range(15)
    ]
    s = findings.summarize_findings(recs)
    assert s["count"] == 15
    assert len(s["examples"]) == 10
    assert s["truncated"] is True
