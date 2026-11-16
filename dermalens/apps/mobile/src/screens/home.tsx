import React, { useCallback, useState } from 'react';
import { Alert, Platform, Pressable, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';

import { Me, Sessions, signOut } from '../api';
import type { Props } from '../nav';
import { useStore } from '../store';
import { Button, C, Card, H1, H2, P, Screen, TONES } from '../ui';

const ROUTE_LABEL: Record<string, { label: string; tone: string }> = {
  urgent_care: { label: 'Seek care promptly', tone: 'urgent' },
  dermatologist: { label: 'See a dermatologist', tone: 'caution' },
  iconic_clinic: { label: 'ICONIC consultation', tone: 'info' },
  self_care: { label: 'At-home routine', tone: 'ok' },
};

export function Home({ navigation }: Props<'Home'>) {
  const [rows, setRows] = useState<Awaited<ReturnType<typeof Sessions.list>>>([]);
  const resetAssessment = useStore((s) => s.resetAssessment);
  useFocusEffect(useCallback(() => { Sessions.list().then(setRows).catch(() => {}); }, []));
  const done = rows.filter((r) => r.status === 'complete');

  return (
    <Screen footer={<>
      <Button testID="new-assessment" title={done.length ? 'New check-in' : 'Start my first check'} onPress={() => { resetAssessment(); navigation.navigate('Concerns'); }} />
      <Button title="Settings and privacy" kind="secondary" onPress={() => navigation.navigate('Settings')} />
    </>}>
      <H1>DermaLens</H1>
      {done.length ? (
        <P muted>Check again 6 to 8 weeks after starting a routine to compare.</P>
      ) : (
        <P muted>Your first check takes about 6 minutes: 5 short question screens, then 3 photos.</P>
      )}
      {done.length ? <H2>History</H2> : null}
      {done.map((r) => {
        const meta = ROUTE_LABEL[r.route ?? ''] ?? { label: r.status, tone: 'info' };
        const t = TONES[meta.tone];
        return (
          <Pressable key={r.session_id} onPress={() => navigation.navigate('Results', { sessionId: r.session_id })}>
            <Card style={{ flexDirection: 'row', alignItems: 'center' }}>
              <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: t.fg, marginRight: 12 }} />
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 16, fontWeight: '600', color: C.text }}>{meta.label}</Text>
                <Text style={{ color: C.muted, fontSize: 14 }}>{new Date(r.created_at).toLocaleDateString()}</Text>
              </View>
              <Text style={{ color: C.primary, fontSize: 15 }}>Open ›</Text>
            </Card>
          </Pressable>
        );
      })}
    </Screen>
  );
}

function confirm(title: string, msg: string, onYes: () => void) {
  if (Platform.OS === 'web') {
    if (window.confirm(`${title}\n\n${msg}`)) onYes();
  } else {
    Alert.alert(title, msg, [{ text: 'Cancel', style: 'cancel' }, { text: 'Continue', style: 'destructive', onPress: onYes }]);
  }
}

export function Settings({ navigation }: Props<'Settings'>) {
  const resetAll = useStore((s) => s.resetAll);
  const [msg, setMsg] = useState<string | null>(null);

  async function exportData() {
    const data = await Me.exportData();
    const json = JSON.stringify(data, null, 2);
    if (Platform.OS === 'web') {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([json], { type: 'application/json' }));
      a.download = 'dermalens-my-data.json';
      a.click();
    }
    setMsg(`Exported ${json.length.toLocaleString()} characters of your data.`);
  }

  async function logout() {
    await signOut();
    resetAll();
    navigation.reset({ index: 0, routes: [{ name: 'Welcome' }] });
  }

  return (
    <Screen>
      <H1>Settings</H1>
      <H2>Privacy</H2>
      <Button title="Privacy choices" kind="secondary" onPress={() => navigation.navigate('Consent', { next: 'Settings' })} />
      <View style={{ height: 10 }} />
      <Button title="Download my data" kind="secondary" onPress={exportData} />
      <View style={{ height: 10 }} />
      <Button title="Edit my profile" kind="secondary" onPress={() => navigation.navigate('Profile')} />
      {msg ? <P muted style={{ marginTop: 10 }}>{msg}</P> : null}
      <H2>Account</H2>
      <Button title="Log out" kind="secondary" onPress={logout} />
      <View style={{ height: 10 }} />
      <Button title="Delete my account and photos" kind="danger" onPress={() => confirm(
        'Delete account?', 'Your photos and personal details will be erased. This cannot be undone.',
        async () => { await Me.deleteAccount(); await logout(); })} />
      <H2>Help</H2>
      <Card>
        <P>DermaLens is an information and pre-screening tool from ICONIC Aesthetic Clinic. It does not diagnose or treat any disease.</P>
        <P style={{ marginBottom: 0 }}>For a changing mole, a sore that does not heal, pain, bleeding, rapid spreading or fever, see a board-certified dermatologist.</P>
      </Card>
    </Screen>
  );
}
