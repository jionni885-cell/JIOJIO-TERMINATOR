import os
import sys
import time
from pathlib import Path

import pytest

from jio.verify.executable import MAX_CAPTURE_BYTES, Sandbox


def test_timeout_preserves_output_and_reports_timeout():
    result = Sandbox(timeout=0.1).run_command(
        [
            sys.executable,
            "-c",
            "import time; print('started', flush=True); time.sleep(5)",
        ]
    )

    assert result.timed_out
    assert result.exit_code == 124
    assert "started" in result.stdout
    assert "TIMEOUT" in result.stderr


@pytest.mark.skipif(os.name != "posix", reason="la terminaison de groupe est POSIX")
def test_timeout_kills_process_descendants(tmp_path: Path):
    marker = tmp_path / "descendant-survivant"
    child = (
        "import pathlib,time; time.sleep(0.7); "
        f"pathlib.Path({str(marker)!r}).write_text('survivant')"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(10)"
    )

    result = Sandbox(timeout=0.2).run_command([sys.executable, "-c", parent])
    time.sleep(0.8)

    assert result.timed_out
    assert not marker.exists(), (
        "un processus enfant a continue apres le verdict de timeout"
    )


def test_large_output_is_spooled_and_offloaded(tmp_path: Path):
    offload = tmp_path / "outputs"
    result = Sandbox(timeout=5, offload_dir=offload).run_command(
        [sys.executable, "-c", "print('x' * 50000)"], tag="large"
    )

    assert result.exit_code == 0
    assert "offloades vers" in result.stdout
    logs = list(offload.glob("large-out-*.log"))
    assert len(logs) == 1
    assert logs[0].stat().st_size > 50_000


def test_output_flood_is_capped_and_never_reported_as_success():
    result = Sandbox(timeout=5).run_command(
        [sys.executable, "-c", "import os; os.write(1, b'x' * 10000000)"]
    )

    assert result.output_limited
    assert result.exit_code == 125
    assert "OUTPUT_LIMIT" in result.stderr
    assert len(result.stdout.encode("utf-8")) <= MAX_CAPTURE_BYTES
