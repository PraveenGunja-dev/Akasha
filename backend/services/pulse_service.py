"""
Pulse Quality Service — Fetches NCs and RFIs from the Pulse OData API
and syncs them into the Akasha PostgreSQL database.

API: https://pulse.cfapps.ap11.hana.ondemand.com/pulse-api
Protocol: OData v4 (no auth required)
Entities: /Ncs, /Rfis
"""
import os
import requests
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from sqlalchemy.orm import Session

load_dotenv()

logger = logging.getLogger(__name__)

# OData $expand queries from the Postman collection
NC_EXPAND = (
    "WORKAREA($expand=PROJECT($expand=SPV)),"
    "WORKLOCATION,SERVICE_ORDER,"
    "CONTRACTOR($expand=VENDOR),ENGINEER,QUALITY,"
    "SUBACTIVITY($expand=ACTIVITY($expand=SUBPACKAGE($expand=PACKAGE))),"
    "PACKAGE,UNIT_OF_MEASUREMENT_DATA,"
    "SCOPES($expand=DESIGNELEMENT,DESIGNELEMENTLOOKUP)"
)

RFI_EXPAND = (
    "WORKAREA,WORKLOCATION,SERVICE_ORDER,"
    "CONTRACTOR($expand=VENDOR),ENGINEER,QUALITY,"
    "INSPECTION_POINT($expand=SUBACTIVITY($expand=ACTIVITY($expand=SUBPACKAGE))),"
    "PACKAGE,UNIT_OF_MEASUREMENT_DATA,"
    "PROJECT($expand=SPV)"
)

# Lighter expand for RFI bulk sync (skip attachments/responses for speed)
RFI_EXPAND_LIGHT = (
    "PROJECT($expand=SPV),WORKLOCATION,WORKAREA,"
    "CONTRACTOR($expand=VENDOR),ENGINEER,QUALITY,PACKAGE,"
    "INSPECTION_POINT($expand=SUBACTIVITY)"
)


def _safe_get(obj, *keys):
    """Safely navigate nested dicts."""
    for key in keys:
        if obj is None or not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _parse_datetime(value: Any) -> Optional[datetime]:
    """Parse ISO datetime strings from Pulse."""
    if not value:
        return None
    try:
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        pass
    return None


class PulseService:
    def __init__(self):
        self.base_url = os.getenv(
            "PULSE_BASE_URL",
            "https://pulse.cfapps.ap11.hana.ondemand.com"
        )
        self.nc_endpoint = os.getenv("PULSE_NC_ENDPOINT", "/pulse-api/Ncs")
        self.rfi_endpoint = os.getenv("PULSE_RFI_ENDPOINT", "/pulse-api/Rfis")
        self.headers = {"Accept": "application/json"}

    # ──────────────────────────────────────────
    # Fetch helpers
    # ──────────────────────────────────────────
    def _fetch_paginated(self, endpoint: str, expand: str, page_size: int = 200) -> List[Dict]:
        """Fetch all records from an OData endpoint with pagination."""
        all_records = []
        skip = 0
        while True:
            url = f"{self.base_url}{endpoint}?$top={page_size}&$skip={skip}&$expand={expand}"
            try:
                resp = requests.get(url, headers=self.headers, timeout=60, verify=False)
                resp.raise_for_status()
                data = resp.json()
                records = data.get("value", [])
                if not records:
                    break
                all_records.extend(records)
                skip += page_size
                if len(records) < page_size:
                    break
            except Exception as e:
                logger.error(f"Error fetching {endpoint} at skip={skip}: {e}")
                break
        return all_records

    def fetch_all_ncs(self) -> List[Dict]:
        """Fetch all Non-Conformance records with full expand."""
        logger.info("Fetching all NCs from Pulse...")
        ncs = self._fetch_paginated(self.nc_endpoint, NC_EXPAND)
        logger.info(f"Fetched {len(ncs)} NCs from Pulse.")
        return ncs

    def fetch_all_rfis(self) -> List[Dict]:
        """Fetch all RFI records with light expand (for performance)."""
        logger.info("Fetching all RFIs from Pulse...")
        rfis = self._fetch_paginated(self.rfi_endpoint, RFI_EXPAND_LIGHT)
        logger.info(f"Fetched {len(rfis)} RFIs from Pulse.")
        return rfis

    # ──────────────────────────────────────────
    # Map OData → SQLAlchemy
    # ──────────────────────────────────────────
    def _map_nc(self, raw: Dict) -> Dict:
        """Flatten a single NC OData response into a flat dict for PulseNC model."""
        workarea = raw.get("WORKAREA") or {}
        project = workarea.get("PROJECT") or {}
        spv = project.get("SPV") or {}
        worklocation = raw.get("WORKLOCATION") or {}
        contractor = raw.get("CONTRACTOR") or {}
        vendor = contractor.get("VENDOR") or {}
        engineer = raw.get("ENGINEER") or {}
        quality = raw.get("QUALITY") or {}
        subactivity = raw.get("SUBACTIVITY") or {}
        activity = subactivity.get("ACTIVITY") or {}
        subpackage = activity.get("SUBPACKAGE") or {}
        package_from_chain = subpackage.get("PACKAGE") or {}
        package_direct = raw.get("PACKAGE") or {}
        service_order = raw.get("SERVICE_ORDER") or {}

        return {
            "pulse_id": raw.get("ID"),
            "nc_label": raw.get("NC_LABEL"),
            "status": raw.get("STATUS"),
            "status_label": raw.get("STATUS_LABEL"),
            "category": raw.get("CATEGORY"),
            "defect_type": raw.get("DEFECT_TYPE"),
            "description": raw.get("DESCRIPTION"),
            "quantity": raw.get("QUANTITY"),
            "ad_hoc": raw.get("AD_HOC", True),
            "archived": raw.get("ARCHIVED", False),
            "version": raw.get("VERSION"),
            "current_handler": raw.get("CURRENT_HANDLER"),
            "debit": raw.get("DEBIT"),
            "debit_reason": raw.get("DEBIT_REASON"),
            # Location
            "cluster_name": raw.get("CLUSTER_NAME"),
            "project_name": project.get("NAME"),
            "project_id": raw.get("PROJECT_ID"),
            "project_type": project.get("TYPE"),
            "spv_name": spv.get("NAME"),
            "worklocation_name": worklocation.get("NAME"),
            "workarea_name": workarea.get("NAME"),
            # People
            "contractor_name": contractor.get("NAME"),
            "vendor_name": vendor.get("NAME"),
            "vendor_code": vendor.get("CODE"),
            "engineer_name": engineer.get("NAME"),
            "quality_name": quality.get("NAME"),
            # Work breakdown
            "package_name": package_direct.get("NAME") or package_from_chain.get("NAME"),
            "subpackage_name": subpackage.get("NAME"),
            "activity_name": activity.get("NAME"),
            "subactivity_name": subactivity.get("NAME"),
            # Service order
            "service_order_number": service_order.get("SO_NUMBER"),
            # Timestamps
            "created_at": _parse_datetime(raw.get("CREATED_AT")),
            "updated_at": _parse_datetime(raw.get("UPDATED_AT")),
            "approved_at": _parse_datetime(raw.get("APPROVED_AT")),
        }

    def _map_rfi(self, raw: Dict) -> Dict:
        """Flatten a single RFI OData response into a flat dict for PulseRFI model."""
        project = raw.get("PROJECT") or {}
        spv = project.get("SPV") or {}
        worklocation = raw.get("WORKLOCATION") or {}
        workarea = raw.get("WORKAREA") or {}
        contractor = raw.get("CONTRACTOR") or {}
        vendor = contractor.get("VENDOR") or {}
        engineer = raw.get("ENGINEER") or {}
        quality = raw.get("QUALITY") or {}
        package = raw.get("PACKAGE") or {}
        inspection_point = raw.get("INSPECTION_POINT") or {}
        subactivity = inspection_point.get("SUBACTIVITY") or {}

        return {
            "pulse_id": raw.get("ID"),
            "rfi_label": raw.get("RFI_LABEL"),
            "status": raw.get("STATUS"),
            "status_label": raw.get("STATUS_LABEL"),
            "current_handler": raw.get("CURRENT_HANDLER"),
            # Location
            "cluster_name": raw.get("CLUSTER_NAME"),
            "project_name": project.get("NAME"),
            "project_id": raw.get("PROJECT_ID"),
            "project_type": project.get("TYPE"),
            "spv_name": spv.get("NAME"),
            "worklocation_name": worklocation.get("NAME"),
            "workarea_name": workarea.get("NAME"),
            # People
            "contractor_name": contractor.get("NAME"),
            "vendor_name": vendor.get("NAME"),
            "engineer_name": engineer.get("NAME"),
            "quality_name": quality.get("NAME"),
            # Work breakdown
            "package_name": package.get("NAME"),
            "inspection_point_name": subactivity.get("NAME"),
            # Timestamps
            "created_at": _parse_datetime(raw.get("CREATED_AT")),
            "updated_at": _parse_datetime(raw.get("UPDATED_AT")),
        }

    # ──────────────────────────────────────────
    # Sync (Upsert)
    # ──────────────────────────────────────────
    def full_sync(self, db: Session) -> Dict[str, int]:
        """Full sync: fetch all NCs and RFIs, upsert into database."""
        import models

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # ── Sync NCs ──
        raw_ncs = self.fetch_all_ncs()
        nc_count = 0
        seen_nc_ids = set()
        for raw in raw_ncs:
            mapped = self._map_nc(raw)
            pulse_id = mapped["pulse_id"]
            if not pulse_id or pulse_id in seen_nc_ids:
                continue
            seen_nc_ids.add(pulse_id)

            existing = db.query(models.PulseNC).filter(
                models.PulseNC.pulse_id == pulse_id
            ).first()

            if existing:
                for key, value in mapped.items():
                    setattr(existing, key, value)
                existing.last_synced_at = now
            else:
                nc = models.PulseNC(**mapped, last_synced_at=now)
                db.add(nc)
            nc_count += 1

        db.commit()
        logger.info(f"Synced {nc_count} NCs to database.")

        # ── Sync RFIs ──
        raw_rfis = self.fetch_all_rfis()
        rfi_count = 0
        batch_size = 500
        seen_rfi_ids = set()
        for i, raw in enumerate(raw_rfis):
            mapped = self._map_rfi(raw)
            pulse_id = mapped["pulse_id"]
            if not pulse_id or pulse_id in seen_rfi_ids:
                continue
            seen_rfi_ids.add(pulse_id)

            existing = db.query(models.PulseRFI).filter(
                models.PulseRFI.pulse_id == pulse_id
            ).first()

            if existing:
                for key, value in mapped.items():
                    setattr(existing, key, value)
                existing.last_synced_at = now
            else:
                rfi = models.PulseRFI(**mapped, last_synced_at=now)
                db.add(rfi)
            rfi_count += 1

            # Batch commit for RFIs (large volume)
            if (i + 1) % batch_size == 0:
                db.commit()

        db.commit()
        logger.info(f"Synced {rfi_count} RFIs to database.")

        # ── Map Pulse Projects to ProjectMapping ──
        pulse_projects_dict = {}
        for raw in raw_ncs + raw_rfis:
            p_name = _safe_get(raw, "PROJECT", "NAME")
            p_cluster = raw.get("CLUSTER_NAME") or _safe_get(raw, "PROJECT", "CLUSTER_NAME")
            p_type = _safe_get(raw, "PROJECT", "TYPE")
            if p_name and p_name not in pulse_projects_dict:
                pulse_projects_dict[p_name] = {
                    "cluster": p_cluster,
                    "type": p_type
                }
                
        existing_mappings = db.query(models.ProjectMapping).all()
        mapped_names = {m.project.lower() if m.project else "": m for m in existing_mappings}
        mapped_p6_names = {m.project_name_from_p6.lower() if m.project_name_from_p6 else "": m for m in existing_mappings}
        new_mappings_added = 0
        if new_mappings_added > 0:
            db.commit()
            logger.info(f"Added {new_mappings_added} new Pulse projects to ProjectMapping.")

        return {"ncs": nc_count, "rfis": rfi_count, "new_projects": new_mappings_added}
