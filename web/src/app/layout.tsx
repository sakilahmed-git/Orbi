import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SCINTILLA — Optical Intelligence",
  description: "Event-based optical-link mission control simulation.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return <html lang="en"><body>{children}</body></html>;
}
