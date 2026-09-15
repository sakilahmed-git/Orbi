"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type MissionPhase = "READY" | "SEARCH" | "DETECT" | "IDENTIFY" | "LOCK" | "ACQUIRE" | "ALIGN" | "TRACK" | "CONNECTED" | "DISTURBANCE" | "CORRECTING" | "DISCONNECTING";
export type MissionConfig = { power: number; gain: number; ground: boolean; intelligence: boolean };
export type Vec3 = [number, number, number];
export type MissionSnapshot = {
  phase: MissionPhase; time: number; source: Vec3; target: Vec3; currentAxis: Vec3; desiredAxis: Vec3; distanceKm: number;
  pointingErrorDeg: number; signalDb: number; quality: number; dataRate: number; latency: number; jitter: number; confidence: number;
  disturbance: number; adaptive: boolean; learned: boolean; ghost: Vec3 | null; uptime: number; cameraOffset: [number, number]; beaconVisible: boolean;
  intelligence: boolean; controller: "conventional_pat_atp" | "scintilla_predictive";
};
type Engine = { t: number; phase: MissionPhase; phaseAt: number; pointing: Vec3; disturbance: number; adaptive: boolean; learned: boolean; connectedAt: number; ghost: Vec3 | null; last: number };

const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const len = (a: Vec3) => Math.hypot(...a);
const norm = (a: Vec3): Vec3 => { const l = len(a) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const mix = (a: Vec3, b: Vec3, k: number): Vec3 => norm([a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k]);

export function useMissionSimulation() {
  const config = useRef<MissionConfig>({ power: 250, gain: .8, ground: false, intelligence: true });
  const engine = useRef<Engine>({ t: 0, phase: "READY", phaseAt: 0, pointing: norm([1, .35, 0]), disturbance: 0, adaptive: false, learned: false, connectedAt: 0, ghost: null, last: performance.now() });
  const [snapshot, setSnapshot] = useState<MissionSnapshot>(() => makeSnapshot(engine.current, config.current));
  const displayAt = useRef(0);
  const raf = useRef<number | null>(null);
  const step = useCallback((now: number) => {
    const e = engine.current; const dt = Math.min(.05, Math.max(.001, (now - e.last) / 1000)); e.last = now; e.t += dt;
    const source = sourcePosition(e.t); const target = targetPosition(e.t, config.current.ground); const desired = norm(sub(target, source));
    const phaseAge = e.t - e.phaseAt; const disturbanceWave = e.disturbance * (Math.sin(e.t * 17.3) + .45 * Math.sin(e.t * 29.1 + .7));
    const conventionalScan = [Math.cos(e.t * 2.2) * .55, .2 + Math.sin(e.t * 1.6) * .4, Math.sin(e.t * 2.2) * .55] as Vec3;
    const scan = e.phase === "SEARCH" && !(config.current.intelligence && e.ghost) ? conventionalScan : desired;
    const gain = config.current.gain * (e.adaptive && config.current.intelligence ? 2.25 : 1); const disturbedDesired = norm([scan[0], scan[1] + disturbanceWave * .035, scan[2] + Math.cos(e.t * 23) * e.disturbance * .02]);
    e.pointing = mix(e.pointing, disturbedDesired, clamp(dt * gain * (e.phase === "SEARCH" ? .42 : 1.3)));
    const error = Math.acos(clamp(dot(e.pointing, desired), -1, 1)) * 180 / Math.PI;
    const distanceKm = len(sub(target, source)) * 130;
    const confidence = confidenceFor(e.phase, phaseAge, error, e.disturbance, e.learned && config.current.intelligence);
    const signalDb = -18 - 20 * Math.log10(Math.max(1, distanceKm) / 1000) + 10 * Math.log10(config.current.power / 250) - error * 4.2 - e.disturbance * 3.8;
    const quality = clamp((signalDb + 43) / 15) * 100;
    advance(e, phaseAge, confidence, error, signalDb, quality, config.current.intelligence);
    if (now - displayAt.current > 66) { displayAt.current = now; setSnapshot(makeSnapshot(e, config.current, { source, target, desired, error, distanceKm, confidence, signalDb, quality })); }
  }, []);
  useEffect(() => { const loop = (now: number) => { step(now); raf.current = requestAnimationFrame(loop); }; raf.current = requestAnimationFrame(loop); return () => { if (raf.current !== null) cancelAnimationFrame(raf.current); }; }, [step]);
  const establish = useCallback(() => { const e = engine.current; if (e.phase === "READY") { e.phase = "SEARCH"; e.phaseAt = e.t; e.adaptive = e.learned && config.current.intelligence; } }, []);
  const disconnect = useCallback(() => { const e = engine.current; if (["CONNECTED", "DISTURBANCE", "CORRECTING", "TRACK"].includes(e.phase)) { e.ghost = targetPosition(e.t, config.current.ground); e.phase = "DISCONNECTING"; e.phaseAt = e.t; } }, []);
  const inject = useCallback(() => { const e = engine.current; if (["CONNECTED", "TRACK"].includes(e.phase)) { e.disturbance = 1; e.phase = "DISTURBANCE"; e.phaseAt = e.t; } }, []);
  const apply = useCallback(() => { const e = engine.current; if (e.phase === "DISTURBANCE") { e.adaptive = config.current.intelligence; e.phase = "CORRECTING"; e.phaseAt = e.t; } }, []);
  const setConfig = useCallback((patch: Partial<MissionConfig>) => { Object.assign(config.current, patch); }, []);
  return { snapshot, establish, disconnect, inject, apply, setConfig };
}

function advance(e: Engine, age: number, confidence: number, error: number, signal: number, quality: number, intelligence: boolean) {
  const next = (p: MissionPhase) => { e.phase = p; e.phaseAt = e.t; };
  if (e.phase === "SEARCH" && confidence > .28 && age > .45) next("DETECT");
  else if (e.phase === "DETECT" && confidence > .58 && age > .38) next("IDENTIFY");
  else if (e.phase === "IDENTIFY" && confidence > .76 && age > .48) next("LOCK");
  else if (e.phase === "LOCK" && confidence > .82 && age > .32) next("ACQUIRE");
  else if (e.phase === "ACQUIRE" && error < 3.2 && signal > -38) next("ALIGN");
  else if (e.phase === "ALIGN" && error < .28 && signal > -34) next("TRACK");
  else if (e.phase === "TRACK" && error < .12 && age > .55) { next("CONNECTED"); e.connectedAt = e.t; e.learned = true; }
  else if (e.phase === "DISTURBANCE" && intelligence && quality < 88 && age > .22) { e.adaptive = true; next("CORRECTING"); }
  else if (e.phase === "CORRECTING" && error < .16 && age > .4) { e.disturbance *= Math.exp(-age * .7); if (e.disturbance < .06) next("CONNECTED"); }
  else if (e.phase === "DISCONNECTING" && age > .42) next("READY");
}
function confidenceFor(phase: MissionPhase, age: number, error: number, disturbance: number, learned: boolean) { if (phase === "READY" || phase === "DISCONNECTING") return 0; const base: Record<MissionPhase, number> = { READY:0, SEARCH:.1, DETECT:.32, IDENTIFY:.6, LOCK:.8, ACQUIRE:.86, ALIGN:.91, TRACK:.96, CONNECTED:.985, DISTURBANCE:.72, CORRECTING:.84, DISCONNECTING:0 }; return clamp(base[phase] + age * .34 + (learned ? .1 : 0) - error * .025 - disturbance * .14); }
function makeSnapshot(e: Engine, config: MissionConfig, cached?: { source: Vec3; target: Vec3; desired: Vec3; error: number; distanceKm: number; confidence: number; signalDb: number; quality: number }): MissionSnapshot { const source=cached?.source ?? sourcePosition(e.t); const target=cached?.target ?? targetPosition(e.t,config.ground); const desired=cached?.desired ?? norm(sub(target,source)); const error=cached?.error ?? Math.acos(clamp(dot(e.pointing,desired),-1,1))*180/Math.PI; const distanceKm=cached?.distanceKm ?? len(sub(target,source))*130; const signalDb=cached?.signalDb ?? -18-20*Math.log10(distanceKm/1000)+10*Math.log10(config.power/250)-error*4.2-e.disturbance*3.8; const quality=cached?.quality ?? clamp((signalDb+43)/15)*100; const confidence=cached?.confidence ?? confidenceFor(e.phase,e.t-e.phaseAt,error,e.disturbance,e.learned&&config.intelligence); const live=["CONNECTED","DISTURBANCE","CORRECTING","TRACK"].includes(e.phase); return { phase:e.phase,time:e.t,source,target,currentAxis:e.pointing,desiredAxis:desired,distanceKm,pointingErrorDeg:error,signalDb,quality,dataRate:live?Math.max(0,10.2*quality/100):0,latency:distanceKm/299.8+.65,jitter:e.disturbance*.071+.007,confidence,disturbance:e.disturbance,adaptive:e.adaptive,learned:e.learned,ghost:e.ghost,uptime:live?e.t-e.connectedAt:0,cameraOffset:[clamp((e.pointing[1]-desired[1])*2,-1,1),clamp((e.pointing[2]-desired[2])*2,-1,1)],beaconVisible:confidence>.32&&error<4.5,intelligence:config.intelligence,controller:config.intelligence?"scintilla_predictive":"conventional_pat_atp" }; }
function sourcePosition(t:number):Vec3{return[-6.1+Math.sin(t*.42)*.8,Math.sin(t*.42)*1.8,Math.cos(t*.42)*1.15]}; function targetPosition(t:number,ground:boolean):Vec3{return ground?[6.1,-3.7,0]:[6.1+Math.sin(t*.42+2)*.8,Math.sin(t*.42+2)*1.8,Math.cos(t*.42+2)*1.15]}
