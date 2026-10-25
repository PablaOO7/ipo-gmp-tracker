import unittest
from unittest.mock import Mock, patch

from collector.collect import inspect_source


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


if __name__ == "__main__":
    unittest.main()
