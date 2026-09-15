"use client";

import { useEffect, useRef } from "react";

export default function BaselineCanvas({
  pixels,
  width,
  height,
  label,
  caption,
}: {
  pixels: number[] | null;
  width: number;
  height: number;
  label: string;
  caption?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !pixels || width === 0 || height === 0) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const off = document.createElement("canvas");
    off.width = width;
    off.height = height;
    const offCtx = off.getContext("2d");
    if (!offCtx) return;
    const imageData = offCtx.createImageData(width, height);
    for (let i = 0; i < width * height; i++) {
      const v = pixels[i] ?? 0;
      imageData.data[i * 4] = v;
      imageData.data[i * 4 + 1] = v;
      imageData.data[i * 4 + 2] = v;
      imageData.data[i * 4 + 3] = 255;
    }
    offCtx.putImageData(imageData, 0, 0);

    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = "#04060a";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(off, 0, 0, canvas.width, canvas.height);
  }, [pixels, width, height]);

  return (
    <div>
      <canvas
        ref={canvasRef}
        width={256}
        height={256}
        className="w-full aspect-square border border-panel-border bg-[#04060a]"
      />
      <p className="mt-2 text-xs font-mono text-text-dim">{label}</p>
      {caption && <p className="mt-1 text-xs leading-relaxed text-text-dim">{caption}</p>}
    </div>
  );
}
