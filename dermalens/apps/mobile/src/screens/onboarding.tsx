import React, { useEffect, useState } from 'react';
import { Pressable, Switch, Text, View } from 'react-native';

import { ApiError, Auth, HOME, Me, Ref, Role } from '../api';
import type { Props } from '../nav';
import { Boundary, Button, C, Card, ErrorText, Field, H1, H2, P, Screen, Segmented } from '../ui';

export function Welcome({ navigation }: Props<'Welcome'>) {
  return (
    <Screen footer={<>
      <Button testID="get-started" title="Get started" onPress={() => navigation.navigate('Boundary')} />
      <Button title="I already have an account" kind="secondary" onPress={() => navigation.navigate('Auth', { mode: 'login' })} />
    </>}>
      <View style={{ alignItems: 'center', marginTop: 24, marginBottom: 20 }}>
        <View style={{ width: 88, height: 88, borderRadius: 44, backgroundColor: C.infoBg, alignItems: 'center', justifyContent: 'center' }}>
          <Text style={{ fontSize: 40, color: C.primary }}>◐</Text>
        </View>
      </View>
      <H1>Welcome to DermaLens</H1>
      <P>A skincare pre-screening companion from ICONIC Aesthetic Clinic.</P>
      <P>In about 6 minutes you will answer a few questions, take three guided face photos, and get:</P>
      <Card>
        <P>• A look at visible concerns: breakouts, uneven tone, redness and texture</P>
        <P>• A simple morning and evening routine from verified products</P>
        <P style={{ marginBottom: 0 }}>• Advice on where to go next: ICONIC, a dermatologist, or care at home</P>
      </Card>
    </Screen>
  );
}

export function BoundaryScreen({ navigation }: Props<'Boundary'>) {
  const [text, setText] = useState<string>();
  const [ok, setOk] = useState(false);
  useEffect(() => { Ref.boundary().then((b) => setText(b.text)).catch(() => {}); }, []);
  return (
    <Screen footer={<Button testID="boundary-continue" title="Continue" disabled={!ok} onPress={() => navigation.navigate('Auth', { mode: 'signup' })} />}>
      <H1>Before you start</H1>
      <P>DermaLens is for information and pre-screening only.</P>
      <Boundary text={text} />
      <Pressable testID="boundary-ack" accessibilityRole="checkbox" accessibilityState={{ checked: ok }} onPress={() => setOk(!ok)}
        style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 12 }}>
        <View style={{ width: 26, height: 26, borderRadius: 6, borderWidth: 2, borderColor: C.primary, backgroundColor: ok ? C.primary : 'transparent', marginRight: 12, alignItems: 'center', justifyContent: 'center' }}>
          {ok ? <Text style={{ color: '#fff', fontWeight: '700' }}>✓</Text> : null}
        </View>
        <Text style={{ fontSize: 17, color: C.text, flex: 1 }}>I understand this is not a medical diagnosis</Text>
      </Pressable>
    </Screen>
  );
}

export function AuthScreen({ navigation, route }: Props<'Auth'>) {
  const signup = route.params.mode === 'signup';
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function go() {
    setBusy(true);
    setError(null);
    try {
      if (signup) {
        await Auth.register(email.trim(), password);
        navigation.reset({ index: 0, routes: [{ name: 'Consent', params: { next: 'Profile' } }] });
      } else {
        const t = await Auth.login(email.trim(), password);
        if (t.role !== 'patient') {
          // Clinic staff, dermatologists and admins go straight to their own workspace.
          navigation.reset({ index: 0, routes: [{ name: HOME[t.role as Role] }] });
          return;
        }
        const profile = await Me.profile();
        navigation.reset({ index: 0, routes: [{ name: profile ? 'Home' : 'Profile' }] });
      }
    } catch (e) {
      const d = e instanceof ApiError ? e.detail : null;
      if (e instanceof ApiError && e.status === 403 && !signup) return setError('This account is disabled. Contact your DermaLens admin.');
      setError(typeof d === 'string' ? d : signup ? 'Check your email, and use a password of at least 10 characters.' : 'Wrong email or password.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen footer={<>
      <Button testID="auth-submit" title={signup ? 'Create account' : 'Log in'} busy={busy} disabled={!email || password.length < (signup ? 10 : 1)} onPress={go} />
      <Button title={signup ? 'I already have an account' : 'Create a new account'} kind="secondary"
        onPress={() => navigation.setParams({ mode: signup ? 'login' : 'signup' })} />
    </>}>
      <H1>{signup ? 'Create your account' : 'Welcome back'}</H1>
      <Field testID="email" label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" autoComplete="email" />
      <Field testID="password" label={signup ? 'Password (at least 10 characters)' : 'Password'} value={password} onChangeText={setPassword} secureTextEntry autoComplete={signup ? 'new-password' : 'current-password'} />
      <ErrorText error={error} />
      {signup ? null : <P muted>ICONIC staff, dermatologists and admins log in here with the account their admin created.</P>}
    </Screen>
  );
}

const CONSENTS: { purpose: string; title: string; body: string }[] = [
  { purpose: 'image_storage', title: 'Keep my photos', body: 'Store photos for 12 months so you can compare progress. Off: photos are deleted within 24 hours.' },
  { purpose: 'share_with_clinic', title: 'Share summaries with ICONIC', body: 'Let you send a pre-screening summary to ICONIC staff before a visit.' },
  { purpose: 'model_improvement', title: 'Help improve DermaLens', body: 'Allow de-identified photos to be used to train future versions. You can withdraw any time.' },
];

export function ConsentScreen({ navigation, route }: Props<'Consent'>) {
  const [state, setState] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { Me.consents().then(setState).catch(() => {}); }, []);

  async function toggle(purpose: string, v: boolean) {
    setError(null);
    setState((s) => ({ ...s, [purpose]: v }));
    try { setState(await Me.setConsent(purpose, v)); } catch { setError('Could not save. Try again.'); }
  }

  return (
    <Screen footer={<Button testID="consent-continue" title="Continue" onPress={() =>
      route.params.next === 'Profile' ? navigation.navigate('Profile') : navigation.goBack()} />}>
      <H1>Your privacy choices</H1>
      <P muted>Using DermaLens to get a result is required. Everything below is optional and off unless you turn it on.</P>
      {CONSENTS.map((c) => (
        <Card key={c.purpose}>
          <View style={{ flexDirection: 'row', alignItems: 'center' }}>
            <View style={{ flex: 1, paddingRight: 12 }}>
              <Text style={{ fontSize: 17, fontWeight: '600', color: C.text, marginBottom: 4 }}>{c.title}</Text>
              <Text style={{ fontSize: 15, color: C.muted, lineHeight: 21 }}>{c.body}</Text>
            </View>
            <Switch testID={`consent-${c.purpose}`} accessibilityLabel={c.title} value={!!state[c.purpose]} onValueChange={(v) => toggle(c.purpose, v)} />
          </View>
        </Card>
      ))}
      <ErrorText error={error} />
    </Screen>
  );
}

const SKIN_TYPES = ['dry', 'oily', 'combination', 'normal', 'sensitive'] as const;

export function ProfileScreen({ navigation }: Props<'Profile'>) {
  const [name, setName] = useState('');
  const [year, setYear] = useState('');
  const [skin, setSkin] = useState<string>();
  const [fitz, setFitz] = useState<number>();
  const [preg, setPreg] = useState<boolean>(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Me.profile().then((p: any) => {
      if (!p) return;
      setName(p.full_name ?? ''); setYear(p.birth_year ? String(p.birth_year) : '');
      setSkin(p.skin_type ?? undefined); setFitz(p.self_fitzpatrick ?? undefined); setPreg(!!p.is_pregnant_or_breastfeeding);
    }).catch(() => {});
  }, []);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await Me.saveProfile({
        full_name: name.trim(), birth_year: year ? Number(year) : null, skin_type: skin ?? null,
        self_fitzpatrick: fitz ?? null, is_pregnant_or_breastfeeding: preg,
      });
      navigation.reset({ index: 0, routes: [{ name: 'Home' }] });
    } catch {
      setError('Please check your details.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen footer={<Button testID="profile-save" title="Save" busy={busy} disabled={!name.trim() || !skin} onPress={save} />}>
      <H1>About you</H1>
      <Field testID="full-name" label="Full name" value={name} onChangeText={setName} autoComplete="name" />
      <Field testID="birth-year" label="Year of birth" value={year} onChangeText={(t) => setYear(t.replace(/\D/g, '').slice(0, 4))} keyboardType="number-pad" />
      <H2>Your skin type</H2>
      <Segmented options={SKIN_TYPES.map((t) => ({ label: t[0].toUpperCase() + t.slice(1), value: t }))} value={skin} onChange={setSkin} />
      <H2>How does your skin react to the sun?</H2>
      <P muted>This helps us check that results are fair across skin tones.</P>
      <Segmented
        options={[
          { label: 'Always burns', value: 1 }, { label: 'Usually burns', value: 2 }, { label: 'Sometimes burns', value: 3 },
          { label: 'Rarely burns', value: 4 }, { label: 'Very rarely burns', value: 5 }, { label: 'Never burns', value: 6 },
        ]}
        value={fitz} onChange={setFitz} />
      <H2>Are you pregnant or breastfeeding?</H2>
      <Segmented options={[{ label: 'No', value: 'no' }, { label: 'Yes', value: 'yes' }]} value={preg ? 'yes' : 'no'} onChange={(v) => setPreg(v === 'yes')} />
      <ErrorText error={error} />
    </Screen>
  );
}
