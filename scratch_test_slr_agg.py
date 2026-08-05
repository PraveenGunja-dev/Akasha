import pandas as pd

filepath = r'd:\Akasha_Platform\Data\NEW31\ZPSPS007 (3).xlsx'
print(f"Reading {filepath}...")
df = pd.read_excel(filepath)

print(f"Original rows: {len(df)}")

# 1. Filter out 'Summary' == 'X'
if 'Summary' in df.columns:
    df = df[df['Summary'].isna() | (df['Summary'].astype(str).str.strip() == '') | (df['Summary'].astype(str).str.lower() == 'nan')]
print(f"After Summary filter: {len(df)}")

# 2. Extract types and ensure numeric amounts
df['Commitment Amt'] = pd.to_numeric(df['Commitment Amt'], errors='coerce').fillna(0.0)
df['Actual Amount'] = pd.to_numeric(df['Actual Amount'], errors='coerce').fillna(0.0)

# 3. Filter out both zero
df = df[(df['Commitment Amt'] != 0) | (df['Actual Amount'] != 0)]
print(f"After 0/0 filter: {len(df)}")

# 4. Group by C.Document, WBS, Type, Description to sum amounts
# C.Document is PO/PR
df['C.Document'] = df['C.Document'].fillna('').astype(str).str.strip()
df['WBS Element'] = df['WBS Element'].fillna('').astype(str).str.strip()
df['Type'] = df['Type'].fillna('').astype(str).str.strip()
df['Description'] = df['Description'].fillna('').astype(str).str.strip()

agg_df = df.groupby(['C.Document', 'WBS Element', 'Type', 'Description'], as_index=False).agg({
    'Commitment Amt': 'sum',
    'Actual Amount': 'sum'
})

print(f"After grouping/aggregation (distinct rows): {len(agg_df)}")
print("\nSample aggregated rows:")
print(agg_df.head(10))
