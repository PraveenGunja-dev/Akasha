import json
import logging
from sqlalchemy.orm import Session
from database import SessionLocal
import models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_or_create_project(db: Session, proj_id: str, proj_name: str, cluster: str, subcluster: str = None):
    """Helper function to update or create a ProjectMapping record."""
    rec = db.query(models.ProjectMapping).filter_by(project_id=proj_id).first()
    if rec:
        rec.project_name_from_p6 = proj_name
        rec.cluster = cluster
        rec.subcluster = subcluster
        # Clear out the unused category
        rec.category = None
        logger.info(f"Updated {proj_id} -> Cluster: {cluster}, Sub-Cluster: {subcluster}")
    else:
        new_proj = models.ProjectMapping(
            project_id=proj_id,
            project_name_from_p6=proj_name,
            cluster=cluster,
            subcluster=subcluster,
            category=None
        )
        db.add(new_proj)
        logger.info(f"Added NEW project {proj_id} -> Cluster: {cluster}, Sub-Cluster: {subcluster}")

def run_vm_migration():
    logger.info("Starting VM DB Migration for Project Mappings & Cleanup...")
    db: Session = SessionLocal()
    
    try:
        # Handle the typo ID from old DB before mapping new ones to avoid conflicts
        old_p13 = db.query(models.ProjectMapping).filter_by(project_id="FY27-P13").first()
        if old_p13 and old_p13.project_name_from_p6 == "ASEJ6PL_S07_FT_300MW_PPA":
            db.delete(old_p13)
            logger.info("Removed erroneous FY27-P13 before creating correct FY26-P13")
            
        old_p07_space = db.query(models.ProjectMapping).filter_by(project_id="FY26- P07").first()
        if old_p07_space:
            db.delete(old_p07_space)
            logger.info("Removed erroneous 'FY26- P07'")

        # ==========================================
        # 1. SOLAR KHAVDA RECONCILIATION
        # ==========================================
        logger.info("--- 1. Mapping 46 Solar Khavda Projects with Sub-Clusters ---")
        
        # AGEL Projects (20 + 1)
        agel = [
            ("FY27-P16-3-2", "NHPC EPC 600 MW Khavda-I"),
            ("FY27-P06&07", "ARE55L_S02A_HSAT_250 MW_PPA"),
            ("FY26-P26", "ARE55L_S10_HSAT_50 MW_PPA"),
            ("FY26-P04", "ARE57L_A12_HSAT_350MW_PPA"),
            ("FY25-P15", "AGE25CL_A06_FT_425MW_PPA"),
            ("FY25-P14", "AGE26AL_A10a_FT_50MW_PPA_Commissioned"),
            ("FY25-P13", "AGE26AL_A16_FT_333MW_PPA_Commissioned"),
            ("FY25-P12", "AGE26AL_A16C_FT_167MW_PPA_Commissioned"),
            ("FY25-P11", "AGE26AL_A16_FT_200MW_PPA_Commissioned"),
            ("FY25-P10", "AGE26AL_A16_FT_50MW_PPA_Commissioned"),
            ("FY25-P09", "AGE25CL_A06_HSAT_75MW_PPA_Commissioned"),
            ("FY25-P08", "ACL_A1_FT_125MW_GROUP_Commissioned"),
            ("FY25-P07", "AGE24L_A14_HSAT_150MW_MERCHANT_Commissioned"),
            ("FY25-P06", "AGE24L_S05_HSAT_150MW_MERCHANT_Commissioned"),
            ("FY25-P05", "AGE26BL_S05_HSAT_292MW_MERCHANT_HYBRID_Commissioned"),
            ("FY25-P04", "AHEJ5L_A15a_HSAT_150MW_MERCHANT"),
            ("FY25-P03", "ARE48L_S08_HSAT_100MW_MERCHANT"),
            ("FY25-P02", "ASEJ6PL_A06_HSAT_35MW_MERCHANT_Commissioned"),
            ("FY25-P01", "ARE3L_A06_HSAT_25MW_MERCHANT_Commissioned"),
            ("FY27-P05", "AGEL_S10_287.5_MW_HSAT"),
            ("FY26-P12", "AGE24L_A03_HSAT_250MW")
        ]
        for pid, pname in agel:
            update_or_create_project(db, pid, pname, "Solar Khavda", "AGEL Projects")
            
        # Larsen and Toubro Limited (9)
        l_and_t = [
            ("FY26-P25", "AE3L_S01_HSAT_75_MW_MERCHANT"),
            ("FY26-P24", "ARE55L_S02B_HSAT_12.5_MW_PPA"),
            ("FY26-P22", "ARE55L_S01_HSAT_200_MW_PPA"),
            ("FY26-P20", "ARE55L_S02A_HSAT_50_MW_PPA"),
            ("FY26-P19", "ARE55L_S01_HSAT_100_MW_PPA"),
            ("FY26-P17", "ARE55L_S02A_HSAT_175_MW_PPA"),
            ("FY26-P10", "ARE55L_A02_HSAT_125MW"),
            ("FY26-P09", "ARE55L_A01_HSAT_150MW_Group_NEW"),
            ("FY26-P08", "ARE8L_A02_HSAT_150MW_PPA_TPL")
        ]
        for pid, pname in l_and_t:
            update_or_create_project(db, pid, pname, "Solar Khavda", "Larsen and Toubro Limited")
            
        # Amara Raja (1)
        amara_raja = [("FY26-P07", "ACL_A01_HSAT_50MW_Group_NEW")]
        for pid, pname in amara_raja:
            update_or_create_project(db, pid, pname, "Solar Khavda", "Amara Raja")
            
        # Sterling and Wilson (3)
        sterling = [
            ("FY26-P23", "ARE55L_A18_HSAT_600MW_PPA"),
            ("FY26-P15", "ARE55L_S09_HSAT_400MW_PPA"),
            ("FY26-P06", "ARE55L_A15b_HSAT_50MW_PPA")
        ]
        for pid, pname in sterling:
            update_or_create_project(db, pid, pname, "Solar Khavda", "Sterling and Wilson")
            
        # KPI Green Energy Limited (1)
        kpi = [("FY26-P18", "AGE26AL_S06A_FT_234MW_PPA")]
        for pid, pname in kpi:
            update_or_create_project(db, pid, pname, "Solar Khavda", "KPI Green Energy Limited")
            
        # Bondada Engineering Limited (2)
        bondada = [
            ("FY26-P14", "ASEJ6PL_S07_FT_300MW_PPA"),
            ("FY26-P13", "ASEJ6PL_S07_FT_300MW_PPA")
        ]
        for pid, pname in bondada:
            update_or_create_project(db, pid, pname, "Solar Khavda", "Bondada Engineering Limited")
            
        # Hild Energy Private Limited (4)
        hild = [
            ("FY26-P05", "AHEJ5L_S04_HSAT_300MW_MERCHANT_HYBRID"),
            ("FY25-P18&19&20", "AGE25BL_A15a_HSAT_50MW_MERCHANT"),
            ("FY27-P01&P02", "ARE55L_S03_HSAT_500MW_MERCHANT"),
            ("FY27-P03&04", "AGEL_SE14_HSAT_500MW_HILD")
        ]
        for pid, pname in hild:
            update_or_create_project(db, pid, pname, "Solar Khavda", "Hild Energy Private Limited")
            
        # Enrich Energy Private Limited (5)
        enrich = [
            ("FY26-P21", "AE2L_S03_HSAT_150MW_MERCHANT"),
            ("FY26-P12-5", "AGE26BL_A03_HSAT_250MW_LTP_T4_AP_NEW"),
            ("FY26-P03", "ACL_A01_E_FT_25MW_GROUP_NEW"),
            ("FY26-P02", "APSEZ_A01_D_HSAT_25MW_GROUP"),
            ("FY26-P01", "ARE41L_A01-C_HSAT_25MW_MERCHANT")
        ]
        for pid, pname in enrich:
            update_or_create_project(db, pid, pname, "Solar Khavda", "Enrich Energy Private Limited")

        # ==========================================
        # 2. SOLAR RAJASTHAN RECONCILIATION
        # ==========================================
        logger.info("\n--- 2. Mapping 3 Solar Rajasthan Projects ---")
        rajasthan_projects = [
            ("FY26-LUDBAY_150MW", "ARE8L_LUDBAY_FT_150MW_PPA"),
            ("FY25-BANDHA_500MW", "AGE25BL_BANDHA_FT_500MW_PPA"),
            ("FY25-BAIYA_600MW", "ASEB1PL_BAIYA_FT_600MW_PPA")
        ]
        for pid, pname in rajasthan_projects:
            update_or_create_project(db, pid, pname, "Solar Rajasthan", "None")

        # ==========================================
        # 3. BESS RECONCILIATION
        # ==========================================
        logger.info("\n--- 3. Mapping 6 BESS Projects ---")
        bess_projects = [
            ("AGE27CL_PSS12_FINAL", "AGE27CL_PSS12"),
            ("AGE27BL_PSS11_FINAL", "AGES11_PSS11"),
            ("ARE35L_PSS10B_FINAL", "ARE35L_PSS10B"),
            ("AGE35L_PSS8B_FINAL", "AGE35L_PSS8B"),
            ("AGE44L_PSS5B_FINAL", "AGE44L_PSS5B"),
            ("AGE27AL_PSS09_FINAL", "AGE27AL_PSS09")
        ]
        for pid, pname in bess_projects:
            update_or_create_project(db, pid, pname, "BESS", "None")
            
        # NOTE: Wind is kept automatically assuming the existing ones have cluster='Wind'.
        
        # ==========================================
        # 3.5 REMOVE LEGACY NON-CORE PROJECTS
        # ==========================================
        logger.info("\n--- 3.5 Removing Legacy Projects ---")
        mappings = db.query(models.ProjectMapping).all()
        to_delete = []
        for m in mappings:
            cluster = str(m.cluster).strip() if m.cluster else ""
            category = str(m.category).strip() if m.category else ""
            is_khavda = cluster == "Solar Khavda"
            is_rajasthan = cluster == "Solar Rajasthan"
            is_bess = cluster == "BESS" or category == "BESS"
            is_wind = cluster == "Wind" or "wind" in category.lower()
            
            # Ensure proper migration for BESS and Wind
            if is_bess and cluster != "BESS":
                m.cluster = "BESS"
                m.category = None
                
            if is_wind and cluster != "Wind":
                m.cluster = "Wind"
                m.category = None
            
            if not (is_khavda or is_rajasthan or is_bess or is_wind):
                to_delete.append(m)
                
        if to_delete:
            mapping_ids = [m.id for m in to_delete]
            try:
                db.query(models.TcNetworkEdge).filter(models.TcNetworkEdge.mapping_id.in_(mapping_ids)).delete(synchronize_session=False)
            except Exception:
                pass
            try:
                db.query(models.TcProjectEntry).filter(models.TcProjectEntry.mapping_id.in_(mapping_ids)).delete(synchronize_session=False)
            except Exception:
                pass
            for m in to_delete:
                db.delete(m)
            logger.info(f"Deleted {len(to_delete)} legacy projects from ProjectMapping.")
        else:
            logger.info("No legacy projects found to delete.")

        db.commit()
        logger.info("Successfully committed all project mappings!")

        # ==========================================
        # 4. UNMAPPED P6 DATA CLEANUP
        # ==========================================
        logger.info("\n--- 4. Cleaning Up Unmapped P6 Data ---")
        mapped_ids = {m.project_id for m in db.query(models.ProjectMapping).all()}
        all_p6 = db.query(models.P6Project).all()
        
        unmapped_p6_objs = [p.p6_object_id for p in all_p6 if p.project_id not in mapped_ids]
        logger.info(f"Found {len(unmapped_p6_objs)} unmapped P6 projects to delete...")
        
        if unmapped_p6_objs:
            # Delete children first (foreign keys)
            db.query(models.P6ActivityRisk).filter(models.P6ActivityRisk.project_object_id.in_(unmapped_p6_objs)).delete(synchronize_session=False)
            db.query(models.P6ResourceAssignment).filter(models.P6ResourceAssignment.project_object_id.in_(unmapped_p6_objs)).delete(synchronize_session=False)
            db.query(models.P6Activity).filter(models.P6Activity.project_object_id.in_(unmapped_p6_objs)).delete(synchronize_session=False)
            db.query(models.P6WBSNode).filter(models.P6WBSNode.project_object_id.in_(unmapped_p6_objs)).delete(synchronize_session=False)
            db.query(models.P6BaselineProject).filter(models.P6BaselineProject.original_project_object_id.in_(unmapped_p6_objs)).delete(synchronize_session=False)
            db.query(models.P6Project).filter(models.P6Project.p6_object_id.in_(unmapped_p6_objs)).delete(synchronize_session=False)
            
            db.commit()
            logger.info("Successfully deleted all unmapped P6 bloated data from the database.")
        else:
            logger.info("No unmapped P6 projects to clean up.")

        logger.info("\n*** VM MIGRATION COMPLETED SUCCESSFULLY ***")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db.rollback()

if __name__ == "__main__":
    run_vm_migration()
