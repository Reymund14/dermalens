// Admin: dashboard, staff accounts, product catalog, rules, models and jobs, audit log.
import React, { useMemo, useState } from 'react';

import { Admin, AuditRow, Me, Product, ProductIn, StaffRole, StaffUser } from '../api';
import { href } from '../router';
import { Badge, errMsg, Field, human, Modal, Notice, ROLE_LABEL, ROUTE_META, useAction, useLoad, when } from '../ui';

const STAFF_ROLES: StaffRole[] = ['clinic_staff', 'dermatologist', 'admin'];

function Head({ title, sub, children }: { title: string; sub?: string; children?: React.ReactNode }) {
  return <div className="pagehead"><div><h1>{title}</h1>{sub ? <p className="muted" style={{ margin: 0 }}>{sub}</p> : null}</div><div className="row">{children}</div></div>;
}

// ----- Dashboard ----------------------------------------------------------------

export function Dashboard() {
  const { data: d, error } = useLoad(() => Admin.dashboard());
  if (error) return <Notice kind="error">{error}</Notice>;
  if (!d) return <p className="muted">Loading…</p>;
  const totalRoutes = Object.values(d.routes).reduce((a, b) => a + b, 0) || 1;
  return (
    <>
      <Head title="Dashboard" sub="DermaLens at a glance." />
      <div className="grid stats">
        <div className="card stat"><div className="n">{d.users.patient}</div><div className="l">Patients</div></div>
        <div className="card stat"><div className="n">{d.sessions}</div><div className="l">Checks run</div></div>
        <div className="card stat"><div className="n" style={{ color: d.unreviewed_summaries ? 'var(--caution)' : 'var(--ok)' }}>{d.unreviewed_summaries}</div><div className="l">Shared summaries not reviewed (of {d.shared_summaries})</div></div>
        <div className="card stat"><div className="n">{d.products_listed}</div><div className="l">Listed products ({d.products_unlisted} not listed)</div></div>
      </div>
      <div className="grid two">
        <div className="card">
          <h2>Where checks sent people</h2>
          <div className="bars">
            {Object.keys(ROUTE_META).map((k) => (
              <div className="bar" key={k}>
                <span>{ROUTE_META[k].label}</span>
                <div className="track"><div className="fill" style={{ width: `${((d.routes[k] ?? 0) / totalRoutes) * 100}%`, background: ROUTE_META[k].color }} /></div>
                <span className="small">{d.routes[k] ?? 0}</span>
              </div>
            ))}
          </div>
          <p className="muted small" style={{ marginBottom: 0 }}>Checks by status: {Object.entries(d.sessions_by_status).filter(([, n]) => n).map(([s, n]) => `${human(s)} ${n}`).join(' · ') || 'none yet'}</p>
        </div>
        <div className="card">
          <h2>System status</h2>
          <div className="kv">
            <div>Staff accounts</div><div>{d.users.clinic_staff} clinic staff · {d.users.dermatologist} dermatologist · {d.users.admin} admin{d.disabled_users ? ` · ${d.disabled_users} disabled` : ''}</div>
            <div>Rules</div><div className="mono">{d.triage_version} / {d.rule_set_version}</div>
            <div>Rule sign-off</div><div>{d.rules_signed_off ? <Badge tone="ok">Signed off by a dermatologist</Badge> : <Badge tone="caution">Waiting for dermatologist sign-off</Badge>}</div>
            <div>Active model</div><div><span className="mono">{d.active_model ?? 'none'}</span>{d.active_model?.includes('stub') ? <> <Badge tone="caution">Not a trained model</Badge></> : null}</div>
            <div>Dermatologist reviews</div><div>{d.derm_reviews}</div>
          </div>
        </div>
      </div>
      <div className="row">
        <a className="btn secondary" href={href('admin/users')}>Manage staff accounts</a>
        <a className="btn secondary" href={href('inbox')}>Open clinic inbox</a>
      </div>
    </>
  );
}

// ----- Staff accounts -----------------------------------------------------------

export function Users({ me }: { me: Me }) {
  const { data, error, reload } = useLoad(() => Admin.users());
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<StaffUser | null>(null);
  const [form, setForm] = useState({ email: '', display_name: '', password: '', role: 'clinic_staff' as StaffRole });
  const [pw, setPw] = useState('');
  const act = useAction();
  const modal = useAction();

  async function create() {
    if (await modal.run(() => Admin.createUser(form), () => '')) {
      act.setMsg({ kind: 'ok', text: `Created ${form.email}. Give them the temporary password in person or by phone.` });
      setAdding(false); setForm({ email: '', display_name: '', password: '', role: 'clinic_staff' }); reload();
    }
  }
  async function update(u: StaffUser, body: Parameters<typeof Admin.updateUser>[1], done: string) {
    if (await act.run(() => Admin.updateUser(u.id, body), () => done)) { reload(); setEditing(null); setPw(''); }
  }

  return (
    <>
      <Head title="Staff accounts" sub="Clinic staff, dermatologists and admins. Patients sign up themselves and are not listed here.">
        <button className="btn" onClick={() => { modal.setMsg(null); setAdding(true); }} data-testid="add-user">Add account</button>
      </Head>
      {act.msg ? <Notice kind={act.msg.kind}>{act.msg.text}</Notice> : null}
      <Notice kind="error">{error}</Notice>
      <div className="card tablewrap" style={{ padding: 6 }}>
        <table>
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Created</th><th /></tr></thead>
          <tbody>
            {(data ?? []).map((u) => (
              <tr key={u.id} data-testid={`user-${u.email}`}>
                <td><b>{u.display_name ?? '–'}</b>{u.id === me.id ? <span className="muted small"> (you)</span> : null}</td>
                <td>{u.email}</td>
                <td>
                  <select value={u.role} disabled={u.id === me.id || act.busy} style={{ width: 160 }} aria-label={`Role for ${u.email}`}
                    onChange={(e) => update(u, { role: e.target.value as StaffRole }, `${u.email} is now ${ROLE_LABEL[e.target.value]}.`)}>
                    {STAFF_ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                  </select>
                </td>
                <td>{u.disabled ? <Badge tone="danger">Disabled</Badge> : u.locked ? <span title="Too many wrong passwords. Unlocks by itself after 15 minutes, or reset the password."><Badge tone="caution">Locked</Badge></span> : <Badge tone="ok">Active</Badge>}</td>
                <td className="small">{when(u.created_at)}</td>
                <td><div className="row" style={{ justifyContent: 'flex-end' }}>
                  <button className="btn secondary small" onClick={() => { setEditing(u); setPw(''); }}>Reset password</button>
                  {u.id === me.id ? null : u.disabled ? (
                    <button className="btn secondary small" onClick={() => update(u, { disabled: false }, `${u.email} enabled.`)} data-testid="enable">Enable</button>
                  ) : (
                    <button className="btn danger small" data-testid="disable"
                      onClick={() => window.confirm(`Disable ${u.email}? They are signed out at once.`) && update(u, { disabled: true }, `${u.email} disabled.`)}>Disable</button>
                  )}
                </div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {adding ? (
        <Modal title="Add a staff account" onClose={() => setAdding(false)} actions={<>
          <button className="btn secondary" onClick={() => setAdding(false)}>Cancel</button>
          <button className="btn" disabled={modal.busy || !form.email || form.display_name.length < 2 || form.password.length < 10} onClick={create} data-testid="create-user">Create account</button>
        </>}>
          <Field label="Name"><input type="text" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} data-testid="new-name" /></Field>
          <Field label="Email"><input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="new-email" /></Field>
          <Field label="Role">
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as StaffRole })} data-testid="new-role">
              {STAFF_ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </select>
          </Field>
          <Field label="Temporary password (at least 10 characters)"><input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="new-password" /></Field>
          {modal.msg?.kind === 'error' ? <Notice kind="error">{modal.msg.text}</Notice> : null}
        </Modal>
      ) : null}

      {editing ? (
        <Modal title={`Reset password for ${editing.display_name ?? editing.email}`} onClose={() => setEditing(null)} actions={<>
          <button className="btn secondary" onClick={() => setEditing(null)}>Cancel</button>
          <button className="btn" disabled={pw.length < 10 || act.busy} onClick={() => update(editing, { password: pw }, `Password reset for ${editing.email}. They are signed out everywhere.`)}>Reset password</button>
        </>}>
          <Field label="New password (at least 10 characters)"><input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus /></Field>
        </Modal>
      ) : null}
    </>
  );
}

// ----- Catalog ------------------------------------------------------------------

const CATEGORIES = ['cleanser', 'toner', 'serum', 'treatment', 'moisturizer', 'sunscreen', 'exfoliant'];
const SKIN = ['dry', 'oily', 'combination', 'normal', 'sensitive'];

export function Catalog() {
  const { data, error, reload } = useLoad(() => Admin.products());
  const [q, setQ] = useState('');
  const [show, setShow] = useState<'all' | 'listed' | 'unlisted'>('all');
  const [verify, setVerify] = useState<Product | null>(null);
  const [fda, setFda] = useState({ notification_no: '', evidence_uri: '', valid_until: '' });
  const [adding, setAdding] = useState(false);
  const [np, setNp] = useState({ id: '', brand: '', name: '', category: 'cleanser', skin: [...SKIN], inci: '', spf: '', price: '', iconic: false });
  const act = useAction();
  const modal = useAction();

  const rows = useMemo(() => (data ?? []).filter((p) => (show === 'all' || (show === 'listed') === p.is_listed)
    && `${p.brand} ${p.name} ${p.id} ${p.category}`.toLowerCase().includes(q.toLowerCase())), [data, q, show]);

  async function saveVerify() {
    const body = { notification_no: fda.notification_no, evidence_uri: fda.evidence_uri, valid_until: fda.valid_until || undefined };
    if (await modal.run(() => Admin.verifyProduct(verify!.id, body), () => '')) {
      act.setMsg({ kind: 'ok', text: `${verify!.name} is verified and listed.` }); setVerify(null); reload();
    }
  }
  async function addProduct() {
    const body: ProductIn = {
      id: np.id, brand: np.brand, name: np.name, category: np.category, suitable_skin_types: np.skin,
      inci: np.inci.split(/[,\n]/).map((s) => s.trim()).filter(Boolean),
      spf: np.spf ? Number(np.spf) : null, price_php: np.price ? Number(np.price) : null, stocked_by_iconic: np.iconic,
    };
    if (await modal.run(() => Admin.createProduct(body), () => '')) {
      act.setMsg({ kind: 'ok', text: `${np.name} was added. It is not listed until you record its FDA verification.` });
      setAdding(false); reload();
    }
  }

  return (
    <>
      <Head title="Product catalog" sub="Only listed products with a recorded Philippine FDA cosmetic notification are ever recommended.">
        <button className="btn" onClick={() => { modal.setMsg(null); setAdding(true); }} data-testid="add-product">Add product</button>
      </Head>
      {act.msg ? <Notice kind={act.msg.kind}>{act.msg.text}</Notice> : null}
      <Notice kind="error">{error}</Notice>
      <div className="row" style={{ marginBottom: 12 }}>
        <input type="search" placeholder="Search products" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 260 }} />
        {(['all', 'listed', 'unlisted'] as const).map((s) => <button key={s} className={`btn small ${show === s ? '' : 'secondary'}`} onClick={() => setShow(s)}>{s === 'all' ? 'All' : s === 'listed' ? 'Listed' : 'Not listed'}</button>)}
        <span className="muted small">{rows.length} products</span>
      </div>
      <div className="card tablewrap" style={{ padding: 6 }}>
        <table>
          <thead><tr><th>Product</th><th>Category</th><th>FDA notification</th><th>Checked</th><th>Status</th><th /></tr></thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id}>
                <td><b>{p.brand} {p.name}</b><div className="muted small">{p.ingredients.map(human).join(', ')}</div></td>
                <td>{p.category}{p.spf ? ` · SPF ${p.spf}` : ''}</td>
                <td className="mono">{p.fda_notification_no ?? '–'}</td>
                <td className="small">{p.verified_on ?? '–'}</td>
                <td>{p.is_listed ? <Badge tone="ok">Listed</Badge> : <Badge tone="caution">Not listed</Badge>}</td>
                <td><div className="row" style={{ justifyContent: 'flex-end' }}>
                  <button className="btn secondary small" onClick={() => { modal.setMsg(null); setVerify(p); setFda({ notification_no: p.fda_notification_no ?? '', evidence_uri: '', valid_until: '' }); }}>{p.is_listed ? 'Re-verify' : 'Verify and list'}</button>
                  {p.is_listed ? <button className="btn danger small" onClick={() => act.run(() => Admin.delistProduct(p.id), () => `${p.name} delisted.`).then(reload)}>Delist</button> : null}
                </div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {verify ? (
        <Modal title={`FDA verification: ${verify.name}`} onClose={() => setVerify(null)} actions={<>
          <button className="btn secondary" onClick={() => setVerify(null)}>Cancel</button>
          <button className="btn" disabled={modal.busy || fda.notification_no.length < 3 || fda.evidence_uri.length < 3} onClick={saveVerify}>Record and list</button>
        </>}>
          <p className="muted small">Look the product up on the FDA Philippines verification portal first. Products not re-checked within 90 days are delisted automatically.</p>
          <Field label="FDA notification number"><input type="text" value={fda.notification_no} onChange={(e) => setFda({ ...fda, notification_no: e.target.value })} /></Field>
          <Field label="Evidence (link or file reference to the portal result)"><input type="text" value={fda.evidence_uri} onChange={(e) => setFda({ ...fda, evidence_uri: e.target.value })} /></Field>
          <Field label="Valid until (optional)"><input type="date" value={fda.valid_until} onChange={(e) => setFda({ ...fda, valid_until: e.target.value })} /></Field>
          {modal.msg?.kind === 'error' ? <Notice kind="error">{modal.msg.text}</Notice> : null}
        </Modal>
      ) : null}

      {adding ? (
        <Modal title="Add a product" onClose={() => setAdding(false)} actions={<>
          <button className="btn secondary" onClick={() => setAdding(false)}>Cancel</button>
          <button className="btn" disabled={modal.busy || !np.id || !np.brand || !np.name || !np.inci.trim()} onClick={addProduct}>Add product</button>
        </>}>
          <p className="muted small">New products start unlisted. Drug-regulated actives (tretinoin, hydroquinone, clindamycin and others) are refused, and every ingredient name must already be in the synonym table.</p>
          <div className="grid two">
            <Field label="Product id (lowercase, dashes)"><input type="text" value={np.id} onChange={(e) => setNp({ ...np, id: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-') })} placeholder="p-brand-gel-cleanser" /></Field>
            <Field label="Category"><select value={np.category} onChange={(e) => setNp({ ...np, category: e.target.value })}>{CATEGORIES.map((c) => <option key={c}>{c}</option>)}</select></Field>
            <Field label="Brand"><input type="text" value={np.brand} onChange={(e) => setNp({ ...np, brand: e.target.value })} /></Field>
            <Field label="Name"><input type="text" value={np.name} onChange={(e) => setNp({ ...np, name: e.target.value })} /></Field>
            <Field label="SPF (sunscreens)"><input type="number" value={np.spf} onChange={(e) => setNp({ ...np, spf: e.target.value })} /></Field>
            <Field label="Price (₱)"><input type="number" value={np.price} onChange={(e) => setNp({ ...np, price: e.target.value })} /></Field>
          </div>
          <Field label="Ingredients (INCI), in label order, comma-separated"><textarea rows={3} value={np.inci} onChange={(e) => setNp({ ...np, inci: e.target.value })} placeholder="Aqua, Glycerin, Niacinamide" /></Field>
          <div style={{ marginBottom: 10 }}><span className="muted small">Suitable for: </span>
            {SKIN.map((s) => <label key={s} className="check"><input type="checkbox" checked={np.skin.includes(s)} onChange={(e) => setNp({ ...np, skin: e.target.checked ? [...np.skin, s] : np.skin.filter((x) => x !== s) })} /> {s}</label>)}
          </div>
          <label className="check"><input type="checkbox" checked={np.iconic} onChange={(e) => setNp({ ...np, iconic: e.target.checked })} /> Stocked by ICONIC</label>
          {modal.msg?.kind === 'error' ? <div style={{ marginTop: 10 }}><Notice kind="error">{modal.msg.text}</Notice></div> : null}
        </Modal>
      ) : null}
    </>
  );
}

// ----- Rules --------------------------------------------------------------------

const SCOPES = ['same_application', 'same_routine', 'same_day'];
const RESOLUTIONS = ['block', 'split_am_pm', 'alternate_nights'];

export function RulesAdmin() {
  const { data: r, error, reload } = useLoad(() => Admin.rules());
  const { data: dash, reload: reloadDash } = useLoad(() => Admin.dashboard());
  const [f, setF] = useState({ family_a: '', family_b: '', scope: 'same_routine', resolution: 'split_am_pm', rationale: '' });
  const act = useAction();
  if (error) return <Notice kind="error">{error}</Notice>;
  if (!r) return <p className="muted">Loading…</p>;
  const famName = (code: string) => r.families.find((x) => x.code === code)?.name ?? human(code);

  async function add() {
    if (!window.confirm('Adding a rule creates a new rule-set version. A dermatologist must sign it off again.')) return;
    if (await act.run(() => Admin.addConflict(f), (o) => `Saved. Rules are now ${o.rule_set_version} and need a new dermatologist sign-off.`)) {
      setF({ ...f, family_a: '', family_b: '', rationale: '' }); reload(); reloadDash();
    }
  }

  return (
    <>
      <Head title="Rules" sub="What the routine builder must never combine, and who must not get which ingredients.">
        <Badge>{r.rule_set_version}</Badge>
        {dash ? <Badge tone={dash.rules_signed_off ? 'ok' : 'caution'}>{dash.rules_signed_off ? 'Signed off' : 'Needs dermatologist sign-off'}</Badge> : null}
      </Head>
      {act.msg ? <Notice kind={act.msg.kind}>{act.msg.text}</Notice> : null}
      <div className="card">
        <h2>Add an ingredient conflict</h2>
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
          <Field label="Family A"><select value={f.family_a} onChange={(e) => setF({ ...f, family_a: e.target.value })} data-testid="family-a"><option value="">Choose…</option>{r.families.map((x) => <option key={x.code} value={x.code}>{x.name}</option>)}</select></Field>
          <Field label="Family B"><select value={f.family_b} onChange={(e) => setF({ ...f, family_b: e.target.value })} data-testid="family-b"><option value="">Choose…</option>{r.families.map((x) => <option key={x.code} value={x.code}>{x.name}</option>)}</select></Field>
          <Field label="When"><select value={f.scope} onChange={(e) => setF({ ...f, scope: e.target.value })}>{SCOPES.map((s) => <option key={s} value={s}>{human(s)}</option>)}</select></Field>
          <Field label="Then"><select value={f.resolution} onChange={(e) => setF({ ...f, resolution: e.target.value })}>{RESOLUTIONS.map((s) => <option key={s} value={s}>{human(s)}</option>)}</select></Field>
        </div>
        <Field label="Rationale (who advised it and why)"><input type="text" value={f.rationale} onChange={(e) => setF({ ...f, rationale: e.target.value })} data-testid="rationale" /></Field>
        <button className="btn" disabled={act.busy || !f.family_a || !f.family_b || f.family_a === f.family_b || f.rationale.length < 3} onClick={add} data-testid="add-conflict">Add rule</button>
      </div>
      <div className="grid two">
        <div className="card">
          <h2>Ingredient conflicts ({r.conflicts.length})</h2>
          <table><thead><tr><th>Families</th><th>Resolution</th><th>Why</th></tr></thead><tbody>
            {r.conflicts.map((x) => <tr key={x.id}><td>{famName(x.family_a)} + {famName(x.family_b)}</td><td>{human(x.resolution)}<div className="muted small">{human(x.scope)}</div></td><td className="small">{x.rationale}</td></tr>)}
          </tbody></table>
        </div>
        <div className="card">
          <h2>Contraindications ({r.contraindications.length})</h2>
          <table><thead><tr><th>Condition</th><th>Action</th></tr></thead><tbody>
            {r.contraindications.map((x, i) => <tr key={i}><td>{human(x.condition)}</td><td>{human(x.action)} {x.family ? famName(x.family) : human(x.ingredient ?? '')}</td></tr>)}
          </tbody></table>
        </div>
      </div>
    </>
  );
}

// ----- Models and jobs ----------------------------------------------------------

export function Models() {
  const { data, error, reload } = useLoad(() => Admin.models());
  const act = useAction();
  return (
    <>
      <Head title="Models and jobs" sub="The model that reads photos, and the scheduled maintenance jobs." />
      {act.msg ? <Notice kind={act.msg.kind}>{act.msg.text}</Notice> : null}
      <Notice kind="error">{error}</Notice>
      <div className="card tablewrap">
        <h2>Model versions</h2>
        <table>
          <thead><tr><th>Version</th><th>Architecture</th><th>Evaluation report</th><th>SHA-256</th><th>Status</th><th /></tr></thead>
          <tbody>
            {(data ?? []).map((m) => (
              <tr key={m.id}>
                <td className="mono">{m.id}</td><td>{m.architecture}</td><td className="small">{m.eval_report_uri}</td>
                <td className="mono">{m.artifact_sha256.slice(0, 12)}…</td>
                <td>{m.is_active ? <Badge tone="ok">Active</Badge> : <Badge tone="gray">Inactive</Badge>}</td>
                <td>{m.is_active ? null : <button className="btn secondary small" disabled={!m.can_activate || act.busy} title={m.can_activate ? '' : 'Attach an evaluation report first'}
                  onClick={() => window.confirm(`Make ${m.id} the live model for all new checks?`) && act.run(() => Admin.activateModel(m.id), () => `${m.id} is now active.`).then(reload)}>Activate</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small" style={{ marginBottom: 0 }}>A model can only be activated once its evaluation report is attached. Register trained models as described in the README.</p>
      </div>
      <div className="grid two">
        <div className="card">
          <h2>Re-verify the catalog</h2>
          <p className="muted">Delists every product whose FDA check is older than 90 days or whose notification has expired. Runs nightly.</p>
          <button className="btn secondary" disabled={act.busy} onClick={() => act.run(() => Admin.delistStale(), (r) => r.delisted.length ? `Delisted: ${r.delisted.join(', ')}.` : 'Every listed product is within its 90 days.')}>Run now</button>
        </div>
        <div className="card">
          <h2>Photo retention</h2>
          <p className="muted">Deletes photos 12 months after a check, or after 24 hours when the patient did not agree to keep them.</p>
          <button className="btn danger" disabled={act.busy} onClick={() => window.confirm('Permanently delete photos past their retention period?') && act.run(() => Admin.purgeImages(), (r) => `Deleted photos from ${r.sessions_purged} check(s).`)}>Run now</button>
        </div>
      </div>
    </>
  );
}

// ----- Audit log ----------------------------------------------------------------

const ACTIONS = ['', 'login', 'register', 'view_summary', 'view_summary_qr', 'view_summary_image', 'review_summary', 'derm_review', 'rule_signoff',
  'create_user', 'update_user', 'create_product', 'verify_product', 'delist_product', 'auto_delist', 'update_rule', 'activate_model', 'purge_images', 'consent'];

export function Audit() {
  const [action, setAction] = useState('');
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [more, setMore] = useState(true);
  const { error } = useLoad(async () => {
    const r = await Admin.audit({ action, limit: 50 });
    setRows(r); setMore(r.length === 50);
  }, [action]);

  async function loadMore() {
    const r = await Admin.audit({ action, limit: 50, before_id: rows[rows.length - 1]?.id });
    setRows([...rows, ...r]); setMore(r.length === 50);
  }
  function exportCsv() {
    const esc = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const lines = [['time', 'actor', 'role', 'action', 'entity', 'entity_id', 'detail'].join(',')]
      .concat(rows.map((r) => [r.at, r.actor.name, r.actor.role, r.action, r.entity, r.entity_id, r.detail ? JSON.stringify(r.detail) : ''].map(esc).join(',')));
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' }));
    a.download = `dermalens-audit-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
  }

  return (
    <>
      <Head title="Audit log" sub='Who did what, and when. Patients appear as "patient", never by email.'>
        <select value={action} onChange={(e) => setAction(e.target.value)} style={{ width: 220 }} aria-label="Filter by action" data-testid="audit-filter">
          {ACTIONS.map((a) => <option key={a} value={a}>{a ? human(a) : 'All actions'}</option>)}
        </select>
        <button className="btn secondary" onClick={exportCsv} disabled={!rows.length}>Export CSV</button>
      </Head>
      <Notice kind="error">{error}</Notice>
      <div className="card tablewrap" style={{ padding: 6 }}>
        <table>
          <thead><tr><th>When</th><th>Who</th><th>Action</th><th>On</th><th>Detail</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="small" style={{ whiteSpace: 'nowrap' }}>{when(r.at)}</td>
                <td>{r.actor.name}{r.actor.role && r.actor.role !== 'patient' ? <div className="muted small">{ROLE_LABEL[r.actor.role]}</div> : null}</td>
                <td>{human(r.action)}</td>
                <td>{human(r.entity)}<div className="muted small mono">{r.entity_id.length > 20 ? `${r.entity_id.slice(0, 8)}…` : r.entity_id}</div></td>
                <td className="mono small" style={{ maxWidth: 360, wordBreak: 'break-word' }}>{r.detail ? JSON.stringify(r.detail) : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length ? <p className="muted" style={{ padding: 10 }}>No entries.</p> : null}
      </div>
      {more && rows.length ? <button className="btn secondary" onClick={() => loadMore().catch((e) => alert(errMsg(e)))}>Load older entries</button> : null}
    </>
  );
}
