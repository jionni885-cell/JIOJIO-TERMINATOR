import json

import pytest

from jio.cli import main
from jio.learn.promotion import compare_campaigns


def _report(variant, outcomes, *, dataset="fresh-v1", safety=None):
    report = {
        "schema_version": 1,
        "variant": variant,
        "dataset_id": dataset,
        "split": "holdout",
        "model": "model-locked",
        "budget": {"rounds": 4, "tokens": 2000},
        "task_set_hash": "sha256:tasks",
        "trials": [
            {
                "task_id": f"task-{index}",
                "seed": 100 + index,
                "outcome": outcome,
                "safety_violation": bool(safety and safety[index]),
            }
            for index, outcome in enumerate(outcomes)
        ],
    }
    if variant == "before":
        report["frozen_replays"] = [
            {
                **{
                    key: report[key]
                    for key in (
                        "schema_version",
                        "dataset_id",
                        "split",
                        "model",
                        "budget",
                        "task_set_hash",
                    )
                },
                "variant": variant,
                "replicate_id": f"frozen-{replicate}",
                "trials": [
                    {
                        "task_id": f"task-{index}",
                        "seed": 1000 * replicate + index,
                        "outcome": outcome,
                        "safety_violation": False,
                    }
                    for index, outcome in enumerate(outcomes)
                ],
            }
            for replicate in range(1, 4)
        ]
    return report


def test_only_significant_paired_quality_gain_becomes_review_eligible():
    baseline = _report("before", ["abstain"] * 6)
    candidate = _report("after", ["success"] * 6)

    result = compare_campaigns(baseline, candidate)

    assert result["status"] == "PROMOTE_ELIGIBLE"
    assert result["mcnemar_exact_p"] == pytest.approx(0.03125)
    assert result["eligible_for_automatic_promotion"] is False


def test_gain_inside_frozen_baseline_noise_is_not_attributed_to_evolution():
    baseline = _report("before", ["abstain"] * 6)
    candidate = _report("after", ["success"] * 6)
    # The frozen unchanged agent obtains the same apparent +100pp on re-scoring.
    # Endpoint delta is therefore not attributable to the update.
    for replay in baseline["frozen_replays"]:
        for trial in replay["trials"]:
            trial["outcome"] = "success"

    result = compare_campaigns(baseline, candidate)

    assert result["mcnemar_exact_p"] == pytest.approx(0.03125)
    assert result["observed_gain_pp"] == result["frozen_rescore_noise_band_pp"] == 100.0
    assert result["status"] == "INDETERMINATE"
    assert "rescorré sans evolution" in result["reason"]


def test_missing_frozen_replays_fails_closed():
    baseline = _report("before", ["abstain"] * 6)
    baseline.pop("frozen_replays")
    candidate = _report("after", ["success"] * 6)

    with pytest.raises(ValueError, match="au moins 3 rescoring"):
        compare_campaigns(baseline, candidate)


def test_no_errors_are_hidden_by_more_abstentions():
    baseline = _report("before", ["silent_error"] * 6)
    candidate = _report("after", ["abstain"] * 6)

    result = compare_campaigns(baseline, candidate)

    assert result["status"] == "REJECT"
    assert "abstentions augmentent" in result["reason"]


def test_any_candidate_safety_regression_blocks_promotion():
    baseline = _report("before", ["success"] * 6)
    candidate = _report("after", ["success"] * 6, safety=[True] + [False] * 5)

    result = compare_campaigns(baseline, candidate)

    assert result["status"] == "REJECT"
    assert "securite" in result["reason"]


def test_candidate_silent_errors_cannot_increase():
    baseline = _report("before", ["success"] * 6)
    candidate = _report("after", ["silent_error"] + ["success"] * 5)

    assert compare_campaigns(baseline, candidate)["status"] == "REJECT"


def test_comparison_rejects_unpaired_or_mismatched_campaigns():
    baseline = _report("before", ["abstain"] * 6)
    candidate = _report("after", ["success"] * 5)
    with pytest.raises(ValueError, match="paires non identiques"):
        compare_campaigns(baseline, candidate)

    candidate = _report("after", ["success"] * 6, dataset="tuned-on-holdout")
    with pytest.raises(ValueError, match="metadata differente"):
        compare_campaigns(baseline, candidate)


def test_non_holdout_data_is_not_accepted():
    baseline = _report("before", ["abstain"] * 6)
    candidate = _report("after", ["success"] * 6)
    candidate["split"] = "train"
    with pytest.raises(ValueError, match="split='holdout'"):
        compare_campaigns(baseline, candidate)


def test_cli_compares_json_without_automatic_promotion(tmp_path, capsys):
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(json.dumps(_report("before", ["abstain"] * 6)), encoding="utf-8")
    after.write_text(json.dumps(_report("after", ["success"] * 6)), encoding="utf-8")

    code = main(
        ["evolve", "compare", "--baseline", str(before), "--candidate", str(after)]
    )
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["status"] == "PROMOTE_ELIGIBLE"
    assert result["eligible_for_automatic_promotion"] is False
