import unittest
from unittest.mock import Mock, patch

from collector.collect import inspect_source
from collector.schema import normalize_record, validate_dataset
from collector.source_ipowatch import extract_records


class CollectorTests(unittest.TestCase):
    @patch("collector.collect.requests.get")
    def test_inspects_page_title_and_tables(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.text = """
        <html>
          <head><title>IPO Watch</title></head>
          <body>
            <table>
              <tr><th>IPO</th><th>GMP</th></tr>
              <tr><td>Example</td><td>Not a real quote</td></tr>
            </table>
          </body>
        </html>
        """
        response.raise_for_status.return_value = None
        response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_get.return_value = response

        result = inspect_source()

        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["page_title"], "IPO Watch")
        self.assertEqual(result["table_count"], 1)
        self.assertTrue(result["gmp_text_detected"])

    @patch("collector.collect.requests.get")
    def test_source_http_error_is_not_silenced(self, mock_get):
        response = Mock()
        response.raise_for_status.side_effect = RuntimeError("HTTP error")
        mock_get.return_value = response

        with self.assertRaises(RuntimeError):
            inspect_source()

    def test_schema_normalizes_valid_record(self):
        record = {
            "id": "example-ipo",
            "company": "Example IPO",
            "category": "sme",
            "status": "open",
            "issuePriceLow": 100,
            "issuePriceHigh": 110,
            "gmp": None,
            "gmpPercent": None,
            "gmpHistory": [],
            "openDate": "2026-11-01",
            "closeDate": "2026-11-07",
            "allotmentDate": None,
            "listingDate": "2026-11-10",
        }
        result = normalize_record(record)
        self.assertEqual(result["category"], "SME")
        self.assertEqual(result["status"], "Open")
        self.assertEqual(result["issuePriceLow"], 100)

    def test_schema_rejects_invalid_category(self):
        record = {
            "id": "bad-ipo",
            "company": "Bad IPO",
            "category": "junk",
            "status": "Upcoming",
            "issuePriceLow": 90,
            "issuePriceHigh": 100,
            "gmp": None,
            "gmpPercent": None,
            "gmpHistory": [],
            "openDate": "2026-11-01",
        }
        with self.assertRaises(ValueError):
            normalize_record(record)

    def test_validate_dataset_accepts_list(self):
        dataset = {
            "source": "https://ipowatch.in/",
            "updated_at": None,
            "data_state": "awaiting_first_successful_collection",
            "demo": False,
            "ipos": [{
                "id": "ipo-1",
                "company": "Example IPO",
                "category": "Mainboard",
                "status": "Upcoming",
                "issuePriceLow": 80,
                "issuePriceHigh": 90,
                "gmp": None,
                "gmpPercent": None,
                "gmpHistory": [],
                "openDate": "2026-11-01",
                "closeDate": "2026-11-04",
                "allotmentDate": None,
                "listingDate": "2026-11-10",
            }],
        }
        result = validate_dataset(dataset)
        self.assertEqual(result["ipos"][0]["id"], "ipo-1")

    def test_extract_records_parses_current_gmp_table(self):
        html = """
        <html>
          <body>
            <h2>Current Mainboard IPO GMP</h2>
            <table>
              <tr><th>Company</th><th>GMP</th><th>Potential</th><th>Issue Price</th><th>Expected Listing</th><th>Open/Close</th></tr>
              <tr><td>Bombay Coated and Special Steels Upcoming</td><td>₹8</td><td>🟢</td><td>₹82</td><td>₹90 (6.10%)</td><td>29-2 Nov</td></tr>
              <tr><td>M.K.Sons Fine Jewels Upcoming</td><td>₹8</td><td>🟢</td><td>₹162</td><td>₹170 (4.94%)</td><td>28-30 Oct</td></tr>
            </table>
            <h2>Current SME IPO GMP</h2>
            <table>
              <tr><td>Antala Industries Upcoming</td><td>₹0</td><td>🟡</td><td>₹67</td><td>₹67 (0.00%)</td><td>29-2 Nov</td></tr>
            </table>
          </body>
        </html>
        """
        records = extract_records(html=html)
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["company"], "Bombay Coated and Special Steels")
        self.assertEqual(records[0]["category"], "Mainboard")
        self.assertEqual(records[0]["status"], "Upcoming")
        self.assertEqual(records[0]["gmp"], 8)
        self.assertEqual(records[2]["category"], "SME")


if __name__ == "__main__":
    unittest.main()
