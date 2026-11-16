import React, { useEffect, useMemo, useState } from 'react';
import { Linking, Pressable, Text, View } from 'react-native';

import { AllergenHit, ConcernRef, Me, ProductCard, Ref, RedFlagQ, Sessions } from '../api';
import type { Props } from '../nav';
import { AllergenDraft, useStore } from '../store';
import { Button, C, Card, Chip, ErrorText, Field, H1, H2, P, Progress, Screen, Segmented, TONES, YesNo } from '../ui';

const TOTAL = 5;

// ----- 1. Concerns ------------------------------------------------------------

export function Concerns({ navigation }: Props<'Concerns'>) {
  const { draft, setDraft } = useStore();
  const [refs, setRefs] = useState<ConcernRef[]>([]);
  useEffect(() => { Ref.concerns().then(setRefs).catch(() => {}); }, []);
  const selected = new Map(draft.concerns.map((c) => [c.code, c]));

  function toggle(code: string) {
    if (selected.has(code)) setDraft({ concerns: draft.concerns.filter((c) => c.code !== code) });
    else setDraft({ concerns: [...draft.concerns, { code, self_severity: 2, duration_weeks: 4 }] });
  }
  function update(code: string, patch: Partial<{ self_severity: 1 | 2 | 3; duration_weeks: number }>) {
    setDraft({ concerns: draft.concerns.map((c) => (c.code === code ? { ...c, ...patch } : c)) });
  }

  return (
    <Screen footer={<Button testID="concerns-next" title="Next" onPress={() => navigation.navigate('Health')} />}>
      <Progress step={1} total={TOTAL} />
      <H1>What would you like to look at?</H1>
      <P muted>Choose any that bother you. You can also choose none.</P>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginBottom: 8 }}>
        {refs.map((r) => <Chip key={r.code} label={r.name} selected={selected.has(r.code)} onPress={() => toggle(r.code)} />)}
      </View>
      {draft.concerns.map((c) => (
        <Card key={c.code}>
          <Text style={{ fontWeight: '700', fontSize: 16, marginBottom: 8, color: C.text }}>{refs.find((r) => r.code === c.code)?.name ?? c.code}</Text>
          <P muted>How bothersome?</P>
          <Segmented options={[{ label: 'A little', value: 1 }, { label: 'Moderately', value: 2 }, { label: 'A lot', value: 3 }]}
            value={c.self_severity} onChange={(v) => update(c.code, { self_severity: v as 1 | 2 | 3 })} />
          <P muted>For how long?</P>
          <Segmented options={[{ label: '< 1 month', value: 2 }, { label: '1–3 months', value: 8 }, { label: '3–6 months', value: 18 }, { label: '> 6 months', value: 30 }]}
            value={c.duration_weeks} onChange={(v) => update(c.code, { duration_weeks: v })} />
        </Card>
      ))}
    </Screen>
  );
}

// ----- 2. Health check (red flags) -------------------------------------------

export function Health({ navigation }: Props<'Health'>) {
  const { draft, setDraft } = useStore();
  const [qs, setQs] = useState<RedFlagQ[]>([]);
  const [profile, setProfile] = useState<any>(null);
  useEffect(() => {
    Ref.redFlags().then(setQs).catch(() => {});
    Me.profile().then(setProfile).catch(() => {});
  }, []);
  const answered = qs.length > 0 && qs.every((q) => draft.red_flags[q.code] !== undefined);

  function answer(q: RedFlagQ, v: boolean) {
    const red_flags = { ...draft.red_flags, [q.code]: v };
    setDraft({ red_flags });
    if (v && q.urgent) navigation.navigate('Urgent', { flags: [q.code] }); // urgent: show care screen immediately
  }
  async function setPregnant(v: boolean) {
    if (!profile) return;
    const p = { ...profile, is_pregnant_or_breastfeeding: v };
    setProfile(p);
    await Me.saveProfile(p).catch(() => {});
  }

  return (
    <Screen footer={<>
      {!answered ? <P muted style={{ textAlign: 'center' }}>Please answer every question.</P> : null}
      <Button testID="health-next" title="Next" disabled={!answered} onPress={() => navigation.navigate('Allergies')} />
      <Button testID="health-all-no" title="None of these apply to me" kind="secondary"
        onPress={() => setDraft({ red_flags: Object.fromEntries(qs.map((q) => [q.code, false])) })} />
    </>}>
      <Progress step={2} total={TOTAL} />
      <H1>A quick health check</H1>
      <P muted>These questions make sure we send you to the right person.</P>
      {qs.map((q) => (
        <Card key={q.code}>
          <P>{q.question}</P>
          <YesNo value={draft.red_flags[q.code]} onChange={(v) => answer(q, v)} />
        </Card>
      ))}
      <H2>Medicines and pregnancy</H2>
      <Card>
        <P>Are you currently taking isotretinoin (for example, for acne)?</P>
        <YesNo value={draft.on_isotretinoin} onChange={(v) => setDraft({ on_isotretinoin: v })} />
      </Card>
      <Card>
        <P>Are you using any prescription creams or gels on your face?</P>
        <YesNo value={draft.current_rx_topicals} onChange={(v) => setDraft({ current_rx_topicals: v })} />
      </Card>
      {profile ? (
        <Card>
          <P>Are you pregnant or breastfeeding?</P>
          <YesNo value={!!profile.is_pregnant_or_breastfeeding} onChange={setPregnant} />
        </Card>
      ) : null}
    </Screen>
  );
}

export function Urgent({ navigation, route }: Props<'Urgent'>) {
  const { draft, setDraft } = useStore();
  const t = TONES.urgent;
  return (
    <Screen footer={<>
      <Button title="Call 911 (Philippines emergency)" kind="danger" onPress={() => Linking.openURL('tel:911')} />
      <Button title="I answered by mistake" kind="secondary" onPress={() => {
        const red_flags = { ...draft.red_flags };
        route.params.flags.forEach((f) => { red_flags[f] = false; });
        setDraft({ red_flags });
        navigation.goBack();
      }} />
    </>}>
      <View testID="urgent-banner" style={{ backgroundColor: t.bg, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: t.fg }}>
        <Text style={{ color: t.fg, fontSize: 22, fontWeight: '700', marginBottom: 8 }}>Please seek medical care promptly</Text>
        <Text style={{ color: C.text, fontSize: 16, lineHeight: 23 }}>
          What you described needs a doctor today. Go to an emergency room or see a physician as soon as you can.
          DermaLens will not suggest a routine for this.
        </Text>
      </View>
    </Screen>
  );
}

// ----- 3. Allergies -----------------------------------------------------------

export function Allergies({ navigation }: Props<'Allergies'>) {
  const { draft, setDraft } = useStore();
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<AllergenHit[]>([]);
  useEffect(() => {
    const t = setTimeout(() => { if (q.trim().length >= 2) Ref.allergens(q).then(setHits).catch(() => {}); else setHits([]); }, 250);
    return () => clearTimeout(t);
  }, [q]);

  function add(a: AllergenDraft) {
    if (!draft.allergens.some((x) => x.label === a.label)) setDraft({ allergens: [...draft.allergens, a] });
    setQ('');
    setHits([]);
  }

  return (
    <Screen footer={<Button testID="allergies-next" title="Next" onPress={() => navigation.navigate('CurrentRoutine')} />}>
      <Progress step={3} total={TOTAL} />
      <H1>Any ingredient allergies?</H1>
      <P muted>We will never suggest a product that contains them. Skip if none.</P>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        {['Fragrance', 'Essential oils', 'Lanolin', 'Parabens'].map((label) => (
          <Chip key={label} label={label} selected={draft.allergens.some((a) => a.label === label)}
            onPress={() => draft.allergens.some((a) => a.label === label)
              ? setDraft({ allergens: draft.allergens.filter((a) => a.label !== label) })
              : add({ family_code: label.toLowerCase().replace(' ', '_'), label })} />
        ))}
      </View>
      <Field testID="allergen-search" label="Search an ingredient" value={q} onChangeText={setQ} placeholder="e.g. salicylic acid, vitamin C" />
      {hits.map((h) => (
        <Pressable key={`${h.kind}-${h.family_code ?? h.ingredient_id}`} onPress={() => add({ family_code: h.family_code, ingredient_id: h.ingredient_id, label: h.label })}
          style={{ paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.line }}>
          <Text style={{ fontSize: 16, color: C.text }}>{h.label}{h.kind === 'family' ? '  (whole group)' : ''}</Text>
        </Pressable>
      ))}
      {q.trim().length >= 2 ? (
        <Button title={`Add "${q.trim()}" as written`} kind="secondary" onPress={() => add({ raw_text: q.trim(), label: q.trim() })} />
      ) : null}
      {draft.allergens.length ? <H2>Your allergies</H2> : null}
      {draft.allergens.map((a) => (
        <Card key={a.label} style={{ flexDirection: 'row', alignItems: 'center' }}>
          <Text style={{ flex: 1, fontSize: 16, color: C.text }}>{a.label}{a.raw_text ? ' (staff will review)' : ''}</Text>
          <Pressable accessibilityLabel={`Remove ${a.label}`} onPress={() => setDraft({ allergens: draft.allergens.filter((x) => x !== a) })}>
            <Text style={{ color: C.urgent, fontSize: 15 }}>Remove</Text>
          </Pressable>
        </Card>
      ))}
    </Screen>
  );
}

// ----- 4. Current routine -----------------------------------------------------

export function CurrentRoutine({ navigation }: Props<'CurrentRoutine'>) {
  const { draft, setDraft } = useStore();
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<ProductCard[]>([]);
  useEffect(() => {
    const t = setTimeout(() => { if (q.trim().length >= 2) Ref.products(q).then(setHits).catch(() => {}); else setHits([]); }, 250);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <Screen footer={<Button testID="routine-next" title="Next" onPress={() => navigation.navigate('Lifestyle')} />}>
      <Progress step={4} total={TOTAL} />
      <H1>What do you use now?</H1>
      <P muted>Add the products you use on your face. Skip if none.</P>
      <Field label="Search products" value={q} onChangeText={setQ} placeholder="Brand or product name" />
      {hits.map((p) => (
        <Pressable key={p.id} onPress={() => { setDraft({ current_routine: [...draft.current_routine, { time_of_day: 'both', product_id: p.id, reaction_reported: false, label: `${p.brand} ${p.name}` }] }); setQ(''); }}
          style={{ paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.line }}>
          <Text style={{ fontSize: 16, color: C.text }}>{p.brand} {p.name}</Text>
        </Pressable>
      ))}
      {q.trim().length >= 2 ? (
        <Button title={`Add "${q.trim()}" (not in list)`} kind="secondary" onPress={() => { setDraft({ current_routine: [...draft.current_routine, { time_of_day: 'both', free_text_name: q.trim(), reaction_reported: false, label: q.trim() }] }); setQ(''); }} />
      ) : null}
      {draft.current_routine.map((r, i) => (
        <Card key={`${r.label}-${i}`}>
          <Text style={{ fontWeight: '600', fontSize: 16, color: C.text, marginBottom: 8 }}>{r.label}</Text>
          <Segmented options={[{ label: 'Morning', value: 'am' }, { label: 'Evening', value: 'pm' }, { label: 'Both', value: 'both' }]}
            value={r.time_of_day} onChange={(v) => setDraft({ current_routine: draft.current_routine.map((x, j) => (j === i ? { ...x, time_of_day: v as 'am' } : x)) })} />
          <P muted>Has it ever caused a reaction (stinging, rash, breakouts)?</P>
          <YesNo value={r.reaction_reported} onChange={(v) => setDraft({ current_routine: draft.current_routine.map((x, j) => (j === i ? { ...x, reaction_reported: v } : x)) })} />
          <Pressable onPress={() => setDraft({ current_routine: draft.current_routine.filter((_, j) => j !== i) })}>
            <Text style={{ color: C.urgent, fontSize: 15, marginTop: 6 }}>Remove</Text>
          </Pressable>
        </Card>
      ))}
      {draft.current_routine.length ? (
        <Card>
          <P>Do you already use exfoliating acids or retinol without problems?</P>
          <YesNo value={draft.uses_actives_without_reaction} onChange={(v) => setDraft({ uses_actives_without_reaction: v })} />
        </Card>
      ) : null}
    </Screen>
  );
}

// ----- 5. Lifestyle (submits the intake) --------------------------------------

export function Lifestyle({ navigation }: Props<'Lifestyle'>) {
  const { draft, setDraft, setSession } = useStore();
  const ls = draft.lifestyle;
  const set = (patch: Partial<typeof ls>) => setDraft({ lifestyle: { ...ls, ...patch } });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const body = useMemo(() => ({
    concerns: draft.concerns,
    red_flags: draft.red_flags,
    allergens: draft.allergens.map(({ label, ...a }) => a),
    current_routine: draft.current_routine.map(({ label, ...r }) => r),
    lifestyle: ls,
    on_isotretinoin: draft.on_isotretinoin,
    current_rx_topicals: draft.current_rx_topicals,
    uses_actives_without_reaction: draft.uses_actives_without_reaction,
  }), [draft, ls]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const intake = await Sessions.createIntake(body);
      if (intake.urgent) {
        navigation.navigate('Urgent', { flags: Object.keys(draft.red_flags).filter((k) => draft.red_flags[k]) });
        return;
      }
      const s = await Sessions.open(intake.intake_id);
      setSession(intake.intake_id, s.session_id, s.upload_urls);
      navigation.navigate('CaptureGuide');
    } catch {
      setError('Could not save your answers. Check your connection and try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen footer={<Button testID="lifestyle-next" title="Continue to photos" busy={busy} onPress={submit} />}>
      <Progress step={5} total={TOTAL} />
      <H1>A little about your day</H1>
      <H2>Time in the sun on a typical day</H2>
      <Segmented options={[{ label: '< 15 min', value: 10 }, { label: '15–60 min', value: 40 }, { label: '1–3 hours', value: 120 }, { label: '> 3 hours', value: 240 }]}
        value={ls.daily_sun_exposure_min} onChange={(v) => set({ daily_sun_exposure_min: v })} />
      <H2>Do you use sunscreen?</H2>
      <Segmented options={[{ label: 'Never', value: 'never' }, { label: 'Sometimes', value: 'sometimes' }, { label: 'Daily', value: 'daily' }]}
        value={ls.sunscreen_use} onChange={(v) => set({ sunscreen_use: v as 'daily' })} />
      <H2>Sleep on a typical night</H2>
      <Segmented options={[{ label: '< 5 h', value: 4.5 }, { label: '5–7 h', value: 6 }, { label: '7–9 h', value: 8 }, { label: '> 9 h', value: 9.5 }]}
        value={ls.sleep_hours} onChange={(v) => set({ sleep_hours: v })} />
      <H2>Stress lately</H2>
      <Segmented options={[1, 2, 3, 4, 5].map((n) => ({ label: ['Very low', 'Low', 'Medium', 'High', 'Very high'][n - 1], value: n }))}
        value={ls.stress_level} onChange={(v) => set({ stress_level: v })} />
      <H2>Do you smoke?</H2>
      <YesNo value={ls.smoker} onChange={(v) => set({ smoker: v })} />
      <ErrorText error={error} />
    </Screen>
  );
}
