# Development environment (Section 1)

Recorded 2026-11-10T12:51Z in the isolated Claude workspace. Not your production server.

| Component | Version |
|---|---|
| Frappe | 16.55.2 (branch version-16) |
| bench CLI | 5.31.1 |
| Python | Python 3.14.6 |
| Node | v24.22.2 (Frappe v16 requires >= 24) |
| Yarn | 1.22.22 |
| MariaDB | 10.11.14-MariaDB-0ubuntu0.24.04.1 |
| Redis | 7.0.15 |
| wkhtmltopdf | 0.12.6 |

- Bench: `/home/frappe/frappe-bench` (user `frappe`)
- Test site: **supabill.local**, served with `bench --site supabill.local serve --port 8001`, `host_name` = http://supabill.local:8001, developer_mode on, allow_tests on.
- Production (`erp.supagigs.cloud`) is not reachable from this workspace and was never targeted.
- Backups: `bench --site supabill.local backup` taken before the first migrate.

## Notes for your server
- Frappe v16 needs Node 24+. Node 22 fails at `yarn install` with an engine error.
- The app has **no ERPNext dependency**; `required_apps` is empty.
