import EnvelopeHeatmap from "@/components/EnvelopeHeatmap";

export default function EnvelopePage() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-12">
      <h1 className="text-2xl font-medium mb-2">Acquisition envelope report</h1>
      <p className="text-sm text-text-dim max-w-2xl mb-8">
        A surrogate model trained on Section 4/5&apos;s classical-vs-learned lock-on results,
        swept across vibration amplitude and background clutter at fixed turbulence and
        sensor-noise settings. This tells an integrator where the system is expected to work
        before they build any hardware.
      </p>
      <EnvelopeHeatmap />
    </div>
  );
}
