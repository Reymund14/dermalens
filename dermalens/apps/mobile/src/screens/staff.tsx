// Clinic staff: inbox of shared summaries, case detail, follow-up tracking.
import { useFocusEffect } from '@react-navigation/native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Platform, Text, View } from 'react-native';
import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';

import { Account, API_URL, authHeader, CaseBrief, CaseDetail, Clinic, FollowUp } from '../api';
import type { Props } from '../nav';
import { Button, C, Card, ErrorText, Field, H1, H2, P, Screen, Segmented } from '../ui';
import { CaseBody, CaseRow, FOLLOW_UP_LABEL, SignOutLink, Tag, Who } from './shared';

type Filter = 'open' | 'urgent' | 'booked' | 'all';
const FILTERS: { label: string; value: Filter }[] = [
  { label: 'Needs review', value: 'open' }, { label: 'Referrals', value: 'urgent' },
  { label: 'Booked', value: 'booked' }, { label: 'All', value: 'all' },
];

export function useAccount() {
  const [me, setMe] = useState<Account | null>(null);
  useEffect(() => { Account.me().then(setMe).catch(() => {}); }, []);
  return me;
}

export function useSignOutHeader(navigation: any) {
  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => <SignOutLink onDone={() => navigation.reset({ index: 0, routes: [{ name: 'Welcome' }] })} />,
    });
  }, [navigation]);
}

export function StaffInbox({ navigation }: Props<'StaffInbox'>) {
  useSignOutHeader(navigation);
  const me = useAccount();
  const [filter, setFilter] = useState<Filter>('open');
  const [rows, setRows] = useState<CaseBrief[] | null>(null);
  const [qr, setQr] = useState('');
  const [scan, setScan] = useState(false);
  const [perm, requestPerm] = useCameraPermissions();
  const scanned = useRef(false);
  const [error, setError] = useState<string | null>(null);

  useFocusEffect(useCallback(() => {
    setError(null);
    const q = filter === 'open' ? { reviewed: false } : filter === 'booked' ? { follow_up: 'booked' } : {};
    Clinic.list(q).then((r) => setRows(filter === 'urgent' ? r.filter((x) => x.route === 'dermatologist' || x.route === 'urgent_care') : r))
      .catch(() => setError('Could not load shared summaries.'));
  }, [filter]));

  // Accept a full QR URL (…/api/v1/clinic/s/<token>) or just the token.
  function openToken(value: string) {
    const token = value.trim().split(/[?#]/)[0].replace(/\/+$/, '').split('/').pop();
    if (!token) return;
    setScan(false);
    navigation.navigate('StaffCase', { qrToken: token });
  }

  function onScan(data: string) {
    if (scanned.current) return;
    scanned.current = true;
    openToken(data);
  }

  async function startScan() {
    if (!perm?.granted && !(await requestPerm()).granted) return;
    scanned.current = false;
    setScan(true);
  }

  return (
    <Screen>
      <H1>Clinic inbox</H1>
      {me ? <Who name={me.display_name} role={me.role} /> : null}
      <P muted>Summaries patients chose to share with ICONIC. Patients appear by initials only, and every view is logged.</P>
      <Segmented options={FILTERS} value={filter} onChange={setFilter} />
      <ErrorText error={error} />
      {rows === null ? <P muted>Loading…</P> : rows.length === 0 ? <Card><P muted>Nothing here.</P></Card> : null}
      {rows?.map((c) => (
        <CaseRow key={c.summary_id} c={c} onPress={() => navigation.navigate('StaffCase', { summaryId: c.summary_id })}
          right={<>
            <Tag label={c.reviewed ? 'Reviewed' : 'New'} tone={c.reviewed ? 'ok' : 'caution'} />
            {c.follow_up_status !== 'new' ? <Tag label={FOLLOW_UP_LABEL[c.follow_up_status]} /> : null}
          </>} />
      ))}
      <H2>Open from a QR code</H2>
      <P muted>Scan the QR code in the patient's PDF, or paste its link or code.</P>
      {scan ? (
        <View style={{ aspectRatio: 1, borderRadius: 16, overflow: 'hidden', backgroundColor: '#222', marginBottom: 12 }}>
          <CameraView style={{ flex: 1 }} facing="back" barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
            onBarcodeScanned={({ data }) => onScan(data)} />
        </View>
      ) : null}
      {Platform.OS !== 'web' ? (
        <Button title={scan ? 'Stop scanning' : 'Scan with camera'} kind="secondary"
          onPress={() => { if (scan) setScan(false); else startScan(); }} />
      ) : null}
      <Field label="Link or code from the patient's PDF" value={qr} onChangeText={setQr} autoCapitalize="none" placeholder="https://…/api/v1/clinic/s/…" />
      <Button title="Open summary" kind="secondary" disabled={!qr.trim()} onPress={() => openToken(qr)} />
    </Screen>
  );
}

async function downloadPdf(summaryId: string) {
  const url = `${API_URL}${Clinic.pdfPath(summaryId)}`;
  const headers = await authHeader();
  if (Platform.OS === 'web') {
    const blob = await (await fetch(url, { headers })).blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `dermalens-summary-${summaryId.slice(0, 8)}.pdf`;
    a.click();
  } else {
    const file = await File.downloadFileAsync(url, new File(Paths.cache, `summary-${summaryId.slice(0, 8)}.pdf`), { headers, idempotent: true });
    if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(file.uri, { mimeType: 'application/pdf' });
  }
}

const FOLLOW_OPTS = (Object.keys(FOLLOW_UP_LABEL) as FollowUp[]).map((v) => ({ label: FOLLOW_UP_LABEL[v], value: v }));

export function StaffCase({ route }: Props<'StaffCase'>) {
  const [c, setC] = useState<CaseDetail | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = route.params.qrToken ? Clinic.openQr(route.params.qrToken) : Clinic.get(route.params.summaryId!);
    load.then((d) => { setC(d); setNote(d.staff_note ?? ''); })
      .catch((e) => setError(e?.status === 410 ? 'This share link has expired.' : 'Summary not found.'));
  }, [route.params]);

  async function save(body: Parameters<typeof Clinic.update>[1], done: string) {
    if (!c) return;
    setBusy(true); setError(null); setMsg(null);
    try {
      setC(await Clinic.update(c.summary_id, body));
      setMsg(done);
    } catch {
      setError('Could not save. Try again.');
    } finally {
      setBusy(false);
    }
  }

  if (!c) return <Screen><ErrorText error={error} />{error ? null : <P muted>Loading…</P>}</Screen>;
  return (
    <Screen>
      <H1>Shared summary</H1>
      <CaseBody c={c} imagePath={(v) => Clinic.imagePath(c.summary_id, v)} />

      <H2>Follow-up</H2>
      <Segmented options={FOLLOW_OPTS} value={c.follow_up_status} onChange={(v) => save({ follow_up_status: v }, `Follow-up set to ${FOLLOW_UP_LABEL[v]}.`)} />
      <Field label="Staff note (not shown to the patient)" value={note} onChangeText={setNote} multiline
        style={{ minHeight: 80, borderWidth: 1, borderColor: C.line, backgroundColor: C.card, borderRadius: 10, padding: 13, fontSize: 16, color: C.text }} />
      <Button testID="save-note" title="Save note" kind="secondary" busy={busy} onPress={() => save({ staff_note: note }, 'Note saved.')} />
      <Text style={{ height: 10 }} />
      <Button testID="mark-reviewed" title={c.reviewed ? 'Mark as not reviewed' : 'Mark reviewed'} busy={busy}
        onPress={() => save({ reviewed: !c.reviewed }, c.reviewed ? 'Marked as not reviewed.' : 'Marked reviewed.')} />
      <Text style={{ height: 10 }} />
      <Button title="Download PDF" kind="secondary" onPress={() => downloadPdf(c.summary_id).catch(() => setError('Could not download the PDF.'))} />
      {msg ? <P style={{ color: C.ok, marginTop: 10 }}>{msg}</P> : null}
      <ErrorText error={error} />
    </Screen>
  );
}
