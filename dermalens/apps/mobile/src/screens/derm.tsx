// Dermatologist: review queue, structured case review, rule sign-off, agreement figures.
import { useFocusEffect } from '@react-navigation/native';
import React, { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';

import { CaseBrief, CaseDetail, Clinic, Derm, DermReview, RouteCode } from '../api';
import type { Props } from '../nav';
import { Button, C, Card, ErrorText, Field, H1, H2, P, Screen, Segmented, YesNo } from '../ui';
import { CaseBody, CaseRow, confirmAction, pct, Row, ROUTE_META, Stat, StatGrid, Tag, when, Who } from './shared';
import { useAccount, useSignOutHeader } from './staff';

const ROUTE_OPTS = (['urgent_care', 'dermatologist', 'iconic_clinic', 'self_care'] as RouteCode[])
  .map((v) => ({ label: ROUTE_META[v].label, value: v }));

export function DermQueue({ navigation }: Props<'DermQueue'>) {
  useSignOutHeader(navigation);
  const me = useAccount();
  const [showDone, setShowDone] = useState<'todo' | 'done'>('todo');
  const [rows, setRows] = useState<(CaseBrief & { my_review: DermReview | null })[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useFocusEffect(useCallback(() => {
    Derm.queue(showDone === 'done')
      .then((r) => setRows(showDone === 'done' ? r.filter((x) => x.my_review) : r))
      .catch(() => setError('Could not load the queue.'));
  }, [showDone]));

  return (
    <Screen footer={<>
      <Button testID="derm-rules" title="Rules and sign-off" kind="secondary" onPress={() => navigation.navigate('DermRules')} />
      <Button testID="derm-stats" title="Agreement with the app" kind="secondary" onPress={() => navigation.navigate('DermStats')} />
    </>}>
      <H1>Review queue</H1>
      {me ? <Who name={me.display_name} role={me.role} /> : null}
      <P muted>Your independent read of each shared case. Cases the app sent to a dermatologist come first.</P>
      <Segmented options={[{ label: 'To review', value: 'todo' }, { label: 'Reviewed by me', value: 'done' }]} value={showDone} onChange={setShowDone} />
      <ErrorText error={error} />
      {rows === null ? <P muted>Loading…</P> : rows.length === 0 ? <Card><P muted>Nothing to review.</P></Card> : null}
      {rows?.map((c) => (
        <CaseRow key={c.summary_id} c={c} onPress={() => navigation.navigate('DermCase', { summaryId: c.summary_id })}
          right={c.my_review ? <Tag label={`You: ${ROUTE_META[c.my_review.derm_route].label}`} tone={c.my_review.derm_route === c.route ? 'ok' : 'caution'} /> : null} />
      ))}
    </Screen>
  );
}

export function DermCase({ route, navigation }: Props<'DermCase'>) {
  const id = route.params.summaryId;
  const [c, setC] = useState<CaseDetail | null>(null);
  const [derm, setDerm] = useState<RouteCode | undefined>();
  const [agree, setAgree] = useState<Record<string, boolean | undefined>>({});
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Clinic.get(id).then(setC).catch(() => setError('Case not found.'));
    Derm.queue(true).then((q) => {
      const mine = q.find((x) => x.summary_id === id)?.my_review;
      if (mine) { setDerm(mine.derm_route); setAgree(mine.concern_agreement); setNote(mine.note ?? ''); }
    }).catch(() => {});
  }, [id]);

  const findings: { code: string; name: string; present: boolean; grade_name: string }[] = c?.data?.visual_prescreen ?? [];
  const complete = !!derm && findings.every((f) => agree[f.code] !== undefined);

  async function submit() {
    setBusy(true); setError(null);
    try {
      await Derm.review(id, {
        derm_route: derm!, note: note || undefined,
        concern_agreement: Object.fromEntries(findings.map((f) => [f.code, !!agree[f.code]])),
      });
      navigation.goBack();
    } catch {
      setError('Could not save the review.');
    } finally {
      setBusy(false);
    }
  }

  if (!c) return <Screen><ErrorText error={error} />{error ? null : <P muted>Loading…</P>}</Screen>;
  return (
    <Screen footer={<Button testID="submit-review" title="Save my review" disabled={!complete} busy={busy} onPress={submit} />}>
      <H1>Case review</H1>
      <CaseBody c={c} imagePath={(v) => Clinic.imagePath(c.summary_id, v)} />

      <H2>Your review</H2>
      <P muted>Make your own call before comparing with the app's route.</P>
      <Text style={{ fontSize: 16, fontWeight: '600', color: C.text, marginBottom: 6 }}>Where should this person go?</Text>
      <Segmented options={ROUTE_OPTS} value={derm} onChange={setDerm} />
      {findings.length ? <Text style={{ fontSize: 16, fontWeight: '600', color: C.text, marginVertical: 6 }}>Do you agree with each visual finding?</Text> : null}
      {findings.map((f) => (
        <View key={f.code} style={{ marginBottom: 6 }}>
          <P>{f.name}: <Text style={{ color: C.muted }}>{f.present ? f.grade_name : 'not seen'}</Text></P>
          <YesNo value={agree[f.code]} onChange={(v) => setAgree((a) => ({ ...a, [f.code]: v }))} />
        </View>
      ))}
      <Field label="Clinical note (optional)" value={note} onChangeText={setNote} multiline />
      <ErrorText error={error} />
    </Screen>
  );
}

export function DermRules() {
  const [r, setR] = useState<Awaited<ReturnType<typeof Derm.rules>> | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = () => Derm.rules().then(setR).catch(() => setError('Could not load the rules.'));
  useEffect(() => { load(); }, []);

  async function sign() {
    if (!r || !(await confirmAction(`Sign off triage ${r.triage_version} and ${r.rule_set_version}? Your name and the time are recorded.`))) return;
    setBusy(true);
    try { await Derm.signoff(note); setNote(''); await load(); } catch { setError('Could not record the sign-off.'); } finally { setBusy(false); }
  }

  if (!r) return <Screen><ErrorText error={error} />{error ? null : <P muted>Loading…</P>}</Screen>;
  return (
    <Screen>
      <H1>Rules and sign-off</H1>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        <Tag label={`Triage ${r.triage_version}`} />
        <Tag label={r.rule_set_version} />
        <Tag label={r.signed_off ? 'Signed off' : 'Not signed off'} tone={r.signed_off ? 'ok' : 'caution'} />
      </View>
      <P muted>Read-only. Admins change the tables; any change creates a new version that needs a new sign-off.</P>

      <H2>Red-flag questions ({r.red_flags.length})</H2>
      {r.red_flags.map((f) => <Row key={f.code} label={f.route === 'urgent_care' ? 'Urgent care' : 'Dermatologist'} value={f.question} />)}

      <H2>Ingredient conflicts ({r.conflicts.length})</H2>
      {r.conflicts.map((x, i) => <Row key={i} label={`${x.family_a} + ${x.family_b}`} value={`${x.resolution.replace(/_/g, ' ')} (${x.scope.replace(/_/g, ' ')}). ${x.rationale}`} />)}

      <H2>Contraindications ({r.contraindications.length})</H2>
      {r.contraindications.map((x, i) => <Row key={i} label={x.condition.replace(/_/g, ' ')} value={`${x.action.replace(/_/g, " ")} ${(x.family ?? x.ingredient ?? "").replace(/_/g, " ")}`.trim()} />)}

      <H2>Sign off this version</H2>
      <Field label="Note (optional)" value={note} onChangeText={setNote} />
      <Button testID="sign-off" title={r.signed_off ? 'Sign off again' : 'Sign off'} busy={busy} onPress={sign} />
      <ErrorText error={error} />

      {r.signoffs.length ? <H2>History</H2> : null}
      {r.signoffs.map((s, i) => <Row key={i} label={when(s.signed_at)} value={`${s.signed_by ?? '–'} · ${s.triage_version} / ${s.rule_set_version}${s.note ? ` · ${s.note}` : ''}`} />)}
    </Screen>
  );
}

export function DermStats({ navigation }: Props<'DermStats'>) {
  const [s, setS] = useState<Awaited<ReturnType<typeof Derm.stats>> | null>(null);
  useFocusEffect(useCallback(() => { Derm.stats().then(setS).catch(() => {}); }, []));
  if (!s) return <Screen><P muted>Loading…</P></Screen>;
  return (
    <Screen>
      <H1>Agreement with the app</H1>
      <P muted>From all dermatologist reviews. These feed the Level 3 clinical-agreement evaluation.</P>
      <StatGrid>
        <Stat label="Cases reviewed" value={s.reviews} />
        <Stat label="Route agreement" value={pct(s.route_agreement)} />
        <Stat label="Missed referrals" value={s.missed_referrals} tone={s.missed_referrals ? 'urgent' : 'ok'} />
        <Stat label="Referral sensitivity" value={pct(s.referral_sensitivity)} />
        <Stat label="Over-referrals" value={s.over_referrals} />
      </StatGrid>
      {s.missed_referral_cases.length ? <>
        <H2>Missed referrals</H2>
        <P muted>You routed these more urgently than the app did. Each one should be looked at against the triage rules.</P>
        {s.missed_referral_cases.map((id) => <Button key={id} kind="secondary" title={`Open case ${id.slice(0, 8)}`} onPress={() => navigation.navigate('DermCase', { summaryId: id })} />)}
      </> : null}
      <H2>Per-concern agreement</H2>
      {Object.keys(s.concern_agreement).length === 0 ? <P muted>No reviews yet.</P> : null}
      {Object.entries(s.concern_agreement).map(([k, v]) => <Row key={k} label={k} value={`${pct(v.rate)} (${v.agree} of ${v.of})`} />)}
      <H2>App route vs your route</H2>
      {s.confusion.map((x, i) => <Row key={i} label={`${ROUTE_META[x.app_route]?.label} → ${ROUTE_META[x.derm_route]?.label}`} value={x.n} />)}
    </Screen>
  );
}
