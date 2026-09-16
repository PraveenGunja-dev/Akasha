"""SharePoint access over Microsoft Graph (msal client-credentials).

The Automation bot writes the SAP extracts into SHAREPOINT_BASE_FOLDER. It used
to place them in a DD.MM.YYYY subfolder per day; it now writes them straight
into the base folder. Both layouts are handled: the newest dated subfolder is
used when one exists, otherwise the base folder itself.
"""
import os
import re
import time
import urllib.parse
from datetime import datetime

import msal
import requests
from dotenv import load_dotenv

load_dotenv()

GRAPH = "https://graph.microsoft.com/v1.0"
DATE_FOLDER = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
TRANSIENT = (429, 503, 504)


def _verify_ssl():
    if os.getenv("PROXY_INSECURE_SSL", "false").lower() in ("true", "1", "yes", "on"):
        return False
    return os.getenv("SHAREPOINT_SSL_VERIFY", "true").lower() not in ("false", "0", "no", "off")


class SharePointService:
    def __init__(self):
        self.tenant_id = os.getenv("SHAREPOINT_TENANT_ID")
        self.client_id = os.getenv("SHAREPOINT_CLIENT_ID")
        self.client_secret = os.getenv("SHAREPOINT_CLIENT_SECRET")
        self.site_url = os.getenv("SHAREPOINT_SITE_URL", "https://adaniltd.sharepoint.com/sites/AGEL-Automation")
        self.base_folder = os.getenv("SHAREPOINT_BASE_FOLDER", "/sites/AGEL-Automation/Shared Documents/Bots/Akasha PlatForm")

        parsed = urllib.parse.urlparse(self.site_url)
        self.hostname = parsed.netloc
        self.site_path = parsed.path.rstrip("/")
        self.target_folder = self.base_folder

        self.session = requests.Session()
        self.session.verify = _verify_ssl()
        proxy = os.getenv("PROXY_URL")
        if proxy and os.getenv("PROXY_ENABLED", "false").lower() in ("true", "1", "yes", "on"):
            self.session.proxies = {"http": proxy, "https": proxy}

        self._token = None
        self._site_id = None

    # ── auth ────────────────────────────────────────────────────────────────
    def _get_access_token(self):
        if not (self.tenant_id and self.client_id and self.client_secret):
            raise RuntimeError("SharePoint credentials missing: set SHAREPOINT_TENANT_ID / CLIENT_ID / CLIENT_SECRET in backend/.env")
        app = msal.ConfidentialClientApplication(
            self.client_id, authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=self.client_secret, http_client=self.session,
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in result:
            raise RuntimeError(f"SharePoint token failed: {result.get('error_description') or result.get('error')}")
        return result["access_token"]

    def _headers(self):
        if not self._token:
            self._token = self._get_access_token()
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, url, retries=3, **kw):
        """GET with backoff on throttling / transient gateway errors."""
        for attempt in range(retries + 1):
            r = self.session.get(url, headers=self._headers(), **kw)
            if r.status_code in TRANSIENT and attempt < retries:
                wait = int(r.headers.get("Retry-After") or 5 * (2 ** attempt))
                print(f"SharePoint HTTP {r.status_code}; retry {attempt + 1}/{retries} in {wait}s")
                time.sleep(wait)
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"SharePoint HTTP {r.status_code} for {url}: {r.text[:300]}")
            return r
        raise RuntimeError(f"SharePoint HTTP retries exhausted for {url}")

    def get_site_id(self, token=None):
        if not self._site_id:
            r = self._get(f"{GRAPH}/sites/{self.hostname}:{self.site_path}")
            self._site_id = r.json()["id"]
        return self._site_id

    # ── listing ─────────────────────────────────────────────────────────────
    def _drive_path(self, folder):
        """Site-relative folder → path inside the default document library."""
        return folder.replace(f"{self.site_path}/Shared Documents", "").strip("/")

    def _children(self, folder):
        url = f"{GRAPH}/sites/{self.get_site_id()}/drive/root:/{self._drive_path(folder)}:/children"
        items = []
        while url:
            data = self._get(url).json()
            items.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
        return items

    def list_files_in_target_folder(self):
        """Files in the newest DD.MM.YYYY subfolder if any, else the base folder.
        Raises on any Graph failure — a sync must not report an auth error as
        'no files today'."""
        items = self._children(self.base_folder)
        dated = [i for i in items if i.get("folder") and DATE_FOLDER.match(i["name"])]
        if dated:
            latest = max(dated, key=lambda f: datetime.strptime(f["name"], "%d.%m.%Y"))
            self.target_folder = f"{self.base_folder}/{latest['name']}"
            print(f"SharePoint: using dated folder {latest['name']}")
            items = self._children(self.target_folder)
        else:
            print("SharePoint: no dated subfolders; using base folder")
        return [
            {"name": f["name"], "id": f["id"], "modified": f.get("lastModifiedDateTime"),
             "size": f.get("size", 0), "download_url": f.get("@microsoft.graph.downloadUrl")}
            for f in items if "file" in f
        ]

    # ── download ────────────────────────────────────────────────────────────
    def download_file(self, download_url, save_path):
        """Stream a file to disk. The pre-authenticated downloadUrl needs no bearer."""
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
        for attempt in range(4):
            r = self.session.get(download_url, stream=True)
            if r.status_code in TRANSIENT and attempt < 3:
                time.sleep(int(r.headers.get("Retry-After") or 10 * (2 ** attempt)))
                continue
            if r.status_code != 200:
                raise RuntimeError(f"SharePoint download HTTP {r.status_code}: {r.text[:200]}")
            tmp = save_path + ".part"
            with open(tmp, "wb") as fh:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    fh.write(chunk)
            os.replace(tmp, save_path)
            return save_path
        raise RuntimeError("SharePoint download retries exhausted")


if __name__ == "__main__":
    sp = SharePointService()
    for f in sp.list_files_in_target_folder():
        print(f"{f['name']:55s} {str(f['modified'])[:10]} {f['size'] / 1e6:6.1f} MB")
