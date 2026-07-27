import { Download, FileText, Share2 } from 'lucide-react';

interface P6Project {
  project_id?: string | null;
  duration_percent_complete?: number | null;
  cpi?: number | null;
  cost_performance_index?: number | null;
  actualTotalCost?: number | null;
  actual_total_cost?: number | null;
  baseline_finish_date?: string | null;
  scheduled_finish_date?: string | null;
  finish_date?: string | null;
}

interface FinancialAggregate {
  actualCapex?: number | null;
}

interface ProcurementDetail {
  vendor_name?: string | null;
  net_order_value_inr?: number | null;
  net_order_value?: number | null;
}

interface DashboardProject {
  p6?: { id?: string | null } | null;
}

interface ReportsInsightsProps {
  p6Data?: P6Project[];
  sapData?: FinancialAggregate[];
  finDetails?: ProcurementDetail[];
  dashboardData?: { projects?: DashboardProject[] } | null;
}

const isFiniteNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

const average = (values: number[]) =>
  values.length > 0 ? values.reduce((sum, value) => sum + value, 0) / values.length : null;

const getProgressPercent = (project: P6Project) => {
  const value = project.duration_percent_complete;
  if (!isFiniteNumber(value) || value < 0) return null;
  const normalized = value <= 1 ? value * 100 : value;
  return normalized <= 100 ? normalized : null;
};

const getCpi = (project: P6Project) => {
  const value = project.cpi ?? project.cost_performance_index;
  if (!isFiniteNumber(value) || value <= 0) return null;

  const actualCost = project.actualTotalCost ?? project.actual_total_cost;
  const hasKnownActualCost = isFiniteNumber(actualCost) && actualCost > 0;

  // /api/summary defaults CPI to 1 when actual cost is unavailable. A non-default
  // result, or a positive P6 actual cost, is required before displaying it.
  return value !== 1 || hasKnownActualCost ? value : null;
};

const parseDate = (value: string | null | undefined) => {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
};

const getForecastDelayDays = (project: P6Project) => {
  const baseline = parseDate(project.baseline_finish_date);
  const forecast = parseDate(project.scheduled_finish_date ?? project.finish_date);
  if (!baseline || !forecast) return null;

  const baselineDay = Date.UTC(baseline.getUTCFullYear(), baseline.getUTCMonth(), baseline.getUTCDate());
  const forecastDay = Date.UTC(forecast.getUTCFullYear(), forecast.getUTCMonth(), forecast.getUTCDate());
  return Math.round((forecastDay - baselineDay) / 86_400_000);
};

const formatInrCrore = (valueInCrore: number) =>
  `INR ${valueInCrore.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} Cr`;

export default function ReportsInsights({
  p6Data = [],
  sapData = [],
  finDetails = [],
  dashboardData,
}: ReportsInsightsProps) {
  const includedP6Ids = new Set(
    dashboardData?.projects?.map((project) => project.p6?.id).filter((id): id is string => Boolean(id)) ?? [],
  );
  const validP6 = p6Data.filter(
    (project) => Boolean(project.project_id) && includedP6Ids.has(project.project_id as string),
  );

  const progressValues = validP6.map(getProgressPercent).filter((value): value is number => value !== null);
  const cpiValues = validP6.map(getCpi).filter((value): value is number => value !== null);
  const scheduleDelayValues = validP6.map(getForecastDelayDays).filter((value): value is number => value !== null);
  const overallProgress = average(progressValues);
  const avgCpi = average(cpiValues);
  const delayedProjects = scheduleDelayValues.filter((days) => days > 30).length;
  const criticalProjects = scheduleDelayValues.filter((days) => days > 60).length;
  const cpiBelowTarget = cpiValues.filter((cpi) => cpi < 1).length;

  // /api/financials is an aggregate already scoped by the page query. Its values
  // are INR crores and it intentionally has no plant_code for a client-side join.
  const actualCapexTotal = sapData.reduce(
    (sum, row) => sum + (isFiniteNumber(row.actualCapex) ? row.actualCapex : 0),
    0,
  );
  const actualCapex = actualCapexTotal > 0 ? actualCapexTotal : null;

  // /api/financials/details is also already scoped. The endpoint currently returns
  // at most 100 records, so these are described as the loaded sample, not totals.
  const vendorValuedRecordCount = new Map<string, number>();
  const vendorValueInr = new Map<string, number>();
  let loadedPoValueInr = 0;
  let poValueCount = 0;

  finDetails.forEach((purchaseOrder) => {
    const vendor = purchaseOrder.vendor_name?.trim() || 'Unknown vendor';
    const valueInr = purchaseOrder.net_order_value_inr ?? purchaseOrder.net_order_value;

    if (isFiniteNumber(valueInr)) {
      vendorValuedRecordCount.set(vendor, (vendorValuedRecordCount.get(vendor) ?? 0) + 1);
      vendorValueInr.set(vendor, (vendorValueInr.get(vendor) ?? 0) + valueInr);
      loadedPoValueInr += valueInr;
      poValueCount += 1;
    }
  });

  const vendorNames = new Set(finDetails.map((row) => row.vendor_name?.trim()).filter(Boolean));
  const topVendorEntry = [...vendorValueInr.entries()]
    .filter(([, valueInr]) => valueInr > 0)
    .sort(([, left], [, right]) => right - left)[0];
  const topVendor = topVendorEntry?.[0] ?? null;
  const topVendorValueInr = topVendorEntry?.[1] ?? null;
  const topVendorRecords = topVendor ? vendorValuedRecordCount.get(topVendor) : null;
  const loadedPoValueCrore = poValueCount > 0 && loadedPoValueInr > 0 ? loadedPoValueInr / 10_000_000 : null;

  const unavailableItems = [
    validP6.length === 0 ? 'Mapped P6 project data is unavailable.' : null,
    validP6.length > 0 && progressValues.length < validP6.length
      ? `Duration progress is unavailable for ${validP6.length - progressValues.length} of ${validP6.length} P6 projects.`
      : null,
    validP6.length > 0 && cpiValues.length < validP6.length
      ? `CPI is unavailable for ${validP6.length - cpiValues.length} of ${validP6.length} P6 projects; default 1.00 values are excluded.`
      : null,
    validP6.length > 0 && scheduleDelayValues.length < validP6.length
      ? `Baseline/forecast finish dates are unavailable for ${validP6.length - scheduleDelayValues.length} of ${validP6.length} P6 projects.`
      : null,
    actualCapex === null ? 'The SAP purchase-order value aggregate is unavailable.' : null,
    finDetails.length === 0 ? 'Procurement detail is unavailable.' : null,
  ].filter((item): item is string => item !== null);

  return (
    <div className="flex flex-col gap-6 max-w-[1000px] mx-auto animate-in fade-in duration-500 pb-10">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-card border border-border rounded-2xl p-4 shadow-sm">
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-medium text-foreground tracking-wide">Automated Executive Brief</h2>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            disabled
            title="PDF export is disabled until a verified export path replaces runtime CDN DOM capture."
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-muted border border-border rounded-lg text-muted-foreground cursor-not-allowed opacity-70"
          >
            <Download className="w-4 h-4" /> PDF unavailable
          </button>
          <button
            type="button"
            disabled
            title="Report sharing is not available."
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-muted border border-border rounded-lg text-muted-foreground cursor-not-allowed opacity-70"
          >
            <Share2 className="w-4 h-4" /> Share unavailable
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
        PDF export is disabled in Phase 0. The previous export loaded html2pdf from a runtime CDN and captured the live DOM,
        which did not provide a controlled or verifiable report artifact.
      </div>

      <div id="executive-report" className="bg-white text-slate-800 rounded-2xl p-6 md:p-10 shadow-sm">
        <div className="w-full overflow-hidden rounded-xl mb-8">
          <img
            src={`${import.meta.env.BASE_URL}coverPhoto.png`}
            alt="Report cover"
            className="w-full h-[150px] md:h-[220px] object-cover object-top block transform scale-[1.1] origin-top"
          />
        </div>

        <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-4 border-b border-slate-200 pb-6 mb-8">
          <div>
            <h1 className="text-2xl font-bold tracking-wider text-black uppercase">AKASHA Intelligence</h1>
            <p className="text-sm text-primary font-medium tracking-[0.2em] uppercase mt-1">Daily Executive Portfolio Report</p>
          </div>
          <div className="sm:text-right">
            <p className="text-sm text-slate-700 font-mono">DATE: {new Date().toLocaleDateString()}</p>
            <p className="text-sm text-slate-700 font-mono">TIME: {new Date().toLocaleTimeString()}</p>
            <p className="text-sm text-amber-700 font-mono mt-2">Available API data only</p>
          </div>
        </div>

        {unavailableItems.length > 0 && (
          <section className="mb-6 rounded-lg border border-amber-300 bg-amber-50 p-4 text-left">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-amber-950">Data availability warning</h3>
            <ul className="list-disc pl-5 mt-2 space-y-1 text-sm text-amber-950">
              {unavailableItems.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </section>
        )}

        <div className="space-y-6 text-slate-700 leading-relaxed text-left sm:text-justify">
          <section>
            <h3 className="text-lg font-semibold text-black mb-2 uppercase tracking-wider border-l-2 border-blue-600 pl-3">
              1. Executive Overview &amp; Financial Health
            </h3>
            <p className="mb-2">
              {validP6.length > 0 ? (
                <>This report includes <strong>{validP6.length} mapped P6 project records</strong>.</>
              ) : (
                <>Mapped P6 project coverage: <strong>N/A</strong>.</>
              )}{' '}
              Mean duration percent complete is{' '}
              <strong>{overallProgress === null ? 'N/A' : `${overallProgress.toFixed(1)}%`}</strong>
              {overallProgress !== null && ` across ${progressValues.length} records with available progress`}.
            </p>
            <p>
              The financial endpoint&apos;s aggregate SAP purchase-order value is{' '}
              <strong>{actualCapex === null ? 'N/A' : formatInrCrore(actualCapex)}</strong>. Planned capital expenditure is{' '}
              <strong>N/A</strong> because the current endpoint does not provide a supported plan value. Mean CPI is{' '}
              <strong>{avgCpi === null ? 'N/A' : avgCpi.toFixed(2)}</strong>
              {avgCpi !== null && ` across ${cpiValues.length} records with evidence of an actual-cost calculation`}.
            </p>
          </section>

          <section>
            <h3 className={`text-lg font-semibold text-black mb-2 uppercase tracking-wider border-l-2 ${delayedProjects > 0 ? 'border-red-600' : 'border-blue-600'} pl-3`}>
              2. Schedule Delay Assessment
            </h3>
            <p className="mb-2">
              Displayed delay is calculated as <strong>forecast finish date minus baseline finish date</strong> in calendar days.
              Positive values mean the current forecast is later than baseline; the API&apos;s raw variance sign is not used.
            </p>
            {scheduleDelayValues.length > 0 ? (
              <p>
                Of <strong>{scheduleDelayValues.length} projects with comparable dates</strong>,{' '}
                <strong>{delayedProjects}</strong> exceed 30 calendar days later than baseline
                {criticalProjects > 0 && `, including ${criticalProjects} exceeding 60 calendar days`}.
                {scheduleDelayValues.length < validP6.length && ' Projects without both dates are excluded rather than treated as on time.'}
              </p>
            ) : (
              <p><strong>N/A:</strong> no projects have both a baseline finish and forecast finish date.</p>
            )}
          </section>

          <section>
            <h3 className="text-lg font-semibold text-black mb-2 uppercase tracking-wider border-l-2 border-amber-600 pl-3">
              3. Supply Chain &amp; Procurement Operations
            </h3>
            {finDetails.length > 0 ? (
              <>
                <p className="mb-2">
                  The loaded procurement sample contains <strong>{finDetails.length} procurement detail records</strong> and{' '}
                  <strong>{vendorNames.size > 0 ? vendorNames.size : 'N/A'} named vendors</strong>. The sum of available net order values is{' '}
                  <strong>{loadedPoValueCrore === null ? 'N/A' : formatInrCrore(loadedPoValueCrore)}</strong>. The details endpoint is capped at
                  100 records, so this is not presented as a portfolio total.
                </p>
                {topVendor && topVendorValueInr !== null && topVendorRecords !== null ? (
                  <p>
                    The largest loaded net order value by vendor is <strong>{topVendor}</strong> at{' '}
                    <strong>{formatInrCrore(topVendorValueInr / 10_000_000)}</strong> across{' '}
                    <strong>{topVendorRecords} records with available order value</strong>. Material quantities are not aggregated because the
                    current response does not provide a reliable common unit of measure. No concentration or resilience conclusion is made
                    from the capped sample.
                  </p>
                ) : (
                  <p>Vendor order-value comparison: <strong>N/A</strong>.</p>
                )}
              </>
            ) : (
              <p><strong>N/A:</strong> no procurement detail records are available for the current scope.</p>
            )}
          </section>

          <section>
            <h3 className="text-lg font-semibold text-black mb-2 uppercase tracking-wider border-l-2 border-purple-600 pl-3">
              4. Executive Action Items
            </h3>
            <ul className="list-disc pl-6 space-y-2 mt-2 text-slate-700">
              {delayedProjects > 0 && (
                <li><strong>Schedule review:</strong> Review the {delayedProjects} projects forecast more than 30 calendar days after baseline.</li>
              )}
              {cpiBelowTarget > 0 && (
                <li><strong>Cost review:</strong> Validate the {cpiBelowTarget} available CPI records below 1.00 against their actual-cost sources.</li>
              )}
              {unavailableItems.length > 0 && (
                <li><strong>Data completeness:</strong> Resolve the availability warnings before using this brief for portfolio-wide conclusions.</li>
              )}
              {finDetails.length > 0 && (
                <li><strong>Procurement scope:</strong> Use a complete, uncapped PO extract before making vendor-concentration decisions.</li>
              )}
              {delayedProjects === 0 && cpiBelowTarget === 0 && unavailableItems.length === 0 && (
                <li>No threshold-based action is identified from the available fields; continue routine source-data validation.</li>
              )}
            </ul>
          </section>
        </div>

        <div className="mt-12 pt-8 border-t border-slate-200 flex flex-col sm:flex-row justify-between gap-8">
          <div className="w-48">
            <div className="border-b border-gray-400 mb-2 h-8" />
            <p className="text-xs text-slate-500 uppercase tracking-wider text-center">Generated by</p>
            <p className="text-sm text-black font-medium text-center">Ask Akasha</p>
          </div>
          <div className="w-48">
            <div className="border-b border-gray-400 mb-2 h-8" />
            <p className="text-xs text-slate-500 uppercase tracking-wider text-center">Reviewed by</p>
            <p className="text-sm text-black font-medium text-center">Executive Office</p>
          </div>
        </div>
      </div>
    </div>
  );
}
