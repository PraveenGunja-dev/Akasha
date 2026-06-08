import pandas as pd
file_path = r"d:\Akasha_Platform\Data\Project_Name_Master (1).xlsx"
df = pd.read_excel(file_path)
print("Unique 'Project' values in Excel:")
print(df['Project'].dropna().unique())
