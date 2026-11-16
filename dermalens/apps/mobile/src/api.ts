import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

// API base URL: EXPO_PUBLIC_API_URL, else app.json "extra.apiUrl", else local dev.
export const API_URL: string =
  process.env.EXPO_PUBLIC_API_URL ??
  ((Constants.expoConfig?.extra as { apiUrl?: string } | undefined)?.apiUrl ?? 'http://localhost:8000');

const KEY = 'dermalens.tokens';

type Tokens = { access_token: string; refresh_token: string; role: string };
let memory: Tokens | null = null;

async function saveTokens(t: Tokens | null) {
  memory = t;
  try {
    if (Platform.OS === 'web') {
      // Web demo only. Native builds keep tokens in the Keychain / Keystore.
      if (t) sessionStorage.setItem(KEY, JSON.stringify(t));
      else sessionStorage.removeItem(KEY);
    } else if (t) await SecureStore.setItemAsync(KEY, JSON.stringify(t));
    else await SecureStore.deleteItemAsync(KEY);
  } catch {
    // Storage unavailable: keep the in-memory copy for this run.
  }
}

export async function loadTokens(): Promise<Tokens | null> {
  if (memory) return memory;
  try {
    const raw = Platform.OS === 'web' ? sessionStorage.getItem(KEY) : await SecureStore.getItemAsync(KEY);
    memory = raw ? (JSON.parse(raw) as Tokens) : null;
  } catch {
    memory = null;
  }
  return memory;
}

export async function signOut() {
  await saveTokens(null);
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === 'string' ? detail : `Request failed (${status})`);
  }
}

async function refresh(): Promise<boolean> {
  const t = await loadTokens();
  if (!t) return false;
  const r = await fetch(`${API_URL}/api/v1/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: t.refresh_token }),
  });
  if (!r.ok) {
    await saveTokens(null);
    return false;
  }
  await saveTokens(await r.json());
  return true;
}

export async function authHeader(): Promise<Record<string, string>> {
  const t = await loadTokens();
  return t ? { Authorization: `Bearer ${t.access_token}` } : {};
}

export async function api<T = any>(path: string, init: RequestInit & { json?: unknown } = {}, retry = true): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>), ...(await authHeader()) };
  let body = init.body;
  if (init.json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(init.json);
  }
  const r = await fetch(`${API_URL}/api/v1${path}`, { ...init, headers, body });
  if (r.status === 401 && retry && (await refresh())) return api<T>(path, init, false);
  if (!r.ok) {
    let detail: unknown = r.statusText;
    try {
      detail = (await r.json()).detail;
    } catch {}
    throw new ApiError(r.status, detail);
  }
  if (r.status === 204) return undefined as T;
  const ct = r.headers.get('content-type') ?? '';
  return (ct.includes('json') ? r.json() : r.text()) as Promise<T>;
}

// ----- Types ------------------------------------------------------------------

export type RedFlagQ = { code: string; question: string; urgent: boolean };
export type ConcernRef = { code: string; name: string; model_label: boolean };
export type AllergenHit = { kind: 'family' | 'ingredient'; family_code?: string; ingredient_id?: string; label: string };
export type ProductCard = {
  id: string; brand: string; name: string; category: string; spf: number | null; pa_rating: string | null;
  price_php: number | null; stocked_by_iconic: boolean; fda_notification_no: string | null; ingredients: string[];
};
export type RoutineStep = { step: number; slot: string; frequency: string; why: string; patch_test: boolean; product: ProductCard };
export type Finding = { code: string; name: string; present: boolean; grade: string; grade_name: string; band: string; uncertain: boolean };
export type Result = {
  session_id: string;
  status: 'open' | 'uploaded' | 'processing' | 'needs_retake' | 'complete' | 'failed';
  created_at: string;
  boundary: string;
  message?: string;
  retake_views?: string[];
  route?: { code: 'urgent_care' | 'dermatologist' | 'iconic_clinic' | 'self_care'; title: string; body: string; tone: string; cta: string };
  reasons?: { code: string; text: string }[];
  findings?: Finding[];
  routine?: { status: string; am: RoutineStep[]; pm: RoutineStep[]; notes: string[]; basics_only: boolean } | null;
  versions?: Record<string, string | null>;
};

// ----- Endpoints --------------------------------------------------------------

export const Auth = {
  async register(email: string, password: string) {
    const t = await api<Tokens>('/auth/register', { method: 'POST', json: { email, password, accepted_boundary: true } }, false);
    await saveTokens(t);
    return t;
  },
  async login(email: string, password: string) {
    const t = await api<Tokens>('/auth/login', { method: 'POST', json: { email, password } }, false);
    await saveTokens(t);
    return t;
  },
};

export const Ref = {
  boundary: () => api<{ text: string }>('/reference/boundary'),
  concerns: () => api<ConcernRef[]>('/reference/concerns'),
  redFlags: () => api<RedFlagQ[]>('/reference/red-flags'),
  allergens: (q: string) => api<AllergenHit[]>(`/allergens/search?q=${encodeURIComponent(q)}`),
  products: (q: string) => api<ProductCard[]>(`/products/search?q=${encodeURIComponent(q)}`),
};

export const Me = {
  profile: () => api('/me/profile'),
  saveProfile: (p: unknown) => api('/me/profile', { method: 'PUT', json: p }),
  consents: () => api<Record<string, boolean>>('/consents'),
  setConsent: (purpose: string, granted: boolean) => api<Record<string, boolean>>('/consents', { method: 'POST', json: { purpose, granted } }),
  exportData: () => api('/me/export'),
  deleteAccount: () => api('/me', { method: 'DELETE' }),
};

export const Sessions = {
  createIntake: (body: unknown) => api<{ intake_id: string; urgent: boolean }>('/intakes', { method: 'POST', json: body }),
  open: (intake_id: string) =>
    api<{ session_id: string; upload_urls: Record<string, string> }>('/sessions', {
      method: 'POST', json: { intake_id, app_version: '0.1.0', device_model: Platform.OS },
    }),
  uploadUrls: (sid: string) => api<{ upload_urls: Record<string, string> }>(`/sessions/${sid}/upload-urls`, { method: 'POST' }),
  async upload(uploadPath: string, localUri: string) {
    const blob = await (await fetch(localUri)).blob();
    const r = await fetch(`${API_URL}${uploadPath}`, { method: 'PUT', body: blob, headers: { 'Content-Type': 'image/jpeg' } });
    if (!r.ok) throw new ApiError(r.status, 'upload failed');
    return (await r.json()) as { object_key: string; sha256: string };
  },
  register: (sid: string, view: string, up: { object_key: string; sha256: string }) =>
    api<{ quality_pass: boolean; checks: Record<string, boolean> }>(`/sessions/${sid}/images`, {
      method: 'POST', json: { view, ...up },
    }),
  submit: (sid: string) => api(`/sessions/${sid}/submit`, { method: 'POST' }),
  result: (sid: string) => api<Result>(`/sessions/${sid}/result`),
  list: () => api<{ session_id: string; status: string; created_at: string; route: string | null }[]>('/sessions'),
  summary: (sid: string, share: boolean) =>
    api<{ summary_id: string; pdf_url: string; share_url: string | null; shared_with: string; expires_at: string | null }>(
      `/sessions/${sid}/summary`, { method: 'POST', json: { share_with_iconic: share } }),
};

// ----- Staff, dermatologist and admin -----------------------------------------

export type Role = 'patient' | 'clinic_staff' | 'dermatologist' | 'admin';
export type RouteCode = 'urgent_care' | 'dermatologist' | 'iconic_clinic' | 'self_care';
export type FollowUp = 'new' | 'contacted' | 'booked' | 'no_response' | 'closed';
export type Account = { id: string; email: string; role: Role; display_name: string | null };

export type CaseBrief = {
  summary_id: string; created_at: string; route: RouteCode | null; reviewed: boolean; follow_up_status: FollowUp;
  expires_at: string | null;
  patient: { initials: string; age_band: string; skin_type: string | null; self_fitzpatrick: number | null; pregnant_or_breastfeeding: boolean };
};
export type CaseDetail = CaseBrief & {
  data: any; staff_note: string | null; views: string[]; reviewed_at: string | null; reviewed_by: string | null;
};
export type DermReview = {
  id: string; summary_id: string; app_route: RouteCode; derm_route: RouteCode;
  concern_agreement: Record<string, boolean>; note: string | null; created_at: string;
};
export type StaffUser = { id: string; email: string; role: Exclude<Role, 'patient'>; display_name: string | null; disabled: boolean; created_at: string };

/** Home screen for each role. */
export const HOME: Record<Role, 'Home' | 'StaffInbox' | 'DermQueue' | 'AdminHome'> = {
  patient: 'Home', clinic_staff: 'StaffInbox', dermatologist: 'DermQueue', admin: 'AdminHome',
};

export const Account = {
  me: () => api<Account>('/auth/me'),
};

export const Clinic = {
  list: (q: { route?: string; reviewed?: boolean; follow_up?: string } = {}) => {
    const p = Object.entries(q).filter(([, v]) => v !== undefined).map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&');
    return api<CaseBrief[]>(`/clinic/summaries${p ? `?${p}` : ''}`);
  },
  get: (id: string) => api<CaseDetail>(`/clinic/summaries/${id}`),
  openQr: (token: string) => api<CaseDetail>(`/clinic/s/${encodeURIComponent(token)}`),
  update: (id: string, body: { reviewed?: boolean; staff_note?: string; follow_up_status?: FollowUp }) =>
    api<CaseDetail>(`/clinic/summaries/${id}`, { method: 'PATCH', json: body }),
  imagePath: (id: string, view: string) => `/api/v1/clinic/summaries/${id}/images/${view}`,
  pdfPath: (id: string) => `/api/v1/clinic/summaries/${id}/pdf`,
};

export const Derm = {
  queue: (includeReviewed = false) => api<(CaseBrief & { my_review: DermReview | null })[]>(`/derm/queue?include_reviewed=${includeReviewed}`),
  review: (id: string, body: { derm_route: RouteCode; concern_agreement: Record<string, boolean>; note?: string }) =>
    api<DermReview>(`/derm/summaries/${id}/review`, { method: 'POST', json: body }),
  rules: () => api<{
    triage_version: string; rule_set_version: string; signed_off: boolean;
    red_flags: { code: string; question: string; route: string }[];
    conflicts: { family_a: string; family_b: string; scope: string; resolution: string; rationale: string }[];
    contraindications: { condition: string; family: string | null; ingredient: string | null; action: string }[];
    signoffs: { triage_version: string; rule_set_version: string; signed_by: string | null; note: string | null; signed_at: string }[];
  }>('/derm/rules'),
  signoff: (note: string) => api('/derm/rules/signoff', { method: 'POST', json: { note: note || undefined } }),
  stats: () => api<{
    reviews: number; route_agreement: number | null; missed_referrals: number; missed_referral_cases: string[];
    over_referrals: number; referral_sensitivity: number | null;
    concern_agreement: Record<string, { agree: number; of: number; rate: number }>;
    confusion: { app_route: RouteCode; derm_route: RouteCode; n: number }[];
  }>('/derm/stats'),
};

export const Admin = {
  dashboard: () => api<{
    users: Record<Role, number>; disabled_users: number; sessions: number; sessions_by_status: Record<string, number>;
    routes: Record<string, number>; shared_summaries: number; unreviewed_summaries: number;
    products_listed: number; products_unlisted: number; rule_set_version: string; triage_version: string;
    rules_signed_off: boolean; active_model: string | null; derm_reviews: number;
  }>('/admin/dashboard'),
  users: () => api<StaffUser[]>('/admin/users'),
  createUser: (body: { email: string; role: StaffUser['role']; display_name: string; password: string }) =>
    api<StaffUser>('/admin/users', { method: 'POST', json: body }),
  updateUser: (id: string, body: { role?: StaffUser['role']; display_name?: string; disabled?: boolean; password?: string }) =>
    api<StaffUser>(`/admin/users/${id}`, { method: 'PATCH', json: body }),
  products: () => api<(ProductCard & { is_listed: boolean; verified_on: string | null })[]>('/admin/products'),
  verifyProduct: (id: string, body: { notification_no: string; evidence_uri: string; valid_until?: string }) =>
    api(`/admin/products/${id}/verify`, { method: 'POST', json: body }),
  delistProduct: (id: string) => api(`/admin/products/${id}/delist`, { method: 'POST' }),
  rules: () => api<{
    rule_set_version: string;
    conflicts: { id: string; family_a: string; family_b: string; scope: string; resolution: string; rationale: string }[];
    contraindications: { condition: string; family: string | null; ingredient: string | null; action: string }[];
  }>('/admin/rules'),
  addConflict: (body: { family_a: string; family_b: string; scope: string; resolution: string; rationale: string }) =>
    api<{ rule_set_version: string }>('/admin/rules/conflicts', { method: 'POST', json: body }),
  models: () => api<{ id: string; architecture: string; artifact_sha256: string; eval_report_uri: string; is_active: boolean; released_at: string | null; can_activate: boolean }[]>('/admin/models'),
  activateModel: (id: string) => api(`/admin/models/${id}/activate`, { method: 'POST' }),
  runJob: (job: 'delist-stale' | 'purge-images') => api<Record<string, unknown>>(`/admin/jobs/${job}`, { method: 'POST' }),
  audit: (q: { action?: string; entity?: string } = {}) => {
    const p = Object.entries(q).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&');
    return api<{ id: number; at: string; actor: { name: string; role: Role | null }; action: string; entity: string; entity_id: string; detail: any }[]>(`/admin/audit${p ? `?${p}` : ''}`);
  },
};
