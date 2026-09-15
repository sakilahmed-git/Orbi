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
