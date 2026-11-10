import frappe

ACCESS_ROLES = {"SupaBill User", "SupaBill Manager", "System Manager"}
MANAGER_ROLES = {"SupaBill Manager", "System Manager"}


def user_access(user: str | None = None) -> dict:
	user = user or frappe.session.user
	if user == "Guest":
		return {"logged_in": False, "has_access": False, "is_manager": False}
	roles = set(frappe.get_roles(user))
	return {
		"logged_in": True,
		"has_access": bool(roles & ACCESS_ROLES),
		"is_manager": bool(roles & MANAGER_ROLES),
	}


def has_app_permission() -> bool:
	"""Used by the Apps screen to show or hide the SupaBill tile."""
	return user_access()["has_access"]


@frappe.whitelist()
def get_session() -> dict:
	"""Who is signed in and what they may do. Safe for any signed-in user."""
	if frappe.session.user == "Guest":
		frappe.throw("Not signed in", frappe.AuthenticationError)
	access = user_access()
	return {
		"user": frappe.session.user,
		"full_name": frappe.utils.get_fullname(frappe.session.user),
		"user_image": frappe.db.get_value("User", frappe.session.user, "user_image"),
		**access,
	}
