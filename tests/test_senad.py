"""آزمون‌های منطق اصلی سیستم سند."""
import os
import tempfile
import unittest

os.environ["SENAD_INSTANCE_DIR"] = tempfile.mkdtemp()
os.environ["SENAD_DB_PATH"] = os.path.join(os.environ["SENAD_INSTANCE_DIR"], "test.db")

from senad_app import auth, config, db, services  # noqa: E402


class TestDates(unittest.TestCase):
    def test_parse_jalali(self):
        d = services.parse_jalali("1405/07/18")
        self.assertEqual((d.year, d.month, d.day), (1405, 7, 18))

    def test_parse_jalali_persian_digits(self):
        d = services.parse_jalali("۱۴۰۵/۰۷/۱۸")
        self.assertEqual(d.year, 1405)

    def test_date_key(self):
        self.assertEqual(services.date_key("1405/07/18"), 14050718)


class TestItems(unittest.TestCase):
    def test_max_items(self):
        items = [{"title": f"x{i}", "insurance": 0, "tax": 0, "amount": 1} for i in range(16)]
        with self.assertRaises(ValueError):
            services.validate_items(items)

    def test_empty_rows_skipped(self):
        cleaned = services.validate_items([
            {"title": "", "amount": 5},
            {"title": "خرید کابل", "item_date": "1405/01/01", "insurance": 10, "tax": 5, "amount": 100},
        ])
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0]["row_no"], 1)

    def test_totals(self):
        t = services.doc_totals([
            {"insurance": 10, "tax": 5, "amount": 100},
            {"insurance": 0, "tax": 0, "amount": 50},
        ])
        self.assertEqual(t["total"], 165)

    def test_overflow_warning(self):
        warns = services.overflow_warnings([{"row_no": 1, "title": "x" * 80}])
        self.assertTrue(warns)


class TestNumbering(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = auth.create_user("u" + os.urandom(4).hex(), "secret12", "test", "admin")

    def _branch(self, code: str, name: str):
        try:
            services.add_branch(code, name)
        except Exception:
            pass
        return next(b for b in services.list_branches() if b["code"] == code)

    def test_number_format_and_reset(self):
        branch = self._branch("45", "شهید کاوه")
        items = [{"title": "ق", "item_date": "1405/07/18", "insurance": 0, "tax": 0, "amount": 100}]
        d1 = services.create_document(self.user_id, branch["id"], "1405/07/18", "", items)
        n1 = services.finalize_document(d1, self.user_id)
        self.assertEqual(n1, "45-1405-0001")

        d2 = services.create_document(self.user_id, branch["id"], "1405/08/01", "", items)
        n2 = services.finalize_document(d2, self.user_id)
        self.assertEqual(n2, "45-1405-0002")

        # سال جدید ← ریست شماره
        d3 = services.create_document(self.user_id, branch["id"], "1406/01/05", "", items)
        n3 = services.finalize_document(d3, self.user_id)
        self.assertEqual(n3, "45-1406-0001")

    def test_void_keeps_number(self):
        branch = self._branch("77", "شمال")
        items = [{"title": "ق", "item_date": "1405/07/18", "insurance": 0, "tax": 0, "amount": 100}]
        d1 = services.create_document(self.user_id, branch["id"], "1405/07/18", "", items)
        n1 = services.finalize_document(d1, self.user_id)
        self.assertEqual(n1, "77-1405-0001")
        services.void_document(d1, self.user_id, "خطای ثبت")
        d2 = services.create_document(self.user_id, branch["id"], "1405/07/19", "", items)
        n2 = services.finalize_document(d2, self.user_id)
        self.assertEqual(n2, "77-1405-0002")  # شماره سند باطل‌شده دوباره استفاده نمی‌شود


class TestTanakhah(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = auth.create_user("t" + os.urandom(4).hex(), "secret12", "test", "admin")
        try:
            services.add_branch("12", "مرکزی")
        except Exception:
            pass
        self.branch = next(b for b in services.list_branches() if b["code"] == "12")

    def test_balance_formula(self):
        services.add_tanakhah(self.user_id, self.branch["id"], "1405/01/01", 1_000_000, "واریز اول")
        items = [{"title": "ق", "item_date": "1405/01/02", "insurance": 100, "tax": 50, "amount": 850}]
        d = services.create_document(self.user_id, self.branch["id"], "1405/01/02", "", items)
        services.finalize_document(d, self.user_id)
        s = services.tanakhah_summary(self.branch["id"])
        self.assertEqual(s["total_in"], 1_000_000)
        self.assertEqual(s["total_docs"], 1_000)
        self.assertEqual(s["balance"], 999_000)
        self.assertEqual(s["last_date"], "1405/01/01")


class TestPermissions(unittest.TestCase):
    def test_roles(self):
        self.assertTrue(config.can("admin", "void"))
        self.assertFalse(config.can("karperdaz", "void"))
        self.assertFalse(config.can("viewer", "create"))
        self.assertTrue(config.can("supervisor", "edit_final"))


if __name__ == "__main__":
    unittest.main()
