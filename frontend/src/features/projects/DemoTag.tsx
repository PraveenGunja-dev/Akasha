/* Marks a demo project (portfolio "Akasha Demo...", added to test the Ordering
   Schedule, approvals and emails) wherever it is listed, so it is never taken
   for a real project. Neutral on purpose: the status colours are for state. */
export default function DemoTag() {
  return (
    <span title="A demo project, for testing - not a real project"
      className="shrink-0 rounded border border-dotted border-border-strong px-1.5 py-px text-[9px] font-bold uppercase tracking-wider text-fg-tertiary">
      Demo
    </span>
  );
}
