import { useCallback, useEffect, useState } from 'react';

import { Auth, hasSession, Me, Notifications, Patient, setOnExpired, signOut } from './api';
import { AccountPage, ErrorBoundary, ForgotPage, NotFound, ResetPage, VerifyBanner, VerifyPage } from './pages/account';
import * as AdminP from './pages/admin';
import { AuthPage, Onboarding } from './pages/auth';
import * as ClinicP from './pages/clinic';
import * as DermP from './pages/derm';
import * as PatientP from './pages/patient';
import { go, href, usePath } from './router';
import { ROLE_LABEL } from './ui';

type NavItem = { path: string; label: string };
const NAV: Record<Me['role'], NavItem[]> = {
  patient: [
    { path: 'home', label: 'My checks' }, { path: 'check', label: 'New check' }, { path: 'settings', label: 'Privacy and data' },
  ],
  clinic_staff: [{ path: 'inbox', label: 'Clinic inbox' }],
  dermatologist: [
    { path: 'queue', label: 'Review queue' }, { path: 'rules', label: 'Rules and sign-off' }, { path: 'stats', label: 'Agreement with the app' },
    { path: 'inbox', label: 'Clinic inbox' },
  ],
  admin: [
    { path: 'admin', label: 'Dashboard' }, { path: 'admin/users', label: 'Staff accounts' }, { path: 'admin/catalog', label: 'Product catalog' },
    { path: 'admin/rules', label: 'Rules' }, { path: 'admin/models', label: 'Models and jobs' }, { path: 'admin/audit', label: 'Audit log' },
    { path: 'inbox', label: 'Clinic inbox' },
  ],
};
for (const items of Object.values(NAV)) items.push({ path: 'account', label: 'My account' });
const PUBLIC = ['login', 'signup', 'forgot', 'reset', 'verify'];

/** Sidebar counters: [number, urgent?] for a nav entry, from /notifications. */
function badge(path: string, n: Notifications | null): [number, boolean] | null {
  if (!n) return null;
  const pick: Record<string, [number | undefined, boolean]> = {
    inbox: [n.inbox_new, !!n.inbox_urgent],
    queue: [n.queue_todo, !!n.queue_urgent],
    'admin/catalog': [n.catalog_due, true],
    'admin/users': [n.locked_accounts, true],
  };
  const v = pick[path];
  return v && v[0] ? [v[0], v[1]] : null;
}

const HOME: Record<Me['role'], string> = { patient: 'home', clinic_staff: 'inbox', dermatologist: 'queue', admin: 'admin' };

function Logo() {
  return (
    <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#2F5D8A" /><circle cx="16" cy="16" r="7" fill="none" stroke="#fff" strokeWidth="3" />
      <path d="M16 9a7 7 0 0 0 0 14z" fill="#fff" />
    </svg>
  );
}

export function App() {
  const path = usePath();
  const [me, setMe] = useState<Me | null>(null);
  const [needsProfile, setNeedsProfile] = useState(false);
  const [ready, setReady] = useState(false);
  const [notes, setNotes] = useState<Notifications | null>(null);

  const enter = useCallback(async (m: Me, fresh = false) => {
    setMe(m);
    const missing = m.role === 'patient' && !(await Patient.profile().catch(() => null));
    setNeedsProfile(missing);
    if (fresh || !path.length || ['login', 'signup', 'forgot', 'reset'].includes(path[0])) go(missing ? 'welcome' : HOME[m.role]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path.join('/')]);

  const leave = useCallback(() => { signOut(); setMe(null); go('login'); }, []);

  useEffect(() => {
    setOnExpired(leave);
    if (!hasSession()) { setReady(true); if (!PUBLIC.includes(path[0])) go('login'); return; }
    Auth.me().then((m) => enter(m)).catch(leave).finally(() => setReady(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const signedIn = me !== null;
  useEffect(() => {
    if (!signedIn) return;
    const load = () => Auth.notifications().then(setNotes).catch(() => {});
    load();
    const t = window.setInterval(load, 60_000);
    return () => window.clearInterval(t);
  }, [signedIn, path.join('/')]);

  if (!ready) return null;
  if (path[0] === 'verify' && path[1]) {
    return <VerifyPage token={path[1]} signedIn={signedIn} onVerified={() => me && setMe({ ...me, email_verified: true })} />;
  }
  if (!me && path[0] === 'forgot') return <ForgotPage />;
  if (!me && path[0] === 'reset' && path[1]) return <ResetPage token={path[1]} />;
  if (!me) return <AuthPage mode={path[0] === 'signup' ? 'signup' : 'login'} onSignedIn={(m) => enter(m, true)} />;
  if (needsProfile) return <Onboarding onDone={() => { setNeedsProfile(false); go('home'); }} />;

  const nav = NAV[me.role];
  // Detail pages light up the list they belong to.
  const parent: Record<string, string> = { case: 'inbox', qr: 'inbox', review: 'queue', result: 'home' };
  const section = parent[path[0]] ?? path.join('/');
  const active = nav.filter((n) => section === n.path || section.startsWith(`${n.path}/`)).sort((a, b) => b.path.length - a.path.length)[0]?.path;

  return (
    <div className="shell">
      <a className="skip" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById('main')?.focus(); }}>Skip to content</a>
      <aside className="side" aria-label="Main menu">
        <div className="brand"><Logo /><div>DermaLens<small>{me.role === 'patient' ? 'Skin pre-screening' : 'ICONIC Aesthetic Clinic'}</small></div></div>
        {nav.map((n) => {
          const b = badge(n.path, notes);
          return (
            <a key={n.path} className={`nav ${active === n.path ? 'active' : ''}`} href={href(n.path)} data-testid={`nav-${n.path}`} aria-current={active === n.path ? 'page' : undefined}>
              <span>{n.label}</span>
              {b ? <span className={`count ${b[1] ? '' : 'quiet'}`} data-testid={`count-${n.path}`} aria-label={`${b[0]} need attention`}>{b[0]}</span> : null}
            </a>
          );
        })}
        <div className="spacer" />
        <div className="who"><b>{me.display_name ?? me.email}</b>{ROLE_LABEL[me.role]}</div>
        <button className="btn secondary small" style={{ margin: '0 12px' }} onClick={leave} data-testid="sign-out">Sign out</button>
      </aside>
      <main className="main" id="main" tabIndex={-1}>
        <VerifyBanner me={me} />
        <ErrorBoundary resetKey={path.join('/')}>
          {path[0] === 'account' ? <AccountPage me={me} onChanged={() => {}} /> : <Page me={me} path={path} />}
        </ErrorBoundary>
      </main>
    </div>
  );
}

function Page({ me, path }: { me: Me; path: string[] }) {
  const [a, b, c] = path;
  const staffish = me.role !== 'patient';
  if (me.role === 'patient') {
    if (a === 'check') return <PatientP.NewCheck />;
    if (a === 'result' && b) return <PatientP.ResultPage sessionId={b} />;
    if (a === 'settings') return <PatientP.Settings />;
    if (!a || a === 'home' || a === 'welcome') return <PatientP.Home />;
    return <NotFound home="home" />;
  }
  if (a === 'inbox' && staffish) return <ClinicP.Inbox />;
  if (a === 'case' && b && staffish) return <ClinicP.CasePage summaryId={b} />;
  if (a === 'qr' && b && staffish) return <ClinicP.CasePage qrToken={b} />;
  if (me.role === 'dermatologist') {
    if (a === 'review' && b) return <DermP.ReviewPage summaryId={b} />;
    if (a === 'rules') return <DermP.RulesPage />;
    if (a === 'stats') return <DermP.StatsPage />;
    if (!a || a === 'queue') return <DermP.Queue />;
    return <NotFound home="queue" />;
  }
  if (me.role === 'admin') {
    if (a === 'admin' && b === 'users') return <AdminP.Users me={me} />;
    if (a === 'admin' && b === 'catalog') return <AdminP.Catalog />;
    if (a === 'admin' && b === 'rules') return <AdminP.RulesAdmin />;
    if (a === 'admin' && b === 'models') return <AdminP.Models />;
    if (a === 'admin' && b === 'audit') return <AdminP.Audit />;
    void c;
    if (!a || (a === 'admin' && !b)) return <AdminP.Dashboard />;
    return <NotFound home="admin" />;
  }
  if (!a) return <ClinicP.Inbox />;
  return <NotFound home={HOME[me.role]} />;
}
