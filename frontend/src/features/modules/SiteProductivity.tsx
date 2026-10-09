import React from 'react';
import type { OrderingSignal, OrderingState, SiteActivity, SiteArea, SiteProductivity } from './types';
import { fmtIsoDate } from './DeliveryLedger';
import { HelpCard, Tip } from './ModuleTip';

/* Site progress behind the module order, opened under a project's row.
   Modules are only useful once the tracker under them is built: this shows
   how far piling, tracker and module erection have got (P6 block quantities),
   the pace each is moving at, what pace and manpower the final FTC needs (the
   site productivity norms), and the front ready for modules. */

export const SIGNAL_PILL: Record<OrderingState, string> = {
  modules_short: 'status-pill-risk',
  order_now: 'status-pill-critical',
  stock_building: 'status-pill-watch',
  records_conflict: 'status-pill-watch',
  complete: 'status-pill-done',
  not_started: 'status-pill',
  piling_only: 'status-pill',
  on_track: 'status-pill-healthy',
  no_progress: 'status-pill',
};

export function SignalPill({ signal }: { signal?: OrderingSignal }) {
  if (!signal) return <span className="text-muted-foreground">—</span>;
  return <span className={`${SIGNAL_PILL[signal.state]} whitespace-nowrap`}>{signal.text}</span>;
}

const AREA_ORDER: ('piling' | 'tracker' | 'module')[] = ['piling', 'tracker', 'module'];
/** P6 data older than this is called out: the pace stops at the data date. */
const STALE_DAYS = 14;

const fmt = (n: number | null | undefined, digits = 0) =>
  n == null ? '—' : n.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
const fmtQty = (n: number, uom: string) => fmt(n, uom === 'MWdc' ? 1 : 0);
const fmtRate = (n: number | null, uom: string) => (n == null ? '—' : fmt(n, uom === 'MWdc' || n < 10 ? 2 : 0));

function Fact({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: 'risk' | 'watch' }) {
  return (
    <div className="min-w-[96px]">
      <div className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-[11px] font-semibold tabular-nums text-foreground">{value}</div>
      {sub && <div className={`text-[9px] tabular-nums ${tone === 'risk' ? 'text-[var(--status-risk-fg)]' : tone === 'watch' ? 'text-[var(--status-watch-fg)]' : 'text-muted-foreground'}`}>{sub}</div>}
    </div>
  );
}

/** Predicted finish against the final FTC: late is the signal that matters. */
function FinishCell({ date, ftc }: { date: string | null; ftc: string | null }) {
  if (!date) return <span className="text-muted-foreground">—</span>;
  const late = ftc && date > ftc;
  if (!late) return <span>{fmtIsoDate(date)}</span>;
  return (
    <Tip width={260} content={<HelpCard title="Finishes after FTC">At today's speed this finishes on {fmtIsoDate(date)}, after the final FTC of {fmtIsoDate(ftc)}.</HelpCard>}>
      <span className="font-semibold text-[var(--status-risk-fg)] underline decoration-dotted underline-offset-2">{fmtIsoDate(date)}</span>
    </Tip>
  );
}

/** Points behind the baseline: amber from 1, red from 20. */
function BehindCell({ pts }: { pts: number | null }) {
  if (pts == null) return <td className="text-right text-muted-foreground">—</td>;
  if (pts < 1) return <td className="text-right text-[var(--status-healthy-fg)]">On plan</td>;
  return <td className={`text-right ${pts >= 20 ? 'font-semibold text-[var(--status-risk-fg)]' : 'text-[var(--status-watch-fg)]'}`}>−{fmt(pts, 0)} pts</td>;
}

function AreaRow({ area, site }: { area: SiteArea; site: SiteProductivity }) {
  return (
    <tr className="bg-[var(--neutral-100)] font-semibold [&>td]:border-b [&>td]:border-border [&>td]:px-2 [&>td]:py-1">
      <td className="text-left text-foreground">{area.label}</td>
      <td className="text-left text-muted-foreground font-normal">MWdc</td>
      <td className="text-right">{fmt(site.module_scope_mwdc, 1)}</td>
      <td className="text-right">{fmt(area.done_mwdc, 1)}</td>
      <td className="text-right">{fmt(area.pct, 1)}%</td>
      <td className="text-right">{area.plan_pct == null ? '—' : `${fmt(area.plan_pct, 1)}%`}</td>
      <BehindCell pts={area.behind_pts} />
      <td className="text-right">{fmtRate(area.pace_mwdc_per_day, 'MWdc')}</td>
      <td className={`text-right ${area.required_mwdc_per_day != null && area.required_mwdc_per_day > area.pace_mwdc_per_day ? 'text-[var(--status-risk-fg)]' : ''}`}>{fmtRate(area.required_mwdc_per_day, 'MWdc')}</td>
      <td className="text-right"><FinishCell date={area.predicted_finish} ftc={site.final_ftc} /></td>
      <td className="text-right text-muted-foreground font-normal">—</td>
      <td className="text-right">{fmt(area.mandays_left)}</td>
      <td className="text-right">{fmt(area.manpower_needed_per_day)}</td>
    </tr>
  );
}

function ActivityRow({ a }: { a: SiteActivity }) {
  const short = a.required_per_day != null && a.required_per_day > a.pace_per_day;
  return (
    <tr className="[&>td]:border-b [&>td]:border-[var(--border-subtle)] [&>td]:px-2 [&>td]:py-[3px] hover:bg-[var(--surface-sunken)]">
      <td className="text-left"><span className="font-mono text-muted-foreground">{a.code}</span> {a.label}
        <span className="text-muted-foreground"> · {a.blocks_done}/{a.blocks} blocks</span></td>
      <td className="text-left text-muted-foreground">{a.uom}</td>
      <td className="text-right">{fmtQty(a.planned, a.uom)}</td>
      <td className="text-right">{fmtQty(a.done, a.uom)}</td>
      <td className="text-right">{fmt(a.pct, 1)}%</td>
      <td className="text-right text-muted-foreground">{a.plan_pct == null ? '—' : `${fmt(a.plan_pct, 1)}%`}</td>
      <BehindCell pts={a.behind_pts} />
      <td className="text-right">{fmtRate(a.pace_per_day, a.uom)}</td>
      <td className={`text-right ${short ? 'font-semibold text-[var(--status-risk-fg)]' : ''}`}>{fmtRate(a.required_per_day, a.uom)}</td>
      <td className="text-right text-muted-foreground">{a.days_to_finish == null ? '—' : a.days_to_finish === 0 ? 'Done' : `${fmt(a.days_to_finish)} d`}</td>
      <td className="text-right text-muted-foreground">{a.norm_units_per_manday == null ? '—' : fmt(a.norm_units_per_manday, a.norm_units_per_manday < 1 ? 3 : 2)}</td>
      <td className="text-right">{fmt(a.mandays_left)}</td>
      <td className="text-right">{fmt(a.manpower_needed_per_day)}</td>
    </tr>
  );
}

/** Panel column header with a help card. */
function HelpTh({ label, title, children }: { label: string; title: string; children: React.ReactNode }) {
  return (
    <th className="text-right">
      <Tip width={300} content={<HelpCard title={title}>{children}</HelpCard>}>
        <span className="underline decoration-dotted underline-offset-2">{label}</span>
      </Tip>
    </th>
  );
}

export function SiteProductivityPanel({ site, signal, modulesAtSiteMwp }: {
  site: SiteProductivity | null | undefined; signal?: OrderingSignal; modulesAtSiteMwp: number;
}) {
  if (!site) {
    return <p className="px-3 py-2.5 text-[10px] text-muted-foreground">P6 has no block-level piling, structure or module activities for this project, so site progress cannot be shown.</p>;
  }
  const stale = site.data_age_days > STALE_DAYS;
  return (
    <div className="flex flex-col gap-2.5 px-3 py-2.5">
      <div className="flex flex-wrap items-start gap-x-5 gap-y-2">
        <Fact label="P6 data date" value={fmtIsoDate(site.data_date)}
          sub={`${site.data_age_days} days old`} tone={stale ? 'watch' : undefined} />
        <Fact label="MMS type" value={site.mms_kind ?? 'Not set'}
          sub={site.mms_kind ? `from ${site.mms_source}` : 'Norms cannot be applied'} tone={site.mms_kind ? undefined : 'watch'} />
        <Fact label="Final FTC · P6" value={fmtIsoDate(site.final_ftc)}
          sub={site.days_to_ftc != null ? (site.days_to_ftc >= 0 ? `${site.days_to_ftc} days after data date` : `${-site.days_to_ftc} days before data date`) : 'No pending FTC'} />
        {site.final_ftc && (
          <Fact label="FTC forecast · site speed"
            value={site.ftc_note ? 'Too slow to forecast' : site.ftc_forecast ? fmtIsoDate(site.ftc_forecast) : '—'}
            sub={site.ftc_note ? site.ftc_driver ?? undefined : site.ftc_delay_days ? `${site.ftc_delay_days} days late · ${site.ftc_driver}` : site.ftc_forecast ? 'On time' : 'No stage moving yet'}
            tone={site.ftc_note || (site.ftc_delay_days ?? 0) > 30 ? 'risk' : (site.ftc_delay_days ?? 0) > 0 ? 'watch' : undefined} />
        )}
        <Fact label="Structure ready, no modules" value={`${fmt(site.front_ready_mwdc, 1)} MWdc`} sub="Can be mounted as soon as modules arrive" />
        <Fact label="Modules in yard" value={`${fmt(Math.max(modulesAtSiteMwp, 0), 1)} MWp`} sub="SAP received − mounted" />
        <div className="ml-auto max-w-[420px]">
          <div className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">Module supply vs site</div>
          <div className="mt-0.5"><SignalPill signal={signal} /></div>
          {signal && <p className="mt-1 text-[10px] leading-snug text-muted-foreground">{signal.detail}</p>}
          {signal?.action && <p className="mt-1 text-[10px] leading-snug text-foreground"><b className="font-semibold text-primary">What to do: </b>{signal.action}</p>}
        </div>
      </div>

      <div className="overflow-auto rounded border border-border bg-card custom-scrollbar">
        <table className="w-full min-w-[880px] text-[10px] tabular-nums">
          <thead className="bg-[var(--neutral-100)] text-[9px] uppercase tracking-wider text-muted-foreground">
            <tr className="[&>th]:border-b [&>th]:border-border [&>th]:px-2 [&>th]:py-1 [&>th]:font-semibold">
              <th className="text-left">Activity</th>
              <th className="text-left">Unit</th>
              <th className="text-right">Scope</th>
              <th className="text-right">Done</th>
              <th className="text-right">Done %</th>
              <HelpTh label="Planned %" title="Planned by now (P6 baseline)">
                What the P6 baseline expected to be done by the date P6 was last updated, from each block's baseline start and finish dates.
              </HelpTh>
              <HelpTh label="Behind" title="Behind the baseline">
                Planned % minus done %, in percentage points. Amber when behind, red when 20 points or more behind.
              </HelpTh>
              <HelpTh label="Speed / day" title="Speed so far, per day">
                What has been done, divided by the days since the first block started (up to the date P6 was last updated). An average, so a recent speed-up or slowdown is smoothed out.
              </HelpTh>
              <HelpTh label="Needed / day" title="Speed needed to make FTC">
                What is left, divided by the days from the P6 update to the final FTC. Red when it is higher than the speed so far.
              </HelpTh>
              <HelpTh label="Finish at speed" title="When it finishes at today's speed">
                What is left divided by the speed so far. An estimate; red when it lands after FTC.
              </HelpTh>
              <HelpTh label="Norm / manday" title="Site productivity norm">
                How much one person does in a day, from the site productivity sheet, for this project's structure type (HSAT or FT). For example 9.51 piles, or 0.25 tables of torque tube.
              </HelpTh>
              <HelpTh label="Mandays left" title="Work left, in person-days">
                Share not done × the project's MWac × the norm mandays per MWac. Uses the site norm because P6's own manpower figures follow progress and are not a head count.
              </HelpTh>
              <HelpTh label="People / day" title="People needed every day to make FTC">
                Mandays left divided by the days to FTC: how many people must work on this activity every day from now to finish on time.
              </HelpTh>
            </tr>
          </thead>
          <tbody>
            {AREA_ORDER.map(key => {
              const area = site.areas[key];
              const acts = site.activities.filter(a => a.area === key);
              if (!area && !acts.length) return null;
              return (
                <React.Fragment key={key}>
                  {area && <AreaRow area={area} site={site} />}
                  {acts.map(a => <ActivityRow key={a.key} a={a} />)}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="text-[9px] leading-snug text-muted-foreground">
        Quantities are P6 block activities (Block-NN - Piling / MMS Erection / Module Installation), on the latest schedule. Pace is measured: what is done divided by the days since the first block started, up to the P6 data date{stale ? ` (${site.data_age_days} days ago — later progress is not in P6 yet)` : ''}. Build order on every block: piles, then the structure (torque tube, bracing, purlin), then modules mounted on the purlins, then stringing (not tracked: P6 has too few stringing entries). The bold rows are in module MWdc so the three stages compare directly; a block's structure counts as done when its purlin is done. Finish at pace and manpower are estimates: manpower uses the site norm (mandays per MWac for {site.mms_kind ?? 'the MMS type'}), because P6's own manpower figures follow progress and are not a site count.
      </p>
    </div>
  );
}
