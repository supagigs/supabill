import frappe
from frappe.tests import IntegrationTestCase

from supabill.api.session import get_session, has_app_permission, user_access
from supabill.supabill.install import ensure_roles


def _user(email, role=None):
	if not frappe.db.exists("User", email):
		doc = frappe.get_doc({"doctype": "User", "email": email, "first_name": "T", "send_welcome_email": 0})
		if role:
			doc.append("roles", {"role": role})
		doc.insert(ignore_permissions=True)
	return email


class TestSession(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_roles()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_roles_map_to_access(self):
		self.assertEqual(user_access(_user("s.user@example.com", "SupaBill User")),
			{"logged_in": True, "has_access": True, "is_manager": False})
		self.assertTrue(user_access(_user("s.mgr@example.com", "SupaBill Manager"))["is_manager"])
		self.assertFalse(user_access(_user("s.none@example.com"))["has_access"])
		self.assertFalse(user_access("Guest")["logged_in"])

	def test_get_session(self):
		frappe.set_user(_user("s.user@example.com", "SupaBill User"))
		s = get_session()
		self.assertEqual(s["user"], "s.user@example.com")
		self.assertTrue(s["has_access"])
		self.assertTrue(has_app_permission())
		frappe.set_user("Guest")
		with self.assertRaises(frappe.AuthenticationError):
			get_session()
