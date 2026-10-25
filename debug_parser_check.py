from collector.source_ipowatch import extract_records

html = '''
<html>
  <body>
    <h2>Current Mainboard IPO GMP</h2>
    <table>
      <tr><td>Bombay Coated and Special Steels Upcoming</td><td>₹8</td><td>🟢</td><td>₹82</td><td>₹90 (6.10%)</td><td>29-2 Nov</td></tr>
    </table>
    <h2>Current SME IPO GMP</h2>
    <table>
      <tr><td>Antala Industries Upcoming</td><td>₹0</td><td>🟡</td><td>₹67</td><td>₹67 (0.00%)</td><td>29-2 Nov</td></tr>
    </table>
  </body>
</html>
'''
records = extract_records(html=html)
print('COUNT', len(records))
print('FIRST_NAME', records[0]['name'])
print('FIRST_CATEGORY', records[0]['category'])
print('FIRST_STATUS', records[0]['status'])
print('FIRST_GMP', records[0]['gmp'])
print('SECOND_CATEGORY', records[1]['category'])
