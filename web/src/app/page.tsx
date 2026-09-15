import Image from "next/image";
import Link from "next/link";

const STAGES = [
  {
    name: "Sense",
    body: "An event-based sensor model reports per-pixel brightness changes as they happen, instead of waiting for a shutter. Vibration that would smear a frame-camera exposure into a blur shows up as a clean, sharp cloud of timestamped events.",
  },
  {
    name: "Discriminate",
    body: "A classifier trained on the beacon's blink signature separates the real modulated source from background clutter and sensor noise, frame by frame, without needing the platform to hold still first.",
  },
  {
    name: "Hand off",
    body: "The same event stream that found the beacon also reveals how the platform is vibrating — frequency, amplitude, how confidently either is known — and that estimate is handed to the downstream fine-tracking loop for free.",
  },
];

export default function LandingPage() {
  return (
    <div className="mx-auto max-w-6xl px-6">
      <section className="pt-16 pb-12 md:pt-24 md:pb-16">
        <p className="font-mono text-xs text-accent mb-4">
          SIH26169 — ISRO
        </p>
        <h1 className="text-4xl md:text-5xl font-medium tracking-tight max-w-3xl leading-[1.1]">
          Coarse alignment that doesn&apos;t blink when the platform vibrates.
        </h1>
        <p className="mt-6 max-w-2xl text-lg text-text-dim leading-relaxed">
          Scintilla is a perception layer for mobile Free-Space Optical Communication
          terminals. It acquires a frequency-modulated beacon under vibration and glare
          conditions that break a conventional frame camera, using event-based vision —
          and reads real-time disturbance state off the same data as a free byproduct,
          handing both to whatever fine-tracking loop sits downstream.
        </p>
        <div className="mt-8 flex flex-wrap gap-4">
          <Link
            href="/demo"
            className="px-5 py-2.5 bg-accent text-[#150a05] text-sm font-medium hover:brightness-110 transition"
          >
            Run the live demo
          </Link>
          <Link
            href="/envelope"
            className="px-5 py-2.5 border border-panel-border text-sm text-text hover:border-text-dim transition"
          >
            See the acquisition envelope
          </Link>
        </div>
      </section>

      <section className="pb-16 border-t border-panel-border pt-10">
        <p className="text-sm text-text-dim mb-4 max-w-2xl">
          Same beacon blink, same vibration, two sensing models, computed from
          the same underlying simulated scene:
        </p>
        <div className="border border-panel-border bg-panel p-2">
          <Image
            src="/assets/section2_event_vs_blur_comparison.png"
            alt="Side-by-side comparison of an event-camera point cloud and a blurred conventional-camera frame of the same vibrating beacon"
            width={1536}
            height={780}
            className="w-full h-auto"
          />
        </div>
      </section>

      <section className="pb-16 border-t border-panel-border pt-10">
        <h2 className="text-sm font-mono text-text-dim mb-8">How it works</h2>
        <div className="grid md:grid-cols-3 gap-8">
          {STAGES.map((stage, i) => (
            <div key={stage.name} className="border-l border-panel-border pl-5">
              <div className="font-mono text-xs text-accent-2 mb-2">{`0${i + 1}`}</div>
              <h3 className="text-lg mb-2">{stage.name}</h3>
              <p className="text-sm text-text-dim leading-relaxed">{stage.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="pb-20 border-t border-panel-border pt-10">
        <div className="max-w-2xl">
          <h2 className="text-lg mb-3">Who this is for</h2>
          <p className="text-sm text-text-dim leading-relaxed">
            FSOC terminal integrators moving from fixed ground-to-space links to mobile
            and inter-satellite links — the transition Astrogate Labs, ISRO&apos;s TRL-8
            FSOC terminal supplier, publicly announced in September 2026. Scintilla is
            built to sit in front of an existing gimbal and tracking stack as a drop-in
            software layer, with real-DVS-hardware as a later upgrade tier rather than a
            day-one requirement.
          </p>
        </div>
      </section>
    </div>
  );
}
