// Clinic staff (and dermatologists, admins): inbox of shared summaries, case detail, follow-up.
import React, { useEffect, useState } from 'react';

import { blobUrl, CaseBrief, CaseDetail, Clinic, download, FollowUp } from '../api';
import { go, href } from '../router';
import { Badge, errMsg, Field, Notice, ROUTE_META, useAction, useLoad, when } from '../ui';

export const FOLLOW_UP_LABEL: Record<FollowUp, string> = {
  new: 'New', contacted: 'Contacted', booked: 'Booked', no_response: 'No response', closed: 'Closed',
};

export function RouteBadge({ route }: { route: string | null }) {
  const m = ROUTE_META[route ?? ''];
  return <Badge tone={m?.tone}>{m?.label ?? route ?? '–'}</Badge>;
}

/** A photo behind sign-in, fetched with the user's token. */
export function AuthImage({ path, width = 160 }: { path: string; width?: number }) {
  const [src, setSrc] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);
  useEffect(() => {
    let url: string | null = null;
    blobUrl(path).then((u) => { url = u; setSrc(u); }).catch(() => setMissing(true));
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [path]);
  return (
    <div className="photo" style={{ width, height: width * 1.25 }}>
      {src ? <img src={src} alt="Patient photo" /> : missing ? <div className="muted small" style={{ padding: 8 }}>Photo deleted</div> : null}
    </div>
  );
}

const FILTERS = [
  { key: 'open', label: 'Needs review' }, { key: 'referrals', label: 'Referrals' }, { key: 'booked', label: 'Booked' }, { key: 'all', label: 'All' },
] as const;

export function Inbox() {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]['key']>('open');
  const [qr, setQr] = useState('');
  const { data, error } = useLoad(() => Clinic.list(filter === 'open' ? { reviewed: false } : filter === 'booked' ? { follow_up: 'booked' } : {}), [filter]);
  const rows = (data ?? []).filter((r) => filter !== 'referrals' || r.route === 'dermatologist' || r.route === 'urgent_care');

  return (
    <>
      <div className="pagehead">
        <div><h1>Clinic inbox</h1><p className="muted" style={{ margin: 0 }}>Summaries patients chose to share with ICONIC. Patients appear by initials only, and every view is logged.</p></div>
        <form className="row" onSubmit={(e) => { e.preventDefault(); const t = qr.trim().split('/').pop(); if (t) go(`qr/${t}`); }}>
          <input type="text" placeholder="Paste the link from a patient's QR code" value={qr} onChange={(e) => setQr(e.target.value)} style={{ width: 300 }} />
          <button className="btn secondary" disabled={!qr.trim()}>Open</button>
        </form>
      </div>
      <div className="row" style={{ marginBottom: 12 }}>
        {FILTERS.map((f) => <button key={f.key} className={`btn small ${filter === f.key ? '' : 'secondary'}`} onClick={() => setFilter(f.key)} data-testid={`filter-${f.key}`}>{f.label}</button>)}
      </div>
      <Notice kind="error">{error}</Notice>
      <CaseTable rows={rows} empty={data ? 'Nothing here.' : 'Loading…'} open={(id) => go(`case/${id}`)} />
    </>
  );
}

export function CaseTable({ rows, empty, open, extra }: {
  rows: CaseBrief[]; empty: string; open: (id: string) => void; extra?: { head: string; cell: (r: any) => React.ReactNode };
}) {
  if (!rows.length) return <div className="card"><p className="muted" style={{ margin: 0 }}>{empty}</p></div>;
  return (
    <div className="card tablewrap" style={{ padding: 6 }}>
      <table>
        <thead><tr><th>Patient</th><th>Shared</th><th>App route</th><th>Status</th>{extra ? <th>{extra.head}</th> : null}<th /></tr></thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.summary_id} style={{ cursor: 'pointer' }} onClick={() => open(c.summary_id)} data-testid={`case-${c.summary_id}`}>
              <td><b>{c.patient?.initials ?? '–'}</b> <span className="muted">· {c.patient?.age_band}</span></td>
              <td>{when(c.created_at)}</td>
              <td><RouteBadge route={c.route} /></td>
              <td><div className="row"><Badge tone={c.reviewed ? 'ok' : 'caution'}>{c.reviewed ? 'Reviewed' : 'New'}</Badge>{c.follow_up_status !== 'new' ? <Badge tone="gray">{FOLLOW_UP_LABEL[c.follow_up_status]}</Badge> : null}</div></td>
              {extra ? <td>{extra.cell(c)}</td> : null}
              <td style={{ textAlign: 'right' }}><a href={href(`case/${c.summary_id}`)} onClick={(e) => e.stopPropagation()}>Open</a></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const VIEW_LABEL: Record<string, string> = { front: 'Front', left45: 'Left 45°', right45: 'Right 45°', closeup: 'Close-up' };

/** What staff and dermatologists see about a case: the PDF's content, initials only. */
export function CaseBody({ c }: { c: CaseDetail }) {
  const d = c.data ?? {};
  const pr = d.patient_reported ?? {};
  const yes = (pr.red_flags ?? []).filter((f: any) => f.answer === 'Yes');
  return (
    <div className="grid two">
      <div>
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <RouteBadge route={c.route} />
            <Badge tone={c.reviewed ? 'ok' : 'caution'}>{c.reviewed ? 'Reviewed' : 'Not reviewed'}</Badge>
            <Badge tone="gray">{FOLLOW_UP_LABEL[c.follow_up_status]}</Badge>
          </div>
          <div className="kv">
            <div>Patient</div><div><b>{d.patient?.initials}</b> (initials only)</div>
            <div>Age band</div><div>{d.patient?.age_band ?? '–'}</div>
            <div>Skin type</div><div>{d.patient?.skin_type ?? '–'}</div>
            <div>Fitzpatrick (self)</div><div>{d.patient?.self_fitzpatrick ?? '–'}</div>
            <div>Pregnant or breastfeeding</div><div>{d.patient?.pregnant_or_breastfeeding ? 'Yes' : 'No'}</div>
            <div>Shared</div><div>{when(c.created_at)}</div>
            {c.reviewed_by ? <><div>Reviewed by</div><div>{c.reviewed_by}{c.reviewed_at ? `, ${when(c.reviewed_at)}` : ''}</div></> : null}
          </div>
        </div>
        <div className="card">
          <h2>Why the app chose this route</h2>
          {(d.reasons ?? []).map((r: any) => <div key={r.code}>• {r.text}</div>)}
        </div>
        <div className="card">
          <h2>Photos</h2>
          <div className="row" style={{ alignItems: 'flex-start' }}>
            {c.views.map((v) => <div key={v}><AuthImage path={Clinic.imagePath(c.summary_id, v)} width={150} /><div className="muted small">{VIEW_LABEL[v] ?? v}</div></div>)}
          </div>
        </div>
      </div>
      <div>
        <div className="card">
          <h2>Visual pre-screen</h2>
          {(d.visual_prescreen ?? []).length === 0 ? <p className="muted">No visual findings (the urgent route skips the model).</p> : (
            <div className="kv">
              {(d.visual_prescreen ?? []).map((f: any) => <React.Fragment key={f.code}><div>{f.name}</div><div>{f.present ? f.grade_name : 'Not seen'}{f.uncertain ? ' (uncertain)' : ''}</div></React.Fragment>)}
            </div>
          )}
        </div>
        <div className="card">
          <h2>Patient reported</h2>
          <div className="kv">
            {(pr.concerns ?? []).map((x: any) => <React.Fragment key={x.name}><div>{x.name}</div><div>bothersome {x.bothersome_1to3}/3{x.duration_weeks ? `, ${x.duration_weeks} weeks` : ''}</div></React.Fragment>)}
            <div>Red flags</div><div>{yes.length ? yes.map((f: any) => f.question).join('; ') : 'None answered yes'}</div>
            <div>Allergies</div><div>{(pr.allergies ?? []).join(', ') || 'None'}</div>
            <div>On isotretinoin</div><div>{pr.on_isotretinoin ? 'Yes' : 'No'}</div>
            <div>Current routine</div><div>{(pr.current_routine ?? []).map((r: any) => `${r.time}: ${r.product}${r.reaction ? ' (reaction)' : ''}`).join('; ') || 'None given'}</div>
          </div>
        </div>
        {d.routine ? (
          <div className="card">
            <h2>Routine shown to the patient</h2>
            <div className="kv">
              <div>Morning</div><div>{(d.routine.am ?? []).map((s: any) => s.product.name).join(' → ') || '–'}</div>
              <div>Evening</div><div>{(d.routine.pm ?? []).map((s: any) => s.product.name).join(' → ') || '–'}</div>
            </div>
          </div>
        ) : null}
        <p className="muted small">Model {d.versions?.model ?? '–'} · triage {d.versions?.triage_rules ?? '–'} · rules {d.versions?.recommendation_rules ?? '–'}</p>
      </div>
    </div>
  );
}

export function CasePage({ summaryId, qrToken }: { summaryId?: string; qrToken?: string }) {
  const [c, setC] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const act = useAction();

  useEffect(() => {
    (qrToken ? Clinic.openQr(qrToken) : Clinic.get(summaryId!))
      .then((d) => { setC(d); setNote(d.staff_note ?? ''); })
      .catch((e) => setError(e?.status === 410 ? 'This share link has expired.' : errMsg(e)));
  }, [summaryId, qrToken]);

  const save = (body: Parameters<typeof Clinic.update>[1], done: string) =>
    act.run(() => Clinic.update(c!.summary_id, body).then((d) => { setC(d); return d; }), () => done);

  if (error) return <Notice kind="error">{error}</Notice>;
  if (!c) return <p className="muted">Loading…</p>;
  return (
    <>
      <div className="pagehead">
        <div><a href={href('inbox')} className="small">← Clinic inbox</a><h1>Shared summary · {c.patient?.initials}</h1></div>
        <button className="btn secondary" onClick={() => download(Clinic.pdfPath(c.summary_id), `summary-${c.summary_id.slice(0, 8)}.pdf`).catch((e) => act.setMsg({ kind: 'error', text: errMsg(e) }))}>Download PDF</button>
      </div>
      <div className="card">
        <h2>Follow-up</h2>
        <div className="row" style={{ marginBottom: 12 }}>
          {(Object.keys(FOLLOW_UP_LABEL) as FollowUp[]).map((f) => (
            <button key={f} className={`btn small ${c.follow_up_status === f ? '' : 'secondary'}`} disabled={act.busy}
              onClick={() => save({ follow_up_status: f }, `Follow-up set to ${FOLLOW_UP_LABEL[f]}.`)} data-testid={`follow-${f}`}>{FOLLOW_UP_LABEL[f]}</button>
          ))}
        </div>
        <Field label="Staff note (never shown to the patient)">
          <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} data-testid="staff-note" />
        </Field>
        <div className="row">
          <button className="btn secondary" disabled={act.busy} onClick={() => save({ staff_note: note }, 'Note saved.')} data-testid="save-note">Save note</button>
          <button className="btn" disabled={act.busy} onClick={() => save({ reviewed: !c.reviewed }, c.reviewed ? 'Marked as not reviewed.' : 'Marked reviewed.')} data-testid="mark-reviewed">
            {c.reviewed ? 'Mark as not reviewed' : 'Mark reviewed'}
          </button>
        </div>
        {act.msg ? <div style={{ marginTop: 12 }}><Notice kind={act.msg.kind}>{act.msg.text}</Notice></div> : null}
      </div>
      <CaseBody c={c} />
    </>
  );
}
