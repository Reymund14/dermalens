import type { NativeStackScreenProps } from '@react-navigation/native-stack';

export type Stack = {
  Welcome: undefined;
  Boundary: undefined;
  Auth: { mode: 'signup' | 'login' };
  Consent: { next: 'Profile' | 'Settings' };
  Profile: undefined;
  Home: undefined;
  Concerns: undefined;
  Health: undefined;
  Urgent: { flags: string[] };
  Allergies: undefined;
  CurrentRoutine: undefined;
  Lifestyle: undefined;
  CaptureGuide: undefined;
  Capture: { view: 'front' | 'left45' | 'right45'; retake?: boolean };
  Review: undefined;
  Processing: undefined;
  Results: { sessionId: string };
  Routine: { sessionId: string };
  Referral: { sessionId: string; kind: 'iconic' | 'dermatologist' };
  Summary: { sessionId: string };
  Settings: undefined;
  // Clinic staff
  StaffInbox: undefined;
  StaffCase: { summaryId?: string; qrToken?: string };
  // Dermatologist
  DermQueue: undefined;
  DermCase: { summaryId: string };
  DermRules: undefined;
  DermStats: undefined;
  // Admin
  AdminHome: undefined;
  AdminUsers: undefined;
  AdminCatalog: undefined;
  AdminRules: undefined;
  AdminModels: undefined;
  AdminAudit: undefined;
};

export type Props<K extends keyof Stack> = NativeStackScreenProps<Stack, K>;
