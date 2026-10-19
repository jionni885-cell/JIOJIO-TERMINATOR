import json

import pytest

from jio.bench.runtime import mesurer_runtime
from jio.cli import main


def test_runtime_benchmark_is_local_and_machine_readable():
    report = mesurer_runtime(1)

    assert report["schema_version"] == 1
    assert report["model_calls"] == 0
    assert set(report["workloads"]) == {"noop", "stdout_8k"}
    for result in report["workloads"].values():
        assert result["runs"] == 1
        assert result["baseline_ms_median"] > 0
        assert result["jio_ms_median"] > 0
        assert result["jio_ms_p95"] >= 0


def test_runtime_benchmark_rejects_unbounded_runs():
    with pytest.raises(ValueError, match="1 et 100"):
        mesurer_runtime(101)


def test_perf_cli_json(capsys):
    assert main(["perf", "--runs", "1", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["kind"] == "local_runner_microbenchmark"
