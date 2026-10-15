/* Changing an LTA or SCOD in the Ordering Schedule needs a reason. It is
   kept in the date history and sent in the schedule-change email
   (backend/routers/mappings.py update_mapping). */
import { useEffect, useState } from 'react';
import { Save } from 'lucide-react';
import { Dialog } from '../../components/ui/primitives';
import { btn, field } from '../admin/adminApi';

export interface PendingDate {
  id: number; field: 'lta' | 'scod'; project: string; from: string; to: string | null;
}

const LABEL = { lta: 'LTA', scod: 'SCOD' } as const;
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const fmt = (iso: string | null) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '');
  return m ? `${m[3]}-${MON[Number(m[2]) - 1]}-${m[1].slice(2)}` : 'cleared';
};

export function DateChangeReason({ pending, onClose, onSaved }: {
  pending: PendingDate | null; onClose: () => void; onSaved: () => void;
}) {
  const [remarks, setRemarks] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { setRemarks(''); setError(''); setBusy(false); }, [pending]);
  if (!pending) return null;
  const label = LABEL[pending.field];

  const save = async () => {
    setBusy(true); setError('');
    try {
      const res = await fetch(`/akasha/api/mappings/${pending.id}`, {
        method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [pending.field === 'lta' ? 'lta_date' : 'manual_scod']: pending.to, remarks: remarks.trim() }),
      });
      if (!res.ok) {
        const b = await res.json().catch(() => ({}));
        throw new Error(b.detail || `Could not save (${res.status})`);
      }
      onSaved();
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(false); }
  };

  return (
    <Dialog open onClose={onClose} busy={busy} title={`Change ${label}?`}
      description={`${pending.project}: ${pending.from || 'not set'} → ${fmt(pending.to)}`}
      footer={<>
        <button type="button" className={btn.secondary} onClick={onClose} disabled={busy}>Cancel</button>
        <button type="button" className={btn.primary} disabled={busy || remarks.trim().length < 5} onClick={save}>
          <Save className="h-3.5 w-3.5" />{busy ? 'Saving…' : `Save ${label}`}
        </button>
      </>}>
      <label className="block text-[12px] font-medium text-foreground">Why is the {label} changing?
        <textarea rows={3} maxLength={1000} className={`${field} mt-1`} value={remarks} data-autofocus
          placeholder="e.g. Revised by the CTUIL letter dated 12-Oct-26" onChange={e => setRemarks(e.target.value)} />
      </label>
      <p className="mt-1.5 text-[11.5px] text-muted-foreground">
        Kept in the {label} history with your name, and sent with the schedule-change email to Projects and PMAG.
      </p>
      {error && <p role="alert" className="mt-2 text-[12px] text-[var(--status-critical-fg)]">{error}</p>}
    </Dialog>
  );
}
