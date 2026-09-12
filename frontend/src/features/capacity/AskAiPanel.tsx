import React, { useRef, useState } from 'react';
import { Send, Sparkles, Loader2, AlertTriangle } from 'lucide-react';
import Drawer from './Drawer';
import type { CapacityFilters, CapacityInsight } from './types';
import type { CapacityTotals } from './capacityCalculations';
import { cx } from '../../components/ui/primitives/cx';

/* ═══════════════════════════════════════════════════════════════════════════
   ASK AI

   Talks to the same /api/chat the rest of the platform uses, so this is the
   real assistant rather than a second, fake one.

   The context block is built deliberately: the filters in force, the headline
   totals, and the titles of the insights already on screen. That is a few
   hundred bytes. Sending the project table or the monthly series would cost
   tokens without improving the answer — the assistant has database access of
   its own, and what it cannot know is what the user is currently looking at.
   ═══════════════════════════════════════════════════════════════════════════ */

interface Msg { id: number; role: 'user' | 'assistant'; content: string; failed?: boolean }

const SUGGESTIONS = [
  'Which projects are closest to COD?',
  'Why is wind capacity behind solar?',
  'Which projects should we prioritise this quarter?',
  'What is stalling the remaining pipeline?',
];

function buildContext(filters: CapacityFilters, totals: CapacityTotals, insights: CapacityInsight[]) {
  return [
    'Context — the user is on the Capacity Overview screen.',
    `Filters: segment=${filters.segment}, range=${filters.dateRange}, aggregation=${filters.aggregation}.`,
    `Portfolio in view: ${totals.portfolioMW.toFixed(1)} MW across ${totals.projectCount} projects.`,
    `COD ${totals.codMW.toFixed(1)} MW (${totals.codPct.toFixed(1)}%), trial run ${totals.trMW.toFixed(1)} MW, remaining ${totals.remainingMW.toFixed(1)} MW.`,
    `Solar ${totals.solarMW.toFixed(1)} MW, wind ${totals.windMW.toFixed(1)} MW.`,
    insights.length ? `Calculated insights on screen: ${insights.map((i) => i.title).join('; ')}.` : '',
  ].filter(Boolean).join('\n');
}

export default function AskAiPanel({
  open, onClose, filters, totals, insights,
}: {
  open: boolean;
  onClose: () => void;
  filters: CapacityFilters;
  totals: CapacityTotals;
  insights: CapacityInsight[];
}) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || loading) return;

    const mine: Msg = { id: Date.now(), role: 'user', content: question };
    setMessages((m) => [...m, mine]);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch('/akasha/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: `${buildContext(filters, totals, insights)}\n\nQuestion: ${question}`,
          history: messages.map((m) => ({ type: m.role === 'user' ? 'user' : 'bot', content: m.content })),
        }),
      });
      const data = await res.json().catch(() => ({}));
      setMessages((m) => [...m, {
        id: Date.now() + 1,
        role: 'assistant',
        content: res.ok ? (data.response || 'No answer returned.') : (data.detail || `Request failed (${res.status}).`),
        failed: !res.ok,
      }]);
    } catch {
      setMessages((m) => [...m, {
        id: Date.now() + 1,
        role: 'assistant',
        content: 'Could not reach the Akasha AI service. The rest of this page is unaffected — every figure here is computed locally.',
        failed: true,
      }]);
    } finally {
      setLoading(false);
      requestAnimationFrame(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }));
    }
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width="max-w-lg"
      title="Ask about capacity"
      subtitle={`Scoped to ${filters.segment === 'All' ? 'the whole portfolio' : filters.segment} · ${totals.projectCount} projects in view`}
      footer={
        <form
          onSubmit={(e) => { e.preventDefault(); send(input); }}
          className="flex items-center gap-2"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything about capacity…"
            aria-label="Ask a question about capacity"
            disabled={loading}
            className="min-w-0 flex-1 rounded-lg border border-border bg-card px-3 py-2 text-[12px] text-foreground placeholder:text-fg-tertiary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            aria-label="Send question"
            className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-brand-blue to-brand-purple px-3 py-2 text-[12px] font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
          </button>
        </form>
      }
    >
      {messages.length === 0 && (
        <div>
          <div className="mb-3 flex items-start gap-2.5 rounded-xl border border-brand-purple/25 bg-brand-purple/[0.05] p-3">
            <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-brand-purple" />
            <p className="text-[12px] leading-relaxed text-fg-secondary">
              Your current filters and the headline capacity figures are sent with each question, so answers
              are about what you are looking at. The figures on the page itself are calculated locally and do
              not depend on this service.
            </p>
          </div>
          <p className="section-label mb-2">Try</p>
          <div className="flex flex-col gap-1.5">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="rounded-lg border border-border px-3 py-2 text-left text-[12px] text-fg-secondary transition-colors hover:border-brand-blue/40 hover:bg-brand-blue/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-3">
        {messages.map((m) => (
          <div key={m.id} className={cx('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
            <div className={cx(
              'max-w-[85%] whitespace-pre-wrap rounded-xl px-3 py-2 text-[12px] leading-relaxed',
              m.role === 'user'
                ? 'bg-primary text-white'
                : m.failed
                  ? 'border border-status-critical-border bg-status-critical-bg text-status-critical-fg'
                  : 'border border-border bg-muted/50 text-fg-secondary',
            )}>
              {m.failed && <AlertTriangle className="mr-1 inline h-3 w-3" />}
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-2 text-[11px] text-fg-tertiary">
            <Loader2 className="h-3 w-3 animate-spin" /> Thinking…
          </div>
        )}
        <div ref={endRef} />
      </div>
    </Drawer>
  );
}
