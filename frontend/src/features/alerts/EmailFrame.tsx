/* An email as it was sent - the same template, in the browser - so the alert
   page, the approval and the email always read alike. Rendered in a sandboxed
   frame: its styles never touch the app, and no script in it can run. */
import { useEffect, useRef, useState } from 'react';
import { Loader } from '../../components/ui/primitives';
import { fmtWhen } from '../admin/adminApi';
import { alertsApi } from './alertsApi';
import type { MailData } from './alertsApi';

export function EmailFrame({ logId, compact }: { logId: number; compact?: boolean }) {
  const [mail, setMail] = useState<MailData | null>(null);
  const [error, setError] = useState('');
  const frame = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    setMail(null); setError('');
    alertsApi.mail(logId).then(setMail).catch(e => setError((e as Error).message));
  }, [logId]);

  const fit = () => {
    const doc = frame.current?.contentDocument;
    if (doc && frame.current) frame.current.style.height = `${doc.documentElement.scrollHeight + 4}px`;
  };

  if (error) return <p role="alert" className="text-[12.5px] text-[var(--status-critical-fg)]">{error}</p>;
  if (!mail) return <div className="flex justify-center py-8"><Loader size="md" label="Loading the email…" /></div>;
  return (
    <div className="space-y-2">
      {!compact && (
        <dl className="grid gap-x-6 gap-y-0.5 text-[12px] sm:grid-cols-[auto_minmax(0,1fr)]">
          <dt className="text-muted-foreground">Subject</dt><dd className="min-w-0 break-words font-medium text-foreground">{mail.subject}</dd>
          <dt className="text-muted-foreground">Sent</dt><dd className="text-foreground">{fmtWhen(mail.at)}{mail.level ? ` · level ${mail.level}` : ''}</dd>
          <dt className="text-muted-foreground">To</dt><dd className="min-w-0 break-words text-foreground">{mail.to.join(', ') || '-'}</dd>
          {mail.cc.length > 0 && <><dt className="text-muted-foreground">Cc</dt><dd className="min-w-0 break-words text-foreground">{mail.cc.join(', ')}</dd></>}
        </dl>
      )}
      <iframe ref={frame} title={mail.subject ?? 'Email'} onLoad={fit}
        sandbox="allow-same-origin allow-top-navigation-by-user-activation"
        srcDoc={mail.html.replace('<head>', '<head><base target="_top">')}
        className="block w-full rounded-lg border border-border bg-white" style={{ height: 640 }} />
    </div>
  );
}
