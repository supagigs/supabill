import frappe

from supabill.api.session import user_access

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.request.path
		raise frappe.Redirect
	access = user_access()
	context.boot = {
		"csrf_token": frappe.sessions.get_csrf_token(),
		"site_name": frappe.local.site,
		"sb_user": frappe.session.user,
		"sb_full_name": frappe.utils.get_fullname(frappe.session.user),
		"sb_has_access": access["has_access"],
		"sb_is_manager": access["is_manager"],
	}
	return context
