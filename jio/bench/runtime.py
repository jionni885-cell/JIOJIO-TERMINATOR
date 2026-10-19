"""Micro-benchmark local du coût de vérification, sans fournisseur de modèle."""

from __future__ import annotations

import statistics
import subprocess
import sys
import time
from typing import Any

from ..verify.executable import Sandbox


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)]


def mesurer_runtime(runs: int = 5) -> dict[str, Any]:
    """Compare l'invocation Python nue au runner JIO pour deux petites charges locales.

    C'est un diagnostic de la machine et du runner, pas une mesure du modèle ni un benchmark de
    qualité. Les commandes sont du code fixe embarqué, sans shell, sans écriture et sans réseau.
    """
    if not 1 <= runs <= 100:
        raise ValueError("runs doit être compris entre 1 et 100")
    workloads = {
        "noop": "pass",
        "stdout_8k": "print('x' * 8192)",
    }
    sandbox = Sandbox(timeout=10)
    details: dict[str, Any] = {}
    for name, source in workloads.items():
        baseline_ms: list[float] = []
        jio_ms: list[float] = []
        for _ in range(runs):
            argv = [sys.executable, "-c", source]
            start = time.perf_counter()
            direct = subprocess.run(argv, capture_output=True, timeout=10, check=False)
            baseline_ms.append((time.perf_counter() - start) * 1000)
            if direct.returncode != 0:
                raise RuntimeError(
                    f"baseline {name} en echec : code {direct.returncode}"
                )

            start = time.perf_counter()
            checked = sandbox.run_command(argv, tag=f"perf-{name}")
            jio_ms.append((time.perf_counter() - start) * 1000)
            if not checked.ok:
                raise RuntimeError(
                    f"Sandbox JIO {name} en echec : {checked.stderr[-300:]}"
                )
        base_median = statistics.median(baseline_ms)
        jio_median = statistics.median(jio_ms)
        details[name] = {
            "runs": runs,
            "baseline_ms_median": round(base_median, 3),
            "baseline_ms_p95": round(_p95(baseline_ms), 3),
            "jio_ms_median": round(jio_median, 3),
            "jio_ms_p95": round(_p95(jio_ms), 3),
            "runner_overhead_ms": round(max(0.0, jio_median - base_median), 3),
            "runner_overhead_percent": round((jio_median / base_median - 1) * 100, 1)
            if base_median
            else None,
        }
    return {
        "schema_version": 1,
        "kind": "local_runner_microbenchmark",
        "model_calls": 0,
        "warning": "Mesure locale indicative ; ne mesure ni qualité du modèle ni efficacité globale de JIO.",
        "workloads": details,
    }


def rendre_runtime(report: dict[str, Any]) -> str:
    lines = ["Performance locale du runner JIO (aucun appel modèle)"]
    for name, item in report["workloads"].items():
        overhead = item["runner_overhead_percent"]
        pct = "n/a" if overhead is None else f"{overhead:+.1f}%"
        lines.append(
            f"  {name:<10} direct {item['baseline_ms_median']:.3f} ms · "
            f"JIO {item['jio_ms_median']:.3f} ms · surcoût {pct} "
            f"(p95 JIO {item['jio_ms_p95']:.3f} ms)"
        )
    lines.append(
        "  Indicatif seulement : le modèle, le réseau et les missions complètes ne sont pas mesurés."
    )
    return "\n".join(lines)
