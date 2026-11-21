// Sign-in, patient sign-up (with the informational-use statement) and first-time setup.
import React, { useState } from 'react';

import { ApiError, Auth, Me, Patient, Profile } from '../api';
import { href } from '../router';
import { BOUNDARY, errMsg, Field, Notice } from '../ui';

export function AuthPage({ mode, onSignedIn }: { mode: 'login' | 'signup'; onSignedIn: (m: Me) => void }) {
  const signup = mode === 'signup';
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      onSignedIn(signup ? await Auth.register(email.trim(), password) : await Auth.login(email.trim(), password));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setError('Wrong email or password.');
      else if (err instanceof ApiError && err.status === 403) setError('This account is disabled. Contact your DermaLens admin.');
      else if (err instanceof ApiError && (err.status === 423 || err.status === 429)) setError(err.message.charAt(0).toUpperCase() + err.message.slice(1).replace(/\.$/, '') + '.');
      else setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div style={{ width: '100%', maxWidth: signup ? 520 : 420 }}>
        <div className="row" style={{ justifyContent: 'center', marginBottom: 18, gap: 10 }}>
          <svg width="36" height="36" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="8" fill="#2F5D8A" /><circle cx="16" cy="16" r="7" fill="none" stroke="#fff" strokeWidth="3" /><path d="M16 9a7 7 0 0 0 0 14z" fill="#fff" /></svg>
          <span style={{ fontSize: 22, fontWeight: 700 }}>DermaLens</span>
        </div>
        <form className="card" onSubmit={submit} style={{ padding: 28 }}>
          <h1 style={{ marginBottom: 6 }}>{signup ? 'Create your account' : 'Sign in'}</h1>
          <p className="muted" style={{ marginTop: 0 }}>
            {signup ? 'A skincare pre-screening companion from ICONIC Aesthetic Clinic.' : 'Patients, ICONIC staff, dermatologists and admins all sign in here.'}
          </p>
          {signup ? (
            <div className="notice info" style={{ color: 'var(--text)' }}>
              <b>What this is not.</b> {BOUNDARY}
              <label className="check" style={{ display: 'flex', marginTop: 10 }}>
                <input type="checkbox" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} data-testid="accept-boundary" />
                I understand DermaLens gives information, not a diagnosis.
              </label>
            </div>
          ) : null}
          <Field label="Email"><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required data-testid="email" /></Field>
          <Field label={signup ? 'Password (at least 10 characters)' : 'Password'}>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={signup ? 'new-password' : 'current-password'} required data-testid="password" />
          </Field>
          {!signup ? <p className="small" style={{ textAlign: 'right', marginTop: -6 }}><a href={href('forgot')} data-testid="to-forgot">Forgot your password?</a></p> : null}
          <Notice kind="error">{error}</Notice>
          <button className="btn" style={{ width: '100%', padding: 11 }} disabled={busy || !email || password.length < (signup ? 10 : 1) || (signup && !accepted)} data-testid="auth-submit">
            {busy ? 'Please wait…' : signup ? 'Create account' : 'Sign in'}
          </button>
          <p className="muted small" style={{ textAlign: 'center', marginBottom: 0 }}>
            {signup ? <>Already have an account? <a href={href('login')}>Sign in</a></> : <>New patient? <a href={href('signup')} data-testid="to-signup">Create an account</a></>}
          </p>
        </form>
      </div>
    </div>
  );
}

const CONSENTS = [
  { purpose: 'image_storage', title: 'Keep my photos', body: 'Store photos for 12 months so you can compare progress. Off: photos are deleted within 24 hours.' },
  { purpose: 'share_with_clinic', title: 'Share summaries with ICONIC', body: 'Lets you send a pre-screening summary to ICONIC staff before a visit.' },
  { purpose: 'model_improvement', title: 'Help improve DermaLens', body: 'Allow de-identified photos to be used to train future versions. You can withdraw any time.' },
];
export { CONSENTS };

const SKIN = ['dry', 'oily', 'combination', 'normal', 'sensitive'];
const FITZ = [
  [1, 'Always burns, never tans'], [2, 'Usually burns, tans a little'], [3, 'Sometimes burns, tans evenly'],
  [4, 'Rarely burns, tans easily'], [5, 'Very rarely burns, tans darkly'], [6, 'Never burns'],
] as const;

/** First-time patient setup: privacy choices, then profile. */
export function Onboarding({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState<'consent' | 'profile'>('consent');
  const [consents, setConsents] = useState<Record<string, boolean>>({});
  const [p, setP] = useState<Profile>({ full_name: '', birth_year: null, sex_at_birth: null, self_fitzpatrick: null, skin_type: null, is_pregnant_or_breastfeeding: false });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function saveConsents() {
    setBusy(true); setError(null);
    try {
      for (const c of CONSENTS) await Patient.setConsent(c.purpose, !!consents[c.purpose]);
      setStep('profile');
    } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  }
  async function saveProfile(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await Patient.saveProfile(p); onDone(); } catch (err) { setError(errMsg(err)); } finally { setBusy(false); }
  }

  return (
    <div className="login">
      <div className="card" style={{ maxWidth: 560, width: '100%', padding: 28 }}>
        <p className="muted small" style={{ margin: 0 }}>Step {step === 'consent' ? 1 : 2} of 2</p>
        {step === 'consent' ? (
          <>
            <h1>Your privacy choices</h1>
            <p className="muted">Each is optional and off until you turn it on. You can change them later.</p>
            {CONSENTS.map((c) => (
              <label key={c.purpose} className="card" style={{ display: 'flex', gap: 12, cursor: 'pointer', marginBottom: 10, padding: 14 }}>
                <input type="checkbox" checked={!!consents[c.purpose]} onChange={(e) => setConsents({ ...consents, [c.purpose]: e.target.checked })} data-testid={`consent-${c.purpose}`} />
                <span><b>{c.title}</b><br /><span className="muted small">{c.body}</span></span>
              </label>
            ))}
            <Notice kind="error">{error}</Notice>
            <button className="btn" onClick={saveConsents} disabled={busy} data-testid="consent-continue">Continue</button>
          </>
        ) : (
          <form onSubmit={saveProfile}>
            <h1>About you</h1>
            <p className="muted">Used to keep suggestions safe. Clinic staff only ever see your initials and age band.</p>
            <Field label="Full name"><input type="text" value={p.full_name} onChange={(e) => setP({ ...p, full_name: e.target.value })} required data-testid="full-name" /></Field>
            <div className="grid two">
              <Field label="Birth year"><input type="number" min={1900} max={2026} value={p.birth_year ?? ''} onChange={(e) => setP({ ...p, birth_year: e.target.value ? Number(e.target.value) : null })} data-testid="birth-year" /></Field>
              <Field label="Skin type">
                <select value={p.skin_type ?? ''} onChange={(e) => setP({ ...p, skin_type: e.target.value || null })} data-testid="skin-type">
                  <option value="">Not sure</option>
                  {SKIN.map((s) => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}
                </select>
              </Field>
            </div>
            <Field label="How does your skin react to the sun?">
              <select value={p.self_fitzpatrick ?? ''} onChange={(e) => setP({ ...p, self_fitzpatrick: e.target.value ? Number(e.target.value) : null })} data-testid="fitzpatrick">
                <option value="">Not sure</option>
                {FITZ.map(([n, l]) => <option key={n} value={n}>{l}</option>)}
              </select>
            </Field>
            <label className="check"><input type="checkbox" checked={p.is_pregnant_or_breastfeeding} onChange={(e) => setP({ ...p, is_pregnant_or_breastfeeding: e.target.checked })} /> I am pregnant or breastfeeding</label>
            <Notice kind="error">{error}</Notice>
            <div style={{ marginTop: 16 }}><button className="btn" disabled={busy || !p.full_name.trim()} data-testid="profile-save">Save and continue</button></div>
          </form>
        )}
      </div>
    </div>
  );
}
