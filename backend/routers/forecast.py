"""
Module forecast & order plan API (training_model/ outputs).

Serves what the offline pipeline in training_model/ produced - block FTC and
module-installation forecasts, the per-project module order plan, the model's
measured accuracy and the planner assumptions - plus planner SAVES:

- A saved figure is what the screen shows from then on. A retrain never
  overwrites it; the response carries the model's current figure next to it
  (`model_now`) and how far it has moved (`drift_days`), so a planner sees when
  a saved date may need revisiting without it changing under them.
- Every save is a new forecast_lock row; saving again supersedes the previous
  one, unlocking supersedes it with no successor - the full history stays.

Nothing here computes a forecast: if the pipeline has not been run, the API
says so rather than inventing one.
"""
import importlib.util
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from models import AkashaUser, ForecastLock
from routers.auth import current_user

router = APIRouter(prefix="/api/forecast")

TM = Path(__file__).resolve().parents[2] / "training_model"
REG = TM / "registry"
_CACHE: Dict[str, Any] = {}


# -- Reading the pipeline's outputs (cached by file time) -------------------------
def _read(path: Path, kind: str):
    if not path.exists():
        return None
    key = f"{path}:{path.stat().st_mtime_ns}"
    if key not in _CACHE:
        _CACHE[key] = json.loads(path.read_text()) if kind == "json" else pd.read_csv(path)
    return _CACHE[key]


def _latest_model_dir() -> Optional[Path]:
    versions = sorted((REG / "ftc_slip").glob("v*")) if (REG / "ftc_slip").exists() else []
    return versions[-1] if versions else None


def _assumptions() -> Dict[str, Any]:
    spec = importlib.util.spec_from_file_location("tm_config", TM / "config.py")
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    return {"site_buffer_days": cfg.SITE_BUFFER_DAYS, "hold_window_days": cfg.HOLD_WINDOW_DAYS,
            "lead_time_quantile": cfg.LEAD_TIME_QUANTILE,
            "tested_horizon_days": [min(cfg.HORIZONS), max(cfg.HORIZONS)]}


def _clean(v):
    if v is None or (isinstance(v, float) and v != v):
        return None
    return v.item() if hasattr(v, "item") else v


def _records(df: Optional[pd.DataFrame]) -> List[Dict[str, Any]]:
    if df is None:
        return []
    return [{k: _clean(v) for k, v in r.items()} for r in df.to_dict("records")]


def _model_summary(d: Path) -> Optional[Dict[str, Any]]:
    meta = _read(d / "meta.json", "json")
    if not meta:
        return None
    ev = {r["horizon"]: r for r in meta.get("evaluation", [])}
    algo = meta["algorithm"]

    def acc(r):
        return {"rows": r["rows"], "blocks": r["blocks"],
                "model_mae_days": r[f"{algo}_p50_mae"], "p6_mae_days": r["p6_mae"],
                "naive_mae_days": r["naive_mae"],
                "model_within30_pct": r[f"{algo}_p50_within30"], "p6_within30_pct": r["p6_within30"]}

    return {"version": meta["version"], "algorithm": algo, "trained_at": meta["trained_at"],
            "deployable": meta.get("deployable"), "training": meta.get("training"),
            "accuracy": acc(ev["all"]) if "all" in ev else None,
            "by_horizon": [dict(horizon=h, **acc(r)) for h, r in ev.items() if h != "all"],
            "range_check": (meta.get("calibration") or {}).get("check_leave_fold_out")}


# -- Locks --------------------------------------------------------------------------
def _active_locks(db: Session, project_id: Optional[str] = None) -> Dict[tuple, ForecastLock]:
    q = db.query(ForecastLock).filter(ForecastLock.superseded_at.is_(None))
    if project_id:
        q = q.filter(ForecastLock.project_id == project_id)
    return {(l.scope, l.project_id, l.block): l for l in q.all()}


def _lock_json(l: Optional[ForecastLock]) -> Optional[Dict[str, Any]]:
    if l is None:
        return None
    return {"id": l.id, "payload": l.payload, "model_version": l.model_version, "note": l.note,
            "locked_by": l.locked_by, "locked_at": l.locked_at.isoformat()}


def _days(a, b) -> Optional[int]:
    try:
        return (pd.Timestamp(a) - pd.Timestamp(b)).days
    except Exception:
        return None


PLAN_FIELDS = ["action", "remaining_need_mwp", "stock_on_site_mwp", "pipeline_mwp", "uncovered_mwp",
               "order_by_import", "order_by_domestic", "shortfall_from", "shortfall_block", "why"]


def _with_plan_lock(p: Dict[str, Any], lock: Optional[ForecastLock]) -> Dict[str, Any]:
    if lock is None:
        return {**p, "lock": None, "model_now": None, "model_changed": False}
    saved = lock.payload or {}
    changed = any(str(saved.get(k)) != str(p.get(k)) for k in ("action", "order_by_import", "order_by_domestic"))
    return {**p, **{k: saved.get(k, p.get(k)) for k in PLAN_FIELDS}, "lock": _lock_json(lock),
            "model_now": {k: p.get(k) for k in PLAN_FIELDS}, "model_changed": changed}


# -- Endpoints ------------------------------------------------------------------------
@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> Dict[str, Any]:
    d = _latest_model_dir()
    plan = _read(REG / "order_plan" / "order_plan.csv", "csv")
    if d is None or plan is None:
        return {"available": False,
                "reason": "The forecast pipeline has not been run on this server (training_model/).",
                "plans": []}
    names = dict(db.execute(text("select project_id, max(project) from project_mapping group by 1")).fetchall())
    locks = _active_locks(db)
    plans = []
    for p in _records(plan):
        p["project_name"] = names.get(p["project_id"])
        plans.append(_with_plan_lock(p, locks.get(("order_plan", p["project_id"], None))))
    counts: Dict[str, int] = {}
    for p in plans:
        key = "Hold" if str(p["action"]).startswith("Hold") else p["action"]
        counts[key] = counts.get(key, 0) + 1
    lt = _read(REG / "lead_time" / "lead_times.json", "json") or {}
    plan_mtime = datetime.fromtimestamp((REG / "order_plan" / "order_plan.csv").stat().st_mtime)
    return {"available": True, "model": _model_summary(d), "assumptions": _assumptions(),
            "lead_times": lt.get("by_origin"), "lead_time_coverage": lt.get("coverage"),
            "plan_generated_at": plan_mtime.isoformat(timespec="minutes"),
            "counts": counts, "plans": plans}


@router.get("/projects/{project_id}")
def project_detail(project_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    d = _latest_model_dir()
    if d is None:
        raise HTTPException(404, "The forecast pipeline has not been run on this server.")
    fc = _read(d / "forecast.csv", "csv")
    need = _read(REG / "order_plan" / "block_need.csv", "csv")
    fc = fc[fc.project_id == project_id] if fc is not None else None
    need = need[need.project_id == project_id] if need is not None else None
    locks = _active_locks(db, project_id)
    blocks: Dict[int, Dict[str, Any]] = {}
    for r in _records(fc):
        b = blocks.setdefault(int(r["block"]), {"block": int(r["block"])})
        b[r["kind"]] = {k: r.get(k) for k in (
            "activity_id", "activity_name", "baseline_finish", "forecast_p20", "forecast_p50", "forecast_p80",
            "slip_p50", "days_to_baseline", "confidence", "typical_slip_days", "why")}
    for r in _records(need):
        b = blocks.setdefault(int(r["block"]), {"block": int(r["block"])})
        b["need"] = {k: r.get(k) for k in ("mwp", "need_by", "covered", "site_started", "forecast_shift_days")}
    out = []
    for b in sorted(blocks.values(), key=lambda x: x["block"]):
        lock = locks.get(("block_ftc", project_id, b["block"]))
        ftc = b.get("ftc")
        b["lock"] = _lock_json(lock)
        if lock is not None and ftc:
            b["drift_days"] = _days(ftc["forecast_p50"], (lock.payload or {}).get("forecast_p50"))
        out.append(b)
    plan_df = _read(REG / "order_plan" / "order_plan.csv", "csv")
    plan = next((p for p in _records(plan_df) if p["project_id"] == project_id), None) if plan_df is not None else None
    if plan:
        plan = _with_plan_lock(plan, locks.get(("order_plan", project_id, None)))
    return {"project_id": project_id, "plan": plan, "blocks": out}


class LockIn(BaseModel):
    scope: str                      # "block_ftc" | "order_plan"
    project_id: str
    block: Optional[int] = None
    payload: Dict[str, Any]
    model_version: Optional[str] = None
    note: Optional[str] = None


@router.post("/locks")
def save_lock(body: LockIn, db: Session = Depends(get_db),
              user: AkashaUser = Depends(current_user)) -> Dict[str, Any]:
    if body.scope not in ("block_ftc", "order_plan"):
        raise HTTPException(400, "scope must be block_ftc or order_plan")
    if (body.scope == "block_ftc") != (body.block is not None):
        raise HTTPException(400, "block_ftc needs a block; order_plan must not have one")
    now = datetime.utcnow()
    prev = db.query(ForecastLock).filter(
        ForecastLock.scope == body.scope, ForecastLock.project_id == body.project_id,
        ForecastLock.block == body.block if body.block is not None else ForecastLock.block.is_(None),
        ForecastLock.superseded_at.is_(None)).all()
    for p in prev:
        p.superseded_at, p.superseded_by = now, user.username
    lock = ForecastLock(scope=body.scope, project_id=body.project_id, block=body.block,
                        payload=body.payload, model_version=body.model_version, note=body.note,
                        locked_by=user.username, locked_at=now)
    db.add(lock)
    db.commit()
    return _lock_json(lock)


@router.post("/locks/{lock_id}/unlock")
def unlock(lock_id: int, db: Session = Depends(get_db),
           user: AkashaUser = Depends(current_user)) -> Dict[str, Any]:
    lock = db.query(ForecastLock).get(lock_id)
    if lock is None or lock.superseded_at is not None:
        raise HTTPException(404, "No active save with that id")
    lock.superseded_at, lock.superseded_by = datetime.utcnow(), user.username
    db.commit()
    return {"unlocked": lock_id}


@router.get("/locks")
def lock_history(project_id: str, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = db.query(ForecastLock).filter(ForecastLock.project_id == project_id) \
        .order_by(ForecastLock.locked_at.desc()).all()
    return [{**_lock_json(l), "scope": l.scope, "block": l.block,
             "superseded_at": l.superseded_at.isoformat() if l.superseded_at else None,
             "superseded_by": l.superseded_by} for l in rows]
