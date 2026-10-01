from app.models import Role

ROLE_DETAILS = {
    Role.ADMIN.value: {
        "label": "Administrator",
        "description": "Manage staff, property settings, and every hotel operation.",
        "permissions": [
            "Dashboard and reports",
            "Manage rooms, room types, and reservations",
            "Create and update guest records",
            "Check guests in and out; manage folios, payments, and refunds",
            "Assign housekeeping and manage maintenance",
            "Manage rates, inventory, notifications, and property settings",
            "Create, change, deactivate, and delete staff accounts",
            "Review the full audit log",
        ],
    },
    Role.MANAGER.value: {
        "label": "Manager",
        "description": "Oversee front desk, rates, staff operations, and financial reporting.",
        "permissions": [
            "Dashboard and reports",
            "Manage rooms, room types, guests, and reservations",
            "Check guests in and out; override unpaid checkout with an audited reason",
            "Manage folios, charges, payments, and refunds",
            "Assign housekeeping and manage maintenance",
            "Manage rates and inventory",
            "Review settings and operational audit events",
        ],
    },
    Role.FRONT_DESK.value: {
        "label": "Front Desk",
        "description": "Handle arrivals, departures, guest records, and room-facing service.",
        "permissions": [
            "Operational dashboard",
            "Search guests and manage guest records",
            "Create, move, cancel, and check in reservations",
            "Check guests out after balances are settled",
            "Post folio charges and record payments",
            "Update room readiness and view housekeeping tasks",
            "Open maintenance tickets and view operating reports",
        ],
    },
    Role.HOUSEKEEPING.value: {
        "label": "Housekeeping",
        "description": "Work assigned room cleans and update room readiness.",
        "permissions": [
            "Housekeeping dashboard figures",
            "View assigned room tasks",
            "Start cleans and mark rooms inspected",
            "View room status and maintenance tickets",
        ],
    },
    Role.ACCOUNTANT.value: {
        "label": "Accountant",
        "description": "Review financial activity, reports, inventory value, and audit history.",
        "permissions": [
            "Financial dashboard and reports; export CSV and PDF",
            "Read reservations, guests, rooms, and folios",
            "Record payments and issue refunds",
            "Review inventory and property settings",
            "Review operational audit events",
        ],
    },
}