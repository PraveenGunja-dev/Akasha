import re

names = [
    'First Time Charging - Phase-I (150 MW)',
    'First Time Charging - Phase-II (200 MW)',
    'First Time Charging Phase I - 251 MW (PPA-I)',
    'First Time Charging Phase II - 139 MW (PPA-I & II)',
    'First Time Charging Phase III - 90 MW (PPA-II)',
    'First Time Charging Phase IV - 120 MW (PPA-II)',
    'Switchyard First Time Charging',
    'First Time Charging - (125 MW)',
    'First Time Charging - 100 MW'
]

for name in names:
    match = re.search(r'(Phase[\s\-]*[IV]+)', name, re.IGNORECASE)
    if match:
        phase_num = match.group(1).upper().replace('PHASE', '').replace('-', '').strip()
        print(f"'{name}' -> Ph-{phase_num}")
    else:
        print(f"'{name}' -> No Phase")
