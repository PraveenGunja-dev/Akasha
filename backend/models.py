from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, BigInteger, JSON
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

# ==========================================
# User Authentication Model
# ==========================================
class AkashaUser(Base):
    __tablename__ = "akasha_user"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    role = Column(String, nullable=False, index=True)  # executive, pmag, projects, tc_ordering, tc_stores
    email = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ==========================================
# SQLAlchemy Database Models (PostgreSQL)
# ==========================================


# ------------------------------------------
# P6 Project Model (Construction Tracking)
# ------------------------------------------
class P6WBSNode(Base):
    __tablename__ = "p6_wbs_node"

    id = Column(Integer, primary_key=True, index=True)
    p6_object_id = Column(BigInteger, unique=True, index=True, nullable=False)
    project_object_id = Column(BigInteger, index=True, nullable=False)
    wbs_code = Column(String)
    wbs_name = Column(String)
    parent_object_id = Column(BigInteger, index=True, nullable=True)
    is_block = Column(Boolean, default=False)
    block_number = Column(Integer, nullable=True)
    
    upload_time = Column(DateTime, default=datetime.utcnow)

class P6Project(Base):
    __tablename__ = "p6_project"

    id = Column(Integer, primary_key=True, index=True)

    # Core Identification
    p6_object_id = Column(BigInteger, unique=True, index=True, nullable=False)
    project_id = Column(String, index=True)  # P6 "Id" field (e.g., "PROJ-001")
    name = Column(String, index=True)
    status = Column(String, index=True)  # Active / Planned / Inactive

    # Schedule Dates
    start_date = Column(DateTime, nullable=True)
    finish_date = Column(DateTime, nullable=True)
    planned_start_date = Column(DateTime, nullable=True)
    scheduled_finish_date = Column(DateTime, nullable=True)
    data_date = Column(DateTime, nullable=True)  # Last schedule update cutoff
    must_finish_by_date = Column(DateTime, nullable=True)  # Contractual deadline

    # Progress & Duration
    duration_percent_complete = Column(Float, nullable=True)  # SummaryDurationPercentComplete
    planned_duration = Column(Float, nullable=True)  # SummaryPlannedDuration
    actual_duration = Column(Float, nullable=True)  # SummaryActualDuration
    remaining_duration = Column(Float, nullable=True)  # SummaryRemainingDuration
    
    # Progress by Units
    actual_non_labor_units = Column(Float, nullable=True)  # SummaryActualNonLaborUnits
    baseline_non_labor_units = Column(Float, nullable=True) # SummaryBaselineNonLaborUnits
    budget_labor_units = Column(Float, nullable=True)  # SummaryBudgetAtCompletionByLaborUnits
    at_completion_non_labor_units = Column(Float, nullable=True) # SummaryAtCompletionNonLaborUnits

    # Activity Counts
    activity_count = Column(Integer, nullable=True)  # SummaryActivityCount
    completed_activity_count = Column(Integer, nullable=True)
    in_progress_activity_count = Column(Integer, nullable=True)
    not_started_activity_count = Column(Integer, nullable=True)

    # Float & Variance (Construction Critical Path)
    total_float = Column(Float, nullable=True)  # SummaryTotalFloat (<=0 = critical)
    finish_date_variance = Column(Float, nullable=True)  # SummaryFinishDateVariance (days)
    start_date_variance = Column(Float, nullable=True)  # SummaryStartDateVariance (days)
    duration_variance = Column(Float, nullable=True)  # SummaryDurationVariance

    # Cost
    actual_total_cost = Column(Float, nullable=True)  # SummaryActualTotalCost
    planned_cost = Column(Float, nullable=True)  # SummaryPlannedCost
    cost_performance_index = Column(Float, nullable=True)  # CPI
    schedule_performance_index = Column(Float, nullable=True)  # SPI
    current_budget = Column(Float, nullable=True)
    total_cost_variance = Column(Float, nullable=True)  # SummaryTotalCostVariance

    # Location & Organization
    location_name = Column(String, nullable=True)
    parent_eps_name = Column(String, nullable=True)

    # Baseline Reference
    current_baseline_project_object_id = Column(BigInteger, nullable=True)

    # Baseline Summary Fields (from Project object)
    baseline_start_date = Column(DateTime, nullable=True)  # SummaryBaselineStartDate
    baseline_finish_date = Column(DateTime, nullable=True)  # SummaryBaselineFinishDate
    baseline_duration = Column(Float, nullable=True)  # SummaryBaselineDuration
    baseline_total_cost = Column(Float, nullable=True)  # SummaryBaselineTotalCost
    baseline_completed_activity_count = Column(Integer, nullable=True)
    baseline_in_progress_activity_count = Column(Integer, nullable=True)
    baseline_not_started_activity_count = Column(Integer, nullable=True)

    # Metadata
    last_synced_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    baselines = relationship("P6BaselineProject", back_populates="project")

    def __repr__(self):
        return f"<P6Project {self.project_id} - {self.name}>"


# ------------------------------------------
# P6 Baseline Project Model
# ------------------------------------------
class P6BaselineProject(Base):
    __tablename__ = "p6_baseline_project"

    id = Column(Integer, primary_key=True, index=True)

    # Core Identification
    p6_object_id = Column(BigInteger, unique=True, index=True, nullable=False)
    original_project_object_id = Column(BigInteger, ForeignKey("p6_project.p6_object_id"), index=True)
    baseline_type_name = Column(String, nullable=True)  # "Project Baseline", etc.
    name = Column(String, nullable=True)

    # Baseline Schedule
    planned_start_date = Column(DateTime, nullable=True)
    finish_date = Column(DateTime, nullable=True)
    scheduled_finish_date = Column(DateTime, nullable=True)
    start_date = Column(DateTime, nullable=True)

    # Baseline Duration & Progress
    planned_duration = Column(Float, nullable=True)  # SummaryPlannedDuration
    actual_duration = Column(Float, nullable=True)  # SummaryActualDuration
    remaining_duration = Column(Float, nullable=True)

    # Baseline Cost
    planned_cost = Column(Float, nullable=True)  # SummaryPlannedCost
    actual_total_cost = Column(Float, nullable=True)
    remaining_total_cost = Column(Float, nullable=True)
    baseline_total_cost = Column(Float, nullable=True)

    # Baseline Activity Counts
    activity_count = Column(Integer, nullable=True)
    completed_activity_count = Column(Integer, nullable=True)
    in_progress_activity_count = Column(Integer, nullable=True)
    not_started_activity_count = Column(Integer, nullable=True)

    # Budget
    current_budget = Column(Float, nullable=True)
    original_budget = Column(Float, nullable=True)
    status = Column(String, nullable=True)

    # Metadata
    last_synced_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    project = relationship("P6Project", back_populates="baselines")

    def __repr__(self):
        return f"<P6BaselineProject {self.p6_object_id} for project {self.original_project_object_id}>"

class MTRequirement(Base):
    __tablename__ = "mt_requirement"

    id = Column(Integer, primary_key=True, index=True)
    activity_name = Column(String, index=True)
    project_name = Column(String, index=True)
    block = Column(String)
    start_date = Column(DateTime)
    activity_id = Column(String, unique=True, index=True)
    budgeted_units_mw = Column(Float)  # Req_Quantity_MW
    unit_of_measure = Column(String)
    project_name_p6 = Column(String)
    spv_plant_code = Column(String, index=True)
    source_of_origin = Column(String)
    upload_time = Column(DateTime, default=datetime.utcnow)

class MTTrialRun(Base):
    __tablename__ = "mt_trialrun"

    id = Column(Integer, primary_key=True, index=True)
    activity_name = Column(String)
    project_name = Column(String)
    project_name_block = Column(String)
    trial_run_start = Column(DateTime)
    trial_run_finish = Column(DateTime)
    activity_id = Column(String, unique=True, index=True)
    tr_quantity_mw = Column(Float)
    unit_of_measure = Column(String)
    project_name_p6 = Column(String)
    spv_plant_code = Column(String, index=True)
    is_start_before_upload = Column(String)
    upload_time = Column(DateTime, default=datetime.utcnow)

class MTPOAmount(Base):
    __tablename__ = "mt_poamount"

    id = Column(Integer, primary_key=True, index=True)
    company_code = Column(String)
    plant_code = Column(String, index=True)
    purchasing_document = Column(String, unique=False, index=True)
    wbs_element = Column(String, index=True)
    material_code = Column(String)
    vendor_code = Column(String)
    vendor_name = Column(String)
    po_quantities = Column(Float)
    material_type = Column(String)
    mw_multiplication_factor = Column(Float)
    po_quantities_mw = Column(Float)
    net_order_value = Column(Float)
    
    # New columns from analysis
    quantity_received = Column(Float, nullable=True)
    still_to_be_delivered_qty = Column(Float, nullable=True)
    delivery_date = Column(DateTime, nullable=True)
    delivery_completed_flag = Column(String, nullable=True)
    deletion_indicator = Column(String, nullable=True)
    document_date = Column(DateTime, nullable=True)
    short_text = Column(String, nullable=True)
    
    # New columns from material logic update
    material_name = Column(String, nullable=True)
    order_quantity = Column(Float, nullable=True)
    net_order_value_inr = Column(Float, nullable=True)
    still_to_deliver_qty = Column(Float, nullable=True)
    still_to_deliver_inr = Column(Float, nullable=True)
    delivered_qty = Column(Float, nullable=True)
    delivered_value_inr_cr = Column(Float, nullable=True)
    storage_location = Column(String, nullable=True)
    block_plot_name = Column(String, nullable=True)
    currency = Column(String, nullable=True)
    buyer_name = Column(String, nullable=True)
    
    upload_time = Column(DateTime, default=datetime.utcnow)

class MTInventory(Base):
    __tablename__ = "mt_inventory"

    id = Column(Integer, primary_key=True, index=True)
    company_code = Column(String)
    plant_code = Column(String, index=True)
    material_code = Column(String)
    quantity_inv = Column(Float)
    vendor_code = Column(String)
    posting_date = Column(DateTime)
    purchase_order = Column(String)
    wbs_element = Column(String, index=True)
    storage_location_mapping = Column(String)
    movement_type_validation = Column(String)
    mw_multiplication_factor = Column(Float)
    quantity_mw = Column(Float)  # Inv_Quantity_MW
    
    # New columns from analysis
    special_stock = Column(String, nullable=True)
    material_type = Column(String, nullable=True)
    material_group = Column(String, nullable=True)
    material_description = Column(String, nullable=True)
    value_unrestricted = Column(Float, nullable=True)
    plant_name = Column(String, nullable=True)
    
    # New columns from material logic update
    material_name = Column(String, nullable=True)
    unrestricted_qty = Column(Float, nullable=True)
    base_unit = Column(String, nullable=True)
    
    upload_time = Column(DateTime, default=datetime.utcnow)

class MTMaterialDocument(Base):
    __tablename__ = "mt_materialdocument"

    id = Column(Integer, primary_key=True, index=True)
    material_code = Column(String, index=True)
    plant_code = Column(String, index=True)
    movement_type = Column(String)
    posting_date = Column(DateTime)
    quantity = Column(Float)
    material_document = Column(String)
    wbs_element = Column(String, index=True)
    
    # New columns from material logic update
    material_name = Column(String, nullable=True)
    material_description = Column(String, nullable=True)
    amount_in_lc = Column(Float, nullable=True)
    amount_in_lc_cr = Column(Float, nullable=True)
    storage_location = Column(String, nullable=True)
    block_plot_name = Column(String, nullable=True)
    purchase_order = Column(String, nullable=True)
    base_unit = Column(String, nullable=True)
    upload_time = Column(DateTime, default=datetime.utcnow)

class MTSLRData(Base):
    __tablename__ = "mt_slr_data"

    id = Column(Integer, primary_key=True, index=True)
    po_document = Column(String, index=True)      # 'A.Document' (PO Number)
    description = Column(String)                  # 'Description'
    actual_amount = Column(Float, nullable=True)  # 'Actual Amount'
    commitment_amount = Column(Float, nullable=True) # 'Commitment Amt'
    wbs_element = Column(String, index=True)      # 'WBS Element'
    type = Column(String, index=True)             # 'Type' (POrd, PReq, etc.)
    plant_code = Column(String, index=True)       # Parsed from first 6 chars of WBS
    
    upload_time = Column(DateTime, default=datetime.utcnow)

class ProjectMapping(Base):
    __tablename__ = "project_mapping"

    id = Column(Integer, primary_key=True, index=True)
    project = Column(String, index=True)            # 'Project'
    spv_name = Column(String)                       # 'SPVName'
    project_id = Column(String, index=True)         # 'Project ID' (P6 mapping key)
    project_name_from_p6 = Column(String)           # 'Project name from P6'
    plot_no = Column(String)                        # 'Plot No'
    category = Column(String)                       # 'Category'
    mms_type = Column(String)                       # 'MMS Type'
    capacity_mwac = Column(Float)                   # 'Capacity (MWac)'
    ol = Column(String)                             # 'OL'
    capacity_mwdc = Column(Float)                   # 'Capacity (MWdc)'
    spv_plant_code = Column(String, index=True)     # 'SPVPlantCode' (SAP mapping key 1)
    agel = Column(String)                           # 'AGEL'
    module_wbs = Column(String, index=True)         # 'Module WBS' (SAP mapping key 2)
    age6l = Column(String)                          # 'AGE6L'
    cluster = Column(String)                        # 'Cluster'
    subcluster = Column(String, nullable=True)      # Sub-cluster / EPC Contractor
    not_allocated = Column(String)                  # 'Not Allocated'
    source_of_origin = Column(String, nullable=True)
    priority = Column(String, nullable=True)
    is_commissioned = Column(Boolean, default=False)
    tc_progress = Column(JSON, nullable=True)  # Added for rich transmission data# ------------------------------------------
# Transmission Portal (Tc) Data Models
# ------------------------------------------

class TcProjectEntry(Base):
    """Stores Khavda-style flat hierarchy projects"""
    __tablename__ = "tc_project_entry"

    id = Column(Integer, primary_key=True, index=True)
    region = Column(String, index=True)  # 'Khavda' or 'Rajasthan'
    project = Column(String, index=True) # E.g. "MLP T1 PPA - J&K"
    phase = Column(String)
    kps = Column(String)
    pss = Column(String)
    block = Column(String)
    breakup = Column(String)
    mw = Column(Float, nullable=True)
    
    # Mapping to global projects
    mapping_id = Column(Integer, ForeignKey("project_mapping.id"), nullable=True)
    
    upload_time = Column(DateTime, default=datetime.utcnow)

class TcNetworkNode(Base):
    """Stores Substation Nodes from Rajasthan/Khavda network data"""
    __tablename__ = "tc_network_node"

    id = Column(Integer, primary_key=True, index=True)
    region = Column(String, index=True)
    node_id = Column(String, index=True)
    label = Column(String)
    type = Column(String)
    status = Column(String)
    x = Column(Float, nullable=True)
    y = Column(Float, nullable=True)
    
    upload_time = Column(DateTime, default=datetime.utcnow)

class TcNetworkEdge(Base):
    """Stores Transmission Lines (Edges) from network data"""
    __tablename__ = "tc_network_edge"

    id = Column(Integer, primary_key=True, index=True)
    region = Column(String, index=True)
    edge_id = Column(String, index=True)
    from_node = Column(String)
    from_label = Column(String)
    to_node = Column(String)
    to_label = Column(String)
    
    projects = Column(String) # JSON serialized string of projects array
    contractor = Column(String)
    voltage = Column(String)
    length = Column(String) # Stored as string because sometimes it contains empty or weird chars in JSON
    
    status = Column(String)
    normalized_status = Column(String)
    
    erection = Column(String)
    foundation = Column(String)
    stringing = Column(String)
    expected_date = Column(String)
    scd = Column(String)
    charged_date = Column(String)
    is_delayed = Column(Boolean)
    
    # Optional mapping to a primary global project if possible, though edges often span multiple projects
    mapping_id = Column(Integer, ForeignKey("project_mapping.id"), nullable=True)
    
    upload_time = Column(DateTime, default=datetime.utcnow)

class P6Activity(Base):
    __tablename__ = "p6_activity"

    id = Column(Integer, primary_key=True, index=True)
    p6_object_id = Column(BigInteger, unique=True, index=True, nullable=False)
    activity_id = Column(String, index=True)
    name = Column(String)
    status = Column(String)
    type = Column(String)
    
    start_date = Column(DateTime, nullable=True)
    finish_date = Column(DateTime, nullable=True)
    planned_start_date = Column(DateTime, nullable=True)
    planned_finish_date = Column(DateTime, nullable=True)
    actual_start_date = Column(DateTime, nullable=True)
    actual_finish_date = Column(DateTime, nullable=True)
    # Baseline dates (per-activity baseline from P6)
    baseline_start_date = Column(DateTime, nullable=True)
    baseline_finish_date = Column(DateTime, nullable=True)
    
    planned_duration = Column(Float, nullable=True)
    actual_duration = Column(Float, nullable=True)
    remaining_duration = Column(Float, nullable=True)
    
    percent_complete = Column(Float, nullable=True)
    
    total_float = Column(Float, nullable=True)
    is_critical = Column(Boolean, nullable=True)
    
    wbs_object_id = Column(BigInteger, nullable=True)
    wbs_name = Column(String, nullable=True)
    wbs_code = Column(String, nullable=True)
    
    project_object_id = Column(BigInteger, ForeignKey("p6_project.p6_object_id"), index=True)
    
    last_synced_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("P6Project", backref="activities")

class P6ResourceAssignment(Base):
    __tablename__ = "p6_resource_assignment"

    id = Column(Integer, primary_key=True, index=True)
    p6_object_id = Column(BigInteger, unique=True, index=True, nullable=False)
    activity_object_id = Column(BigInteger, ForeignKey("p6_activity.p6_object_id"), index=True)
    project_object_id = Column(BigInteger, ForeignKey("p6_project.p6_object_id"), index=True)
    
    resource_type = Column(String)  # Labor, Nonlabor, Material
    resource_name = Column(String, nullable=True)
    
    planned_units = Column(Float, nullable=True)
    actual_units = Column(Float, nullable=True)
    
    last_synced_at = Column(DateTime, default=datetime.utcnow)

    activity = relationship("P6Activity", backref="resource_assignments")

class P6ActivityRisk(Base):
    __tablename__ = "p6_activity_risk"

    id = Column(Integer, primary_key=True, index=True)
    activity_object_id = Column(BigInteger, ForeignKey("p6_activity.p6_object_id"), index=True, nullable=False)
    project_object_id = Column(BigInteger, ForeignKey("p6_project.p6_object_id"), index=True, nullable=False)
    
    risk_id = Column(String, index=True)
    risk_name = Column(String)
    risk_object_id = Column(BigInteger)
    
    activity_id = Column(String)
    activity_name = Column(String)
    
    last_synced_at = Column(DateTime, default=datetime.utcnow)

# ==========================================
# Notification Model
# ==========================================
class Notification(Base):
    __tablename__ = "notification"

    id = Column(Integer, primary_key=True, index=True)
    project_name = Column(String, index=True, nullable=True)
    module = Column(String, index=True)  # P6 / Transmission
    change_type = Column(String)  # Date Change / Budget Exceeded / Status Update / Critical Date Slip
    message = Column(String)
    
    # Structured Data
    block = Column(String, nullable=True)
    activity_name = Column(String, nullable=True)
    old_value = Column(String, nullable=True)
    new_value = Column(String, nullable=True)
    reason = Column(String, nullable=True)
    
    # Action & Category
    action_status = Column(String, default="Pending") # Pending, Acknowledged, Resolved
    category = Column(String, index=True, default="Other") # Budgets, COD, Trials, Dates
    
    # P6 Linking for Push
    p6_object_id = Column(BigInteger, nullable=True)
    p6_type = Column(String, nullable=True) # Activity, Project, ResourceAssignment
    
    ai_suggestion = Column(String, nullable=True) # Pre-generated AI suggestion for the notification
    
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, index=True, default=datetime.utcnow)
    
    threads = relationship("NotificationThread", back_populates="notification", cascade="all, delete-orphan")


class NotificationThread(Base):
    __tablename__ = "notification_thread"

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(Integer, ForeignKey("notification.id", ondelete="CASCADE"), index=True)
    sender = Column(String)  # e.g. "PMAG", "User"
    message = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    notification = relationship("Notification", back_populates="threads")


# ==========================================
# Intelligent Chatbot Models
# ==========================================

class MetricsCache(Base):
    """Per-project computed metrics cache with freshness tracking.
    Avoids recomputing dashboard/360/variance data on every chat question.
    Only invalidated when upstream data actually changes (Step 2-3 of pipeline).
    """
    __tablename__ = "metrics_cache"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, nullable=False, index=True)
    cache_key = Column(String, nullable=False)  # 'dashboard' | 'project_360' | 'variance'
    data = Column(JSON, nullable=False)          # The cached computed result
    computed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    # Snapshots of sync timestamps when this cache entry was computed
    p6_synced_at = Column(DateTime, nullable=True)
    sap_synced_at = Column(DateTime, nullable=True)
    tc_synced_at = Column(DateTime, nullable=True)


class ChatSession(Base):
    """Server-side conversation sessions — replaces browser localStorage."""
    __tablename__ = "chat_session"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, nullable=False, unique=True, index=True)
    title = Column(String, nullable=True)        # Auto-generated from first message
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    """Individual chat messages with full provenance metadata.
    Every response records what data was used, how fresh it was, and how long it took.
    """
    __tablename__ = "chat_message"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("chat_session.session_id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, nullable=False)          # 'user' | 'assistant'
    content = Column(String, nullable=False)
    # Intent metadata (from Step 1)
    intent_type = Column(String, nullable=True)    # 'factual' | 'analytical' | 'advisory' | 'document'
    project_ids = Column(String, nullable=True)    # Comma-separated project IDs referenced
    data_domains = Column(String, nullable=True)   # Comma-separated: 'p6,sap,tc'
    # Provenance (from Step 5)
    data_as_of = Column(DateTime, nullable=True)   # Freshness timestamp of data used
    sources_used = Column(JSON, nullable=True)     # {"tables": [...], "cache_hit": true}
    # Performance
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")
    feedback = relationship("ChatFeedback", back_populates="message", cascade="all, delete-orphan")


class ChatFeedback(Base):
    """User feedback on chatbot responses — the self-improving memory loop (Step 6).
    Corrections get injected into future prompts for the same project/question pattern.
    """
    __tablename__ = "chat_feedback"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("chat_message.id", ondelete="CASCADE"), nullable=False, index=True)
    feedback_type = Column(String, nullable=False)   # 'thumbs_up' | 'thumbs_down' | 'correction'
    correction_text = Column(String, nullable=True)  # User's correction if provided
    project_id = Column(String, nullable=True)       # Which project this feedback is about
    question_pattern = Column(String, nullable=True)  # Normalized question for pattern matching
    created_at = Column(DateTime, default=datetime.utcnow)

    message = relationship("ChatMessage", back_populates="feedback")


# ==========================================
# Pulse Quality Management Models
# ==========================================

class PulseNC(Base):
    """Non-Conformance records from Pulse quality system.
    Flattened from deeply nested OData $expand for fast dashboard queries."""
    __tablename__ = "pulse_nc"

    id = Column(Integer, primary_key=True, index=True)
    pulse_id = Column(String, unique=True, index=True, nullable=False)  # Pulse UUID

    # Core NC fields
    nc_label = Column(String, index=True)
    status = Column(String, index=True)           # raised, submitted, approved, completed, rejected
    status_label = Column(String)                  # Raised, In Review EE, In Review QI, Approved, Rejected
    category = Column(String, index=True)          # Critical, Non Critical
    defect_type = Column(String)
    description = Column(String, nullable=True)
    quantity = Column(Float, nullable=True)
    ad_hoc = Column(Boolean, default=True)
    archived = Column(Boolean, default=False)
    version = Column(Integer, nullable=True)
    current_handler = Column(String, index=True)   # contractor, execution_engineer, quality_inspector

    # Financial penalty
    debit = Column(Float, nullable=True)
    debit_reason = Column(String, nullable=True)

    # Location (flattened from WORKAREA, WORKLOCATION, CLUSTER)
    cluster_name = Column(String, index=True)      # Gujarat, Rajasthan
    project_name = Column(String, index=True)      # BESS PSS-12 Project
    project_id = Column(String, index=True)        # Pulse project UUID
    project_type = Column(String, nullable=True)   # bess, solar, pss
    spv_name = Column(String, nullable=True)       # AGE27CL
    worklocation_name = Column(String, nullable=True)  # BESS PSS-12
    workarea_name = Column(String, nullable=True)  # BL07 (block)

    # People (flattened from CONTRACTOR, ENGINEER, QUALITY)
    contractor_name = Column(String, nullable=True)
    vendor_name = Column(String, index=True, nullable=True)
    vendor_code = Column(String, nullable=True)
    engineer_name = Column(String, nullable=True)
    quality_name = Column(String, nullable=True)

    # Work breakdown (flattened from SUBACTIVITY → ACTIVITY → SUBPACKAGE → PACKAGE)
    package_name = Column(String, index=True, nullable=True)      # Civil
    subpackage_name = Column(String, nullable=True)                # CT Foundation
    activity_name = Column(String, nullable=True)                  # 6. CT Foundation Backfilling with Compaction
    subactivity_name = Column(String, nullable=True)               # Compaction & FDD test

    # Service order
    service_order_number = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)

    # Sync metadata
    last_synced_at = Column(DateTime, default=datetime.utcnow)


class PulseRFI(Base):
    """Request-For-Inspection records from Pulse quality system."""
    __tablename__ = "pulse_rfi"

    id = Column(Integer, primary_key=True, index=True)
    pulse_id = Column(String, unique=True, index=True, nullable=False)

    # Core RFI fields
    rfi_label = Column(String, index=True)
    status = Column(String, index=True)
    status_label = Column(String)
    current_handler = Column(String, nullable=True)

    # Location
    cluster_name = Column(String, index=True)
    project_name = Column(String, index=True)
    project_id = Column(String, index=True)
    project_type = Column(String, nullable=True)
    spv_name = Column(String, nullable=True)
    worklocation_name = Column(String, nullable=True)
    workarea_name = Column(String, nullable=True)

    # People
    contractor_name = Column(String, nullable=True)
    vendor_name = Column(String, nullable=True)
    engineer_name = Column(String, nullable=True)
    quality_name = Column(String, nullable=True)

    # Work breakdown
    package_name = Column(String, nullable=True)
    inspection_point_name = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)

    # Sync metadata
    last_synced_at = Column(DateTime, default=datetime.utcnow)

# ==========================================
# E-Invoice Model
# ==========================================
class EInvoiceRecord(Base):
    __tablename__ = "einvoice_records"

    id = Column(Integer, primary_key=True, index=True)
    invoiceNo = Column(String, index=True)
    invoiceCode = Column(String)
    invoiceRequestID = Column(Integer)
    vendorName = Column(String, index=True)
    sapVendorCode = Column(String)
    projectType = Column(String, index=True)
    packageName = Column(String, index=True)
    workLocation = Column(String, index=True)
    site = Column(String)
    invoiceAmount = Column(Float)
    soAmount = Column(Float)
    statusDesc = Column(String, index=True)
    invoiceDate = Column(DateTime)
    createdAt = Column(DateTime)
    completionDate = Column(DateTime)
    workDescription = Column(String)
    workOrderNo = Column(String, index=True)
    p6ProjectName = Column(String, index=True)
    # Workflow fields
    stage = Column(String, index=True)
    isPending = Column(Boolean, default=False, index=True)
    submittedOn = Column(DateTime)
    currentApprover = Column(String)
    latestAction = Column(String)
