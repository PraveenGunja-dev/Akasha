import pandas as pd

def analyze_zsps():
    path = r'D:\Akasha_Platform\Data\NEW31\ZPSPS007 (3).xlsx'
    df = pd.read_excel(path)
    
    # Filter where C.Document is not null (has PO)
    df_po = df[df['C.Document'].notna()].head(5)
    print("--- Sample PO records ---")
    for _, row in df_po.iterrows():
        print(row[['WBS Element', 'C.Document', 'Commitment Amt', 'Actual Amount', 'C.Quantity', 'A.Quantity', 'Vendor Name', 'Short text']].to_dict())

if __name__ == "__main__":
    analyze_zsps()
