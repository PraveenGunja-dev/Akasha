"""Live connectivity probes, one per external feed — answers "is it reachable
right now", with the real error if not. Distinct from sync_log (which only
says what happened at the last scheduled sync, and can be hours or days
stale): this hits each source live, so it is triggered on demand only, never
polled automatically.

Every probe is read-only / auth-only — no data is pulled or written. P6 is
the one exception worth knowing about: P6Service.__init__ performs a real
OAuth token request as a side effect (that's how the rest of the app already
authenticates to it), and P6Service._GLOBAL_AUTH_FAILED latches after a 401
to stop repeated bad logins from locking the Oracle account out. This check
respects that latch rather than forcing a retry — a latched failure is itself
an honest "down".
"""
import os
from typing import Tuple

import requests


def _fail(e: Exception) -> Tuple[bool, str]:
    return False, str(e) or e.__class__.__name__


def check_sap() -> Tuple[bool, str]:
    from services.sharepoint_service import SharePointService
    try:
        sp = SharePointService()
        sp._get_access_token()
        site_id = sp.get_site_id()
        return True, f"Authenticated to Microsoft Graph; site resolved ({site_id[:24]}…)."
    except Exception as e:
        return _fail(e)


def check_p6() -> Tuple[bool, str]:
    from services.p6_service import P6Service
    try:
        P6Service()
        return True, "OAuth token acquired from Oracle P6."
    except Exception as e:
        return _fail(e)


def check_capacity(p6_result: Tuple[bool, str] | None = None) -> Tuple[bool, str]:
    """Capacity milestones ride on P6's own credential — no separate
    connection to test, so this reuses P6's result instead of authenticating
    a second time in the same check."""
    ok, msg = p6_result if p6_result is not None else check_p6()
    return ok, f"Uses the Primavera P6 connection — {msg}"


def check_tc() -> Tuple[bool, str]:
    from services.tc_sync import AUTH_URL, CREDENTIALS
    try:
        r = requests.post(AUTH_URL, json=CREDENTIALS, verify=False, timeout=15)
        r.raise_for_status()
        data = r.json()
        token = data.get("token") or (data.get("data") or {}).get("token") or data.get("access_token")
        if not token:
            return False, f"Login responded but no token was returned: {str(data)[:200]}"
        return True, "Authenticated."
    except Exception as e:
        return _fail(e)


def check_pulse() -> Tuple[bool, str]:
    base = os.getenv("PULSE_BASE_URL", "https://pulse.cfapps.in30.hana.ondemand.com")
    ep = os.getenv("PULSE_NC_ENDPOINT", "/pulse-api/Ncs")
    try:
        r = requests.get(f"{base}{ep}?$top=1", headers={"Accept": "application/json"}, timeout=15, verify=False)
        r.raise_for_status()
        return True, f"Responded to a test query (HTTP {r.status_code})."
    except Exception as e:
        return _fail(e)


def check_einvoice() -> Tuple[bool, str]:
    token_url = os.getenv("EINVOICE_TOKEN_URL")
    client_id = os.getenv("EINVOICE_CLIENT_ID")
    client_secret = os.getenv("EINVOICE_CLIENT_SECRET")
    if not all([token_url, client_id, client_secret]):
        return False, "EINVOICE_TOKEN_URL / EINVOICE_CLIENT_ID / EINVOICE_CLIENT_SECRET missing from backend/.env"
    try:
        r = requests.post(token_url, data={"grant_type": "client_credentials"},
                          auth=(client_id, client_secret), verify=False, timeout=15)
        r.raise_for_status()
        if not r.json().get("access_token"):
            return False, f"Token endpoint responded but returned no access_token: {r.text[:200]}"
        return True, "Authenticated."
    except Exception as e:
        return _fail(e)


def check_mapping() -> Tuple[bool, str]:
    """Not a network feed — a local Excel file the bot drops. 'Working' means
    the file is present and openable, which is exactly what ingest_mapping()
    itself requires to run."""
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(os.path.dirname(backend_dir), "Data")
    path = os.path.join(data_dir, "NEW31", "AKASHA SAP MASTER FILE (2).xlsx")
    if not os.path.exists(path):
        return False, f"Source file not found: {path}"
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True)
        wb.close()
        return True, f"Source file present and readable ({os.path.basename(path)})."
    except Exception as e:
        return False, f"Source file present but could not be opened: {e}"
