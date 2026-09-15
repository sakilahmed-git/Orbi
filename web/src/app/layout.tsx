import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Scintilla — coarse alignment for mobile FSOC terminals",
  description:
    "Event-based beacon acquisition and disturbance sensing for mobile Free-Space Optical Communication terminals.",
};

const NAV_LINKS = [
  { href: "/", label: "Overview" },
  { href: "/demo", label: "Live demo" },
  { href: "/envelope", label: "Envelope report" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-bg text-text">
        <header className="border-b border-panel-border">
          <div className="mx-auto max-w-6xl px-6 h-14 flex items-center justify-between">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="font-mono text-sm tracking-tight text-accent">SCINTILLA</span>
              <span className="hidden sm:inline text-xs text-text-dim font-mono">SIH26169</span>
            </Link>
            <nav className="flex gap-6 text-sm">
              {NAV_LINKS.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="text-text-dim hover:text-text transition-colors"
                >
                  {link.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="flex-1">{children}</main>
        <footer className="border-t border-panel-border">
          <div className="mx-auto max-w-6xl px-6 py-6 text-xs text-text-dim font-mono">
            Scintilla — perception layer for mobile FSOC coarse alignment. Synthetic simulation, validated against e-STURT where noted.
          </div>
        </footer>
      </body>
    </html>
  );
}
