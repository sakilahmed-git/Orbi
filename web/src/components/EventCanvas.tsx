"use client";

import { useEffect, useRef } from "react";

export interface EventPoint {
  x: number;
  y: number;
  polarity: number;
}

export default function EventCanvas({
  points,
  frameW,
  frameH,
  label,
}: {
  points: EventPoint[];
  frameW: number;
  frameH: number;
  label: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const scaleX = canvas.width / frameW;
    const scaleY = canvas.height / frameH;

    ctx.fillStyle = "#04060a";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    for (const p of points) {
      ctx.fillStyle = p.polarity > 0 ? "#ff6a3d" : "#4fa6ff";
      ctx.fillRect(p.x * scaleX, p.y * scaleY, Math.max(1, scaleX), Math.max(1, scaleY));
    }
  }, [points, frameW, frameH]);

  return (
    <div>
      <canvas
        ref={canvasRef}
        width={256}
        height={256}
        className="w-full aspect-square border border-panel-border bg-[#04060a]"
      />
      <p className="mt-2 text-xs font-mono text-text-dim">{label}</p>
    </div>
  );
}
