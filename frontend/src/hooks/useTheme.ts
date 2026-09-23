import { useEffect, useState } from 'react';
import {
  type Theme, getCurrentTheme, setTheme as commitTheme, subscribe,
} from '../lib/theme';

/** Read and change the app theme. Every consumer stays in sync, because the
    shared module notifies all of them rather than each holding its own copy. */
export function useTheme(): [Theme, (t: Theme) => void, () => void] {
  const [theme, setLocal] = useState<Theme>(getCurrentTheme);

  useEffect(() => {
    setLocal(getCurrentTheme());
    return subscribe(setLocal);
  }, []);

  const set = (t: Theme) => commitTheme(t);
  const toggle = () => commitTheme(theme === 'dark' ? 'light' : 'dark');
  return [theme, set, toggle];
}

export default useTheme;
