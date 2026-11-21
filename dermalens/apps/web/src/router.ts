// Tiny hash router: #/path/segments. Hash routes need no server rewrites, so the
// built site works on any static host.
import { useEffect, useState } from 'react';

export function usePath(): string[] {
  const read = () => window.location.hash.replace(/^#\/?/, '').split('?')[0].split('/').filter(Boolean);
  const [path, setPath] = useState(read);
  useEffect(() => {
    const on = () => { setPath(read()); window.scrollTo(0, 0); };
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  return path;
}

export const go = (path: string) => { window.location.hash = `#/${path.replace(/^\//, '')}`; };
export const href = (path: string) => `#/${path.replace(/^\//, '')}`;
