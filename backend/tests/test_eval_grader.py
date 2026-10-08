import unittest

from eval.contract import format_output, route_for
from eval.grader import check_grounding, figures, grade, parse_strict

GOOD = format_output("hazard_report", "high", "escalate_to_human",
                     "Phone Health and Safety immediately, then submit a report within 24 hours.")
EX = {"classification": "hazard_report", "urgency": "high", "resolution": "escalate_to_human"}
CLAUSE = ["Report serious hazards by phone, then submit a written hazard report within 24 hours."]


class ParseStrict(unittest.TestCase):
    def test_well_formed(self):
        r = parse_strict(GOOD)
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.fields["urgency"], "high")

    def test_one_trailing_newline_is_tolerated_but_not_two(self):
        self.assertTrue(parse_strict(GOOD + "\n").ok)
        self.assertFalse(parse_strict(GOOD + "\n\n").ok)

    def test_rejects_malformed(self):
        cases = {
            "extra line": GOOD + "\nNote: hello",
            "missing line": "\n".join(GOOD.split("\n")[:3]),
            "wrong case": GOOD.replace("hazard_report", "Hazard_Report"),
            "capitalised urgency": GOOD.replace("Urgency: high", "Urgency: High"),
            "unknown enum": GOOD.replace("escalate_to_human", "call_someone"),
            "wrong label": GOOD.replace("Summary:", "Answer:"),
            "empty summary": GOOD.split("Summary:")[0] + "Summary: ",
            "leading space in value": GOOD.replace("Urgency: high", "Urgency:  high"),
            "three sentences": GOOD.rsplit("Summary:", 1)[0] + "Summary: One. Two. Three.",
            "no terminal punctuation": GOOD.rstrip("."),
            "crlf": GOOD.replace("\n", "\r\n"),
            "prose preamble": "Sure! " + GOOD,
        }
        for label, text in cases.items():
            with self.subTest(label):
                self.assertFalse(parse_strict(text).ok, label)

    def test_truncation_flag_fails(self):
        self.assertFalse(parse_strict(GOOD, truncated=True).ok)

    def test_non_string(self):
        self.assertFalse(parse_strict(None).ok)

    def test_labels_only_contract(self):
        three = format_output("complaint", "low", "answer_from_policy")
        self.assertTrue(parse_strict(three, "labels_only").ok)
        self.assertFalse(parse_strict(three, "full").ok)
        self.assertFalse(parse_strict(GOOD, "labels_only").ok)


class Grounding(unittest.TestCase):
    def test_figures_digits_words_and_canonical_form(self):
        self.assertEqual(figures("up to 20 days, or twenty"), {"20"})
        self.assertEqual(figures("someone should contact one adviser"), set())  # 'one' excluded
        self.assertEqual(figures("5.5 days"), {"5.5"})
        self.assertEqual(figures("08:30"), {"8", "30"})

    def test_invented_figure_detected(self):
        self.assertEqual(check_grounding("You have 30 days.", ["You have 20 days."], False), ["30"])

    def test_supported_figure_ok(self):
        self.assertEqual(check_grounding("You have 20 days.", ["You have 20 days."], False), [])

    def test_abstention_allows_no_figures(self):
        self.assertEqual(check_grounding("Refer to HR.", ["20 days"], True), [])
        self.assertEqual(check_grounding("About 20 days.", ["20 days"], True), ["20"])


class Grade(unittest.TestCase):
    def test_perfect(self):
        g = grade(GOOD, EX, CLAUSE)
        self.assertTrue(g["pass"])
        self.assertEqual(g["route"], "health_safety")
        self.assertFalse(g["critical_misroute"] or g["under_urgency"])

    def test_invented_figure_fails_pass_but_not_format(self):
        bad = GOOD.replace("24 hours", "48 hours")
        g = grade(bad, EX, CLAUSE)
        self.assertTrue(g["format_ok"])
        self.assertFalse(g["grounding_ok"])
        self.assertFalse(g["pass"])
        self.assertEqual(g["invented_figures"], ["48"])

    def test_critical_misroute_and_under_urgency(self):
        g = grade(format_output("leave_policy", "low", "answer_from_policy", "Ok."), EX, CLAUSE)
        self.assertTrue(g["critical_misroute"])
        self.assertTrue(g["under_urgency"])
        self.assertEqual(g["urgency_abs_err"], 2)

    def test_unparseable_on_costly_row_counts_as_miss(self):
        g = grade("garbage", EX, CLAUSE)
        self.assertFalse(g["format_ok"])
        self.assertTrue(g["critical_misroute"])
        self.assertTrue(g["under_urgency"])

    def test_non_costly_gold_never_counts_as_misroute(self):
        ex = {"classification": "leave_policy", "urgency": "low", "resolution": "answer_from_policy"}
        g = grade("garbage", ex, CLAUSE)
        self.assertFalse(g["critical_misroute"])
        self.assertFalse(g["under_urgency"])

    def test_abstention_violation(self):
        ex = EX | {"abstention": True, "resolution": "escalate_to_human"}
        g = grade(format_output("hazard_report", "high", "answer_from_policy", "Within 24 hours."), ex, CLAUSE)
        self.assertTrue(g["abstention_violation"])

    def test_route_table_covers_all_classes(self):
        from eval.contract import CLASSES
        for c in CLASSES:
            self.assertIsNotNone(route_for(c), c)


if __name__ == "__main__":
    unittest.main()
