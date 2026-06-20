import pandas as pd
df = pd.read_excel('d:\\Akasha_Platform\\Data\\ME2K (1).xlsx')
test = df[df['Still to be delivered (qty)'] > 0].head(1)
r = test.iloc[0]
sq = r['Still to be delivered (qty)']
si = r['Still to be delivered in INR']
print(f'Derived unit price: {si/sq}')
print(f'Net Price in INR: {r["Net Price in INR"]}')
