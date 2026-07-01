import sys
sys.path.append('d:\\Akasha_Platform\\backend')
from database import SessionLocal
import models
from routers.dashboard import MANUAL_PSS_MAPPING
print(MANUAL_PSS_MAPPING.get('AGE25BL_BANDHA_FT_500MW_PPA'))
