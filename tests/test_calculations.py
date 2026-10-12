import unittest

from dashboard_app.calculations import build_report
from dashboard_app.config import ACTUAL_TYPE, BUDGET_TYPE, PRIOR_ACTUAL_TYPE


class ReportCalculationTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            {
                "year": 1402,
                "month": 1,
                "section": "واردات",
                "service": "انبارداری",
                "unit": "تن",
                "record_type": PRIOR_ACTUAL_TYPE,
                "quantity": 100,
                "revenue_million_rial": 1000,
                "cost_million_rial": 600,
            },
            {
                "year": 1403,
                "month": 1,
                "section": "واردات",
                "service": "انبارداری",
                "unit": "تن",
                "record_type": BUDGET_TYPE,
                "quantity": 110,
                "revenue_million_rial": 1200,
                "cost_million_rial": 750,
            },
            {
                "year": 1403,
                "month": 1,
                "section": "واردات",
                "service": "انبارداری",
                "unit": "تن",
                "record_type": ACTUAL_TYPE,
                "quantity": 120,
                "revenue_million_rial": 1440,
                "cost_million_rial": 800,
            },
        ]

    def test_budget_yoy_and_profit_calculations(self):
        report = build_report(self.records, 1403, [1])
        row = report.iloc[0]
        self.assertAlmostEqual(row["quantity_attainment_pct"], 120 / 110 * 100)
        self.assertAlmostEqual(row["revenue_attainment_pct"], 1440 / 1200 * 100)
        self.assertAlmostEqual(row["actual_profit"], 640)
        self.assertAlmostEqual(row["budget_profit"], 450)
        self.assertAlmostEqual(row["profit_attainment_pct"], 640 / 450 * 100)
        self.assertAlmostEqual(row["quantity_variance_vs_prior"], 20)
        self.assertAlmostEqual(row["revenue_variance_vs_prior"], 440)
        self.assertAlmostEqual(row["revenue_growth_pct"], 44)

    def test_zero_budget_displays_no_attainment_percentage(self):
        records = [
            {
                "year": 1403,
                "month": 1,
                "section": "صادرات",
                "service": "بیمه",
                "unit": "میلیون ریال",
                "record_type": BUDGET_TYPE,
                "quantity": 0,
                "revenue_million_rial": 0,
                "cost_million_rial": 0,
            },
            {
                "year": 1403,
                "month": 1,
                "section": "صادرات",
                "service": "بیمه",
                "unit": "میلیون ریال",
                "record_type": ACTUAL_TYPE,
                "quantity": 10,
                "revenue_million_rial": 50,
                "cost_million_rial": 30,
            },
        ]
        report = build_report(records, 1403, [1])
        self.assertIsNone(report.iloc[0]["revenue_attainment_pct"])

    def test_average_duration_is_averaged_not_summed(self):
        records = []
        for month, value in ((1, 10), (2, 20)):
            records.append(
                {
                    "year": 1403,
                    "month": month,
                    "section": "واردات",
                    "service": "میانگین مدت ماندگاری کالا",
                    "unit": "روز",
                    "record_type": ACTUAL_TYPE,
                    "quantity": value,
                    "revenue_million_rial": 0,
                    "cost_million_rial": 0,
                }
            )
        report = build_report(records, 1403, [1, 2])
        self.assertAlmostEqual(report.iloc[0]["actual_quantity"], 15)


if __name__ == "__main__":
    unittest.main()
