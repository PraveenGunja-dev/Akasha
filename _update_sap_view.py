import re

with open("frontend/src/components/dashboards/SAPView.tsx", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add state and effect for mappings + filtering logic
new_logic = """  const [companyFilter, setCompanyFilter] = useState<'all' | 'spv' | 'agel' | 'age6l'>('all');
  const [mappings, setMappings] = useState<any[]>([]);

  useEffect(() => {
    fetch('/akasha/api/mappings/')
      .then(res => res.json())
      .then(data => setMappings(data))
      .catch(err => console.error("Error fetching mappings:", err));
  }, []);

  const allSpvCodes = mappings.map(m => m.spv_plant_code).filter(Boolean).flatMap(c => c.split(/[\\s,]+/));
  const allAgelCodes = mappings.map(m => m.agel).filter(Boolean).flatMap(c => c.split(/[\\s,]+/));
  const allAge6lCodes = mappings.map(m => m.age6l).filter(Boolean).flatMap(c => c.split(/[\\s,]+/));

  const isMatch = (po: any, codes: string[]) => {
    return codes.some(c => (po.plant_code || '').includes(c) || (po.wbs_element || '').includes(c));
  };

  const filteredFinDetails = companyFilter === 'all' 
    ? (finDetails || [])
    : (finDetails || []).filter((po: any) => {
        if (companyFilter === 'spv') return isMatch(po, allSpvCodes);
        if (companyFilter === 'agel') return isMatch(po, allAgelCodes);
        if (companyFilter === 'age6l') return isMatch(po, allAge6lCodes);
        return true;
      });

  const filteredLogDetails = companyFilter === 'all'
    ? (logDetails || [])
    : (logDetails || []).filter((po: any) => {
        if (companyFilter === 'spv') return isMatch(po, allSpvCodes);
        if (companyFilter === 'agel') return isMatch(po, allAgelCodes);
        if (companyFilter === 'age6l') return isMatch(po, allAge6lCodes);
        return true;
      });"""

old_logic_pattern = r"  // No local filtering needed since it's an overall dashboard.*?:\s*\(logDetails \|\| \[\]\);"

content = re.sub(old_logic_pattern, new_logic.replace("\\", "\\\\"), content, flags=re.DOTALL)

# 2. Update KPI calculations to respect the local filter if not 'all'
kpi_logic_old = """  const totalPos = globalSap.totalPos ?? filteredFinDetails.length ?? 0;
  const vendors = globalSap.vendors ?? new Set(filteredFinDetails.map((f:any) => f.vendor_name).filter(Boolean)).size ?? 0;
  const materials = globalSap.materials ?? new Set(filteredFinDetails.map((f:any) => f.material_code).filter(Boolean)).size ?? 0;
  
  const poVolume = globalSap.volume ?? filteredFinDetails.reduce((acc:any, curr:any) => acc + (curr.po_quantities || curr.menge || curr.po_quantity || 0), 0) ?? 0; 
  const inventory = trendsData?.total_inventory ?? 0;
  
  // Financial metrics (The true global sum is actualCapex)
  const supplyPoAmount = globalSap.actualCapex ?? filteredFinDetails.reduce((acc:any, curr:any) => acc + ((curr.net_order_value_inr || curr.net_order_value || 0) / 10000000), 0);"""

kpi_logic_new = """  const totalPos = (companyFilter === 'all' && globalSap.totalPos) ? globalSap.totalPos : filteredFinDetails.length;
  const vendors = (companyFilter === 'all' && globalSap.vendors) ? globalSap.vendors : new Set(filteredFinDetails.map((f:any) => f.vendor_name).filter(Boolean)).size;
  const materials = (companyFilter === 'all' && globalSap.materials) ? globalSap.materials : new Set(filteredFinDetails.map((f:any) => f.material_code).filter(Boolean)).size;
  
  const poVolume = (companyFilter === 'all' && globalSap.volume) ? globalSap.volume : filteredFinDetails.reduce((acc:any, curr:any) => acc + (curr.po_quantities || curr.menge || curr.po_quantity || 0), 0); 
  const inventory = trendsData?.total_inventory ?? 0;
  
  // Financial metrics (The true global sum is actualCapex)
  const supplyPoAmount = (companyFilter === 'all' && globalSap.actualCapex) ? globalSap.actualCapex : filteredFinDetails.reduce((acc:any, curr:any) => acc + ((curr.net_order_value_inr || curr.net_order_value || 0) / 10000000), 0);"""

content = content.replace(kpi_logic_old, kpi_logic_new)

# 3. Add the UI buttons
ui_old = """        <div className="flex flex-wrap items-center gap-4">
          <button className="flex items-center gap-2 px-4 py-2 bg-card border border-border rounded-lg text-sm font-medium text-primary hover:bg-muted transition-colors">
            <Download className="w-4 h-4" /> Export SAP Report
          </button>
        </div>"""

ui_new = """        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center bg-muted border border-border rounded-lg p-0.5">
            {[
              { key: 'all' as const, label: 'All' },
              { key: 'spv' as const, label: 'SPV' },
              { key: 'agel' as const, label: 'AGEL' },
              { key: 'age6l' as const, label: 'AGE6L' },
            ].map(opt => (
              <button
                key={opt.key}
                onClick={() => setCompanyFilter(opt.key)}
                className={`px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider rounded-md transition-all ${
                  companyFilter === opt.key
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <button className="flex items-center gap-2 px-4 py-2 bg-card border border-border rounded-lg text-sm font-medium text-primary hover:bg-muted transition-colors">
            <Download className="w-4 h-4" /> Export SAP Report
          </button>
        </div>"""

content = content.replace(ui_old, ui_new)

with open("frontend/src/components/dashboards/SAPView.tsx", "w", encoding="utf-8") as f:
    f.write(content)
