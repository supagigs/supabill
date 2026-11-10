from frappe.tests import UnitTestCase

from supabill.supabill import calc


class TestCalc(UnitTestCase):
	def test_invoice_number_format(self):
		self.assertEqual(calc.format_invoice_number("Supa/26-27/", 28, 3), "Supa/26-27/028")
		self.assertEqual(calc.format_invoice_number("INV-", 1234, 3), "INV-1234")

	def test_gst_return_period(self):
		self.assertEqual(calc.gst_return_period("2026-04-01"), "April - June 2026")
		self.assertEqual(calc.gst_return_period("2026-11-10"), "October - December 2026")
		self.assertEqual(calc.gst_return_period("2027-02-15"), "January - March 2027")
		self.assertEqual(calc.gst_return_period(None), "")

	def test_lines_per_tax_mode(self):
		for mode, tax in (("Export under LUT", 0), ("IGST 18%", 36), ("CGST + SGST 9%", 36)):
			items = [{"qty": 2, "rate": 100}]
			t = calc.compute_lines(items, mode)
			self.assertEqual((t["subtotal"], t["tax_total"], t["grand_total"]), (200, tax, 200 + tax))
			self.assertEqual(items[0]["amount"], 200 + tax)

	def test_unknown_tax_mode(self):
		with self.assertRaises(Exception):
			calc.compute_lines([{"qty": 1, "rate": 1}], "VAT 20%")

	def test_register_calcs(self):
		self.assertEqual(calc.register_calcs(1000, None, 0), {"forex_gain": None, "net_received": None})
		self.assertEqual(calc.register_calcs(1000, 1050, 20), {"forex_gain": 50, "net_received": 1030})

	def test_payment_status(self):
		self.assertEqual(calc.derive_payment_status("Pending", 980, 1000), "Received")
		self.assertEqual(calc.derive_payment_status("Pending", 500, 1000), "Partially received")
		self.assertEqual(calc.derive_payment_status("Pending", None, 1000), "Pending")
		# never overrides a status set by hand
		self.assertEqual(calc.derive_payment_status("Partially received", 1000, 1000), "Partially received")
