import { CameraView, useCameraPermissions } from 'expo-camera';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import * as ImagePicker from 'expo-image-picker';
import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, Platform, Text, View } from 'react-native';

import { ApiError, Sessions } from '../api';
import type { Props } from '../nav';
import { useStore, View as V, VIEWS } from '../store';
import { Button, C, Card, ErrorText, H1, H2, P, Screen } from '../ui';

const VIEW_COPY: Record<V, { title: string; prompt: string }> = {
  front: { title: 'Front view', prompt: 'Look straight at the camera. Keep your face inside the oval.' },
  left45: { title: 'Left side', prompt: 'Turn your head about halfway to your right so your LEFT cheek faces the camera.' },
  right45: { title: 'Right side', prompt: 'Turn your head about halfway to your left so your RIGHT cheek faces the camera.' },
};

const CHECK_TIPS: Record<string, string> = {
  resolution: 'Move a little closer, or use a sharper camera.',
  face_present: 'Fit your whole face inside the oval.',
  sharpness: 'The photo is blurry. Hold the phone still at arm’s length.',
  exposure: 'The light is too dim or too harsh. Face a window or a bright, even light.',
  even_lighting: 'One side of your face is brighter. Turn so the light falls evenly.',
};

export function CaptureGuide({ navigation }: Props<'CaptureGuide'>) {
  return (
    <Screen footer={<Button testID="guide-start" title="I'm ready" onPress={() => navigation.navigate('Capture', { view: 'front' })} />}>
      <H1>Taking good photos</H1>
      <P muted>Three photos: front, left side and right side. Good photos give more reliable results.</P>
      <Card>
        <P>• Clean, dry face: no makeup or tinted sunscreen</P>
        <P>• Glasses off, hair pulled back</P>
        <P>• Face a window or a bright, even light. No flash</P>
        <P>• Hold the phone at arm’s length</P>
        <P style={{ marginBottom: 0 }}>• Beauty mode and filters off (DermaLens uses the plain camera)</P>
      </Card>
      <P muted>Location data and other hidden photo details are removed before upload.</P>
    </Screen>
  );
}

async function prepare(uri: string): Promise<string> {
  // Re-encoding drops all EXIF (GPS, device serials) and keeps uploads small.
  const ctx = ImageManipulator.manipulate(uri);
  ctx.resize({ width: 1440 });
  const ref = await ctx.renderAsync();
  const out = await ref.saveAsync({ compress: 0.9, format: SaveFormat.JPEG });
  return out.uri;
}

export function Capture({ navigation, route }: Props<'Capture'>) {
  const view = route.params.view;
  const { sessionId, uploadUrls, setUploadUrls, setCapture, captures } = useStore();
  const [perm, requestPerm] = useCameraPermissions();
  const cam = useRef<CameraView>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const useCamera = Platform.OS !== 'web' && perm?.granted;

  useEffect(() => { setFailed(null); setError(null); }, [view]);

  async function upload(localUri: string) {
    if (!sessionId || !uploadUrls) return;
    setBusy(true);
    setError(null);
    setFailed(null);
    try {
      const uri = await prepare(localUri);
      let up;
      try {
        up = await Sessions.upload(uploadUrls[view], uri);
      } catch (e) {
        if (e instanceof ApiError && e.status === 403) { // upload URL expired: get fresh ones
          const fresh = await Sessions.uploadUrls(sessionId);
          setUploadUrls(fresh.upload_urls);
          up = await Sessions.upload(fresh.upload_urls[view], uri);
        } else throw e;
      }
      const q = await Sessions.register(sessionId, view, up);
      setCapture(view, { uri, quality: { pass: q.quality_pass, checks: q.checks } });
      if (!q.quality_pass) {
        setFailed(Object.entries(q.checks).filter(([, ok]) => !ok).map(([k]) => k));
        return;
      }
      // Next photo still missing (in front, left, right order), else back to review.
      const have = useStore.getState().captures;
      const missing = VIEWS.find((v) => !have[v]?.quality?.pass);
      if (missing) navigation.replace('Capture', { view: missing, retake: route.params.retake });
      else navigation.navigate('Review');
    } catch {
      setError('Upload failed. Check your connection and try again.');
    } finally {
      setBusy(false);
    }
  }

  async function shoot() {
    const pic = await cam.current?.takePictureAsync({ quality: 0.95, exif: false, skipProcessing: false });
    if (pic?.uri) await upload(pic.uri);
  }

  async function pick() {
    const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 1, exif: false });
    if (!r.canceled && r.assets[0]) await upload(r.assets[0].uri);
  }

  const copy = VIEW_COPY[view];
  const idx = VIEWS.indexOf(view) + 1;
  return (
    <Screen footer={<>
      {useCamera ? <Button testID="shutter" title={busy ? 'Checking photo…' : 'Take photo'} busy={busy} onPress={shoot} /> : null}
      {Platform.OS !== 'web' && !perm?.granted ? <Button title="Allow camera" onPress={requestPerm} /> : null}
      <Button testID="pick-photo" title={useCamera ? 'Choose a photo instead' : 'Choose a photo'} kind={useCamera ? 'secondary' : 'primary'} busy={busy && !useCamera} onPress={pick} />
    </>}>
      <Text style={{ color: C.muted, fontSize: 15, marginBottom: 4 }}>Photo {idx} of 3</Text>
      <H1>{copy.title}</H1>
      <P>{copy.prompt}</P>
      <View style={{ aspectRatio: 3 / 4, borderRadius: 16, overflow: 'hidden', backgroundColor: '#222', marginVertical: 8 }}>
        {useCamera ? (
          <CameraView ref={cam} style={{ flex: 1 }} facing="front" animateShutter={false} />
        ) : captures[view]?.uri ? (
          <Image source={{ uri: captures[view]!.uri }} style={{ flex: 1 }} resizeMode="cover" />
        ) : (
          <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 }}>
            <Text style={{ color: '#ddd', fontSize: 16, textAlign: 'center' }}>
              {Platform.OS === 'web' ? 'On the web demo, choose a photo taken following the guide.' : 'Camera permission is needed to take photos.'}
            </Text>
          </View>
        )}
        {/* Oval face guide */}
        <View pointerEvents="none" style={{ position: 'absolute', left: '17%', right: '17%', top: '10%', bottom: '10%', borderRadius: 999, borderWidth: 3, borderColor: 'rgba(255,255,255,0.85)' }} />
        {busy ? <View style={{ ...absFill, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(0,0,0,0.35)' }}><ActivityIndicator color="#fff" size="large" /></View> : null}
      </View>
      {failed ? (
        <Card style={{ borderColor: C.caution, backgroundColor: C.cautionBg }}>
          <Text testID="quality-fail" style={{ fontWeight: '700', color: C.caution, fontSize: 16, marginBottom: 6 }}>Let’s retake this one</Text>
          {failed.map((k) => <P key={k}>• {CHECK_TIPS[k] ?? k}</P>)}
        </Card>
      ) : null}
      <ErrorText error={error} />
    </Screen>
  );
}

const absFill = { position: 'absolute' as const, left: 0, right: 0, top: 0, bottom: 0 };

export function Review({ navigation }: Props<'Review'>) {
  const { captures, sessionId } = useStore();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = VIEWS.every((v) => captures[v]?.quality?.pass);

  async function submit() {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      await Sessions.submit(sessionId);
      navigation.replace('Processing');
    } catch {
      setError('Could not send your photos. Try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen footer={<Button testID="review-submit" title="Check my skin" busy={busy} disabled={!ready} onPress={submit} />}>
      <H1>Review your photos</H1>
      <P muted>Tap Retake on any photo you are not happy with.</P>
      <View style={{ flexDirection: 'row', gap: 10 }}>
        {VIEWS.map((v) => (
          <View key={v} style={{ flex: 1 }}>
            <View style={{ aspectRatio: 3 / 4, borderRadius: 10, overflow: 'hidden', backgroundColor: '#ddd' }}>
              {captures[v]?.uri ? <Image source={{ uri: captures[v]!.uri }} style={{ flex: 1 }} /> : null}
            </View>
            <Text style={{ textAlign: 'center', marginVertical: 6, color: C.text }}>{VIEW_COPY[v].title}</Text>
            <Button title="Retake" kind="secondary" onPress={() => navigation.navigate('Capture', { view: v, retake: true })} />
          </View>
        ))}
      </View>
      <ErrorText error={error} />
    </Screen>
  );
}

export function Processing({ navigation }: Props<'Processing'>) {
  const { sessionId, setCapture, setUploadUrls } = useStore();
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let tries = 0;
    async function poll() {
      if (!sessionId || !alive) return;
      try {
        const r = await Sessions.result(sessionId);
        if (r.status === 'complete') return navigation.replace('Results', { sessionId });
        if (r.status === 'needs_retake') {
          const fresh = await Sessions.uploadUrls(sessionId);
          setUploadUrls(fresh.upload_urls);
          (r.retake_views ?? VIEWS).forEach((v) => setCapture(v as V, undefined));
          setMsg(r.message ?? 'Some photos need a retake.');
          return navigation.replace('Capture', { view: (r.retake_views?.[0] ?? 'front') as V, retake: true });
        }
        if (r.status === 'failed') return setMsg(r.message ?? 'Something went wrong.');
      } catch {}
      tries += 1;
      if (tries < 60) setTimeout(poll, 1500);
      else setMsg('This is taking longer than usual. Check History later.');
    }
    poll();
    return () => { alive = false; };
  }, [sessionId]);

  return (
    <Screen scroll={false}>
      <View style={{ alignItems: 'center', marginTop: 80 }}>
        {msg ? <H2>{msg}</H2> : <ActivityIndicator size="large" color={C.primary} />}
        {!msg ? <P muted style={{ marginTop: 16, textAlign: 'center' }}>Checking photo quality and looking at visible concerns…</P> : null}
        {msg ? <Button title="Back to home" onPress={() => navigation.reset({ index: 0, routes: [{ name: 'Home' }] })} /> : null}
      </View>
    </Screen>
  );
}
