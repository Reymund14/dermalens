import React from 'react';
import {
  ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, TextInputProps, View, ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export const C = {
  bg: '#F7F6F3',
  card: '#FFFFFF',
  text: '#1C1B19',
  muted: '#5E5A55',
  line: '#E3DFD8',
  primary: '#2F5D8A', // calm clinic blue
  primaryText: '#FFFFFF',
  ok: '#2E7D4F', okBg: '#E8F4EC',
  info: '#2F5D8A', infoBg: '#E7EEF6',
  caution: '#8A5A00', cautionBg: '#FBF1DC',
  urgent: '#A12A2A', urgentBg: '#FBE7E7',
};

export const TONES: Record<string, { fg: string; bg: string; icon: string }> = {
  ok: { fg: C.ok, bg: C.okBg, icon: '✓' },
  info: { fg: C.info, bg: C.infoBg, icon: 'i' },
  caution: { fg: C.caution, bg: C.cautionBg, icon: '!' },
  urgent: { fg: C.urgent, bg: C.urgentBg, icon: '!' },
};

export function Screen({ children, scroll = true, footer }: { children: React.ReactNode; scroll?: boolean; footer?: React.ReactNode }) {
  const body = <View style={s.inner}>{children}</View>;
  return (
    <SafeAreaView style={s.screen} edges={['bottom', 'left', 'right']}>
      {scroll ? <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">{body}</ScrollView> : body}
      {footer ? <View style={s.footer}>{footer}</View> : null}
    </SafeAreaView>
  );
}

export function H1({ children }: { children: React.ReactNode }) {
  return <Text style={s.h1} accessibilityRole="header">{children}</Text>;
}
export function H2({ children }: { children: React.ReactNode }) {
  return <Text style={s.h2} accessibilityRole="header">{children}</Text>;
}
export function P({ children, muted, style }: { children: React.ReactNode; muted?: boolean; style?: any }) {
  return <Text style={[s.p, muted && { color: C.muted }, style]}>{children}</Text>;
}

export function Button({ title, onPress, kind = 'primary', disabled, busy, testID }: {
  title: string; onPress: () => void; kind?: 'primary' | 'secondary' | 'danger'; disabled?: boolean; busy?: boolean; testID?: string;
}) {
  const primary = kind === 'primary';
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled || !!busy }}
      onPress={onPress}
      disabled={disabled || busy}
      style={({ pressed }) => [
        s.btn,
        primary ? { backgroundColor: C.primary } : { backgroundColor: C.card, borderWidth: 1, borderColor: kind === 'danger' ? C.urgent : C.primary },
        (disabled || busy) && { opacity: 0.45 },
        pressed && { opacity: 0.8 },
      ]}>
      {busy ? <ActivityIndicator color={primary ? '#fff' : C.primary} /> : (
        <Text style={[s.btnText, { color: primary ? C.primaryText : kind === 'danger' ? C.urgent : C.primary }]}>{title}</Text>
      )}
    </Pressable>
  );
}

export function Chip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: selected }} onPress={onPress}
      style={[s.chip, selected && { backgroundColor: C.primary, borderColor: C.primary }]}>
      <Text style={[s.chipText, selected && { color: '#fff' }]}>{label}</Text>
    </Pressable>
  );
}

export function Segmented<T extends string | number>({ options, value, onChange }: {
  options: { label: string; value: T }[]; value: T | undefined; onChange: (v: T) => void;
}) {
  return (
    <View style={s.seg}>
      {options.map((o) => (
        <Chip key={String(o.value)} label={o.label} selected={value === o.value} onPress={() => onChange(o.value)} />
      ))}
    </View>
  );
}

export function YesNo({ value, onChange }: { value: boolean | undefined; onChange: (v: boolean) => void }) {
  return <Segmented options={[{ label: 'No', value: 'no' }, { label: 'Yes', value: 'yes' }]}
    value={value === undefined ? undefined : value ? 'yes' : 'no'} onChange={(v) => onChange(v === 'yes')} />;
}

export function Card({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <View style={[s.card, style]}>{children}</View>;
}

export function Field(props: TextInputProps & { label: string }) {
  const { label, ...rest } = props;
  return (
    <View style={{ marginBottom: 14 }}>
      <Text style={s.label}>{label}</Text>
      <TextInput placeholderTextColor="#8F8A84" style={s.input} accessibilityLabel={label} {...rest} />
    </View>
  );
}

export function Progress({ step, total }: { step: number; total: number }) {
  return (
    <View accessibilityLabel={`Step ${step} of ${total}`} style={{ marginBottom: 16 }}>
      <Text style={[s.p, { color: C.muted, marginBottom: 6 }]}>Step {step} of {total}</Text>
      <View style={s.track}><View style={[s.fill, { width: `${(step / total) * 100}%` }]} /></View>
    </View>
  );
}

export function Boundary({ text }: { text?: string }) {
  return (
    <View style={s.boundary} accessibilityRole="text">
      <Text style={s.boundaryTitle}>What this is not</Text>
      <Text style={s.boundaryText}>
        {text ?? 'DermaLens gives general skincare information and a visual pre-screening. It does not diagnose, treat or rule out any disease. For a changing mole, a sore that does not heal, pain, bleeding, rapid spreading or fever, see a board-certified dermatologist.'}
      </Text>
    </View>
  );
}

export function ErrorText({ error }: { error?: string | null }) {
  return error ? <Text style={s.error} accessibilityLiveRegion="polite">{error}</Text> : null;
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.bg },
  scroll: { flexGrow: 1 },
  inner: { padding: 20, maxWidth: 640, width: '100%', alignSelf: 'center' },
  footer: { padding: 16, borderTopWidth: 1, borderTopColor: C.line, backgroundColor: C.bg, gap: 10, maxWidth: 640, width: '100%', alignSelf: 'center' },
  h1: { fontSize: 26, fontWeight: '700', color: C.text, marginBottom: 10 },
  h2: { fontSize: 19, fontWeight: '700', color: C.text, marginTop: 18, marginBottom: 8 },
  p: { fontSize: 16, lineHeight: 23, color: C.text, marginBottom: 8 },
  btn: { minHeight: 52, borderRadius: 12, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18 },
  btnText: { fontSize: 17, fontWeight: '600' },
  chip: { borderWidth: 1, borderColor: C.line, backgroundColor: C.card, borderRadius: 999, paddingVertical: 9, paddingHorizontal: 15, marginRight: 8, marginBottom: 8 },
  chipText: { fontSize: 16, color: C.text },
  seg: { flexDirection: 'row', flexWrap: 'wrap' },
  card: { backgroundColor: C.card, borderRadius: 14, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.line },
  label: { fontSize: 15, color: C.muted, marginBottom: 6 },
  input: { borderWidth: 1, borderColor: C.line, backgroundColor: C.card, borderRadius: 10, padding: 13, fontSize: 16, color: C.text },
  track: { height: 6, borderRadius: 3, backgroundColor: C.line },
  fill: { height: 6, borderRadius: 3, backgroundColor: C.primary },
  boundary: { borderRadius: 12, padding: 14, backgroundColor: '#EFEDE8', marginVertical: 12 },
  boundaryTitle: { fontWeight: '700', fontSize: 15, color: C.text, marginBottom: 4 },
  boundaryText: { fontSize: 14.5, lineHeight: 21, color: C.muted },
  error: { color: C.urgent, fontSize: 15, marginVertical: 8 },
});
