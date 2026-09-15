"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import EventCanvas, { EventPoint } from "./EventCanvas";
import BaselineCanvas from "./BaselineCanvas";
import { streamUrl, StreamMessage, ControlComparisonSide } from "@/lib/api";

type RunStatus = "idle" | "connecting" | "running" | "done" | "error";

interface ScenarioForm {
  vibration_freq_hz: number;
  vibration_amp_px: number;
  noise_rate_hz_per_px: number;
  seed: number;
}

const DEFAULT_FORM: ScenarioForm = {
  vibration_freq_hz: 17.3,
  vibration_amp_px: 3.0,
  noise_rate_hz_per_px: 5.0,
  seed: 812,
};

export default function LiveDemo() {
  const [form, setForm] = useState<ScenarioForm>(DEFAULT_FORM);
  const [status, setStatus] = useState<RunStatus>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [eventPoints, setEventPoints] = useState<EventPoint[]>([]);
  const [baselinePixels, setBaselinePixels] = useState<number[] | null>(null);
  const [baselineDims, setBaselineDims] = useState({ width: 0, height: 0 });
  const [psd, setPsd] = useState<{ frequency_hz: number; psd_mag: number }[]>([]);
  const [dominantFreq, setDominantFreq] = useState<number | null>(null);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [comparison, setComparison] = useState<{
    baseline: ControlComparisonSide;
    disturbance_armed: ControlComparisonSide;
  } | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pendingCanvasRef = useRef<{
    points?: EventPoint[];
    pixels?: number[];
    dims?: { width: number; height: number };
  }>({});
  const animationFrameRef = useRef<number | null>(null);

  const flushCanvas = useCallback(() => {
    const pending = pendingCanvasRef.current;
    if (pending.points) setEventPoints(pending.points);
    if (pending.pixels && pending.dims) {
      setBaselinePixels(pending.pixels);
      setBaselineDims(pending.dims);
    }
    pendingCanvasRef.current = {};
    animationFrameRef.current = null;
  }, []);

  const queueCanvas = useCallback((update: typeof pendingCanvasRef.current) => {
    Object.assign(pendingCanvasRef.current, update);
    if (animationFrameRef.current === null) {
      animationFrameRef.current = requestAnimationFrame(flushCanvas);
    }
  }, [flushCanvas]);

  useEffect(() => () => {
    wsRef.current?.close();
    if (animationFrameRef.current !== null) cancelAnimationFrame(animationFrameRef.current);
  }, []);

  const runDemo = useCallback(() => {
    wsRef.current?.close();
    setStatus("connecting");
    setErrorMsg(null);
    setEventPoints([]);
    setBaselinePixels(null);
    setPsd([]);
    setDominantFreq(null);
    setConfidence(null);
    setComparison(null);
    pendingCanvasRef.current = {};
    if (animationFrameRef.current !== null) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    let ws: WebSocket;
    try {
      ws = new WebSocket(streamUrl());
    } catch {
      setStatus("error");
      setErrorMsg("Could not open a connection to the backend.");
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("running");
      ws.send(
        JSON.stringify({
          vibration_freq_hz: form.vibration_freq_hz,
          vibration_amp_px: form.vibration_amp_px,
          noise_rate_hz_per_px: form.noise_rate_hz_per_px,
          seed: form.seed,
        })
      );
    };

    ws.onmessage = (evt) => {
      const msg: StreamMessage = JSON.parse(evt.data);
      if (msg.type === "events") {
        queueCanvas({ points: msg.points });
      } else if (msg.type === "baseline_frame") {
        queueCanvas({ pixels: msg.pixels, dims: { width: msg.width, height: msg.height } });
      } else if (msg.type === "disturbance") {
        setDominantFreq(msg.dominant_frequency_hz);
        setConfidence(msg.confidence);
        setPsd(
          msg.psd.frequency_hz.map((f, i) => ({
            frequency_hz: f,
            psd_mag: msg.psd.psd_mag[i],
          }))
        );
      } else if (msg.type === "done") {
        setComparison(msg.control_comparison);
        setStatus("done");
      }
    };

    ws.onerror = () => {
      setStatus("error");
      setErrorMsg("Connection to the backend failed. Is the API running?");
    };
  }, [form, queueCanvas]);

  const baselineCaption = baselinePixels ? describeBaselineFrame(baselinePixels) : undefined;

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="text-2xl font-medium mb-2">Live demo</h1>
      <p className="text-sm text-text-dim max-w-2xl mb-8">
        Runs the full pipeline — scene, event stream, discriminator, disturbance estimate,
        control-loop comparison — on the backend for the scenario below, then replays it
        here paced to the scenario&apos;s own clock. This is a computed simulation, not a
        physical sensor feed.
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8 border border-panel-border bg-panel p-4 sm:p-5 shadow-[0_18px_60px_rgba(0,0,0,0.16)]">
        <Field
          label="Vibration freq (Hz)"
          value={form.vibration_freq_hz}
          onChange={(v) => setForm((f) => ({ ...f, vibration_freq_hz: v }))}
          min={5}
          max={30}
          step={0.1}
        />
        <Field
          label="Vibration amp (px)"
          value={form.vibration_amp_px}
          onChange={(v) => setForm((f) => ({ ...f, vibration_amp_px: v }))}
          min={0.5}
          max={6}
          step={0.1}
        />
        <Field
          label="Sensor noise (Hz/px)"
          value={form.noise_rate_hz_per_px}
          onChange={(v) => setForm((f) => ({ ...f, noise_rate_hz_per_px: v }))}
          min={0}
          max={7}
          step={0.5}
        />
        <Field
          label="Seed"
          value={form.seed}
          onChange={(v) => setForm((f) => ({ ...f, seed: Math.round(v) }))}
          min={0}
          max={9999}
          step={1}
        />
        <div className="col-span-2 md:col-span-4 flex flex-wrap items-center gap-3 pt-2 border-t border-panel-border/70 mt-1">
          <button
            onClick={runDemo}
            disabled={status === "connecting" || status === "running"}
            className="rounded-sm border border-accent bg-accent px-5 py-2.5 text-sm font-semibold text-[#150a05] shadow-[0_0_22px_rgba(255,106,61,0.18)] transition hover:brightness-110 hover:shadow-[0_0_28px_rgba(255,106,61,0.28)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {status === "running" || status === "connecting" ? "Running…" : "Run scenario"}
          </button>
          <StatusBadge status={status} />
          {errorMsg && <span className="text-xs text-bad">{errorMsg}</span>}
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6 mb-10">
        <EventCanvas
          points={eventPoints}
          frameW={128}
          frameH={128}
          label={`Event cloud (${eventPoints.length} events this window)`}
        />
        <BaselineCanvas
          pixels={baselinePixels}
          width={baselineDims.width}
          height={baselineDims.height}
          label="Conventional frame-camera baseline (30fps)"
          caption={baselineCaption}
        />
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="border border-panel-border bg-panel p-5">
          <h2 className="text-sm font-mono text-text-dim mb-4">
            Disturbance PSD{dominantFreq !== null && confidence !== null ? "" : " — awaiting estimate"}
          </h2>
          {psd.length > 0 ? (
            <>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={psd}>
                    <CartesianGrid stroke="#212a3b" />
                    <XAxis
                      dataKey="frequency_hz"
                      stroke="#8794a8"
                      tick={{ fontSize: 11 }}
                      tickFormatter={formatFrequencyTick}
                      label={{ value: "Hz", position: "insideBottomRight", fill: "#8794a8", fontSize: 11 }}
                    />
                    <YAxis stroke="#8794a8" tick={{ fontSize: 11 }} />
                    <Tooltip
                      contentStyle={{ background: "#10151f", border: "1px solid #212a3b", fontSize: 12 }}
                    />
                    <Line type="monotone" dataKey="psd_mag" stroke="#4fa6ff" dot={false} strokeWidth={1.5} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-3 text-xs font-mono text-text-dim">
                dominant: {dominantFreq?.toFixed(1)} Hz · confidence: {confidence?.toFixed(2)}
              </p>
            </>
          ) : (
            <div className="h-48 flex items-center justify-center text-xs text-text-dim">
              Estimate arrives once the scenario finishes streaming.
            </div>
          )}
        </div>

        <div className="border border-panel-border bg-panel p-5">
          <h2 className="text-sm font-mono text-text-dim mb-4">
            Settle-time comparison{comparison ? "" : " — awaiting result"}
          </h2>
          {comparison ? (
            <div>
              <ComparisonHighlight comparison={comparison} />
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                <ComparisonColumn title="Fixed-gain baseline" side={comparison.baseline} />
                <ComparisonColumn
                  title="Disturbance-armed"
                  side={comparison.disturbance_armed}
                  highlight
                />
              </div>
            </div>
          ) : (
            <div className="h-48 flex items-center justify-center text-xs text-text-dim">
              Result arrives once the scenario finishes streaming.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  min,
  max,
  step,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1.5">
      <span className="text-xs text-text-dim">{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full rounded-sm border border-panel-border bg-bg px-3 py-2 text-sm font-mono text-text shadow-inner shadow-black/20 transition placeholder:text-text-dim/50 hover:border-text-dim focus:border-accent-2 focus:outline-none focus:ring-2 focus:ring-accent-2/20"
      />
    </label>
  );
}

function StatusBadge({ status }: { status: RunStatus }) {
  const map: Record<RunStatus, { label: string; color: string }> = {
    idle: { label: "idle", color: "text-text-dim" },
    connecting: { label: "connecting…", color: "text-accent-2" },
    running: { label: "streaming…", color: "text-accent-2" },
    done: { label: "complete", color: "text-good" },
    error: { label: "error", color: "text-bad" },
  };
  const { label, color } = map[status];
  return <span className={`text-xs font-mono ${color}`}>{label}</span>;
}

function ComparisonColumn({
  title,
  side,
  highlight,
}: {
  title: string;
  side: ControlComparisonSide;
  highlight?: boolean;
}) {
  return (
    <div className={highlight ? "border-l-2 border-accent-2 pl-3" : "pl-3 border-l-2 border-transparent"}>
      <p className="text-xs text-text-dim mb-2">{title}</p>
      <dl className="space-y-1.5 font-mono text-xs">
        <Row label="RMS error" value={`${side.rms_error_px.toFixed(2)} px`} />
        <Row label="P95 error" value={`${side.p95_error_px.toFixed(2)} px`} />
        <Row
          label="Settle time"
          value={side.settle_time_s !== null ? `${side.settle_time_s.toFixed(2)} s` : "not reached"}
        />
      </dl>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-text-dim">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function formatFrequencyTick(value: number | string) {
  const frequency = Number(value);
  return Number.isFinite(frequency) ? frequency.toFixed(0) : "";
}

function describeBaselineFrame(pixels: number[]) {
  const sorted = [...pixels].sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length * 0.5)] ?? 0;
  const p99 = sorted[Math.floor(sorted.length * 0.99)] ?? median;
  const contrast = Math.max(0, p99 - median);
  if (contrast < 18) {
    return `This frame's 99th-percentile signal is only ${contrast} grayscale levels above its median background: the beacon is barely distinguishable at this vibration level.`;
  }
  if (contrast < 45) {
    return `This frame's upper signal is only ${contrast} grayscale levels above its median background: the beacon is faint and spatially spread under this scenario.`;
  }
  return `This frame has ${contrast} grayscale levels of upper-signal contrast, but the beacon is exposure-spread rather than the compact event cluster shown alongside it.`;
}

function ComparisonHighlight({
  comparison,
}: {
  comparison: { baseline: ControlComparisonSide; disturbance_armed: ControlComparisonSide };
}) {
  const rmsImprovement = percentImprovement(
    comparison.baseline.rms_error_px,
    comparison.disturbance_armed.rms_error_px
  );
  const settleImprovement =
    comparison.baseline.settle_time_s !== null && comparison.disturbance_armed.settle_time_s !== null
      ? percentImprovement(comparison.baseline.settle_time_s, comparison.disturbance_armed.settle_time_s)
      : null;
  const maxRms = Math.max(comparison.baseline.rms_error_px, comparison.disturbance_armed.rms_error_px, 0.01);

  return (
    <div className="mb-5 border-b border-panel-border pb-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-[0.16em] text-text-dim">Disturbance-armed outcome</p>
          <p className="mt-1 text-3xl font-medium tracking-tight text-accent-2">
            {settleImprovement !== null ? `${settleImprovement.toFixed(0)}% faster` : "Settled first"}
          </p>
        </div>
        <p className="text-xs font-mono text-text-dim">{rmsImprovement.toFixed(0)}% lower RMS error</p>
      </div>
      <div className="mt-4 space-y-2.5">
        <MetricBar label="Fixed gain" value={comparison.baseline.rms_error_px} max={maxRms} color="#ff6a3d" />
        <MetricBar label="Armed" value={comparison.disturbance_armed.rms_error_px} max={maxRms} color="#4fa6ff" />
      </div>
    </div>
  );
}

function MetricBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  return (
    <div className="grid grid-cols-[4.5rem_1fr_auto] items-center gap-2 text-[11px] font-mono">
      <span className="text-text-dim">{label}</span>
      <div className="h-1.5 overflow-hidden bg-bg">
        <div className="h-full" style={{ width: `${(value / max) * 100}%`, background: color }} />
      </div>
      <span>{value.toFixed(2)}px</span>
    </div>
  );
}

function percentImprovement(baseline: number, armed: number) {
  return baseline > 0 ? ((baseline - armed) / baseline) * 100 : 0;
}
