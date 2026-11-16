import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Linking, Platform, Pressable, Text, View } from 'react-native';

import { API_URL, authHeader, Me, Result, RoutineStep, Sessions } from '../api';
import type { Props } from '../nav';
import { Boundary, Button, C, Card, ErrorText, H1, H2, P, Screen, TONES } from '../ui';

function useResult(sessionId: string) {
  const [r, setR] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { Sessions.result(sessionId).then(setR).catch(() => setError('Could not load the result.')); }, [sessionId]);
  return { r, error };
}

const GRADE_DOTS: Record<string, number> = { none: 0, mild: 1, moderate: 2, marked: 3 };
const BAND_TEXT: Record<string, string> = { low: 'Unlikely', medium: 'Possible', high: 'Likely' };

export function RouteBanner({ route }: { route: NonNullable<Result['route']> }) {
  const t = TONES[route.tone] ?? TONES.info;
  return (
    <View testID={`route-${route.code}`} accessibilityRole="summary"
      style={{ backgroundColor: t.bg, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: t.fg, marginBottom: 12 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6 }}>
        <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: t.fg, alignItems: 'center', justifyContent: 'center', marginRight: 10 }}>
          <Text style={{ color: '#fff', fontWeight: '800' }}>{t.icon}</Text>
        </View>
        <Text style={{ color: t.fg, fontSize: 19, fontWeight: '700', flex: 1 }}>{route.title}</Text>
      </View>
      <Text style={{ color: C.text, fontSize: 16, lineHeight: 23 }}>{route.body}</Text>
    </View>
  );
}

export function Results({ navigation, route: nav }: Props<'Results'>) {
  const { r, error } = useResult(nav.params.sessionId);
  if (!r) return <Screen><ErrorText error={error} />{!error ? <ActivityIndicator color={C.primary} /> : null}</Screen>;
  if (!r.route) return <Screen><P>{r.message ?? 'This assessment is not finished yet.'}</P></Screen>;
  const code = r.route.code;
  const sid = nav.params.sessionId;

  const primary = {
    urgent_care: <Button title="Call 911 (Philippines emergency)" kind="danger" onPress={() => Linking.openURL('tel:911')} />,
    dermatologist: <Button testID="cta" title="Find a dermatologist" onPress={() => navigation.navigate('Referral', { sessionId: sid, kind: 'dermatologist' })} />,
    iconic_clinic: <Button testID="cta" title="Book with ICONIC" onPress={() => navigation.navigate('Referral', { sessionId: sid, kind: 'iconic' })} />,
    self_care: <Button testID="cta" title="See my routine" onPress={() => navigation.navigate('Routine', { sessionId: sid })} />,
  }[code];

  return (
    <Screen footer={<>
      {primary}
      {code !== 'urgent_care' && code !== 'self_care' && r.routine ? (
        <Button testID="see-routine" title={r.routine.basics_only ? 'See gentle basics' : 'See my routine'} kind="secondary" onPress={() => navigation.navigate('Routine', { sessionId: sid })} />
      ) : null}
    </>}>
      <H1>Your results</H1>
      <RouteBanner route={r.route} />
      {r.reasons?.filter((x) => x.code !== 'model:uncertain_label').length ? (
        <Card>
          <Text style={{ fontWeight: '700', marginBottom: 6, color: C.text, fontSize: 16 }}>Why</Text>
          {r.reasons.filter((x) => x.code !== 'model:uncertain_label').map((x) => <P key={x.code}>• {x.text}</P>)}
        </Card>
      ) : null}
      {r.findings?.length ? <H2>What the photos show</H2> : null}
      {r.findings?.map((f) => (
        <Card key={f.code} style={{ flexDirection: 'row', alignItems: 'center' }}>
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 16, fontWeight: '600', color: C.text }}>{f.name}</Text>
            <Text style={{ fontSize: 15, color: C.muted, marginTop: 2 }}>
              {f.present ? f.grade_name : BAND_TEXT[f.band] === 'Unlikely' ? 'Not seen' : `${BAND_TEXT[f.band]}, not confirmed`}
              {f.uncertain ? '  ·  Uncertain' : ''}
            </Text>
          </View>
          <View style={{ flexDirection: 'row' }} accessibilityLabel={`Level ${GRADE_DOTS[f.grade]} of 3`}>
            {[1, 2, 3].map((n) => (
              <View key={n} style={{ width: 12, height: 12, borderRadius: 6, marginLeft: 4, backgroundColor: n <= GRADE_DOTS[f.grade] ? C.primary : C.line }} />
            ))}
          </View>
        </Card>
      ))}
      {r.findings?.some((f) => f.uncertain) ? <P muted>“Uncertain” means the photos were not clear enough to be sure. ICONIC staff will see this flagged.</P> : null}
      <Boundary text={r.boundary} />
      <Pressable onPress={() => navigation.navigate('Referral', { sessionId: sid, kind: code === 'iconic_clinic' ? 'dermatologist' : 'iconic' })}>
        <Text style={{ color: C.primary, fontSize: 15, textAlign: 'center', marginVertical: 6 }}>
          {code === 'iconic_clinic' ? 'Prefer a dermatologist? Find one' : 'Book with ICONIC anyway'}
        </Text>
      </Pressable>
    </Screen>
  );
}

function Step({ s }: { s: RoutineStep }) {
  return (
    <Card>
      <Text style={{ color: C.muted, fontSize: 14, marginBottom: 2 }}>Step {s.step} · {s.slot[0].toUpperCase() + s.slot.slice(1)}
        {s.frequency !== 'daily' ? ` · ${s.frequency === 'alternate_nights' ? 'Alternate nights' : 'Twice a week'}` : ''}</Text>
      <Text style={{ fontSize: 17, fontWeight: '700', color: C.text }}>{s.product.brand} {s.product.name}</Text>
      <Text style={{ fontSize: 15, color: C.text, marginTop: 4, lineHeight: 21 }}>{s.why}</Text>
      <Text style={{ fontSize: 13, color: C.muted, marginTop: 6 }}>FDA notification: {s.product.fda_notification_no}
        {s.product.price_php ? `  ·  ₱${s.product.price_php.toFixed(0)}` : ''}{s.product.stocked_by_iconic ? '  ·  Available at ICONIC' : ''}</Text>
      {s.patch_test ? <Text style={{ fontSize: 14, color: C.caution, marginTop: 6 }}>New active: patch-test first</Text> : null}
    </Card>
  );
}

export function Routine({ navigation, route: nav }: Props<'Routine'>) {
  const { r, error } = useResult(nav.params.sessionId);
  const [tab, setTab] = useState<'am' | 'pm'>('am');
  if (!r) return <Screen><ErrorText error={error} />{!error ? <ActivityIndicator color={C.primary} /> : null}</Screen>;
  const rt = r.routine;
  return (
    <Screen footer={<Button testID="to-summary" title="Get my pre-screening summary" onPress={() => navigation.navigate('Summary', { sessionId: nav.params.sessionId })} />}>
      <H1>{rt?.basics_only ? 'Gentle basics' : 'Your routine'}</H1>
      {rt?.basics_only ? <P muted>Until you see a dermatologist, keep to a mild cleanser, a moisturizer and sunscreen. No active treatments.</P> : null}
      {!rt || rt.status !== 'ok' ? (
        <Card><P>{rt?.notes?.join(' ') ?? 'No routine for this result.'}</P></Card>
      ) : (
        <>
          <View style={{ flexDirection: 'row', marginBottom: 12, backgroundColor: C.line, borderRadius: 10, padding: 3 }}>
            {(['am', 'pm'] as const).map((t) => (
              <Pressable key={t} testID={`tab-${t}`} onPress={() => setTab(t)} accessibilityRole="tab" accessibilityState={{ selected: tab === t }}
                style={{ flex: 1, padding: 10, borderRadius: 8, backgroundColor: tab === t ? C.card : 'transparent', alignItems: 'center' }}>
                <Text style={{ fontWeight: '600', fontSize: 16, color: C.text }}>{t === 'am' ? 'Morning' : 'Evening'}</Text>
              </Pressable>
            ))}
          </View>
          {rt[tab].map((s) => <Step key={`${tab}-${s.step}`} s={s} />)}
          {rt.notes.length ? <Card style={{ backgroundColor: C.infoBg }}>{rt.notes.map((n) => <P key={n}>{n}</P>)}</Card> : null}
          <P muted>Introduce one new product every 2 weeks. Check again with DermaLens in 6 to 8 weeks.</P>
        </>
      )}
      <Boundary text={r.boundary} />
    </Screen>
  );
}

export function Referral({ navigation, route: nav }: Props<'Referral'>) {
  const iconic = nav.params.kind === 'iconic';
  return (
    <Screen footer={<>
      <Button testID="referral-summary" title={iconic ? 'Share a summary with ICONIC' : 'Get a summary to bring'} onPress={() => navigation.navigate('Summary', { sessionId: nav.params.sessionId })} />
      {iconic ? <Button title="Contact ICONIC" kind="secondary" onPress={() => Linking.openURL('https://www.google.com/search?q=ICONIC+Aesthetic+Clinic')} /> :
        <Button title="Find a board-certified dermatologist" kind="secondary" onPress={() => Linking.openURL('https://www.google.com/search?q=Philippine+Dermatological+Society+find+a+dermatologist')} />}
    </>}>
      <H1>{iconic ? 'ICONIC Aesthetic Clinic' : 'See a dermatologist'}</H1>
      {iconic ? (
        <>
          <P>A consultation lets ICONIC staff look at your skin in person and talk through options.</P>
          <P>Nothing is booked or treated without an in-person assessment.</P>
        </>
      ) : (
        <>
          <P>A board-certified dermatologist can examine your skin, ask about your history and, if needed, prescribe treatment.</P>
          <P>Bring your pre-screening summary so they can see what you told us and your photos.</P>
        </>
      )}
    </Screen>
  );
}

export function Summary({ route: nav }: Props<'Summary'>) {
  const sid = nav.params.sessionId;
  const [consent, setConsent] = useState<boolean | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { Me.consents().then((c) => setConsent(!!c.share_with_clinic)).catch(() => setConsent(false)); }, []);

  async function make(share: boolean) {
    setBusy(share ? 'share' : 'pdf');
    setError(null);
    try {
      const s = await Sessions.summary(sid, share);
      const url = `${API_URL}${s.pdf_url}`;
      const headers = await authHeader();
      if (Platform.OS === 'web') {
        const blob = await (await fetch(url, { headers })).blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `dermalens-summary-${s.summary_id.slice(0, 8)}.pdf`;
        a.click();
      } else {
        const file = await File.downloadFileAsync(url, new File(Paths.cache, `dermalens-summary-${s.summary_id.slice(0, 8)}.pdf`), { headers, idempotent: true });
        if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(file.uri, { mimeType: 'application/pdf', dialogTitle: 'Share your summary' });
      }
      setDone(share ? 'Sent to ICONIC. Staff can open it for 30 days after logging in.' : 'Your summary is ready.');
    } catch {
      setError('Could not create the summary. Try again.');
    } finally {
      setBusy(null);
    }
  }

  return (
    <Screen footer={<>
      <Button testID="summary-pdf" title="Download PDF" busy={busy === 'pdf'} onPress={() => make(false)} />
      <Button testID="summary-share" title="Send to ICONIC" kind="secondary" busy={busy === 'share'}
        disabled={!consent} onPress={() => make(true)} />
    </>}>
      <H1>Pre-screening summary</H1>
      <P>A two-page summary of your answers, photos, results and routine, for clinic staff or your dermatologist.</P>
      <P muted>It is a pre-screening aid, not a diagnosis.</P>
      {consent === false ? <Card><P>To send it to ICONIC, turn on “Share summaries with ICONIC” in Settings › Privacy.</P></Card> : null}
      {done ? <Card style={{ backgroundColor: C.okBg, borderColor: C.ok }}><Text testID="summary-done" style={{ color: C.ok, fontSize: 16, fontWeight: '600' }}>{done}</Text></Card> : null}
      <ErrorText error={error} />
    </Screen>
  );
}
