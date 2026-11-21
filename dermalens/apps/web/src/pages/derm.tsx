// Dermatologist: review queue, structured case review, rule sign-off, agreement figures.
import { useEffect, useState } from 'react';

import { CaseDetail, Clinic, Derm, RouteCode } from '../api';
import { go, href } from '../router';
import { Badge, errMsg, Field, human, Notice, ROUTE_META, useAction, useLoad, when } from '../ui';
import { CaseBody, CaseTable, RouteBadge } from './clinic';

const ROUTES: RouteCode[] = ['urgent_care', 'dermatologist', 'iconic_clinic', 'self_care'];
const pct = (x: number | null | undefined) => (x === null || x === undefined ? '–' : `${Math.round(x * 100)}%`);

export function Queue() {
  const [done, setDone] = useState(false);
  const { data, error } = useLoad(() => Derm.queue(done), [done]);
  const rows = (data ?? []).filter((r) => (done ? r.my_review : true));
  return (
    <>
      <div className="pagehead">
        <div><h1>Review queue</h1><p className="muted" style={{ margin: 0 }}>Your independent read of each shared case. Cases the app sent to a dermatologist come first.</p></div>
      </div>
      <div className="row" style={{ marginBottom: 12 }}>
        <button className={`btn small ${done ? 'secondary' : ''}`} onClick={() => setDone(false)}>To review</button>
        <button className={`btn small ${done ? '' : 'secondary'}`} onClick={() => setDone(true)} data-testid="reviewed-tab">Reviewed by me</button>
      </div>
      <Notice kind="error">{error}</Notice>
      <CaseTable rows={rows} empty={data ? 'Nothing to review.' : 'Loading…'} open={(id) => go(`review/${id}`)}
        extra={{ head: 'Your route', cell: (r) => (r.my_review ? <Badge tone={r.my_review.derm_route === r.route ? 'ok' : 'caution'}>{ROUTE_META[r.my_review.derm_route].label}</Badge> : <span className="muted">–</span>) }} />
    </>
  );
}

export function ReviewPage({ summaryId }: { summaryId: string }) {
  const [c, setC] = useState<CaseDetail | null>(null);
  const [route, setRoute] = useState<RouteCode | undefined>();
  const [agree, setAgree] = useState<Record<string, boolean | undefined>>({});
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const act = useAction();

  useEffect(() => {
    Clinic.get(summaryId).then(setC).catch((e) => setError(errMsg(e)));
    Derm.queue(true).then((q) => {
      const mine = q.find((x) => x.summary_id === summaryId)?.my_review;
      if (mine) { setRoute(mine.derm_route); setAgree(mine.concern_agreement); setNote(mine.note ?? ''); }
    }).catch(() => {});
  }, [summaryId]);

  const findings: { code: string; name: string; present: boolean; grade_name: string }[] = c?.data?.visual_prescreen ?? [];
  const complete = !!route && findings.every((f) => agree[f.code] !== undefined);

  async function submit() {
    const ok = await act.run(() => Derm.review(summaryId, {
      derm_route: route!, note: note || undefined,
      concern_agreement: Object.fromEntries(findings.map((f) => [f.code, !!agree[f.code]])),
    }), () => 'Review saved.');
    if (ok) go('queue');
  }

  if (error) return <Notice kind="error">{error}</Notice>;
  if (!c) return <p className="muted">Loading…</p>;
  return (
    <>
      <div className="pagehead"><div><a href={href('queue')} className="small">← Review queue</a><h1>Case review · {c.patient?.initials}</h1></div></div>
      <div className="card" style={{ borderColor: 'var(--primary)' }}>
        <h2>Your review</h2>
        <p className="muted" style={{ marginTop: -6 }}>Make your own call from the photos and answers below, then compare with the app's route.</p>
        <div className="grid two">
          <div>
            <b>Where should this person go?</b>
            <div className="row" style={{ margin: '8px 0 14px' }}>
              {ROUTES.map((r) => <button key={r} className={`btn small ${route === r ? '' : 'secondary'}`} onClick={() => setRoute(r)} data-testid={`derm-route-${r}`}>{ROUTE_META[r].label}</button>)}
            </div>
            <Field label="Clinical note (optional)"><textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          </div>
          <div>
            <b>Do you agree with each visual finding?</b>
            {findings.length === 0 ? <p className="muted">No findings on this case.</p> : null}
            <table style={{ marginTop: 6 }}><tbody>
              {findings.map((f) => (
                <tr key={f.code}>
                  <td>{f.name}: <span className="muted">{f.present ? f.grade_name : 'not seen'}</span></td>
                  <td style={{ width: 200 }}><div className="row">
                    {[false, true].map((v) => <button key={String(v)} className={`btn small ${agree[f.code] === v ? '' : 'secondary'}`} onClick={() => setAgree({ ...agree, [f.code]: v })} data-testid={`agree-${f.code}-${v ? 'yes' : 'no'}`}>{v ? 'Agree' : 'Disagree'}</button>)}
                  </div></td>
                </tr>
              ))}
            </tbody></table>
          </div>
        </div>
        {act.msg ? <Notice kind={act.msg.kind}>{act.msg.text}</Notice> : null}
        <button className="btn" disabled={!complete || act.busy} onClick={submit} data-testid="submit-review">Save my review</button>
      </div>
      <CaseBody c={c} />
    </>
  );
}

export function RulesPage() {
  const { data: r, error, reload } = useLoad(() => Derm.rules());
  const [note, setNote] = useState('');
  const act = useAction();
  if (error) return <Notice kind="error">{error}</Notice>;
  if (!r) return <p className="muted">Loading…</p>;

  async function sign() {
    if (!window.confirm(`Sign off triage ${r!.triage_version} and ${r!.rule_set_version}? Your name and the time are recorded.`)) return;
    if (await act.run(() => Derm.signoff(note), () => 'Signed off.')) { setNote(''); reload(); }
  }

  return (
    <>
      <div className="pagehead">
        <div><h1>Rules and sign-off</h1><p className="muted" style={{ margin: 0 }}>Read-only. Admins change the tables; any change creates a new version that needs a new sign-off.</p></div>
        <div className="row"><Badge>Triage {r.triage_version}</Badge><Badge>{r.rule_set_version}</Badge><Badge tone={r.signed_off ? 'ok' : 'caution'}>{r.signed_off ? 'Signed off' : 'Not signed off'}</Badge></div>
      </div>
      <div className="card">
        <h2>Sign off this version</h2>
        <div className="row">
          <input type="text" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} style={{ flex: 1, minWidth: 240 }} />
          <button className="btn" onClick={sign} disabled={act.busy} data-testid="sign-off">{r.signed_off ? 'Sign off again' : 'Sign off'}</button>
        </div>
        {act.msg ? <div style={{ marginTop: 10 }}><Notice kind={act.msg.kind}>{act.msg.text}</Notice></div> : null}
        {r.signoffs.length ? (
          <table style={{ marginTop: 12 }}><thead><tr><th>When</th><th>Who</th><th>Versions</th><th>Note</th></tr></thead><tbody>
            {r.signoffs.map((s, i) => <tr key={i}><td>{when(s.signed_at)}</td><td>{s.signed_by}</td><td className="mono">{s.triage_version} / {s.rule_set_version}</td><td>{s.note}</td></tr>)}
          </tbody></table>
        ) : null}
      </div>
      <div className="card">
        <h2>Red-flag questions ({r.red_flags.length})</h2>
        <table><thead><tr><th>Question</th><th>A "yes" sends the patient to</th></tr></thead><tbody>
          {r.red_flags.map((f) => <tr key={f.code}><td>{f.question}</td><td><RouteBadge route={f.route} /></td></tr>)}
        </tbody></table>
      </div>
      <div className="grid two">
        <div className="card">
          <h2>Ingredient conflicts ({r.conflicts.length})</h2>
          <table><thead><tr><th>Families</th><th>Resolution</th><th>Why</th></tr></thead><tbody>
            {r.conflicts.map((x, i) => <tr key={i}><td>{human(x.family_a)} + {human(x.family_b)}</td><td>{human(x.resolution)}<div className="muted small">{human(x.scope)}</div></td><td className="small">{x.rationale}</td></tr>)}
          </tbody></table>
        </div>
        <div className="card">
          <h2>Contraindications ({r.contraindications.length})</h2>
          <table><thead><tr><th>Condition</th><th>Action</th></tr></thead><tbody>
            {r.contraindications.map((x, i) => <tr key={i}><td>{human(x.condition)}</td><td>{human(x.action)} {human(x.family ?? x.ingredient ?? '')}</td></tr>)}
          </tbody></table>
        </div>
      </div>
    </>
  );
}

export function StatsPage() {
  const { data: s, error } = useLoad(() => Derm.stats());
  if (error) return <Notice kind="error">{error}</Notice>;
  if (!s) return <p className="muted">Loading…</p>;
  return (
    <>
      <div className="pagehead"><div><h1>Agreement with the app</h1><p className="muted" style={{ margin: 0 }}>From all dermatologist reviews. These feed the Level 3 clinical-agreement evaluation.</p></div></div>
      <div className="grid stats">
        <div className="card stat"><div className="n">{s.reviews}</div><div className="l">Cases reviewed</div></div>
        <div className="card stat"><div className="n">{pct(s.route_agreement)}</div><div className="l">Route agreement</div></div>
        <div className="card stat"><div className="n" style={{ color: s.missed_referrals ? 'var(--danger)' : 'var(--ok)' }}>{s.missed_referrals}</div><div className="l">Missed referrals</div></div>
        <div className="card stat"><div className="n">{pct(s.referral_sensitivity)}</div><div className="l">Referral sensitivity</div></div>
        <div className="card stat"><div className="n">{s.over_referrals}</div><div className="l">Over-referrals</div></div>
      </div>
      <div className="grid two">
        <div className="card">
          <h2>App route compared with yours</h2>
          {s.confusion.length === 0 ? <p className="muted">No reviews yet.</p> : (
            <table><thead><tr><th>App said</th><th>Dermatologist said</th><th style={{ textAlign: 'right' }}>Cases</th></tr></thead><tbody>
              {s.confusion.map((x, i) => <tr key={i}><td><RouteBadge route={x.app_route} /></td><td><RouteBadge route={x.derm_route} /></td><td style={{ textAlign: 'right' }}>{x.n}</td></tr>)}
            </tbody></table>
          )}
          {s.missed_referral_cases.length ? (
            <>
              <h2 style={{ marginTop: 16 }}>Missed referrals</h2>
              <p className="muted small">Cases a dermatologist routed more urgently than the app did. Check each one against the triage rules.</p>
              {s.missed_referral_cases.map((id) => <div key={id}><a href={href(`review/${id}`)} className="mono">{id.slice(0, 8)}</a></div>)}
            </>
          ) : null}
        </div>
        <div className="card">
          <h2>Agreement per concern</h2>
          {Object.keys(s.concern_agreement).length === 0 ? <p className="muted">No reviews yet.</p> : (
            <div className="bars">
              {Object.entries(s.concern_agreement).map(([k, v]) => (
                <div className="bar" key={k}><span>{human(k)}</span><div className="track"><div className="fill" style={{ width: pct(v.rate), background: 'var(--primary)' }} /></div><span className="small">{pct(v.rate)}</span></div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
