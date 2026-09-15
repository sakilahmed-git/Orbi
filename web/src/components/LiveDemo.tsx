"use client";

import { useCallback, useRef, useState } from "react";
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
        setEventPoints(msg.points);
      } else if (msg.type === "baseline_frame") {
        setBaselinePixels(msg.pixels);
        setBaselineDims({ width: msg.width, height: msg.height });
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
  }, [form]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="text-2xl font-medium mb-2">Live demo</h1>
      <p className="text-sm text-text-dim max-w-2xl mb-8">
        Runs the full pipeline — scene, event stream, discriminator, disturbance estimate,
        control-loop comparison — on the backend for the scenario below, then replays it
        here paced to the scenario&apos;s own clock. This is a computed simulation, not a
        physical sensor feed.
      </p>

      <div className="grid md:grid-cols-4 gap-4 mb-8 border border-panel-border bg-panel p-5">
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
        <div className="md:col-span-4 flex items-center gap-4 pt-2">
          <button
            onClick={runDemo}
            disabled={status === "connecting" || status === "running"}
            className="px-5 py-2 bg-accent text-[#150a05] text-sm font-medium disabled:opacity-50 hover:brightness-110 transition"
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
            <div className="grid grid-cols-2 gap-4 text-sm">
              <ComparisonColumn title="Fixed-gain baseline" side={comparison.baseline} />
              <ComparisonColumn
                title="Disturbance-armed"
                side={comparison.disturbance_armed}
                highlight
              />
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
    <label className="flex flex-col gap-1.5">
      <span className="text-xs text-text-dim">{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="bg-bg border border-panel-border px-2.5 py-1.5 text-sm font-mono focus-visible:outline-2 focus-visible:outline-accent-2"
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
    <div className={highlight ? "border-l-2 border-accent pl-3" : "pl-3 border-l-2 border-transparent"}>
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
