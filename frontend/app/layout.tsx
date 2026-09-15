import type { Metadata } from "next";
import Providers from "@/components/Providers";
import AppShell from "@/components/AppShell";
import "./globals.css";

export const metadata: Metadata = {
  title: "CrisisWatch AI — Real-Time Global Crisis Intelligence",
  description:
    "Aggregates global crisis data from 7+ public sources, applies ML prediction and explainable AI, and delivers actionable real-time intelligence for NGOs, governments and first responders.",
  icons: {
    icon: "/icon.svg",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" style={{ backgroundColor: "#0a0a0f", colorScheme: "dark" }}>
      <body className="min-h-screen bg-navy-deep text-slate-100 antialiased">
        <Providers>
          <div className="fixed inset-0 -z-10 bg-[radial-gradient(ellipse_at_top_right,rgba(59,130,246,0.12),transparent_55%),radial-gradient(ellipse_at_bottom_left,rgba(168,85,247,0.08),transparent_50%)]" />
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}