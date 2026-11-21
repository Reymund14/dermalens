import React, { useCallback, useEffect, useState } from 'react';

export const ROLE_LABEL: Record<string, string> = {
  patient: 'Patient', clinic_staff: 'Clinic staff', dermatologist: 'Dermatologist', admin: 'Admin',
};
export const ROUTE_META: Record<string, { label: string; tone: string; color: string }> = {
  urgent_care: { label: 'Urgent care', tone: 'danger', color: '#a12a2a' },
  dermatologist: { label: 'Dermatologist', tone: 'caution', color: '#c08a1a' },
  iconic_clinic: { label: 'ICONIC consult', tone: '', color: '#2f5d8a' },
  self_care: { label: 'Self-care', tone: 'ok', color: '#2e7d4f' },
};

export const BOUNDARY = 'DermaLens gives general skincare information and a visual pre-screening. It does not diagnose, treat or rule out any disease. For a changing mole, a sore that does not heal, pain, bleeding, rapid spreading or fever, see a board-certified dermatologist.';

export const human = (s: string) => s.replace(/_/g, ' ');
export const when = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
export const errMsg = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong.');

/** Loads data once and on demand; keeps the last good value while reloading. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(() => {
    setError(null);
    return fn().then(setData).catch((e) => setError(errMsg(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, reload };
}

export function Badge({ children, tone = '' }: { children: React.ReactNode; tone?: string }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function Notice({ kind, children }: { kind: 'ok' | 'error' | 'info'; children: React.ReactNode }) {
  return children ? <div className={`notice ${kind}`} role={kind === 'error' ? 'alert' : 'status'}>{children}</div> : null;
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

export function Modal({ title, onClose, children, actions }: {
  title: string; onClose: () => void; children: React.ReactNode; actions: React.ReactNode;
}) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [onClose]);
  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <h2>{title}</h2>
        {children}
        <div className="actions">{actions}</div>
      </div>
    </div>
  );
}

/** Runs an action, tracks busy state and the result message. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  async function run<T>(fn: () => Promise<T>, ok: (r: T) => string): Promise<boolean> {
    setBusy(true); setMsg(null);
    try {
      const r = await fn();
      setMsg({ kind: 'ok', text: ok(r) });
      return true;
    } catch (e) {
      setMsg({ kind: 'error', text: errMsg(e) });
      return false;
    } finally {
      setBusy(false);
    }
  }
  return { busy, msg, setMsg, run };
}
