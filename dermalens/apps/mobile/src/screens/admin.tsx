// Admin: dashboard, staff accounts, catalog, rules, models, jobs and audit log.
import { useFocusEffect } from '@react-navigation/native';
import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { Admin, ApiError, StaffUser } from '../api';
import type { Props } from '../nav';
import { Button, C, Card, ErrorText, Field, H1, H2, P, Screen, Segmented } from '../ui';
import { confirmAction, ROLE_LABEL, ROUTE_META, Row, Stat, StatGrid, Tag, when, Who } from './shared';
import { useAccount, useSignOutHeader } from './staff';

const errText = (e: unknown, fallback: string) => {
  const d = e instanceof ApiError ? e.detail : null;
  if (typeof d === 'string') return d;
  if (d && typeof d === 'object' && 'detail' in (d as any)) return `${(d as any).detail}: ${JSON.stringify(Object.values(d as any)[0])}`;
  if (Array.isArray(d)) return d.map((x: any) => x.msg).join('; ');
  return fallback;
};

function Nav({ title, sub, onPress, testID }: { title: string; sub: string; onPress: () => void; testID?: string }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" testID={testID}>
      <Card style={{ flexDirection: 'row', alignItems: 'center' }}>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 17, fontWeight: '600', color: C.text }}>{title}</Text>
          <Text style={{ color: C.muted, fontSize: 14 }}>{sub}</Text>
        </View>
        <Text style={{ color: C.primary, fontSize: 15 }}>Open ›</Text>
      </Card>
    </Pressable>
  );
}

export function AdminHome({ navigation }: Props<'AdminHome'>) {
  useSignOutHeader(navigation);
  const me = useAccount();
  const [d, setD] = useState<Awaited<ReturnType<typeof Admin.dashboard>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  useFocusEffect(useCallback(() => { Admin.dashboard().then(setD).catch(() => setError('Could not load the dashboard.')); }, []));

  return (
    <Screen>
      <H1>Admin</H1>
      {me ? <Who name={me.display_name} role={me.role} /> : null}
      <ErrorText error={error} />
      {d ? <>
        <StatGrid>
          <Stat label="Patients" value={d.users.patient} />
          <Stat label="Checks run" value={d.sessions} />
          <Stat label="Shared, not reviewed" value={d.unreviewed_summaries} tone={d.unreviewed_summaries ? 'caution' : 'ok'} />
          <Stat label="Listed products" value={d.products_listed} />
        </StatGrid>
        <Card>
          <Row label="Staff accounts" value={`${d.users.clinic_staff} staff · ${d.users.dermatologist} dermatologist · ${d.users.admin} admin${d.disabled_users ? ` · ${d.disabled_users} disabled` : ''}`} />
          <Row label="Routes given" value={Object.entries(d.routes).map(([k, v]) => `${ROUTE_META[k]?.label ?? k} ${v}`).join(' · ') || '–'} />
          <Row label="Rules" value={`${d.triage_version} / ${d.rule_set_version}`} />
          <Row label="Rule sign-off" value={<Text style={{ color: d.rules_signed_off ? C.ok : C.caution }}>{d.rules_signed_off ? 'Signed off by a dermatologist' : 'Waiting for dermatologist sign-off'}</Text>} />
          <Row label="Active model" value={d.active_model ?? 'Stub (not trained)'} />
          <Row label="Dermatologist reviews" value={d.derm_reviews} />
        </Card>
      </> : <P muted>Loading…</P>}
      <H2>Manage</H2>
      <Nav testID="admin-users" title="Staff accounts" sub="Create, disable, reset passwords, change roles" onPress={() => navigation.navigate('AdminUsers')} />
      <Nav testID="admin-catalog" title="Product catalog" sub="FDA verification, listing and delisting" onPress={() => navigation.navigate('AdminCatalog')} />
      <Nav testID="admin-rules" title="Rules" sub="Ingredient conflicts and contraindications" onPress={() => navigation.navigate('AdminRules')} />
      <Nav testID="admin-models" title="Models and jobs" sub="Model versions, re-verification and image retention" onPress={() => navigation.navigate('AdminModels')} />
      <Nav testID="admin-audit" title="Audit log" sub="Who did what, and when" onPress={() => navigation.navigate('AdminAudit')} />
    </Screen>
  );
}

const ROLE_OPTS = (['clinic_staff', 'dermatologist', 'admin'] as const).map((v) => ({ label: ROLE_LABEL[v], value: v }));

export function AdminUsers() {
  const me = useAccount();
  const [users, setUsers] = useState<StaffUser[] | null>(null);
  const [form, setForm] = useState({ email: '', display_name: '', password: '', role: 'clinic_staff' as StaffUser['role'] });
  const [open, setOpen] = useState<string | null>(null);
  const [pw, setPw] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => Admin.users().then(setUsers).catch(() => setError('Could not load accounts.'));
  useEffect(() => { load(); }, []);

  async function run(fn: () => Promise<unknown>, done: string) {
    setError(null); setMsg(null);
    try { await fn(); setMsg(done); await load(); } catch (e) { setError(errText(e, 'That did not work.')); }
  }

  return (
    <Screen>
      <H1>Staff accounts</H1>
      <P muted>Patients sign up in the app and are not listed here. Disabling an account signs it out everywhere.</P>
      {msg ? <P style={{ color: C.ok }}>{msg}</P> : null}
      <ErrorText error={error} />
      {users?.map((u) => (
        <Card key={u.id}>
          <Pressable onPress={() => { setOpen(open === u.id ? null : u.id); setPw(''); }} testID={`user-${u.email}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 16, fontWeight: '600', color: C.text }}>{u.display_name ?? u.email}</Text>
                <Text style={{ color: C.muted, fontSize: 14 }}>{u.email}</Text>
              </View>
              <Tag label={ROLE_LABEL[u.role]} />
              {u.disabled ? <Tag label="Disabled" tone="urgent" /> : null}
            </View>
          </Pressable>
          {open === u.id ? (
            <View style={{ marginTop: 12 }}>
              {u.id === me?.id ? <P muted>This is you. You cannot disable or demote your own account.</P> : <>
                <Segmented options={ROLE_OPTS} value={u.role} onChange={(role) => run(() => Admin.updateUser(u.id, { role }), `${u.email} is now ${ROLE_LABEL[role]}.`)} />
                <Button testID="toggle-disabled" kind={u.disabled ? 'secondary' : 'danger'} title={u.disabled ? 'Enable account' : 'Disable account'}
                  onPress={async () => { if (u.disabled || await confirmAction(`Disable ${u.email}? They are signed out at once.`)) run(() => Admin.updateUser(u.id, { disabled: !u.disabled }), u.disabled ? 'Account enabled.' : 'Account disabled.'); }} />
              </>}
              <View style={{ height: 10 }} />
              <Field label="New password (at least 10 characters)" value={pw} onChangeText={setPw} secureTextEntry />
              <Button kind="secondary" title="Reset password" disabled={pw.length < 10} onPress={() => run(() => Admin.updateUser(u.id, { password: pw }), 'Password reset. Give it to them in person or by phone.')} />
            </View>
          ) : null}
        </Card>
      ))}

      <H2>Add an account</H2>
      <Field label="Name" value={form.display_name} onChangeText={(display_name) => setForm({ ...form, display_name })} testID="new-name" />
      <Field label="Email" value={form.email} onChangeText={(email) => setForm({ ...form, email })} autoCapitalize="none" keyboardType="email-address" testID="new-email" />
      <Field label="Temporary password (at least 10 characters)" value={form.password} onChangeText={(password) => setForm({ ...form, password })} secureTextEntry testID="new-password" />
      <Segmented options={ROLE_OPTS} value={form.role} onChange={(role) => setForm({ ...form, role })} />
      <Button testID="create-user" title="Create account" disabled={!form.email || form.display_name.length < 2 || form.password.length < 10}
        onPress={() => run(async () => { await Admin.createUser(form); setForm({ email: '', display_name: '', password: '', role: 'clinic_staff' }); }, `Created ${form.email}.`)} />
    </Screen>
  );
}

export function AdminCatalog() {
  const [rows, setRows] = useState<Awaited<ReturnType<typeof Admin.products>> | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [fda, setFda] = useState({ notification_no: '', evidence_uri: '' });
  const [error, setError] = useState<string | null>(null);
  const load = () => Admin.products().then(setRows).catch(() => setError('Could not load the catalog.'));
  useEffect(() => { load(); }, []);

  async function run(fn: () => Promise<unknown>) {
    setError(null);
    try { await fn(); await load(); setOpen(null); } catch (e) { setError(errText(e, 'That did not work.')); }
  }

  return (
    <Screen>
      <H1>Product catalog</H1>
      <P muted>Only listed products with a recorded Philippine FDA notification are recommended. New products are added through the API (POST /admin/products), which refuses drug-regulated actives and unmapped INCI names.</P>
      <ErrorText error={error} />
      {rows?.map((p) => (
        <Card key={p.id}>
          <Pressable onPress={() => { setOpen(open === p.id ? null : p.id); setFda({ notification_no: p.fda_notification_no ?? '', evidence_uri: '' }); }}>
            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 16, fontWeight: '600', color: C.text }}>{p.brand} {p.name}</Text>
                <Text style={{ color: C.muted, fontSize: 14 }}>{p.category} · {p.fda_notification_no ?? 'no FDA record'}{p.verified_on ? ` · checked ${p.verified_on}` : ''}</Text>
              </View>
              <Tag label={p.is_listed ? 'Listed' : 'Not listed'} tone={p.is_listed ? 'ok' : 'caution'} />
            </View>
          </Pressable>
          {open === p.id ? (
            <View style={{ marginTop: 12 }}>
              <Field label="FDA notification number" value={fda.notification_no} onChangeText={(notification_no) => setFda({ ...fda, notification_no })} />
              <Field label="Evidence (link or file reference to the FDA portal result)" value={fda.evidence_uri} onChangeText={(evidence_uri) => setFda({ ...fda, evidence_uri })} autoCapitalize="none" />
              <Button title="Record verification and list" disabled={fda.notification_no.length < 3 || fda.evidence_uri.length < 3} onPress={() => run(() => Admin.verifyProduct(p.id, fda))} />
              {p.is_listed ? <><View style={{ height: 10 }} /><Button kind="danger" title="Delist" onPress={() => run(() => Admin.delistProduct(p.id))} /></> : null}
            </View>
          ) : null}
        </Card>
      ))}
    </Screen>
  );
}

const SCOPES = ['same_application', 'same_routine', 'same_day'];
const RESOLUTIONS = ['block', 'split_am_pm', 'alternate_nights'];
const opt = (xs: string[]) => xs.map((v) => ({ label: v.replace(/_/g, ' '), value: v }));

export function AdminRules() {
  const [r, setR] = useState<Awaited<ReturnType<typeof Admin.rules>> | null>(null);
  const [f, setF] = useState({ family_a: '', family_b: '', scope: 'same_routine', resolution: 'split_am_pm', rationale: '' });
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => Admin.rules().then(setR).catch(() => setError('Could not load rules.'));
  useEffect(() => { load(); }, []);

  async function add() {
    if (!(await confirmAction('Adding a rule creates a new rule-set version. A dermatologist must sign it off again.'))) return;
    setError(null);
    try {
      const out = await Admin.addConflict(f);
      setMsg(`Saved. Rules are now ${out.rule_set_version} and need a new sign-off.`);
      setF({ ...f, family_a: '', family_b: '', rationale: '' });
      await load();
    } catch (e) { setError(errText(e, 'Could not save the rule.')); }
  }

  if (!r) return <Screen><ErrorText error={error} />{error ? null : <P muted>Loading…</P>}</Screen>;
  return (
    <Screen>
      <H1>Rules</H1>
      <Tag label={r.rule_set_version} />
      <H2>Ingredient conflicts</H2>
      {r.conflicts.map((x) => <Row key={x.id} label={`${x.family_a} + ${x.family_b}`} value={`${x.resolution.replace(/_/g, ' ')} (${x.scope.replace(/_/g, ' ')}). ${x.rationale}`} />)}
      <H2>Contraindications</H2>
      {r.contraindications.map((x, i) => <Row key={i} label={x.condition.replace(/_/g, ' ')} value={`${x.action.replace(/_/g, " ")} ${(x.family ?? x.ingredient ?? "").replace(/_/g, " ")}`.trim()} />)}
      <H2>Add a conflict</H2>
      <P muted>Use ingredient family codes, for example retinoids, aha, bha, benzoyl_peroxide, vitamin_c.</P>
      <Field label="Family A" value={f.family_a} onChangeText={(family_a) => setF({ ...f, family_a })} autoCapitalize="none" />
      <Field label="Family B" value={f.family_b} onChangeText={(family_b) => setF({ ...f, family_b })} autoCapitalize="none" />
      <Segmented options={opt(SCOPES)} value={f.scope} onChange={(scope) => setF({ ...f, scope })} />
      <Segmented options={opt(RESOLUTIONS)} value={f.resolution} onChange={(resolution) => setF({ ...f, resolution })} />
      <Field label="Rationale (who advised it and why)" value={f.rationale} onChangeText={(rationale) => setF({ ...f, rationale })} />
      <Button title="Add conflict rule" disabled={!f.family_a || !f.family_b || f.rationale.length < 3} onPress={add} />
      {msg ? <P style={{ color: C.ok, marginTop: 10 }}>{msg}</P> : null}
      <ErrorText error={error} />
    </Screen>
  );
}

export function AdminModels() {
  const [models, setModels] = useState<Awaited<ReturnType<typeof Admin.models>> | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => Admin.models().then(setModels).catch(() => setError('Could not load models.'));
  useEffect(() => { load(); }, []);

  async function run(fn: () => Promise<unknown>, done: (x: any) => string) {
    setError(null); setMsg(null);
    try { setMsg(done(await fn())); await load(); } catch (e) { setError(errText(e, 'That did not work.')); }
  }

  return (
    <Screen>
      <H1>Models and jobs</H1>
      <H2>Model versions</H2>
      {models?.length === 0 ? <P muted>No trained model registered. The app runs on the stub classifier.</P> : null}
      {models?.map((m) => (
        <Card key={m.id}>
          <View style={{ flexDirection: 'row', alignItems: 'center' }}>
            <Text style={{ flex: 1, fontSize: 16, fontWeight: '600', color: C.text }}>{m.id}</Text>
            {m.is_active ? <Tag label="Active" tone="ok" /> : null}
          </View>
          <Row label="Architecture" value={m.architecture} />
          <Row label="Evaluation report" value={m.eval_report_uri} />
          <Row label="SHA-256" value={m.artifact_sha256.slice(0, 16) + '…'} />
          {!m.is_active ? <Button kind="secondary" title={m.can_activate ? 'Activate' : 'Needs an evaluation report'} disabled={!m.can_activate}
            onPress={async () => { if (await confirmAction(`Make ${m.id} the live model for all new checks?`)) run(() => Admin.activateModel(m.id), () => `${m.id} is now active.`); }} /> : null}
        </Card>
      ))}
      <H2>Jobs</H2>
      <P muted>These also run on a schedule. Running one here is logged.</P>
      <Button kind="secondary" title="Delist products not re-verified in 90 days" onPress={() => run(() => Admin.runJob('delist-stale'), (x) => `Delisted ${x.delisted.length} product(s).`)} />
      <View style={{ height: 10 }} />
      <Button kind="secondary" title="Purge photos past retention" onPress={async () => { if (await confirmAction('Permanently delete photos past their retention period?')) run(() => Admin.runJob('purge-images'), (x) => `Purged photos from ${x.sessions_purged} check(s).`); }} />
      {msg ? <P style={{ color: C.ok, marginTop: 10 }}>{msg}</P> : null}
      <ErrorText error={error} />
    </Screen>
  );
}

const AUDIT_FILTERS = [
  { label: 'All', value: '' }, { label: 'Logins', value: 'login' }, { label: 'Summary views', value: 'view_summary' },
  { label: 'Accounts', value: 'update_user' }, { label: 'Catalog', value: 'verify_product' }, { label: 'Rules', value: 'update_rule' },
];

export function AdminAudit() {
  const [action, setAction] = useState('');
  const [rows, setRows] = useState<Awaited<ReturnType<typeof Admin.audit>> | null>(null);
  useEffect(() => { setRows(null); Admin.audit({ action }).then(setRows).catch(() => setRows([])); }, [action]);
  return (
    <Screen>
      <H1>Audit log</H1>
      <P muted>Newest first. Patients appear as "patient", never by email.</P>
      <Segmented options={AUDIT_FILTERS} value={action} onChange={setAction} />
      {rows === null ? <P muted>Loading…</P> : rows.length === 0 ? <P muted>No entries.</P> : null}
      {rows?.map((r) => (
        <Card key={r.id} style={{ paddingVertical: 10 }}>
          <Text style={{ fontSize: 15, fontWeight: '600', color: C.text }}>{r.action.replace(/_/g, ' ')} · {r.entity.replace(/_/g, ' ')}</Text>
          <Text style={{ color: C.muted, fontSize: 14 }}>{when(r.at)} · {r.actor.name}{r.actor.role && r.actor.role !== 'patient' ? ` (${ROLE_LABEL[r.actor.role]})` : ''}</Text>
          {r.detail ? <Text style={{ color: C.muted, fontSize: 13 }}>{JSON.stringify(r.detail)}</Text> : null}
        </Card>
      ))}
    </Screen>
  );
}
