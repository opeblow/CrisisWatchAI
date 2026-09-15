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
    <html lang="en" style={{ backgroundColor: "#ffffff", colorScheme: "light" }}>
      <body className="min-h-screen bg-white text-zinc-900 antialiased">
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}