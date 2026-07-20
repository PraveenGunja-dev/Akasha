import sys
import os
import requests
import urllib3
urllib3.disable_warnings()

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from services.p6_service import P6Service
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

service = P6Service()
url = os.getenv('ORACLE_P6_BASE_URL') + '/project'
params = {'Fields': 'Id,Name,SummaryActualNonLaborUnits,SummaryAtCompletionNonLaborUnits,SummaryBaselineNonLaborUnits,SummaryPlannedNonLaborUnits,SummaryBudgetAtCompletionByLaborUnits'}
response = requests.get(url, params=params, headers=service.headers, verify=False)
try:
    data = response.json()
    print('\n' + '='*140)
    print(f"{'ID':<15} | {'Actual NL':<15} | {'AtComp NL':<15} | {'Base NL':<15} | {'Plan NL':<15} | {'Budget Lab':<15}")
    print('='*140)
    for p in data:
        a_nl = p.get('SummaryActualNonLaborUnits', 0)
        ac_nl = p.get('SummaryAtCompletionNonLaborUnits', 0)
        b_nl = p.get('SummaryBaselineNonLaborUnits', 0)
        p_nl = p.get('SummaryPlannedNonLaborUnits', 0)
        blab = p.get('SummaryBudgetAtCompletionByLaborUnits', 0)
        
        if a_nl or ac_nl or b_nl or p_nl or blab:
            print(f"{p.get('Id', '')[:15]:<15} | {a_nl:<15} | {ac_nl:<15} | {b_nl:<15} | {p_nl:<15} | {blab:<15}")
except Exception as e:
    print(response.text)
