import unittest

from eval.metrics import macro_f1
from eval.stats import mcnemar_exact, paired_bootstrap, quadratic_weighted_kappa, wilson

L = ("low", "medium", "high")


class Stats(unittest.TestCase):
    def test_qwk_perfect_and_chance(self):
        y = ["low", "medium", "high", "low", "medium", "high"]
        self.assertAlmostEqual(quadratic_weighted_kappa(y, y, L), 1.0)
        self.assertAlmostEqual(quadratic_weighted_kappa(y, ["low"] * 6, L), 0.0)

    def test_qwk_penalises_far_errors_more(self):
        y = ["low", "medium", "high", "low", "medium", "high"]
        near = ["medium", "medium", "high", "low", "medium", "medium"]
        far = ["high", "medium", "high", "low", "medium", "low"]
        self.assertGreater(quadratic_weighted_kappa(y, near, L), quadratic_weighted_kappa(y, far, L))

    def test_qwk_undefined_cases(self):
        self.assertIsNone(quadratic_weighted_kappa([], [], L))

    def test_wilson(self):
        lo, hi = wilson(50, 100)
        self.assertAlmostEqual(lo, 0.404, places=2)
        self.assertAlmostEqual(hi, 0.596, places=2)
        self.assertEqual(wilson(0, 0), (0.0, 1.0))

    def test_mcnemar(self):
        self.assertEqual(mcnemar_exact([True, False], [True, False])[2], 1.0)
        b, a, p = mcnemar_exact([True] * 10, [False] * 10)
        self.assertEqual((b, a), (0, 10))
        self.assertAlmostEqual(p, 2 / 1024)

    def test_paired_bootstrap_is_seeded_and_brackets_the_mean(self):
        a = [1.0] * 30 + [0.0] * 10
        b = [1.0] * 25 + [0.0] * 15
        r1, r2 = paired_bootstrap(a, b, 2000, 7), paired_bootstrap(a, b, 2000, 7)
        self.assertEqual(r1, r2)
        d, lo, hi = r1
        self.assertAlmostEqual(d, 0.125)
        self.assertLessEqual(lo, d)
        self.assertGreaterEqual(hi, d)

    def test_macro_f1_invalid_prediction_is_a_miss(self):
        self.assertAlmostEqual(macro_f1(["a", "b"], ["a", "b"], ("a", "b")), 1.0)
        self.assertAlmostEqual(macro_f1(["a", "b"], ["a", None], ("a", "b")), 0.5)


if __name__ == "__main__":
    unittest.main()
