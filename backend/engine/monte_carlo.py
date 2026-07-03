"""
Akasha Deterministic Monte Carlo Engine — Phase 2

Uses historical empirical data (72,000+ completed P6 activities) to build
PERT Beta distributions (Optimistic, Most Likely, Pessimistic) for different
construction phases.

Runs N iterations sampling from these distributions to compute P10, P50, and P90
completion dates for a project.

No LLM guessing. Pure statistics.
"""

import logging
import random
import math
from datetime import datetime, timedelta, date
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func

import models
from engine.variance import _classify_phase, _safe_date_str

logger = logging.getLogger(__name__)

# Cache the PERT distributions so we don't query 73k rows every simulation run
_PERT_CACHE = {}


def get_pert_distributions(db: Session) -> dict:
    """
    Query historical completed activities to compute Optimistic (P10),
    Most Likely (Median), and Pessimistic (P90) duration multipliers per phase.
    
    A multiplier > 1.0 means the activity took longer than planned.
    Returns: dict mapping phase_name -> {"O": float, "M": float, "P": float}
    """
    global _PERT_CACHE
    if _PERT_CACHE:
        return _PERT_CACHE

    logger.info("Computing empirical PERT distributions from historical completed activities...")
    
    # Query all completed activities that have both planned and actual durations
    completed = db.query(
        models.P6Activity.name,
        models.P6Activity.planned_duration,
        models.P6Activity.actual_duration
    ).filter(
        models.P6Activity.status == 'Completed',
        models.P6Activity.planned_duration > 0,
        models.P6Activity.actual_duration.isnot(None)
    ).all()

    phase_multipliers = defaultdict(list)
    for name, planned, actual in completed:
        phase = _classify_phase(name)
        # Ratio of actual vs planned (e.g. 1.2 = took 20% longer)
        ratio = float(actual) / float(planned)
        # Cap extreme outliers for statistical stability
        ratio = min(max(ratio, 0.1), 10.0)
        phase_multipliers[phase].append(ratio)

    pert_dists = {}
    for phase, ratios in phase_multipliers.items():
        if not ratios:
            continue
        ratios.sort()
        n = len(ratios)
        # Extract percentiles
        O = ratios[int(n * 0.10)]  # 10th percentile (Optimistic)
        M = ratios[int(n * 0.50)]  # 50th percentile (Median/Most Likely)
        P = ratios[int(n * 0.90)]  # 90th percentile (Pessimistic)
        
        pert_dists[phase] = {"O": O, "M": M, "P": P, "sample_size": n}

    # Fallback for any unknown phase
    if "Other" not in pert_dists:
        pert_dists["Other"] = {"O": 0.8, "M": 1.1, "P": 2.0, "sample_size": 0}

    _PERT_CACHE = pert_dists
    return _PERT_CACHE


def _sample_pert(O: float, M: float, P: float) -> float:
    """
    Sample a value from a PERT Beta distribution.
    Uses the standard approximation method.
    """
    # Mean and standard deviation of PERT
    mean = (O + 4 * M + P) / 6.0
    std_dev = (P - O) / 6.0
    
    # We approximate using a normal distribution truncated at O and P
    # (True Beta sampling is more complex but Normal approximation is standard for SRA)
    sample = random.gauss(mean, std_dev)
    return max(O, min(P, sample))


def run_monte_carlo_simulation(
    db: Session, 
    project_id: str, 
    iterations: int = 2000, 
    seed: int | None = None,
    modifiers: dict | None = None
) -> dict:
    """
    Run a Monte Carlo Schedule Risk Analysis (SRA) with optional What-If modifiers.
    
    1. Loads empirical PERT distributions.
    2. Loads all Not Started / In Progress activities for the project.
    3. Runs `iterations` scenarios.
    4. To approximate the P6 network logic, we use the already-scheduled P6 start dates
       and apply the PERT multiplier to the duration to find the simulated finish date.
       The project completion is the max finish date across all activities.
    
    Returns: P10, P50, P90 completion dates and convergence data.
    """
    if seed is not None:
        random.seed(seed)
        
    modifiers = modifiers or {}

    # 1. Load historical distributions
    pert_dists = get_pert_distributions(db)

    # 2. Get the P6 project
    p6_proj = db.query(models.P6Project).filter(
        models.P6Project.project_id == project_id
    ).first()
    
    if not p6_proj:
        return {"error": f"Project not found: {project_id}"}

    data_date = p6_proj.data_date or datetime.today()
    if isinstance(data_date, datetime):
        data_date = data_date.date()

    # 3. Get pending activities (ORDER BY ensures fixed-seed reproducibility)
    pending_acts = db.query(models.P6Activity).filter(
        models.P6Activity.project_object_id == p6_proj.p6_object_id,
        models.P6Activity.status.in_(['Not Started', 'In Progress'])
    ).order_by(models.P6Activity.activity_id).all()

    if not pending_acts:
        return {"error": "No pending activities found to simulate."}

    simulation_nodes = []
    for act in pending_acts:
        phase = _classify_phase(act.name)
        start = act.start_date or act.planned_start_date or data_date
        finish = act.finish_date or act.planned_finish_date or data_date
        
        if isinstance(start, datetime): start = start.date()
        if isinstance(finish, datetime): finish = finish.date()
            
        base_dur_days = (finish - start).days
        if base_dur_days <= 0:
            base_dur_days = 1 # give it at least 1 day to allow perturbation
            
        simulation_nodes.append({
            "id": act.activity_id,
            "name": act.name,
            "phase": phase,
            "start": start,
            "base_dur_days": base_dur_days
        })

    # 4. Run iterations
    project_completion_dates = []
    convergence_data = []
    criticality_counts = defaultdict(int)

    # Extract specific modifiers
    monsoon = modifiers.get("weather_monsoon", "Normal")
    wind = modifiers.get("weather_wind", "Normal")
    added_crews = int(modifiers.get("added_crews", 0))

    for i in range(1, iterations + 1):
        max_proj_date = data_date
        iteration_longest_path_act = None
        
        for node in simulation_nodes:
            dist = pert_dists.get(node["phase"], pert_dists["Other"]).copy()
            
            # PHASE 4: Apply Weather Modifiers
            if monsoon == "Heavy" and node["phase"] in ["Foundation", "Cabling"]:
                dist["P"] *= 1.2
            elif monsoon == "Severe" and node["phase"] in ["Foundation", "Cabling"]:
                dist["P"] *= 1.5
                
            if wind == "High Alerts" and node["phase"] == "WTG":
                dist["P"] *= 1.5
                
            multiplier = _sample_pert(dist["O"], dist["M"], dist["P"])
            
            # PHASE 3: Apply Resource Modifiers (added crews to Foundation)
            if node["phase"] == "Foundation" and added_crews > 0:
                # 10% duration reduction per added crew, max 50%
                reduction = min(0.50, added_crews * 0.10)
                multiplier *= (1.0 - reduction)
            
            simulated_dur = node["base_dur_days"] * multiplier
            sim_finish = node["start"] + timedelta(days=int(simulated_dur))
            
            if sim_finish > max_proj_date:
                max_proj_date = sim_finish
                iteration_longest_path_act = node["id"]

        project_completion_dates.append(max_proj_date)
        
        if iteration_longest_path_act:
            criticality_counts[iteration_longest_path_act] += 1

        # Record convergence every 10% of iterations
        if i % max(1, (iterations // 10)) == 0 or i == iterations:
            current_sorted = sorted(project_completion_dates)
            current_p50 = current_sorted[int(len(current_sorted) * 0.50)]
            convergence_data.append({
                "iteration": i,
                "p50_estimate": _safe_date_str(current_p50)
            })

    # 5. Calculate Final Statistics
    project_completion_dates.sort()
    n = len(project_completion_dates)
    
    p10_date = project_completion_dates[int(n * 0.10)]
    p50_date = project_completion_dates[int(n * 0.50)]
    p90_date = project_completion_dates[int(n * 0.90)]

    criticality_index = []
    for node in simulation_nodes:
        count = criticality_counts.get(node["id"], 0)
        if count > 0:
            pct = round((count / iterations) * 100, 1)
            criticality_index.append({
                "activity_id": node["id"],
                "name": node["name"],
                "phase": node["phase"],
                "pct_of_iterations_on_critical_path": pct
            })
    
    criticality_index.sort(key=lambda x: x["pct_of_iterations_on_critical_path"], reverse=True)

    return {
        "project_id": project_id,
        "data_date": _safe_date_str(data_date),
        "iterations_run": iterations,
        "completion_dates": {
            "p10": _safe_date_str(p10_date),
            "p50": _safe_date_str(p50_date),
            "p90": _safe_date_str(p90_date),
        },
        "spread_days": (p90_date - p10_date).days,
        "convergence": convergence_data,
        "criticality_index": criticality_index[:20],
        "pert_distributions_used": {
            k: {"O": round(v["O"],2), "M": round(v["M"],2), "P": round(v["P"],2)}
            for k,v in pert_dists.items()
        }
    }
