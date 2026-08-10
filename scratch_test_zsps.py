import pandas as pd

def test_zsps():
    path = r'D:\Akasha_Platform\Data\NEW31\ZPSPS007 (3).xlsx'
    df = pd.read_excel(path, nrows=10)
    for _, row in df.iterrows():
        print(row.to_dict())

if __name__ == "__main__":
    test_zsps()
