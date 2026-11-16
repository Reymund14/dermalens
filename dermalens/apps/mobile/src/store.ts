import { create } from 'zustand';

export type View = 'front' | 'left45' | 'right45';
export const VIEWS: View[] = ['front', 'left45', 'right45'];

export type ConcernDraft = { code: string; self_severity: 1 | 2 | 3; duration_weeks: number };
export type AllergenDraft = { ingredient_id?: string; family_code?: string; raw_text?: string; label: string };
export type RoutineDraft = { time_of_day: 'am' | 'pm' | 'both'; product_id?: string; free_text_name?: string; reaction_reported: boolean; label: string };

export type Draft = {
  concerns: ConcernDraft[];
  red_flags: Record<string, boolean>;
  on_isotretinoin: boolean;
  current_rx_topicals: boolean;
  pregnant: boolean;
  allergens: AllergenDraft[];
  current_routine: RoutineDraft[];
  uses_actives_without_reaction: boolean;
  lifestyle: {
    sleep_hours?: number;
    daily_sun_exposure_min?: number;
    sunscreen_use?: 'never' | 'sometimes' | 'daily';
    smoker?: boolean;
    stress_level?: number;
    water_glasses_per_day?: number;
  };
};

const emptyDraft: Draft = {
  concerns: [], red_flags: {}, on_isotretinoin: false, current_rx_topicals: false, pregnant: false,
  allergens: [], current_routine: [], uses_actives_without_reaction: false, lifestyle: {},
};

type Capture = { uri: string; quality?: { pass: boolean; checks: Record<string, boolean> } };

type State = {
  draft: Draft;
  intakeId?: string;
  sessionId?: string;
  uploadUrls?: Record<string, string>;
  captures: Partial<Record<View, Capture>>;
  setDraft: (patch: Partial<Draft>) => void;
  setSession: (intakeId: string, sessionId: string, urls: Record<string, string>) => void;
  setUploadUrls: (urls: Record<string, string>) => void;
  setCapture: (view: View, c: Capture | undefined) => void;
  resetAssessment: () => void;
  resetAll: () => void;
};

export const useStore = create<State>((set) => ({
  draft: emptyDraft,
  captures: {},
  setDraft: (patch) => set((s) => ({ draft: { ...s.draft, ...patch } })),
  setSession: (intakeId, sessionId, uploadUrls) => set({ intakeId, sessionId, uploadUrls, captures: {} }),
  setUploadUrls: (uploadUrls) => set({ uploadUrls }),
  setCapture: (view, c) => set((s) => ({ captures: { ...s.captures, [view]: c } })),
  // A returning user keeps the last intake answers as a pre-filled draft to confirm.
  resetAssessment: () => set({ intakeId: undefined, sessionId: undefined, uploadUrls: undefined, captures: {} }),
  resetAll: () => set({ draft: emptyDraft, intakeId: undefined, sessionId: undefined, uploadUrls: undefined, captures: {} }),
}));
