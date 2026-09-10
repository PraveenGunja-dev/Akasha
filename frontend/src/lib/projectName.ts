/* ═══════════════════════════════════════════════════════════════════════════
   PROJECT NAME
   One canonical display form for a project, used by every screen.

   Generation projects arrive from P6 as
     SPV_PLOT_TYPE_CAPACITY_CATEGORY[_...rest]   ARE55L_S02A_HSAT_175_MW_PPA
   and are shown as
     PLOT_SPV_CAPACITY_CATEGORY_TYPE[_...rest]   S02A_ARE55L_175_MW_HSAT_PPA

   The plot leads because that is what people search and speak by; the
   equipment type trails because it is the least distinguishing part.

   This lived as two byte-identical private copies (ProjectWorkspace,
   ProjectMap) while ~20 other screens printed the raw P6 string, so the same
   project appeared under two different names depending on the screen.

   DISPLAY ONLY. Never use the result as a key, a route param, or an API
   argument — the backend knows projects by their raw P6 name.

   ── What the live data actually contains (62 distinct names) ──

   1. Capacity is punctuated three different ways: `175_MW`, `425MW`, and
      `250 MW`. Only the first splits into its own segment, so the other two
      left the name one segment short and it fell through unformatted — which
      is why two projects still read differently from the rest. Normalising
      the separator first brings all 47 generation projects to one shape.

   2. At least one name is ALREADY capacity-first — `AGEL_S10_287.5_MW_HSAT`.
      Reordering it positionally produced `S10_AGEL_MW_HSAT_287.5`. When the
      capacity already sits in slot 3, only the SPV and plot are swapped.

   3. The 15 substation and site names (`AGE27AL_PSS09`, `ARE3L PSS-08
      (05 Loc.)`, `MANDVI`, `NHPC EPC 600 MW Khavda-I`) are a different
      convention entirely and are deliberately returned untouched. Anything
      that is not a 5+ segment underscore name passes through unchanged,
      which makes this safe to apply to any display string.
   ═══════════════════════════════════════════════════════════════════════════ */

/** `250 MW` / `425MW` → `250_MW`. Underscore is a word character, so `\b`
 *  will not fire before `_PPA`; the lookahead has to exclude alphanumerics
 *  explicitly instead. Guarded to underscore-structured names so a prose
 *  title like `NHPC EPC 600 MW Khavda-I` is left alone. */
const normaliseCapacity = (name: string): string =>
  name.split('_').length >= 4
    ? name.replace(/([0-9.]+)[ _]?MW(?![A-Za-z0-9])/i, '$1_MW')
    : name;

const isCapacity = (seg: string): boolean => /^[0-9]+(\.[0-9]+)?$/.test(seg);

export const formatProjectName = (name: string): string => {
  if (!name) return name;

  const parts = normaliseCapacity(name).split('_');
  if (parts.length < 5) return name;

  const [spv, plot, third, fourth, ...tail] = parts;

  /* Already SPV_PLOT_CAPACITY_MW_TYPE — swap the first two and stop. */
  if (isCapacity(third) && /^MW$/i.test(fourth)) {
    return [plot, spv, third, fourth, ...tail].join('_');
  }

  /* SPV_PLOT_TYPE_CAPACITY_CATEGORY → PLOT_SPV_CAPACITY_CATEGORY_TYPE */
  const [category, ...rest] = tail;
  const reordered = [plot, spv, fourth, category, third].join('_');
  return rest.length ? `${reordered}_${rest.join('_')}` : reordered;
};
