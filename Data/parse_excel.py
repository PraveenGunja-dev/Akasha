import pandas as pd
import json

def get_excel_info(file_path):
    try:
        df = pd.read_excel(file_path, nrows=5)
        return {
            "columns": list(df.columns),
            "sample_data": df.head(2).to_dict(orient='records')
        }
    except Exception as e:
        return {"error": str(e)}

def main():
    files = [
        r"d:\Akasha_Platform\Data\Project_Name_Master (1).xlsx"
    ]
    results = {}
    for f in files:
        results[f] = get_excel_info(f)
        
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
