import sys
import os
import pdfplumber
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal
from routers.module_deliveries import get_module_deliveries_summary

def parse_date(d_str):
    if not d_str or str(d_str).strip() in ('-', 'None', ''):
        return None
    try:
        return datetime.strptime(str(d_str).strip(), '%d-%b-%y').strftime('%d-%b-%y')
    except Exception:
        return str(d_str).strip()

def extract_pdf_data(pdf_path):
    rows_data = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table:
                continue
            
            header_idx = -1
            for i, row in enumerate(table):
                if row and str(row[0]).strip() == 'Sr':
                    header_idx = i
                    break
            
            if header_idx == -1:
                continue
                
            for row in table[header_idx+2:]:
                if not row or not row[0] or not str(row[0]).strip().isdigit():
                    continue
                
                try:
                    r_dict = {
                        'project': str(row[1]).strip().replace('\n', ' '),
                        'spv': str(row[2]).strip(),
                        'capacity_mwp': float(str(row[10]).replace(',', '')) if row[10] else 0,
                        'lta': parse_date(row[12]),
                        'scod': parse_date(row[13]),
                        'ordered': float(str(row[15]).replace(',', '')) if row[15] and str(row[15]).strip() != '-' else 0,
                        'total_receipt': float(str(row[17]).replace(',', '')) if row[17] and str(row[17]).strip() != '-' else 0,
                    }
                    rows_data.append(r_dict)
                except Exception as e:
                    print(f"Error parsing PDF row {row}: {e}")
                    
    return rows_data

def main():
    pdf_path = r"d:\Akasha_Platform\Data\Khavda FY 26-27 Solar Projects Module Deliveries_02-Sep-26.pdf"
    
    print("Extracting PDF data...")
    pdf_data = extract_pdf_data(pdf_path)
    
    print("Fetching API data...")
    db = SessionLocal()
    api_summary = get_module_deliveries_summary(db)
    api_projects = api_summary["projects"]
    
    report_path = r"C:\Users\USER\.gemini\antigravity-ide\brain\4a4a94fa-5cd0-46a2-a26e-87a61705a967\pdf_comparison_report.md"
    
    with open(report_path, "w") as f:
        f.write("# Module Deliveries: PDF vs Database Validation Report\n\n")
        f.write("This report compares the values in the CEO tracker PDF with the live data in our application.\n\n")
        
        mismatches = []
        matches = 0
        
        for pdf_row in pdf_data:
            proj_name = pdf_row['project']
            spv = pdf_row['spv']
            
            matched_api = None
            for ap in api_projects:
                api_name = ap['project_name'].replace('\n', ' ')
                if proj_name.lower() in api_name.lower() or api_name.lower() in proj_name.lower():
                    matched_api = ap
                    break
                    
            if not matched_api:
                mismatches.append(f"**{proj_name}** ({spv}): Not found in API data.")
                continue
                
            issues = []
            
            if abs(pdf_row['capacity_mwp'] - matched_api['capacity_mwp']) > 1:
                issues.append(f"Capacity MWp mismatch: PDF={pdf_row['capacity_mwp']}, API={matched_api['capacity_mwp']}")
                
            if abs(pdf_row['ordered'] - matched_api['ordered_mwp']) > 1:
                issues.append(f"Ordered MWp mismatch: PDF={pdf_row['ordered']}, API={matched_api['ordered_mwp']}")
                
            if abs(pdf_row['total_receipt'] - matched_api['total_receipt_mwp']) > 1:
                issues.append(f"Total Receipt MWp mismatch: PDF={pdf_row['total_receipt']}, API={matched_api['total_receipt_mwp']}")
                
            if pdf_row['lta'] and pdf_row['lta'] != matched_api['lta']:
                issues.append(f"LTA mismatch: PDF={pdf_row['lta']}, API={matched_api['lta']}")
                
            if pdf_row['scod'] and pdf_row['scod'] != matched_api['scod']:
                issues.append(f"SCOD mismatch: PDF={pdf_row['scod']}, API={matched_api['scod']}")
                
            if issues:
                issue_str = "\n".join([f"  - {i}" for i in issues])
                mismatches.append(f"**{proj_name}**:\n{issue_str}")
            else:
                matches += 1
                
        f.write(f"**Total PDF Projects Parsed:** {len(pdf_data)}\n")
        f.write(f"**Projects fully matching (within tested fields):** {matches}\n")
        f.write(f"**Projects with discrepancies:** {len(mismatches)}\n\n")
        
        if mismatches:
            f.write("## Discrepancies\n\n")
            for m in mismatches:
                f.write(f"- {m}\n")
                
    print(f"Report generated at {report_path}")

if __name__ == "__main__":
    main()
