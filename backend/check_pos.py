import json
import os

po_list = [
    '4510017176', '4510017177', '4810023520', '5710013067', '4510017696',
    '4510017874', '4510017889', '5710013325', '5710013338', '4510018077',
    '4510018306', '5710015439', '5710016372', '4810027047', '5710017117',
    '4510021232', '5710017355', '5710017455', '4910000523', '4910000542',
    '5710017888', '4510022212', '4510022371', '5710019990', '5710020043',
    '5710020047', '5710020056', '5710020170'
]

for f_name in ['Get All Invoices Production(E-invoice) json response.txt', 'Get All Invoices uat(E-invoice) json response.txt']:
    print(f'Checking {f_name}...')
    try:
        with open('d:/Akasha_Platform/Data/NEW31/' + f_name, 'r', encoding='utf-8') as f:
            data = json.load(f)
            found = set()
            for r in data.get('d', {}).get('results', []):
                if r.get('workOrderNo') in po_list:
                    found.add(r.get('workOrderNo'))
            
            found_list = []
            missing_list = []
            for po in po_list:
                if po in found:
                    found_list.append(po)
                else:
                    missing_list.append(po)
            
            print(f'  FOUND ({len(found_list)}): {", ".join(found_list)}')
            print(f'  MISSING ({len(missing_list)}): {", ".join(missing_list)}')
            
    except Exception as e:
        print(f'Error reading {f_name}: {e}')
