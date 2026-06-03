"""Route modules. Each module exports a `router: APIRouter` that is included
into the main app in server.py.

Pattern: route modules lazy-import shared helpers (db, admin_tab_dep, iso, now_utc)
from server inside each handler — this avoids circular imports at module load time.
"""
