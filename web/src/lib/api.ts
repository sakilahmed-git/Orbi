export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface ScenarioRequest {
  duration_s?: number;
  fps?: number;
  blink_freq_hz?: number;
  vibration_freq_hz?: number;
  vibration_amp_px?: number;
  vibration_phase?: number;
  broadband_std_px?: number;
  turbulence_strength?: number;
  turbulence_correlation_time_s?: number;
  clutter_level?: number;
  noise_rate_hz_per_px?: number;
  frame_size?: [number, number];
  seed?: number;
  /** Selects fixed-gain conventional PAT/ATP vs the existing disturbance-informed controller. */
  scintilla_enabled?: boolean;
  range_km?: number;
  angular_offset_deg?: number;
  acquisition_cone_px?: number;
}

export interface DetectionPoint {
  t: number;
  x: number;
  y: number;
  confidence: number;
}

export interface ControlComparisonSide {
  rms_error_px: number;
  p95_error_px: number;
  settle_time_s: number | null;
  kp_track_used?: number;
}

export interface RunScenarioResponse {
  scenario: Required<ScenarioRequest>;
  events: { n_clean: number; n_noisy: number };
  detections: {
    n_windows: number;
    n_hits: number;
    hit_rate: number;
    points: DetectionPoint[];
  };
  disturbance: {
    dominant_frequency_hz: number | null;
    confidence: number;
    psd: { frequency_hz: number[]; psd_mag: number[] };
  };
  control_comparison: {
    start_offset_px: [number, number];
    baseline: ControlComparisonSide;
    disturbance_armed: ControlComparisonSide;
    trace: { t: number[]; baseline_err_px: number[]; armed_err_px: number[] };
    selected_control: { mode: "conventional_pat_atp" | "scintilla_predictive"; rms_error_px: number; p95_error_px: number; settle_time_s: number | null };
  };
}

export interface EnvelopeSweepResponse {
  vibration_amp_px: number[];
  clutter_level: number[];
  success_probability: number[][];
  fixed_turbulence_strength: number;
  fixed_noise_rate_hz_per_px: number;
}

export async function runScenario(
  body: ScenarioRequest
): Promise<RunScenarioResponse> {
  const res = await fetch(`${API_BASE}/run-scenario`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`run-scenario failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function fetchEnvelopeSweep(): Promise<EnvelopeSweepResponse> {
  const res = await fetch(`${API_BASE}/envelope-sweep`);
  if (!res.ok) {
    throw new Error(`envelope-sweep failed (${res.status})`);
  }
  return res.json();
}

export interface VerifiedResults {
  learned_mean_error_px: number;
  classical_mean_error_px: number;
  n_scenarios: number;
}

export async function fetchVerifiedResults(): Promise<VerifiedResults> {
  const res = await fetch(`${API_BASE}/verified-results`);
  if (!res.ok) throw new Error(`verified-results failed (${res.status})`);
  return res.json();
}

export interface ComparePath { label: string; rms_error_px: number; p95_error_px: number; trace: { t: number[]; error_px: number[] } }
export interface CompareResponse {
  scenario: Required<ScenarioRequest>;
  classical_frame_baseline: ComparePath;
  event_only_no_ai: ComparePath;
  scintilla: ComparePath;
  envelope_point: { vibration_amp_px: number; clutter_level: number };
  data_source: "synthetic";
  validation_label: string;
}

export async function compareScenario(body: ScenarioRequest): Promise<CompareResponse> {
  const res = await fetch(`${API_BASE}/compare`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) throw new Error(`compare failed (${res.status}): ${await res.text()}`);
  return res.json();
}

export function streamUrl(): string {
  const url = new URL(API_BASE);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/stream";
  return url.toString();
}

// Message shapes sent over WS /stream, in the exact order the server sends them.
export type StreamMessage =
  | { type: "events"; t: number; points: { x: number; y: number; polarity: number }[] }
  | { type: "detection"; t: number; x: number; y: number; confidence: number }
  | { type: "baseline_frame"; t: number; width: number; height: number; pixels: number[] }
  | { type: "disturbance"; t: number; dominant_frequency_hz: number | null; confidence: number; psd: { frequency_hz: number[]; psd_mag: number[] } }
  | {
      type: "done";
      control_comparison: {
        start_offset_px: [number, number];
        baseline: ControlComparisonSide;
        disturbance_armed: ControlComparisonSide;
      };
    };
