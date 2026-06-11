from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

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

class MTInTransit(Base):
    __tablename__ = "mt_intransit"

    id = Column(Integer, primary_key=True, index=True)
    material_code = Column(String, index=True)
    inbound_delivery_quantity = Column(Float)
    company_code = Column(String)
    plant_code = Column(String, index=True)
    gr_posting_date = Column(DateTime, nullable=True)
    ariba_invoice_date = Column(DateTime, nullable=True)
    vendor_code = Column(String)
    vendor_name = Column(String)
    po_number = Column(String)
    wbs_element = Column(String, index=True)
    mw_multiplication_factor = Column(Float)
    quantity_mw = Column(Float)  # IT_Quantity_MW
    
    # New columns from analysis
    grn_quantity = Column(Float, nullable=True)
    ibd_creation_date = Column(DateTime, nullable=True)
    po_quantity = Column(Float, nullable=True)
    rejected_quantity = Column(Float, nullable=True)
    
    upload_time = Column(DateTime, default=datetime.utcnow)

class MTPOAmount(Base):
    __tablename__ = "mt_poamount"

    id = Column(Integer, primary_key=True, index=True)
    company_code = Column(String)
    plant_code = Column(String, index=True)
    purchasing_document = Column(String, unique=True, index=True)
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
    upload_time = Column(DateTime, default=datetime.utcnow)

class MTUnderConstruction(Base):
    __tablename__ = "mt_underconstruction"

    id = Column(Integer, primary_key=True, index=True)
    company_code = Column(String)
    plant_code = Column(String, index=True)
    material_code = Column(String)
    quantity_uc = Column(Float)
    vendor_code = Column(String)
    posting_date = Column(DateTime)
    purchase_order = Column(String)
    storage_location_mapping = Column(String)
    movement_type_validation = Column(String)
    mw_multiplication_factor = Column(Float)
    quantity_mw = Column(Float)  # UC_Quantity_MW
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
    not_allocated = Column(String)                  # 'Not Allocated'# ------------------------------------------
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
    
    # Optional mapping to a primary global project if possible, though edges often span multiple projects
    mapping_id = Column(Integer, ForeignKey("project_mapping.id"), nullable=True)
    
    upload_time = Column(DateTime, default=datetime.utcnow)
