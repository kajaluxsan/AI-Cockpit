export type CandidateStatus =
  | "new"
  | "parsed"
  | "info_requested"
  | "matched"
  | "contacted"
  | "interview"
  | "placed"
  | "rejected";

export type CandidateSource = "email" | "linkedin" | "external_api" | "manual";

export interface Candidate {
  id: number;
  full_name: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  language: string | null;
  headline: string | null;
  summary: string | null;
  skills: string[] | null;
  experience_years: number | null;
  salary_expectation: number | null;
  salary_currency: string | null;
  availability: string | null;
  languages_spoken: string[] | null;
  source: CandidateSource;
  status: CandidateStatus;
  missing_fields: string[] | null;
  created_at: string;
  updated_at: string;
}

export type JobStatus = "open" | "paused" | "filled" | "closed";
export type JobSource = "email" | "linkedin" | "external_api" | "manual";

export interface Job {
  id: number;
  title: string;
  company: string | null;
  location: string | null;
  description: string | null;
  required_skills: string[] | null;
  nice_to_have_skills: string[] | null;
  min_experience_years: number | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  employment_type: string | null;
  source: JobSource;
  status: JobStatus;
  created_at: string;
  updated_at: string;
}

export type MatchStatus = "new" | "contacted" | "interview" | "placed" | "rejected";

export interface Match {
  id: number;
  candidate_id: number;
  job_id: number;
  score: number;
  score_breakdown: Record<string, unknown> | null;
  rationale: string | null;
  status: MatchStatus;
  created_at: string;
  updated_at: string;
}

export type CallStatus =
  | "initiated"
  | "ringing"
  | "in_progress"
  | "completed"
  | "no_answer"
  | "busy"
  | "failed"
  | "canceled";

export interface CallLog {
  id: number;
  candidate_id: number | null;
  match_id: number | null;
  twilio_call_sid: string | null;
  direction: "outbound" | "inbound";
  from_number: string | null;
  to_number: string | null;
  status: CallStatus;
  detected_language: string | null;
  duration_seconds: number | null;
  transcript: string | null;
  transcript_segments: Array<{ role: string; text: string }> | null;
  summary: string | null;
  interest_level: string | null;
  next_steps: string | null;
  recording_url: string | null;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
}

export interface EmailLog {
  id: number;
  candidate_id: number | null;
  direction: "inbound" | "outbound";
  kind: "application" | "followup_request" | "reply" | "notification" | "other";
  message_id: string | null;
  from_address: string | null;
  to_address: string | null;
  subject: string | null;
  body: string | null;
  attachments_count: number;
  answered: boolean;
  created_at: string;
}

export interface DashboardStats {
  new_candidates_today: number;
  open_jobs: number;
  matches_this_week: number;
  calls_today: number;
  completed_calls: number;
  placed_candidates: number;
}

export interface ActivityItem {
  type: string;
  timestamp: string;
  title: string;
  candidate_id?: number;
  job_id?: number;
  call_id?: number;
  source?: string;
}

export interface AppSettings {
  app: { name: string; env: string; agent_name: string; company_name: string };
  sources: { email: boolean; linkedin: boolean; external_api: boolean };
  matching: {
    threshold_percent: number;
    auto_call_enabled: boolean;
    auto_email_followup: boolean;
    missing_info_fields: string[];
  };
  email: Record<string, unknown>;
  twilio: { phone_number: string | null; configured: boolean };
  elevenlabs: { configured: boolean; model: string };
  deepgram: { configured: boolean; model: string; language_detect: boolean };
  anthropic: { configured: boolean; model: string };
  external_api: { base_url: string | null; auth_type: string };
}
