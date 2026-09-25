/* The CPAG pack as the backend renders it: the pages of the downloadable deck
   itself, so what is reviewed on screen and what is sent to management are
   the same file. */
import { useCallback, useEffect, useState } from 'react';

export interface PackPage { n: number; title: string; section: string }

export interface CPAGPack {
  loading: boolean;
  error: string | null;
  pages: PackPage[];
  pageSrc: (n: number) => string;
  downloadHref: string;
  retry: () => void;
}

const API = '/akasha/api/bess';

export function useCPAGPack(enabled: boolean): CPAGPack {
  const [key, setKey] = useState<string | null>(null);
  const [pages, setPages] = useState<PackPage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!enabled || key) return;
    let live = true;
    setLoading(true);
    setError(null);
    fetch(`${API}/portfolio/cpag/preview`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`CPAG pack unavailable (${r.status})`);
        return r.json();
      })
      .then((d: { key: string; slides: PackPage[] }) => {
        if (!live) return;
        setKey(d.key);
        setPages(d.slides);
      })
      .catch((e: Error) => { if (live) setError(e.message); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [enabled, key, attempt]);

  const retry = useCallback(() => { setKey(null); setAttempt((a) => a + 1); }, []);

  return {
    loading, error, pages, retry,
    pageSrc: (n: number) => (key ? `${API}/cpag/preview/${key}/${n}.png` : ''),
    downloadHref: key ? `${API}/cpag/preview/${key}/deck.pptx` : '',
  };
}
