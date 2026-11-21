// Account pages every role uses: forgotten password, reset link, email verification,
// change password, plus the "confirm your email" banner and the not-found page.
import React, { useEffect, useState } from 'react';

import { ApiError, Auth, Me } from '../api';
import { href } from '../router';
import { errMsg, Field, Notice, ROLE_LABEL } from '../ui';

function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="login">
      <div style={{ width: '100%', maxWidth: 440 }}>
        <div className="row" style={{ justifyContent: 'center', marginBottom: 18, gap: 10 }}>
          <svg width="36" height="36" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="8" fill="#2F5D8A" /><circle cx="16" cy="16" r="7" fill="none" stroke="#fff" strokeWidth="3" /><path d="M16 9a7 7 0 0 0 0 14z" fill="#fff" /></svg>
          <span style={{ fontSize: 22, fontWeight: 700 }}>DermaLens</span>
        </div>
        <div className="card" style={{ padding: 28, maxWidth: 'none' }}>
          <h1 style={{ marginBottom: 6 }}>{title}</h1>
          {children}
        </div>
      </div>
    </div>
  );
}

export function ForgotPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try { setSent((await Auth.forgot(email.trim())).message); } catch (err) { setError(errMsg(err)); } finally { setBusy(false); }
  }
  return (
    <Shell title="Forgot your password?">
      {sent ? (
        <>
          <Notice kind="ok">{sent}</Notice>
          <p className="muted">The link works once, for 30 minutes. Check your spam folder if it does not arrive.</p>
          <a className="btn" href={href('login')} style={{ width: '100%', textAlign: 'center' }}>Back to sign in</a>
        </>
      ) : (
        <form onSubmit={submit}>
          <p className="muted" style={{ marginTop: 0 }}>Enter the email you sign in with. We will send you a link to choose a new password.</p>
          <Field label="Email"><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required data-testid="forgot-email" /></Field>
          <Notice kind="error">{error}</Notice>
          <button className="btn" style={{ width: '100%', padding: 11 }} disabled={busy || !email} data-testid="forgot-submit">{busy ? 'Sending…' : 'Send reset link'}</button>
          <p className="muted small" style={{ textAlign: 'center', marginBottom: 0 }}><a href={href('login')}>Back to sign in</a></p>
        </form>
      )}
    </Shell>
  );
}

function NewPasswordFields({ pw, setPw, confirm, setConfirm }: { pw: string; setPw: (s: string) => void; confirm: string; setConfirm: (s: string) => void }) {
  const short = pw.length > 0 && pw.length < 10;
  const mismatch = confirm.length > 0 && confirm !== pw;
  return (
    <>
      <Field label="New password (at least 10 characters)">
        <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" required aria-invalid={short} data-testid="new-password" />
      </Field>
      {short ? <p className="small" style={{ color: 'var(--danger)', marginTop: -6 }}>{10 - pw.length} more character(s) needed.</p> : null}
      <Field label="Type it again">
        <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required aria-invalid={mismatch} data-testid="confirm-password" />
      </Field>
      {mismatch ? <p className="small" style={{ color: 'var(--danger)', marginTop: -6 }}>The two passwords do not match.</p> : null}
    </>
  );
}

export function ResetPage({ token }: { token: string }) {
  const [pw, setPw] = useState('');
  const [confirm, setConfirm] = useState('');
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try { await Auth.reset(token, pw); setDone(true); } catch (err) { setError(errMsg(err)); } finally { setBusy(false); }
  }
  return (
    <Shell title="Choose a new password">
      {done ? (
        <>
          <Notice kind="ok">Your password was changed. Every device that was signed in has been signed out.</Notice>
          <a className="btn" href={href('login')} style={{ width: '100%', textAlign: 'center' }} data-testid="reset-to-login">Sign in</a>
        </>
      ) : (
        <form onSubmit={submit}>
          <NewPasswordFields pw={pw} setPw={setPw} confirm={confirm} setConfirm={setConfirm} />
          <Notice kind="error">{error}</Notice>
          <button className="btn" style={{ width: '100%', padding: 11 }} disabled={busy || pw.length < 10 || pw !== confirm} data-testid="reset-submit">{busy ? 'Saving…' : 'Save new password'}</button>
          {error ? <p className="muted small" style={{ textAlign: 'center' }}><a href={href('forgot')}>Request a new link</a></p> : null}
        </form>
      )}
    </Shell>
  );
}

export function VerifyPage({ token, signedIn, onVerified }: { token: string; signedIn: boolean; onVerified?: () => void }) {
  const [state, setState] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => {
    Auth.verify(token)
      .then((r) => { setState({ ok: true, text: `Thanks, ${r.email} is confirmed.` }); onVerified?.(); })
      .catch((e) => setState({ ok: false, text: errMsg(e) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);
  return (
    <Shell title="Confirm your email">
      {state ? <Notice kind={state.ok ? 'ok' : 'error'}>{state.text}</Notice> : <p className="muted">Checking your link…</p>}
      {state ? <a className="btn" href={href(signedIn ? '' : 'login')} style={{ width: '100%', textAlign: 'center' }}>{signedIn ? 'Continue' : 'Sign in'}</a> : null}
    </Shell>
  );
}

export function VerifyBanner({ me }: { me: Me }) {
  const [sent, setSent] = useState<string | null>(null);
  if (me.email_verified) return null;
  return (
    <div className="notice info banner" role="status" data-testid="verify-banner">
      <span>Please confirm <b>{me.email}</b> so you can recover your account if you forget your password. We sent you a link.</span>
      {sent ? <span className="small">{sent}</span> : (
        <button className="btn secondary small" onClick={() => Auth.resendVerification().then(() => setSent('Sent. Check your inbox.')).catch((e) => setSent(errMsg(e)))}>Send it again</button>
      )}
    </div>
  );
}

export function AccountPage({ me, onChanged }: { me: Me; onChanged: () => void }) {
  const [current, setCurrent] = useState('');
  const [pw, setPw] = useState('');
  const [confirm, setConfirm] = useState('');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setMsg(null);
    try {
      await Auth.changePassword(current, pw);
      setCurrent(''); setPw(''); setConfirm('');
      setMsg({ ok: true, text: 'Password changed. Other devices were signed out; this one stays signed in.' });
      onChanged();
    } catch (err) {
      setMsg({ ok: false, text: err instanceof ApiError && err.status === 429 ? 'Too many tries. Wait a few minutes and try again.' : errMsg(err) });
    } finally { setBusy(false); }
  }
  return (
    <>
      <div className="pagehead"><div><h1>My account</h1><p className="muted" style={{ margin: 0 }}>Your sign-in details and password.</p></div></div>
      <div className="grid two">
        <div className="card">
          <h2>Signed in as</h2>
          <div className="kv">{me.display_name ? <><div>Name</div><div>{me.display_name}</div></> : null}<div>Email</div><div>{me.email}</div><div>Role</div><div>{ROLE_LABEL[me.role]}</div>
            <div>Email confirmed</div><div>{me.email_verified ? 'Yes' : 'Not yet'}</div></div>
          <p className="muted small" style={{ marginBottom: 0 }}>To change your name or email, ask a DermaLens admin{me.role === 'patient' ? ' or contact ICONIC' : ''}.</p>
        </div>
        <form className="card" onSubmit={submit}>
          <h2>Change password</h2>
          <Field label="Current password"><input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required data-testid="current-password" /></Field>
          <NewPasswordFields pw={pw} setPw={setPw} confirm={confirm} setConfirm={setConfirm} />
          {msg ? <Notice kind={msg.ok ? 'ok' : 'error'}>{msg.text}</Notice> : null}
          <button className="btn" disabled={busy || !current || pw.length < 10 || pw !== confirm} data-testid="change-submit">{busy ? 'Saving…' : 'Change password'}</button>
        </form>
      </div>
    </>
  );
}

export function NotFound({ home }: { home: string }) {
  return (
    <div className="card" style={{ maxWidth: 520 }} data-testid="not-found">
      <h1>Page not found</h1>
      <p className="muted">This page does not exist, or your account does not have access to it.</p>
      <a className="btn" href={href(home)}>Go to my home page</a>
    </div>
  );
}

/** Shows a friendly message instead of a blank screen if a page crashes. */
export class ErrorBoundary extends React.Component<{ children: React.ReactNode; resetKey: string }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error) { console.error('DermaLens page error', error); }
  componentDidUpdate(prev: { resetKey: string }) { if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null }); }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="card" style={{ maxWidth: 560 }} role="alert">
        <h1>Something went wrong on this page</h1>
        <p className="muted">Your data is safe. Reload the page, or go back and try again. If it keeps happening, tell your DermaLens admin what you were doing.</p>
        <div className="row"><button className="btn" onClick={() => window.location.reload()}>Reload</button><button className="btn secondary" onClick={() => history.back()}>Go back</button></div>
      </div>
    );
  }
}
