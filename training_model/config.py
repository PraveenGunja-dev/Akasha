"""Shared settings for the forecasting pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
DATASETS = ROOT / "data" / "datasets"
REPORTS = ROOT / "reports"
REGISTRY = ROOT / "registry"

# Block milestones the FTC model learns from. FTC itself is what it is graded
# on; the earlier steps of the same chain add examples of how late block work
# runs given its state, which matters with FTC labels from only 18 projects.
TARGET_KINDS = ["module_installation", "ftc_application", "ftc_approval", "ftc"]
GRADED_KIND = "ftc"

# Forecast cut-offs, in days before the milestone's baseline date. Negative =
# the baseline has already passed and the milestone is still open - the
# planner's most common question ("it was due last month - when now?").
HORIZONS = [-90, -60, -30, 0, 30, 60, 90, 120, 180]

# Groups for reporting accuracy by how far ahead the forecast is made.
HORIZON_BUCKETS = [(-999, -1, "overdue"), (0, 45, "0-45d"), (46, 100, "46-100d"), (101, 999, "100d+")]

QUANTILES = {"p20": 0.2, "p50": 0.5, "p80": 0.8}
N_FOLDS = 5          # cross-validation folds, grouped by project
SEED = 42

# -- Order planner assumptions (planner-owned; shown on screen with each plan) --
# Modules must be on site this many days before a block's module installation
# starts: unloading, stores, quality checks and distribution to the block.
SITE_BUFFER_DAYS = 14
# Ordering more than this many days before the latest safe date means modules
# sit in stores: capital tied up, storage space, handling damage, and price
# risk. The planner recommends holding until the window opens.
HOLD_WINDOW_DAYS = 45
# Lead time used for a "safe" order date: the P80 (4 in 5 POs arrived sooner).
LEAD_TIME_QUANTILE = "p80"
