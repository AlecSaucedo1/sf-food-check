import unittest
from backend.normalize import normalize_row, normalize_status
from backend.taxonomy import categorize

class NormalizeTests(unittest.TestCase):
    def test_aliases(self):
        row = {"Permit Number":"123", "Facility Name":"Cafe", "Inspection Date":"08/01/2026", "Facility Rating Status":"Conditional Pass", "Violation Codes":"A;B", "Location":{"coordinates":[-122.42,37.77]}}
        n = normalize_row(row)
        self.assertEqual(n["permit_number"], "123")
        self.assertEqual(n["dba"], "Cafe")
        self.assertEqual(n["inspection_date"], "2026-08-01")
        self.assertEqual(n["facility_rating_status"], "Conditional Pass")
        self.assertEqual(n["violation_codes"], ["A","B"])
        self.assertAlmostEqual(n["latitude"], 37.77)
    def test_status(self):
        self.assertEqual(normalize_status("permit closure"), "Closure")
        self.assertEqual(normalize_status("PASS"), "Pass")
    def test_taxonomy(self):
        t = categorize("Evidence of rodent activity")
        self.assertEqual(t["normalized_category"], "Pests")

if __name__ == '__main__':
    unittest.main()
