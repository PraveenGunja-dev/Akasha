import pandas as pd
import os

def test_join():
    data_dir = r"D:\Akasha_Platform\Data\NEW31"
    me2j_path = os.path.join(data_dir, "Me2J 1.xlsx")
    zsps_path = os.path.join(data_dir, "ZPSPS007 (3).xlsx")
    
    print("Reading ME2J...")
    df_me2j = pd.read_excel(me2j_path, usecols=['Purchasing Document', 'Buyer Name', 'Document Date', 'Storage Location', 'Material', 'Plant', 'Currency', 'Delivery Completed'])
    # Drop duplicates by PO Number to create a mapping
    df_me2j = df_me2j.drop_duplicates(subset=['Purchasing Document'])
    print(f"ME2J unique POs: {len(df_me2j)}")
    
    print("Reading ZSPS...")
    df_zsps = pd.read_excel(zsps_path, usecols=['C.Document', 'WBS Element']).head(10)
    
    # Merge
    merged = pd.merge(df_zsps, df_me2j, left_on='C.Document', right_on='Purchasing Document', how='left')
    print("Merged sample:")
    print(merged.head())

if __name__ == "__main__":
    test_join()
