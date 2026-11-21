// DermaLens API client for the web app (all roles).
export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';

const KEY = 'dermalens.web.tokens';
type Tokens = { access_token: string; refresh_token: string; role: string };

function load(): Tokens | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Tokens) : null;
  } catch {
    return null;
  }
}
let tokens: Tokens | null = load();

function save(t: Tokens | null) {
  tokens = t;
  try {
    // sessionStorage: signed out when the browser tab closes.
    if (t) sessionStorage.setItem(KEY, JSON.stringify(t));
    else sessionStorage.removeItem(KEY);
  } catch {
    /* storage blocked: keep the in-memory copy */
  }
}

export const hasSession = () => tokens !== null;
export function signOut() {
  save(null);
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(describe(detail) ?? `Request failed (${status})`);
  }
}

function describe(d: unknown): string | null {
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x: any) => `${(x.loc ?? []).slice(1).join('.')}: ${x.msg}`).join('; ');
  if (d && typeof d === 'object') {
    const o = d as Record<string, unknown>;
    const extra = Object.entries(o).filter(([k]) => k !== 'detail').map(([k, v]) => `${k.replace(/_/g, ' ')}: ${Array.isArray(v) ? v.join(', ') : v}`);
    return [o.detail, ...extra].filter(Boolean).join(' · ');
  }
  return null;
}

let onExpired: () => void = () => {};
export const setOnExpired = (f: () => void) => { onExpired = f; };

async function refresh(): Promise<boolean> {
  if (!tokens) return false;
  const r = await fetch(`${API_URL}/api/v1/auth/refresh`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: tokens.refresh_token }),
  });
  if (!r.ok) { save(null); return false; }
  save(await r.json());
  return true;
}

export async function api<T = any>(path: string, init: RequestInit & { json?: unknown } = {}, retry = true): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (tokens) headers.Authorization = `Bearer ${tokens.access_token}`;
  let body = init.body;
  if (init.json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(init.json);
  }
  const r = await fetch(`${API_URL}/api/v1${path}`, { ...init, headers, body });
  if (r.status === 401 && retry && tokens) {
    if (await refresh()) return api<T>(path, init, false);
    onExpired();
  }
  if (!r.ok) {
    let detail: unknown = r.statusText;
    try { detail = (await r.json()).detail; } catch { /* not JSON */ }
    throw new ApiError(r.status, detail);
  }
  return (r.headers.get('content-type') ?? '').includes('json') ? r.json() : (r.text() as Promise<T>);
}

// ----- Types --------------------------------------------------------------------

export type StaffRole = 'clinic_staff' | 'dermatologist' | 'admin';
export type Role = 'patient' | StaffRole;
export type Me = { id: string; email: string; role: Role; display_name: string | null; email_verified: boolean };
export type Notifications = {
  role: Role; email_verified: boolean; inbox_new?: number; inbox_urgent?: number; inbox_unreviewed?: number;
  queue_todo?: number; queue_urgent?: number; catalog_due?: number; locked_accounts?: number; email_failures?: number;
  checks_in_progress?: number;
};
export type Compare = {
  previous_session_id: string; previous_at: string; days_between: number; route_before: string | null; route_now: string | null;
  concerns: { code: string; name: string; trend: 'better' | 'same' | 'worse' | 'unknown'; before: string | null; now: string | null }[];
  note: string;
};
export type StaffUser = { id: string; email: string; role: StaffRole; display_name: string | null; disabled: boolean; locked?: boolean; created_at: string };
export type Dashboard = {
  users: Record<Role, number>; disabled_users: number; sessions: number; sessions_by_status: Record<string, number>;
  routes: Record<string, number>; shared_summaries: number; unreviewed_summaries: number;
  products_listed: number; products_unlisted: number; rule_set_version: string; triage_version: string;
  rules_signed_off: boolean; active_model: string | null; derm_reviews: number;
};
export type Product = {
  id: string; brand: string; name: string; category: string; spf: number | null; pa_rating: string | null;
  price_php: number | null; stocked_by_iconic: boolean; fda_notification_no: string | null; ingredients: string[];
  is_listed: boolean; verified_on: string | null;
};
export type ProductIn = {
  id: string; brand: string; name: string; category: string; suitable_skin_types: string[]; inci: string[];
  spf?: number | null; pa_rating?: string | null; price_php?: number | null; stocked_by_iconic: boolean;
};
export type Conflict = { id: string; family_a: string; family_b: string; scope: string; resolution: string; rationale: string };
export type Rules = {
  rule_set_version: string; families: { code: string; name: string }[]; conflicts: Conflict[];
  contraindications: { condition: string; family: string | null; ingredient: string | null; action: string }[];
};
export type ModelVersion = { id: string; architecture: string; artifact_sha256: string; eval_report_uri: string; is_active: boolean; released_at: string | null; can_activate: boolean };
export type AuditRow = { id: number; at: string; actor: { name: string; role: Role | null }; action: string; entity: string; entity_id: string; detail: Record<string, unknown> | null };

// ----- Endpoints ----------------------------------------------------------------

const qs = (q: Record<string, unknown>) => {
  const p = Object.entries(q).filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&');
  return p ? `?${p}` : '';
};

export const Auth = {
  async login(email: string, password: string): Promise<Me> {
    save(await api<Tokens>('/auth/login', { method: 'POST', json: { email, password } }, false));
    return api<Me>('/auth/me');
  },
  async register(email: string, password: string): Promise<Me> {
    save(await api<Tokens>('/auth/register', { method: 'POST', json: { email, password, accepted_boundary: true } }, false));
    return api<Me>('/auth/me');
  },
  me: () => api<Me>('/auth/me'),
  forgot: (email: string) => api<{ message: string }>('/auth/forgot-password', { method: 'POST', json: { email } }, false),
  reset: (token: string, password: string) => api('/auth/reset-password', { method: 'POST', json: { token, password } }, false),
  verify: (token: string) => api<{ email: string }>('/auth/verify-email', { method: 'POST', json: { token } }, false),
  resendVerification: () => api('/auth/resend-verification', { method: 'POST' }),
  async changePassword(current_password: string, new_password: string) {
    save(await api<Tokens>('/auth/change-password', { method: 'POST', json: { current_password, new_password } }));
  },
  notifications: () => api<Notifications>('/notifications'),
};

/** Fetches a protected file (photo, PDF) as an object URL. */
export async function blobUrl(path: string): Promise<string> {
  const headers: Record<string, string> = tokens ? { Authorization: `Bearer ${tokens.access_token}` } : {};
  let r = await fetch(`${API_URL}${path}`, { headers });
  if (r.status === 401 && (await refresh())) r = await fetch(`${API_URL}${path}`, { headers: { Authorization: `Bearer ${tokens!.access_token}` } });
  if (!r.ok) throw new ApiError(r.status, 'could not load the file');
  return URL.createObjectURL(await r.blob());
}

export async function download(path: string, filename: string) {
  const url = await blobUrl(path);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

// ----- Patient ------------------------------------------------------------------

export type RouteCode = 'urgent_care' | 'dermatologist' | 'iconic_clinic' | 'self_care';
export type Profile = {
  full_name: string; birth_year: number | null; sex_at_birth: string | null; self_fitzpatrick: number | null;
  skin_type: string | null; is_pregnant_or_breastfeeding: boolean;
};
export type ConcernRef = { code: string; name: string; model_label: boolean };
export type RedFlagQ = { code: string; question: string; urgent: boolean };
export type AllergenHit = { kind: 'family' | 'ingredient'; family_code?: string; ingredient_id?: string; label: string };
export type ProductCard = Omit<Product, 'is_listed' | 'verified_on'>;
export type RoutineStep = { step: number; slot: string; frequency: string; why: string; patch_test: boolean; product: ProductCard };
export type Finding = { code: string; name: string; present: boolean; grade: string; grade_name: string; band: string; uncertain: boolean };
export type Result = {
  session_id: string; status: 'open' | 'uploaded' | 'processing' | 'needs_retake' | 'complete' | 'failed';
  created_at: string; boundary: string; message?: string; retake_views?: string[];
  images?: Record<string, { quality_pass: boolean; server_checks: Record<string, boolean> | null }>;
  route?: { code: RouteCode; title: string; body: string; tone: string; cta: string };
  reasons?: { code: string; text: string }[];
  findings?: Finding[];
  routine?: { status: string; am: RoutineStep[]; pm: RoutineStep[]; notes: string[]; basics_only: boolean } | null;
  versions?: Record<string, string | null>;
  compare?: Compare | null;
};
export type IntakeBody = {
  concerns: { code: string; self_severity: number; duration_weeks: number }[];
  red_flags: Record<string, boolean>;
  allergens: { ingredient_id?: string; family_code?: string; raw_text?: string }[];
  current_routine: { time_of_day: 'am' | 'pm' | 'both'; free_text_name?: string; product_id?: string; reaction_reported: boolean }[];
  lifestyle: { sleep_hours?: number; daily_sun_exposure_min?: number; sunscreen_use?: string; smoker?: boolean; stress_level?: number; water_glasses_per_day?: number };
  on_isotretinoin: boolean; current_rx_topicals: boolean;
};

export const Ref = {
  concerns: () => api<ConcernRef[]>('/reference/concerns'),
  redFlags: () => api<RedFlagQ[]>('/reference/red-flags'),
  allergens: (q: string) => api<AllergenHit[]>(`/allergens/search${qs({ q })}`),
  products: (q: string) => api<ProductCard[]>(`/products/search${qs({ q })}`),
};

export const Patient = {
  profile: () => api<Profile | null>('/me/profile'),
  saveProfile: (p: Profile) => api<Profile>('/me/profile', { method: 'PUT', json: p }),
  consents: () => api<Record<string, boolean>>('/consents'),
  setConsent: (purpose: string, granted: boolean) => api<Record<string, boolean>>('/consents', { method: 'POST', json: { purpose, granted } }),
  exportData: () => api<unknown>('/me/export'),
  deleteAccount: () => api('/me', { method: 'DELETE' }),
  createIntake: (b: IntakeBody) => api<{ intake_id: string; urgent: boolean }>('/intakes', { method: 'POST', json: b }),
  openSession: (intake_id: string) => api<{ session_id: string; upload_urls: Record<string, string> }>('/sessions', {
    method: 'POST', json: { intake_id, app_version: 'web-0.1.0', device_model: 'web' },
  }),
  uploadUrls: (sid: string) => api<{ upload_urls: Record<string, string> }>(`/sessions/${sid}/upload-urls`, { method: 'POST' }),
  async upload(uploadPath: string, data: Blob) {
    const r = await fetch(`${API_URL}${uploadPath}`, { method: 'PUT', body: data, headers: { 'Content-Type': 'image/jpeg' } });
    if (!r.ok) {
      let d: unknown = 'upload failed';
      try { d = (await r.json()).detail; } catch { /* not JSON */ }
      throw new ApiError(r.status, d);
    }
    return (await r.json()) as { object_key: string; sha256: string };
  },
  registerImage: (sid: string, view: string, up: { object_key: string; sha256: string }) =>
    api<{ quality_pass: boolean; checks: Record<string, boolean> }>(`/sessions/${sid}/images`, { method: 'POST', json: { view, ...up } }),
  submit: (sid: string) => api(`/sessions/${sid}/submit`, { method: 'POST' }),
  result: (sid: string) => api<Result>(`/sessions/${sid}/result`),
  sessions: () => api<{ session_id: string; status: string; created_at: string; route: RouteCode | null }[]>('/sessions'),
  imagePath: (sid: string, view: string) => `/api/v1/sessions/${sid}/images/${view}`,
  summary: (sid: string, share: boolean) => api<{ summary_id: string; pdf_url: string; share_url: string | null; shared_with: string; expires_at: string | null }>(
    `/sessions/${sid}/summary`, { method: 'POST', json: { share_with_iconic: share } }),
};

// ----- Clinic staff and dermatologist -------------------------------------------

export type FollowUp = 'new' | 'contacted' | 'booked' | 'no_response' | 'closed';
export type CaseBrief = {
  summary_id: string; created_at: string; route: RouteCode | null; reviewed: boolean; follow_up_status: FollowUp; expires_at: string | null;
  patient: { initials: string; age_band: string; skin_type: string | null; self_fitzpatrick: number | null; pregnant_or_breastfeeding: boolean };
};
export type CaseDetail = CaseBrief & { data: any; staff_note: string | null; views: string[]; reviewed_at: string | null; reviewed_by: string | null };
export type DermReview = { id: string; summary_id: string; app_route: RouteCode; derm_route: RouteCode; concern_agreement: Record<string, boolean>; note: string | null; created_at: string };
export type DermRules = {
  triage_version: string; rule_set_version: string; signed_off: boolean;
  red_flags: { code: string; question: string; route: string }[];
  conflicts: Omit<Conflict, 'id'>[];
  contraindications: Rules['contraindications'];
  signoffs: { triage_version: string; rule_set_version: string; signed_by: string | null; note: string | null; signed_at: string }[];
};
export type DermStats = {
  reviews: number; route_agreement: number | null; missed_referrals: number; missed_referral_cases: string[];
  over_referrals: number; referral_sensitivity: number | null;
  concern_agreement: Record<string, { agree: number; of: number; rate: number }>;
  confusion: { app_route: RouteCode; derm_route: RouteCode; n: number }[];
};

export const Clinic = {
  list: (q: { route?: string; reviewed?: boolean; follow_up?: string } = {}) => api<CaseBrief[]>(`/clinic/summaries${qs(q)}`),
  get: (id: string) => api<CaseDetail>(`/clinic/summaries/${id}`),
  openQr: (token: string) => api<CaseDetail>(`/clinic/s/${encodeURIComponent(token)}`),
  update: (id: string, b: { reviewed?: boolean; staff_note?: string; follow_up_status?: FollowUp }) =>
    api<CaseDetail>(`/clinic/summaries/${id}`, { method: 'PATCH', json: b }),
  imagePath: (id: string, view: string) => `/api/v1/clinic/summaries/${id}/images/${view}`,
  pdfPath: (id: string) => `/api/v1/clinic/summaries/${id}/pdf`,
};

export const Derm = {
  queue: (includeReviewed = false) => api<(CaseBrief & { my_review: DermReview | null })[]>(`/derm/queue${qs({ include_reviewed: includeReviewed })}`),
  review: (id: string, b: { derm_route: RouteCode; concern_agreement: Record<string, boolean>; note?: string }) =>
    api<DermReview>(`/derm/summaries/${id}/review`, { method: 'POST', json: b }),
  rules: () => api<DermRules>('/derm/rules'),
  signoff: (note: string) => api('/derm/rules/signoff', { method: 'POST', json: { note: note || undefined } }),
  stats: () => api<DermStats>('/derm/stats'),
};

export const Admin = {
  dashboard: () => api<Dashboard>('/admin/dashboard'),
  users: () => api<StaffUser[]>('/admin/users'),
  createUser: (b: { email: string; role: StaffRole; display_name: string; password: string }) =>
    api<StaffUser>('/admin/users', { method: 'POST', json: b }),
  updateUser: (id: string, b: { role?: StaffRole; display_name?: string; disabled?: boolean; password?: string }) =>
    api<StaffUser>(`/admin/users/${id}`, { method: 'PATCH', json: b }),
  products: () => api<Product[]>('/admin/products'),
  createProduct: (b: ProductIn) => api('/admin/products', { method: 'POST', json: b }),
  verifyProduct: (id: string, b: { notification_no: string; evidence_uri: string; valid_until?: string }) =>
    api(`/admin/products/${id}/verify`, { method: 'POST', json: b }),
  delistProduct: (id: string) => api(`/admin/products/${id}/delist`, { method: 'POST' }),
  rules: () => api<Rules>('/admin/rules'),
  addConflict: (b: Omit<Conflict, 'id'>) => api<{ rule_set_version: string }>('/admin/rules/conflicts', { method: 'POST', json: b }),
  models: () => api<ModelVersion[]>('/admin/models'),
  activateModel: (id: string) => api(`/admin/models/${id}/activate`, { method: 'POST' }),
  delistStale: () => api<{ delisted: string[] }>('/admin/jobs/delist-stale', { method: 'POST' }),
  purgeImages: () => api<{ sessions_purged: number }>('/admin/jobs/purge-images', { method: 'POST' }),
  audit: (q: { action?: string; entity?: string; limit?: number; before_id?: number }) => api<AuditRow[]>(`/admin/audit${qs(q)}`),
};
