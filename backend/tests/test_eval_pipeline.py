import json
import os
import tempfile
import unittest

from eval.backends import make_backend
from eval.backends.controls import Keyword, Majority, Oracle
from eval.compare_rows import compare, load_preds, non_inferiority_verdict
from eval.contract import CLASSES, RESOLUTIONS, URGENCIES, gold_output, render_example
from eval.grader import grade, parse_strict
from eval.runner import load_corpus, load_jsonl, run, select_shots, write_outputs

FIX = os.path.join(os.path.dirname(__file__), "..", "eval", "fixtures")
ROWS = load_jsonl(os.path.join(FIX, "test_fixture.jsonl"))
TRAIN = load_jsonl(os.path.join(FIX, "train_fixture.jsonl"))
CORPUS = load_corpus(os.path.join(FIX, "policy_fixture.json"))
GATES = {"frozen": False, "format_min": 0.99, "classification_margin": 0.05, "resolution_margin": 0.05,
         "urgency_qwk_margin": None, "bootstrap_resamples": 500, "seed": 0}


class Fixtures(unittest.TestCase):
    def test_labels_and_clause_ids_valid(self):
        for r in ROWS + TRAIN:
            self.assertIn(r["classification"], CLASSES, r["row_id"])
            self.assertIn(r["urgency"], URGENCIES, r["row_id"])
            self.assertIn(r["resolution"], RESOLUTIONS, r["row_id"])
            for cid in r["clause_ids"] + r["gold_clause_ids"]:
                self.assertIn(cid, CORPUS, r["row_id"])

    def test_row_ids_unique_and_no_query_overlap_between_train_and_test(self):
        ids = [r["row_id"] for r in ROWS + TRAIN]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse({r["query"] for r in ROWS} & {r["query"] for r in TRAIN})

    def test_reference_outputs_pass_the_strict_grader_and_grounding(self):
        for r in ROWS + TRAIN:
            g = grade(gold_output(r), r, [CORPUS[c] for c in r["clause_ids"]])
            self.assertTrue(g["pass"], (r["row_id"], g["format_errors"], g["invented_figures"]))

    def test_abstention_rows_have_no_gold_clause_and_no_figures(self):
        for r in ROWS:
            if r["abstention"]:
                self.assertEqual(r["gold_clause_ids"], [], r["row_id"])
                self.assertNotEqual(r["resolution"], "answer_from_policy", r["row_id"])

    def test_every_class_and_urgency_present(self):
        self.assertEqual({r["classification"] for r in ROWS}, set(CLASSES))
        self.assertEqual({r["urgency"] for r in ROWS}, set(URGENCIES))

    def test_render_is_deterministic_and_contains_query_and_clauses(self):
        r = ROWS[0]
        s1, u1 = render_example(r, CORPUS)
        s2, u2 = render_example(r, CORPUS)
        self.assertEqual((s1, u1), (s2, u2))
        self.assertIn(r["query"], u1)
        for cid in r["clause_ids"]:
            self.assertIn(f"[{cid}]", u1)


class Pipeline(unittest.TestCase):
    def test_oracle_scores_perfect_only_with_permission(self):
        with self.assertRaises(PermissionError):
            run(Oracle(), ROWS, CORPUS)
        row, _ = run(Oracle(), ROWS, CORPUS, allow_gold=True)
        q = row["quality"]
        self.assertEqual(q["pass_rate"]["rate"], 1.0)
        self.assertEqual((q["critical_misroute"], q["under_urgency"]), (0, 0))
        self.assertAlmostEqual(q["urgency_qwk"], 1.0)

    def test_majority_control_is_poor_and_trips_safety_counts(self):
        row, _ = run(Majority(TRAIN), ROWS, CORPUS)
        q = row["quality"]
        self.assertEqual(q["format_pass"]["rate"], 1.0)
        self.assertLess(q["class_acc"]["rate"], 0.5)
        self.assertGreater(q["critical_misroute"], 0)

    def test_keyword_control_summary_copy_trips_abstention_check(self):
        row, _ = run(Keyword(), ROWS, CORPUS)
        self.assertGreater(row["quality"]["abstention_violations"], 0)

    def test_labels_only_contract_has_no_grounding(self):
        class Labels(Oracle):
            def generate(self, *a, example=None, **k):
                from eval.backends import Generation
                from eval.contract import format_output
                return Generation(format_output(example["classification"], example["urgency"], example["resolution"]))
        row, _ = run(Labels(), ROWS, CORPUS, contract="labels_only", allow_gold=True)
        self.assertEqual(row["quality"]["pass_rate"]["rate"], 1.0)
        self.assertNotIn("grounding_clean", row["quality"])

    def test_malformed_backend_scores_zero_format(self):
        class Junk(Majority):
            def generate(self, *a, **k):
                from eval.backends import Generation
                return Generation("I think this is about leave.")
        row, preds = run(Junk(TRAIN), ROWS, CORPUS)
        self.assertEqual(row["quality"]["format_pass"]["rate"], 0.0)
        self.assertEqual(row["quality"]["critical_misroute"], sum(r["classification"] in ("hazard_report", "complaint") for r in ROWS))

    def test_few_shot_selection_is_deterministic_and_class_diverse(self):
        a, b = select_shots(TRAIN, CORPUS, 3), select_shots(TRAIN, CORPUS, 3)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 3)
        for _, answer in a:
            self.assertTrue(parse_strict(answer).ok)
        self.assertEqual(select_shots(TRAIN, CORPUS, 0), [])

    def test_unimplemented_backends_fail_loudly(self):
        for kind in ("hf", "onnx", "ctranslate2"):
            with self.assertRaises(NotImplementedError):
                make_backend(kind + ":x")
        with self.assertRaises(ValueError):
            make_backend("nope")

    def test_outputs_round_trip_and_compare(self):
        row_o, preds_o = run(Oracle(), ROWS, CORPUS, allow_gold=True)
        row_m, preds_m = run(Majority(TRAIN), ROWS, CORPUS)
        with tempfile.TemporaryDirectory() as d:
            write_outputs(row_o, preds_o, d, "o", {})
            write_outputs(row_m, preds_m, d, "m", {})
            o, m = load_preds(os.path.join(d, "o.preds.jsonl")), load_preds(os.path.join(d, "m.preds.jsonl"))
            self.assertTrue(os.path.exists(os.path.join(d, "o.json")))
        same = compare(o, o, GATES)
        self.assertEqual(same["primary"]["classification"]["diff"], 0.0)
        self.assertTrue(same["primary"]["critical_misroute"]["ok"])
        worse = compare(o, m, GATES)
        self.assertEqual(worse["primary"]["classification"]["verdict"], "inferior")
        self.assertFalse(worse["primary"]["critical_misroute"]["ok"])
        self.assertFalse(worse["frozen"])
        self.assertEqual(compare(o, m, GATES), worse)  # seeded: identical on rerun


class Verdict(unittest.TestCase):
    def test_three_way(self):
        self.assertEqual(non_inferiority_verdict(0.0, -0.03, 0.03, 0.05), "non-inferior")
        self.assertEqual(non_inferiority_verdict(-0.08, -0.12, -0.04, 0.05), "inferior")
        self.assertEqual(non_inferiority_verdict(-0.03, -0.09, 0.03, 0.05), "inconclusive")


if __name__ == "__main__":
    unittest.main()
