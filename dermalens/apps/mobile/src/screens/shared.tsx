// Pieces shared by the clinic staff, dermatologist and admin screens.
import React, { useEffect, useState } from 'react';
import { Image, Platform, Pressable, Text, View } from 'react-native';

import { API_URL, authHeader, CaseBrief, CaseDetail, signOut } from '../api';
import { C, Card, H2, P, TONES } from '../ui';

export const ROUTE_META: Record<string, { label: string; tone: string }> = {
  urgent_care: { label: 'Urgent care', tone: 'urgent' },
  dermatologist: { label: 'Dermatologist', tone: 'caution' },
  iconic_clinic: { label: 'ICONIC consult', tone: 'info' },
  self_care: { label: 'Self-care', tone: 'ok' },
};

export const FOLLOW_UP_LABEL: Record<string, string> = {
  new: 'New', contacted: 'Contacted', booked: 'Booked', no_response: 'No response', closed: 'Closed',
};

export const ROLE_LABEL: Record<string, string> = {
  patient: 'Patient', clinic_staff: 'Clinic staff', dermatologist: 'Dermatologist', admin: 'Admin',
};

export function Tag({ label, tone = 'info' }: { label: string; tone?: string }) {
  const t = TONES[tone] ?? TONES.info;
  return (
    <View style={{ backgroundColor: t.bg, borderRadius: 999, paddingVertical: 3, paddingHorizontal: 10, alignSelf: 'flex-start', marginRight: 6, marginBottom: 4 }}>
      <Text style={{ color: t.fg, fontSize: 13, fontWeight: '600' }}>{label}</Text>
    </View>
  );
}

export function RouteTag({ route }: { route: string | null }) {
  const m = ROUTE_META[route ?? ''] ?? { label: route ?? 'Unknown', tone: 'info' };
  return <Tag label={m.label} tone={m.tone} />;
}

export function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <View style={{ flexDirection: 'row', paddingVertical: 5, borderBottomWidth: 1, borderBottomColor: C.line }}>
      <Text style={{ color: C.muted, fontSize: 15, width: 150 }}>{label}</Text>
      <Text style={{ color: C.text, fontSize: 15, flex: 1 }}>{value}</Text>
    </View>
  );
}

export function Stat({ label, value, tone }: { label: string; value: React.ReactNode; tone?: string }) {
  const fg = tone ? TONES[tone].fg : C.text;
  return (
    <Card style={{ flexBasis: '47%', flexGrow: 1, marginRight: 8 }}>
      <Text style={{ fontSize: 26, fontWeight: '700', color: fg }}>{value}</Text>
      <Text style={{ color: C.muted, fontSize: 14 }}>{label}</Text>
    </Card>
  );
}

export function StatGrid({ children }: { children: React.ReactNode }) {
  return <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginRight: -8 }}>{children}</View>;
}

export const pct = (x: number | null | undefined) => (x === null || x === undefined ? '–' : `${Math.round(x * 100)}%`);
export const when = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });

/** Lists a shared case in the staff inbox and dermatologist queue. */
export function CaseRow({ c, onPress, right }: { c: CaseBrief; onPress: () => void; right?: React.ReactNode }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" testID={`case-${c.summary_id}`}>
      <Card style={{ flexDirection: 'row', alignItems: 'center' }}>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 17, fontWeight: '600', color: C.text }}>{c.patient?.initials ?? '–'} · {c.patient?.age_band ?? ''}</Text>
          <Text style={{ color: C.muted, fontSize: 14, marginBottom: 6 }}>{when(c.created_at)}</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
            <RouteTag route={c.route} />
            {right}
          </View>
        </View>
        <Text style={{ color: C.primary, fontSize: 15 }}>Open ›</Text>
      </Card>
    </Pressable>
  );
}

/** A photo behind staff auth. Native Image sends headers; on web we fetch a blob. */
export function AuthImage({ path, size = 150 }: { path: string; size?: number }) {
  const [src, setSrc] = useState<{ uri: string; headers?: Record<string, string> } | null>(null);
  useEffect(() => {
    let url: string | null = null;
    (async () => {
      const headers = await authHeader();
      if (Platform.OS === 'web') {
        const r = await fetch(`${API_URL}${path}`, { headers });
        if (!r.ok) return;
        url = URL.createObjectURL(await r.blob());
        setSrc({ uri: url });
      } else setSrc({ uri: `${API_URL}${path}`, headers });
    })().catch(() => {});
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [path]);
  return (
    <View style={{ width: size, height: size * 1.25, borderRadius: 10, overflow: 'hidden', backgroundColor: C.line, marginRight: 8, marginBottom: 8 }}>
      {src ? <Image source={src} style={{ flex: 1 }} resizeMode="cover" accessibilityLabel="Patient photo" /> : null}
    </View>
  );
}

const VIEW_LABEL: Record<string, string> = { front: 'Front', left45: 'Left 45°', right45: 'Right 45°', closeup: 'Close-up' };

/** Read-only case content: the same facts as the PDF summary, initials only. */
export function CaseBody({ c, imagePath }: { c: CaseDetail; imagePath: (view: string) => string }) {
  const d = c.data ?? {};
  const pr = d.patient_reported ?? {};
  const yesFlags = (pr.red_flags ?? []).filter((f: any) => f.answer === 'Yes');
  return (
    <View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginBottom: 6 }}>
        <RouteTag route={c.route} />
        <Tag label={c.reviewed ? 'Reviewed' : 'Not reviewed'} tone={c.reviewed ? 'ok' : 'caution'} />
        <Tag label={FOLLOW_UP_LABEL[c.follow_up_status]} tone="info" />
      </View>
      <Card>
        <Row label="Patient" value={`${d.patient?.initials ?? '–'} (initials only)`} />
        <Row label="Age band" value={d.patient?.age_band ?? '–'} />
        <Row label="Skin type" value={d.patient?.skin_type ?? '–'} />
        <Row label="Fitzpatrick (self)" value={d.patient?.self_fitzpatrick ?? '–'} />
        <Row label="Pregnant / breastfeeding" value={d.patient?.pregnant_or_breastfeeding ? 'Yes' : 'No'} />
        <Row label="Shared" value={when(c.created_at)} />
        {c.reviewed_by ? <Row label="Reviewed by" value={`${c.reviewed_by}${c.reviewed_at ? `, ${when(c.reviewed_at)}` : ''}`} /> : null}
      </Card>

      <H2>Why the app chose this route</H2>
      {(d.reasons ?? []).map((r: any) => <P key={r.code}>• {r.text}</P>)}

      {c.views.length ? <H2>Photos</H2> : null}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        {c.views.map((v) => (
          <View key={v}>
            <AuthImage path={imagePath(v)} size={130} />
            <Text style={{ color: C.muted, fontSize: 13, marginTop: -4, marginBottom: 8 }}>{VIEW_LABEL[v] ?? v}</Text>
          </View>
        ))}
      </View>

      <H2>Visual pre-screen</H2>
      {(d.visual_prescreen ?? []).length === 0 ? <P muted>No visual findings (urgent route skips the model).</P> : null}
      {(d.visual_prescreen ?? []).map((f: any) => (
        <Row key={f.code} label={f.name} value={`${f.present ? f.grade_name : 'Not seen'}${f.uncertain ? ' (uncertain)' : ''}`} />
      ))}

      <H2>Patient reported</H2>
      {(pr.concerns ?? []).map((x: any) => (
        <Row key={x.name} label={x.name} value={`bothersome ${x.bothersome_1to3}/3${x.duration_weeks ? `, ${x.duration_weeks} wk` : ''}`} />
      ))}
      <Row label="Red flags" value={yesFlags.length ? yesFlags.map((f: any) => f.question).join('; ') : 'None answered yes'} />
      <Row label="Allergies" value={(pr.allergies ?? []).join(', ') || 'None'} />
      <Row label="On isotretinoin" value={pr.on_isotretinoin ? 'Yes' : 'No'} />
      <Row label="Current routine" value={(pr.current_routine ?? []).map((r: any) => `${r.time}: ${r.product}${r.reaction ? ' (reaction)' : ''}`).join('; ') || 'None given'} />

      {d.routine ? (
        <>
          <H2>Routine shown to the patient</H2>
          <Row label="Morning" value={(d.routine.am ?? []).map((s: any) => s.product.name).join(' → ') || '–'} />
          <Row label="Evening" value={(d.routine.pm ?? []).map((s: any) => s.product.name).join(' → ') || '–'} />
        </>
      ) : null}
      <P muted style={{ marginTop: 12, fontSize: 13 }}>Model {d.versions?.model ?? '–'} · triage {d.versions?.triage_rules ?? '–'} · rules {d.versions?.recommendation_rules ?? '–'}</P>
    </View>
  );
}

/** Header-right "Sign out" for non-patient homes. */
export function SignOutLink({ onDone }: { onDone: () => void }) {
  return (
    <Pressable accessibilityRole="button" testID="sign-out" onPress={async () => { await signOut(); onDone(); }} style={{ padding: 8 }}>
      <Text style={{ color: C.primary, fontSize: 16 }}>Sign out</Text>
    </Pressable>
  );
}

export function Who({ name, role }: { name: string | null | undefined; role: string }) {
  return <P muted>Signed in as {name ?? 'staff'} · {ROLE_LABEL[role]}</P>;
}

export function confirmAction(msg: string): Promise<boolean> {
  if (Platform.OS === 'web') return Promise.resolve(window.confirm(msg));
  const { Alert } = require('react-native');
  return new Promise((res) => Alert.alert('Please confirm', msg, [
    { text: 'Cancel', style: 'cancel', onPress: () => res(false) },
    { text: 'Continue', onPress: () => res(true) },
  ]));
}
