import csv
import unittest
from collections import Counter
from pathlib import Path

DEMO_PATH = Path(__file__).resolve().parents[1] / "data" / "demo_records.csv"
ACTUAL_TYPE = "عملکرد دوره جاری"
BUDGET_TYPE = "بودجه مصوب دوره"


class DemoDatasetTests(unittest.TestCase):
    def test_three_years_each_have_actual_and_budget_rows(self):
        with DEMO_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 288)
        self.assertEqual({int(row["year"]) for row in rows}, {1402, 1403, 1404})
        self.assertEqual({row["section"] for row in rows}, {"واردات", "صادرات"})
        counts = Counter((int(row["year"]), row["record_type"]) for row in rows)
        for year in (1402, 1403, 1404):
            self.assertEqual(counts[(year, ACTUAL_TYPE)], 48)
            self.assertEqual(counts[(year, BUDGET_TYPE)], 48)


if __name__ == "__main__":
    unittest.main()
