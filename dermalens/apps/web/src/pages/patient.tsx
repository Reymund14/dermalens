// Patient: check history, the guided check (questions + 3 photos), results, privacy settings.
import { useEffect, useMemo, useRef, useState } from 'react';

import { AllergenHit, Compare, ConcernRef, download, IntakeBody, Patient, RedFlagQ, Ref, Result, RoutineStep } from '../api';
import { go, href } from '../router';
import { Badge, BOUNDARY, errMsg, Field, Notice, ROUTE_META, useLoad, when } from '../ui';
import { CONSENTS } from './auth';
import { AuthImage } from './clinic';

// ----- Home ---------------------------------------------------------------------

export function Home() {
  const { data, error } = useLoad(() => Patient.sessions());
  const done = (data ?? []).filter((s) => s.status === 'complete');
  return (
    <>
      <div className="pagehead">
        <div><h1>My checks</h1><p className="muted" style={{ margin: 0 }}>{done.length ? 'Check again 6 to 8 weeks after starting a routine to compare.' : 'Your first check takes about 6 minutes: 5 short question steps, then 3 photos.'}</p></div>
        <a className="btn" href={href('check')} data-testid="new-check">{done.length ? 'New check' : 'Start my first check'}</a>
      </div>
      <Notice kind="error">{error}</Notice>
      {data && !done.length ? <div className="card"><p className="muted" style={{ margin: 0 }}>No checks yet.</p></div> : null}
      {done.length ? (
        <div className="card tablewrap">
          <table>
            <thead><tr><th>Date</th><th>Where to go next</th><th /></tr></thead>
            <tbody>
              {done.map((s) => (
                <tr key={s.session_id}>
                  <td>{when(s.created_at)}</td>
                  <td><Badge tone={ROUTE_META[s.route ?? '']?.tone}>{ROUTE_META[s.route ?? '']?.label ?? '–'}</Badge></td>
                  <td style={{ textAlign: 'right' }}><a href={href(`result/${s.session_id}`)}>Open</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <p className="muted small">{BOUNDARY}</p>
    </>
  );
}

// ----- New check ----------------------------------------------------------------

const STEPS = ['Concerns', 'Health', 'Allergies', 'Current routine', 'Lifestyle', 'Photos'];
const VIEWS = [
  { view: 'front', label: 'Front', tip: 'Face the camera, hair off your face, neutral expression.' },
  { view: 'left45', label: 'Left side', tip: 'Turn your head about 45° so your left cheek faces the camera.' },
  { view: 'right45', label: 'Right side', tip: 'Turn your head about 45° so your right cheek faces the camera.' },
] as const;
const CHECK_TIPS: Record<string, string> = {
  resolution: 'Move a little closer, or use a sharper camera.',
  face_present: 'Fit your whole face in the photo.',
  sharpness: 'The photo is blurry. Hold the camera still.',
  exposure: 'The light is too dim or too harsh. Face a window or a bright, even light.',
  even_lighting: 'One side of your face is brighter. Turn so the light falls evenly.',
};
const QUICK_ALLERGENS = [
  { family_code: 'fragrance', label: 'Fragrance' }, { family_code: 'essential_oils', label: 'Essential oils' },
  { family_code: 'lanolin', label: 'Lanolin' }, { family_code: 'parabens', label: 'Parabens' },
];

type Allergen = { family_code?: string; ingredient_id?: string; raw_text?: string; label: string };
type Photo = { blob: Blob; url: string; status: 'pending' | 'uploading' | 'pass' | 'fail'; failed: string[] };

/** Re-encodes a photo: drops EXIF (location, device), fixes rotation, caps width at 1440 px. */
async function prepare(file: File): Promise<Blob> {
  const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' });
  const scale = Math.min(1, 1440 / bmp.width);
  const c = document.createElement('canvas');
  c.width = Math.round(bmp.width * scale);
  c.height = Math.round(bmp.height * scale);
  c.getContext('2d')!.drawImage(bmp, 0, 0, c.width, c.height);
  return new Promise((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error('could not read the photo'))), 'image/jpeg', 0.9));
}

function Choice<T extends string | number>({ options, value, onChange, testid }: {
  options: { label: string; value: T }[]; value: T | undefined; onChange: (v: T) => void; testid?: string;
}) {
  return (
    <div className="row" role="radiogroup">
      {options.map((o) => (
        <button key={String(o.value)} type="button" role="radio" aria-checked={value === o.value}
          className={`btn small ${value === o.value ? '' : 'secondary'}`} onClick={() => onChange(o.value)}
          data-testid={testid ? `${testid}-${o.value}` : undefined}>{o.label}</button>
      ))}
    </div>
  );
}
const YESNO = [{ label: 'No', value: 'no' }, { label: 'Yes', value: 'yes' }] as const;
const yn = (v: boolean | undefined) => (v === undefined ? undefined : v ? 'yes' : 'no');

export function NewCheck() {
  const [step, setStep] = useState(0);
  const [concernRefs, setConcernRefs] = useState<ConcernRef[]>([]);
  const [flags, setFlags] = useState<RedFlagQ[]>([]);
  const [concerns, setConcerns] = useState<IntakeBody['concerns']>([]);
  const [answers, setAnswers] = useState<Record<string, boolean>>({});
  const [iso, setIso] = useState<boolean | undefined>();
  const [rx, setRx] = useState<boolean | undefined>();
  const [allergens, setAllergens] = useState<Allergen[]>([]);
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<AllergenHit[]>([]);
  const [routine, setRoutine] = useState<IntakeBody['current_routine']>([]);
  const [life, setLife] = useState<IntakeBody['lifestyle']>({});
  const [photos, setPhotos] = useState<Record<string, Photo | undefined>>({});
  const [session, setSession] = useState<{ id: string; urls: Record<string, string> } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Ref.concerns().then(setConcernRefs).catch(() => {});
    Ref.redFlags().then(setFlags).catch(() => {});
  }, []);
  useEffect(() => {
    const t = setTimeout(() => { if (q.trim().length >= 2) Ref.allergens(q).then(setHits).catch(() => {}); else setHits([]); }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const urgent = flags.filter((f) => f.urgent && answers[f.code]);
  const healthDone = flags.length > 0 && flags.every((f) => answers[f.code] !== undefined) && iso !== undefined && rx !== undefined;
  const canNext = step === 1 ? healthDone : true;

  function intakeBody(): IntakeBody {
    return {
      concerns, red_flags: answers, on_isotretinoin: !!iso, current_rx_topicals: !!rx,
      allergens: allergens.map(({ label: _l, ...a }) => a),
      current_routine: routine.filter((r) => r.free_text_name?.trim()),
      lifestyle: life,
    };
  }

  async function next() {
    setError(null);
    if (step === 4) {
      // Questions are done: save the intake and open a photo session.
      setBusy('intake');
      try {
        const intake = await Patient.createIntake(intakeBody());
        const s = await Patient.openSession(intake.intake_id);
        setSession({ id: s.session_id, urls: s.upload_urls });
        setStep(5);
      } catch (e) { setError(errMsg(e)); } finally { setBusy(null); }
      return;
    }
    setStep(step + 1);
  }

  async function addPhoto(view: string, file: File | undefined) {
    if (!file || !session) return;
    setError(null);
    let blob: Blob;
    try { blob = await prepare(file); } catch { setError('That file is not a photo we can read. Use a JPEG or PNG.'); return; }
    const url = URL.createObjectURL(blob);
    setPhotos((p) => ({ ...p, [view]: { blob, url, status: 'uploading', failed: [] } }));
    try {
      let urls = session.urls;
      let up;
      try { up = await Patient.upload(urls[view], blob); } catch {
        urls = (await Patient.uploadUrls(session.id)).upload_urls; // signed URLs last 5 minutes
        setSession({ ...session, urls });
        up = await Patient.upload(urls[view], blob);
      }
      const r = await Patient.registerImage(session.id, view, up);
      const failed = Object.entries(r.checks).filter(([, ok]) => !ok).map(([k]) => k);
      setPhotos((p) => ({ ...p, [view]: { blob, url, status: r.quality_pass ? 'pass' : 'fail', failed } }));
    } catch (e) {
      setPhotos((p) => ({ ...p, [view]: undefined }));
      setError(errMsg(e));
    }
  }

  async function submit() {
    if (!session) return;
    setBusy('submit'); setError(null);
    try {
      await Patient.submit(session.id);
      go(`result/${session.id}`);
    } catch (e) { setError(errMsg(e)); setBusy(null); }
  }

  const allPhotos = VIEWS.every((v) => photos[v.view] && photos[v.view]!.status !== 'uploading');

  return (
    <>
      <div className="pagehead"><div><h1>New check</h1><p className="muted" style={{ margin: 0 }}>Step {step + 1} of {STEPS.length}: {STEPS[step]}</p></div></div>
      <div className="row" style={{ marginBottom: 18, gap: 4 }}>
        {STEPS.map((s, i) => <div key={s} title={s} style={{ flex: 1, height: 6, borderRadius: 3, background: i <= step ? 'var(--primary)' : 'var(--line)' }} />)}
      </div>

      {urgent.length ? (
        <div className="notice error" data-testid="urgent-banner" style={{ border: '1px solid var(--danger)' }}>
          <b style={{ fontSize: 17 }}>Please seek medical care promptly.</b><br />
          What you described needs a doctor today. Go to an emergency room or see a physician as soon as you can (Philippines emergency: 911). DermaLens will not suggest a routine for this.
          <div style={{ marginTop: 8 }}><button className="btn danger small" onClick={() => setAnswers({ ...answers, ...Object.fromEntries(urgent.map((f) => [f.code, false])) })}>I answered by mistake</button></div>
        </div>
      ) : null}

      <div className="card">
        {step === 0 ? (
          <>
            <h2>What would you like to look at?</h2>
            <p className="muted">Choose any that bother you. You can also choose none.</p>
            <div className="row" style={{ marginBottom: 14 }}>
              {concernRefs.map((r) => {
                const on = concerns.some((c) => c.code === r.code);
                return <button key={r.code} type="button" className={`btn small ${on ? '' : 'secondary'}`} aria-pressed={on}
                  onClick={() => setConcerns(on ? concerns.filter((c) => c.code !== r.code) : [...concerns, { code: r.code, self_severity: 2, duration_weeks: 4 }])}>{r.name}</button>;
              })}
            </div>
            {concerns.map((c) => (
              <div key={c.code} className="card" style={{ background: 'var(--bg)' }}>
                <b>{concernRefs.find((r) => r.code === c.code)?.name}</b>
                <div className="grid two" style={{ marginTop: 8 }}>
                  <div><p className="muted small">How bothersome?</p>
                    <Choice options={[{ label: 'A little', value: 1 }, { label: 'Moderately', value: 2 }, { label: 'A lot', value: 3 }]} value={c.self_severity}
                      onChange={(v) => setConcerns(concerns.map((x) => (x.code === c.code ? { ...x, self_severity: v } : x)))} /></div>
                  <div><p className="muted small">For how long?</p>
                    <Choice options={[{ label: '< 1 month', value: 2 }, { label: '1–3 months', value: 8 }, { label: '3–6 months', value: 18 }, { label: '> 6 months', value: 30 }]} value={c.duration_weeks}
                      onChange={(v) => setConcerns(concerns.map((x) => (x.code === c.code ? { ...x, duration_weeks: v } : x)))} /></div>
                </div>
              </div>
            ))}
          </>
        ) : null}

        {step === 1 ? (
          <>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <h2 style={{ margin: 0 }}>A quick health check</h2>
              <button type="button" className="btn secondary small" data-testid="health-all-no"
                onClick={() => { setAnswers(Object.fromEntries(flags.map((f) => [f.code, false]))); setIso(false); setRx(false); }}>None of these apply to me</button>
            </div>
            <p className="muted">These questions make sure we send you to the right person. Please answer every one.</p>
            <table><tbody>
              {flags.map((f) => (
                <tr key={f.code}><td>{f.question}</td><td style={{ width: 130 }}><Choice options={[...YESNO]} value={yn(answers[f.code])} onChange={(v) => setAnswers({ ...answers, [f.code]: v === 'yes' })} /></td></tr>
              ))}
              <tr><td>Are you currently taking isotretinoin (for example, for acne)?</td><td><Choice options={[...YESNO]} value={yn(iso)} onChange={(v) => setIso(v === 'yes')} /></td></tr>
              <tr><td>Are you using any prescription creams or gels on your face?</td><td><Choice options={[...YESNO]} value={yn(rx)} onChange={(v) => setRx(v === 'yes')} /></td></tr>
            </tbody></table>
          </>
        ) : null}

        {step === 2 ? (
          <>
            <h2>Any ingredient allergies?</h2>
            <p className="muted">We will never suggest a product that contains them. Skip if none.</p>
            <div className="row" style={{ marginBottom: 12 }}>
              {QUICK_ALLERGENS.map((a) => {
                const on = allergens.some((x) => x.label === a.label);
                return <button key={a.label} type="button" className={`btn small ${on ? '' : 'secondary'}`} aria-pressed={on}
                  onClick={() => setAllergens(on ? allergens.filter((x) => x.label !== a.label) : [...allergens, a])}>{a.label}</button>;
              })}
            </div>
            <Field label="Search an ingredient"><input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. salicylic acid, vitamin C" data-testid="allergen-search" /></Field>
            {hits.length ? (
              <div className="card" style={{ padding: 6 }}>
                {hits.map((h) => (
                  <button key={`${h.kind}-${h.family_code ?? h.ingredient_id}`} type="button" className="btn secondary small" style={{ margin: 4 }}
                    onClick={() => { if (!allergens.some((x) => x.label === h.label)) setAllergens([...allergens, { family_code: h.family_code, ingredient_id: h.ingredient_id, label: h.label }]); setQ(''); }}>
                    + {h.label}
                  </button>
                ))}
              </div>
            ) : q.trim().length >= 2 ? (
              <button type="button" className="btn secondary small" onClick={() => { setAllergens([...allergens, { raw_text: q.trim(), label: q.trim() }]); setQ(''); }}>Add “{q.trim()}” as written</button>
            ) : null}
            {allergens.length ? <p>Your allergies: {allergens.map((a) => <Badge key={a.label} tone="caution">{a.label}</Badge>)}</p> : null}
          </>
        ) : null}

        {step === 3 ? (
          <>
            <h2>What do you use now?</h2>
            <p className="muted">Optional. List products you use on your face, especially any that caused a reaction.</p>
            {routine.map((r, i) => (
              <div key={i} className="row" style={{ marginBottom: 8 }}>
                <input type="text" style={{ flex: 1, minWidth: 200 }} placeholder="Product name" value={r.free_text_name ?? ''}
                  onChange={(e) => setRoutine(routine.map((x, j) => (j === i ? { ...x, free_text_name: e.target.value } : x)))} />
                <select style={{ width: 140 }} value={r.time_of_day} onChange={(e) => setRoutine(routine.map((x, j) => (j === i ? { ...x, time_of_day: e.target.value as 'am' } : x)))}>
                  <option value="am">Morning</option><option value="pm">Evening</option><option value="both">Both</option>
                </select>
                <label className="check"><input type="checkbox" checked={r.reaction_reported} onChange={(e) => setRoutine(routine.map((x, j) => (j === i ? { ...x, reaction_reported: e.target.checked } : x)))} /> Caused a reaction</label>
                <button type="button" className="btn danger small" onClick={() => setRoutine(routine.filter((_, j) => j !== i))}>Remove</button>
              </div>
            ))}
            <button type="button" className="btn secondary small" onClick={() => setRoutine([...routine, { time_of_day: 'am', free_text_name: '', reaction_reported: false }])}>+ Add a product</button>
          </>
        ) : null}

        {step === 4 ? (
          <>
            <h2>Your daily habits</h2>
            <p className="muted">Optional. These help explain what the photos show.</p>
            <div className="grid two">
              <div><p className="muted small">Time in the sun on a normal day</p>
                <Choice testid="sun" options={[{ label: '< 15 min', value: 10 }, { label: '15–60 min', value: 40 }, { label: '1–3 hours', value: 120 }, { label: '> 3 hours', value: 240 }]} value={life.daily_sun_exposure_min} onChange={(v) => setLife({ ...life, daily_sun_exposure_min: v })} /></div>
              <div><p className="muted small">Sunscreen</p>
                <Choice testid="sunscreen" options={[{ label: 'Never', value: 'never' }, { label: 'Sometimes', value: 'sometimes' }, { label: 'Daily', value: 'daily' }]} value={life.sunscreen_use} onChange={(v) => setLife({ ...life, sunscreen_use: v })} /></div>
              <div><p className="muted small">Sleep per night</p>
                <Choice options={[{ label: '< 6 h', value: 5 }, { label: '6–8 h', value: 7 }, { label: '> 8 h', value: 9 }]} value={life.sleep_hours} onChange={(v) => setLife({ ...life, sleep_hours: v })} /></div>
              <div><p className="muted small">Stress lately (1 low, 5 high)</p>
                <Choice options={[1, 2, 3, 4, 5].map((n) => ({ label: String(n), value: n }))} value={life.stress_level} onChange={(v) => setLife({ ...life, stress_level: v })} /></div>
              <div><p className="muted small">Do you smoke?</p>
                <Choice options={[...YESNO]} value={yn(life.smoker)} onChange={(v) => setLife({ ...life, smoker: v === 'yes' })} /></div>
              <div><p className="muted small">Glasses of water a day</p>
                <Choice options={[{ label: '< 4', value: 3 }, { label: '4–7', value: 6 }, { label: '8+', value: 8 }]} value={life.water_glasses_per_day} onChange={(v) => setLife({ ...life, water_glasses_per_day: v })} /></div>
            </div>
          </>
        ) : null}

        {step === 5 ? (
          <>
            <h2>Three face photos</h2>
            <p className="muted">Use a phone or webcam photo in bright, even light (face a window), no filters, no makeup if you can. Each photo is checked as soon as you add it. Location and device details are removed before upload.</p>
            <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
              {VIEWS.map((v) => {
                const ph = photos[v.view];
                return (
                  <div key={v.view} className="card" style={{ background: 'var(--bg)', marginBottom: 0 }}>
                    <b>{v.label}</b><p className="muted small" style={{ marginTop: 2 }}>{v.tip}</p>
                    <div style={{ aspectRatio: '4 / 5', maxWidth: 220, background: 'var(--line)', borderRadius: 8, overflow: 'hidden', marginBottom: 8 }}>
                      {ph ? <img src={ph.url} alt={`${v.label} photo`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : null}
                    </div>
                    {ph?.status === 'uploading' ? <p className="small muted">Checking…</p> : null}
                    {ph?.status === 'pass' ? <p className="small" style={{ color: 'var(--ok)', fontWeight: 600 }} data-testid={`ok-${v.view}`}>✓ Looks good</p> : null}
                    {ph?.status === 'fail' ? <div className="small" style={{ color: 'var(--caution)' }}><b>Please retake:</b>{ph.failed.map((k) => <div key={k}>• {CHECK_TIPS[k] ?? k}</div>)}</div> : null}
                    <label className="btn secondary small" style={{ display: 'inline-block', marginTop: 6 }}>
                      {ph ? 'Replace photo' : 'Choose photo'}
                      <input type="file" accept="image/*" capture="user" hidden data-testid={`photo-${v.view}`} onChange={(e) => { addPhoto(v.view, e.target.files?.[0]); e.target.value = ''; }} />
                    </label>
                  </div>
                );
              })}
            </div>
          </>
        ) : null}
      </div>

      <Notice kind="error">{error}</Notice>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <button className="btn secondary" disabled={step === 0 || step === 5 || !!busy} onClick={() => setStep(step - 1)}>Back</button>
        {step < 5 ? (
          <button className="btn" disabled={!canNext || !!busy} onClick={next} data-testid="next">{busy === 'intake' ? 'Saving…' : step === 4 ? 'Continue to photos' : 'Next'}</button>
        ) : (
          <button className="btn" disabled={!allPhotos || !!busy} onClick={submit} data-testid="submit-check">{busy === 'submit' ? 'Sending…' : 'Check my skin'}</button>
        )}
      </div>
      {step === 1 && !healthDone ? <p className="muted small" style={{ textAlign: 'right' }}>Please answer every question.</p> : null}
    </>
  );
}

// ----- Result -------------------------------------------------------------------

const TONE_CLASS: Record<string, string> = { urgent: 'error', caution: 'caution', info: 'info', ok: 'ok' };
const BAND_DOTS: Record<string, number> = { low: 1, medium: 2, high: 3 };

function RoutineList({ steps }: { steps: RoutineStep[] }) {
  return (
    <>
      {steps.map((s) => (
        <div key={`${s.step}-${s.product.id}`} className="card" style={{ marginBottom: 10 }}>
          <div className="muted small">Step {s.step} · {s.slot[0].toUpperCase() + s.slot.slice(1)} · {s.frequency.replace(/_/g, ' ')}</div>
          <b>{s.product.brand} {s.product.name}</b>
          <div>{s.why}</div>
          <div className="muted small">FDA notification: {s.product.fda_notification_no ?? '–'}{s.product.price_php ? ` · ₱${s.product.price_php}` : ''}{s.product.stocked_by_iconic ? ' · Available at ICONIC' : ''}</div>
          {s.patch_test ? <div className="small" style={{ color: 'var(--caution)', fontWeight: 600 }}>New active: patch-test first</div> : null}
        </div>
      ))}
    </>
  );
}

const TREND: Record<string, string> = { better: 'Looks better', same: 'About the same', worse: 'Looks more noticeable', unknown: 'Not compared' };

/** Since your last check: how each concern moved. Estimates only, so the wording stays cautious. */
function Progress({ c }: { c: Compare }) {
  const days = c.days_between;
  return (
    <div className="card" data-testid="progress">
      <h2>Since your last check</h2>
      <p className="muted small" style={{ marginTop: -4 }}>
        Compared with <a href={href(`result/${c.previous_session_id}`)}>your check {days === 0 ? 'earlier today' : `${days} day${days === 1 ? '' : 's'} before`}</a>.
      </p>
      <table><tbody>
        {c.concerns.map((x) => (
          <tr key={x.code}>
            <td><b>{x.name}</b><div className="muted small">{x.before ?? '?'} then, {(x.now ?? '?').toLowerCase()} now</div></td>
            <td style={{ textAlign: 'right' }}><span className={`trend ${x.trend}`} data-testid={`trend-${x.code}`}>{TREND[x.trend]}</span></td>
          </tr>
        ))}
      </tbody></table>
      <p className="muted small" style={{ marginBottom: 0 }}>{c.note}</p>
    </div>
  );
}

export function ResultPage({ sessionId }: { sessionId: string }) {
  const [r, setR] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<'am' | 'pm'>('am');
  const [consents, setConsents] = useState<Record<string, boolean>>({});
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    let stop = false;
    const poll = async () => {
      try {
        const res = await Patient.result(sessionId);
        if (stop) return;
        setR(res);
        if (res.status === 'processing' || res.status === 'uploaded') timer.current = window.setTimeout(poll, 1200);
      } catch (e) { setError(errMsg(e)); }
    };
    poll();
    Patient.consents().then(setConsents).catch(() => {});
    return () => { stop = true; window.clearTimeout(timer.current); };
  }, [sessionId]);

  async function summary(share: boolean) {
    setBusy(share ? 'share' : 'pdf'); setMsg(null);
    try {
      if (share && !consents.share_with_clinic) setConsents(await Patient.setConsent('share_with_clinic', true));
      const s = await Patient.summary(sessionId, share);
      await download(s.pdf_url, `dermalens-summary-${s.summary_id.slice(0, 8)}.pdf`);
      setMsg({ kind: 'ok', text: share ? 'Sent to ICONIC. Staff can open it for 30 days after signing in. A copy was downloaded for you.' : 'Your summary was downloaded.' });
    } catch (e) { setMsg({ kind: 'error', text: errMsg(e) }); } finally { setBusy(null); }
  }

  if (error) return <Notice kind="error">{error}</Notice>;
  if (!r || r.status === 'processing' || r.status === 'uploaded') {
    return <div className="card" style={{ textAlign: 'center', padding: 48 }}><h2>Checking your photos…</h2><p className="muted">This usually takes a few seconds.</p></div>;
  }
  if (r.status === 'needs_retake' || r.status === 'failed') {
    return (
      <>
        <h1>We need new photos</h1>
        <Notice kind="info">{r.message}</Notice>
        <a className="btn" href={href('check')}>Start a new check</a>
      </>
    );
  }
  const route = r.route!;
  return (
    <>
      <div className="pagehead"><div><h1>Your results</h1><p className="muted" style={{ margin: 0 }}>{when(r.created_at)}</p></div></div>
      <div className={`notice ${TONE_CLASS[route.tone] ?? 'info'}`} style={{ border: '1px solid currentColor' }} data-testid={`route-${route.code}`}>
        <b style={{ fontSize: 18 }}>{route.title}</b>
        <div style={{ color: 'var(--text)', marginTop: 4 }}>{route.body}</div>
      </div>
      <div className="grid two">
        <div>
          <div className="card">
            <h2>Why</h2>
            {(r.reasons ?? []).map((x) => <div key={x.code}>• {x.text}</div>)}
          </div>
          {r.findings?.length ? (
            <div className="card">
              <h2>What the photos show</h2>
              <table><tbody>
                {r.findings.map((f) => (
                  <tr key={f.code}>
                    <td><b>{f.name}</b><div className="muted small">{f.present ? f.grade_name : 'Not seen'}{f.uncertain ? ' (hard to tell from the photos)' : ''}</div></td>
                    <td style={{ textAlign: 'right' }} title={`Confidence: ${f.band}`}>
                      {[1, 2, 3].map((i) => <span key={i} style={{ display: 'inline-block', width: 9, height: 9, borderRadius: 5, marginLeft: 3, background: f.present && i <= BAND_DOTS[f.band] ? 'var(--primary)' : 'var(--line)' }} />)}
                    </td>
                  </tr>
                ))}
              </tbody></table>
            </div>
          ) : null}
          {r.compare ? <Progress c={r.compare} /> : null}
          <div className="card">
            <h2>Your photos</h2>
            <div className="row">{['front', 'left45', 'right45'].map((v) => <AuthImage key={v} path={Patient.imagePath(sessionId, v)} width={120} />)}</div>
          </div>
        </div>
        <div>
          {r.routine ? (
            <div className="card">
              <div className="row" style={{ justifyContent: 'space-between', marginBottom: 10 }}>
                <h2 style={{ margin: 0 }}>{r.routine.basics_only ? 'Gentle basics until your visit' : 'Your routine'}</h2>
                <Choice testid="tab" options={[{ label: 'Morning', value: 'am' }, { label: 'Evening', value: 'pm' }]} value={tab} onChange={setTab} />
              </div>
              <RoutineList steps={r.routine[tab]} />
              {r.routine.notes.map((n, i) => <p key={i} className="muted small">{n}</p>)}
            </div>
          ) : null}
          <div className="card">
            <h2>Pre-screening summary</h2>
            <p className="muted">A two-page PDF with your answers, the photo findings and your routine. Bring it to a consultation, or send it to ICONIC staff before your visit.</p>
            <div className="row">
              <button className="btn" onClick={() => summary(false)} disabled={!!busy} data-testid="summary-pdf">{busy === 'pdf' ? 'Preparing…' : 'Download PDF'}</button>
              <button className="btn secondary" onClick={() => summary(true)} disabled={!!busy} data-testid="summary-share">{busy === 'share' ? 'Sending…' : 'Send to ICONIC'}</button>
            </div>
            {!consents.share_with_clinic ? <p className="muted small">Sending turns on the “Share summaries with ICONIC” choice. You can turn it off in Privacy and account.</p> : null}
            {msg ? <div style={{ marginTop: 10 }} data-testid="summary-msg"><Notice kind={msg.kind}>{msg.text}</Notice></div> : null}
          </div>
        </div>
      </div>
      <p className="muted small">{r.boundary}</p>
    </>
  );
}

// ----- Settings -----------------------------------------------------------------

export function Settings() {
  const { data: consents, reload } = useLoad(() => Patient.consents());
  const { data: profile } = useLoad(() => Patient.profile());
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const greeting = useMemo(() => profile?.full_name?.split(' ')[0], [profile]);

  async function toggle(purpose: string, granted: boolean) {
    try { await Patient.setConsent(purpose, granted); await reload(); setMsg({ kind: 'ok', text: 'Saved.' }); } catch (e) { setMsg({ kind: 'error', text: errMsg(e) }); }
  }
  async function exportData() {
    const data = await Patient.exportData();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
    a.download = 'dermalens-my-data.json';
    a.click();
    setMsg({ kind: 'ok', text: 'Your data was downloaded.' });
  }
  async function remove() {
    if (!window.confirm('Delete your DermaLens account, photos and summaries? This cannot be undone.')) return;
    await Patient.deleteAccount();
    window.location.hash = '#/login';
    window.location.reload();
  }

  return (
    <>
      <div className="pagehead"><div><h1>Privacy and account</h1>{greeting ? <p className="muted" style={{ margin: 0 }}>Signed in as {greeting}</p> : null}</div></div>
      {msg ? <Notice kind={msg.kind}>{msg.text}</Notice> : null}
      <div className="card">
        <h2>Your choices</h2>
        {CONSENTS.map((c) => (
          <label key={c.purpose} style={{ display: 'flex', gap: 12, padding: '10px 0', borderBottom: '1px solid var(--line)', cursor: 'pointer' }}>
            <input type="checkbox" checked={!!consents?.[c.purpose]} onChange={(e) => toggle(c.purpose, e.target.checked)} />
            <span><b>{c.title}</b><br /><span className="muted small">{c.body}</span></span>
          </label>
        ))}
      </div>
      <div className="card">
        <h2>Your data</h2>
        <div className="row">
          <button className="btn secondary" onClick={exportData}>Download my data</button>
          <button className="btn danger" onClick={remove}>Delete my account</button>
        </div>
      </div>
    </>
  );
}
