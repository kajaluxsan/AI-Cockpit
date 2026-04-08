import axios from "axios";
import type {
  ActivityItem,
  AppSettings,
  CallLog,
  Candidate,
  DashboardStats,
  EmailLog,
  Job,
  Match,
  Message,
  ProtocolEntry,
  ChatMessage,
  MatchingJob,
  MatchingCandidate,
} from "@/types";

const BASE_URL =
  (import.meta as any).env?.VITE_API_URL || "http://localhost:8000";

export const http = axios.create({
  baseURL: BASE_URL,
  timeout: 60_000,
});

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------
export const dashboard = {
  stats: () => http.get<DashboardStats>("/api/dashboard/stats").then((r) => r.data),
  activity: () =>
    http.get<ActivityItem[]>("/api/dashboard/activity").then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Candidates (CRM profiles)
// ---------------------------------------------------------------------------
export const candidates = {
  list: (params?: {
    status?: string;
    q?: string;
    limit?: number;
    offset?: number;
    sort?: "recent" | "name";
  }) =>
    http
      .get<Candidate[]>("/api/candidates/", { params })
      .then((r) => r.data),

  get: (id: number) =>
    http.get<Candidate>(`/api/candidates/${id}`).then((r) => r.data),

  update: (id: number, body: Partial<Candidate>) =>
    http.patch<Candidate>(`/api/candidates/${id}`, body).then((r) => r.data),

  protocol: (id: number) =>
    http
      .get<ProtocolEntry[]>(`/api/candidates/${id}/protocol`)
      .then((r) => r.data),

  matchingJobs: (id: number) =>
    http
      .get<MatchingJob[]>(`/api/candidates/${id}/matching-jobs`)
      .then((r) => r.data),

  cvUrl: (id: number) => `${BASE_URL}/api/candidates/${id}/cv`,
  photoUrl: (id: number) => `${BASE_URL}/api/candidates/${id}/photo`,

  /**
   * Resolve a relative photo path returned by the API into an absolute URL
   * the browser can render, or `null` when the candidate has no photo.
   */
  resolvePhoto: (relativeOrAbsolute?: string | null): string | null => {
    if (!relativeOrAbsolute) return null;
    if (/^https?:\/\//i.test(relativeOrAbsolute)) return relativeOrAbsolute;
    return `${BASE_URL}${relativeOrAbsolute}`;
  },

  uploadCv: (file: File, email?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    if (email) fd.append("email", email);
    return http
      .post<Candidate>("/api/candidates/upload-cv", fd)
      .then((r) => r.data);
  },

  uploadPhoto: (id: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return http
      .post<Candidate>(`/api/candidates/${id}/photo`, fd)
      .then((r) => r.data);
  },

  reextractPhoto: (id: number) =>
    http
      .post<Candidate>(`/api/candidates/${id}/extract-photo`)
      .then((r) => r.data),

  saveNotes: (id: number, notes: string) =>
    http.post<Candidate>(`/api/candidates/${id}/notes`, { notes }).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------
export const jobs = {
  list: (params?: { status?: string; q?: string; limit?: number }) =>
    http.get<Job[]>("/api/jobs/", { params }).then((r) => r.data),
  get: (id: number) => http.get<Job>(`/api/jobs/${id}`).then((r) => r.data),
  create: (body: Partial<Job>) =>
    http.post<Job>("/api/jobs/", body).then((r) => r.data),
  matchingCandidates: (id: number) =>
    http
      .get<MatchingCandidate[]>(`/api/jobs/${id}/candidates`)
      .then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Matches
// ---------------------------------------------------------------------------
export const matches = {
  list: (params?: {
    candidate_id?: number;
    job_id?: number;
    status?: string;
  }) => http.get<Match[]>("/api/matches/", { params }).then((r) => r.data),
  update: (id: number, body: Partial<Match>) =>
    http.patch<Match>(`/api/matches/${id}`, body).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Calls
// ---------------------------------------------------------------------------
export const calls = {
  list: (params?: { candidate_id?: number; status?: string }) =>
    http.get<CallLog[]>("/api/calls/", { params }).then((r) => r.data),
  initiate: (body: { candidate_id: number; to_number?: string }) =>
    http.post<CallLog>("/api/calls/initiate", body).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Emails (raw log)
// ---------------------------------------------------------------------------
export const emails = {
  list: (params?: { candidate_id?: number }) =>
    http.get<EmailLog[]>("/api/emails/", { params }).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Unified messages (new messages tab)
// ---------------------------------------------------------------------------
export const messages = {
  list: (params?: { only_unanswered?: boolean; limit?: number }) =>
    http.get<Message[]>("/api/messages/", { params }).then((r) => r.data),
  markRead: (id: number, answered: boolean = true) =>
    http
      .post(`/api/messages/${id}/read`, { answered })
      .then((r) => r.data),
};

// ---------------------------------------------------------------------------
// AI chat
// ---------------------------------------------------------------------------
export const chat = {
  history: (candidateId: number) =>
    http.get<ChatMessage[]>(`/api/chat/${candidateId}`).then((r) => r.data),
  send: (candidateId: number, content: string, autoExec: boolean = true) =>
    http
      .post<ChatMessage[]>(`/api/chat/${candidateId}`, {
        content,
        auto_execute_tools: autoExec,
      })
      .then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------
export const settings = {
  get: () => http.get<AppSettings>("/api/settings/").then((r) => r.data),
};

export type RuntimeConfig = {
  crm_required_fields: string[];
};

export const settingsApi = {
  get: () => http.get<AppSettings>("/api/settings/").then((r) => r.data),
  testEmail: (to: string) =>
    http
      .post<{ success: boolean }>(
        `/api/settings/test/email?to=${encodeURIComponent(to)}`
      )
      .then((r) => r.data),
  testTwilio: () =>
    http
      .post<Record<string, unknown>>("/api/settings/test/twilio")
      .then((r) => r.data),
  getRuntime: () =>
    http.get<RuntimeConfig>("/api/settings/runtime").then((r) => r.data),
  updateRuntime: (patch: Partial<RuntimeConfig>) =>
    http.put<RuntimeConfig>("/api/settings/runtime", patch).then((r) => r.data),
};
