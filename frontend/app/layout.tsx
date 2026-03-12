import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { Providers } from "./providers";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Alex Ops Desk",
  description: "Local-first control desk for AI agent teams, explicit plans, and observability.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-[var(--ops-canvas)] antialiased`}>
        <Providers>
          <div className="flex h-screen overflow-hidden">
            <Sidebar />
            <main className="h-full min-w-0 flex-1 overflow-hidden bg-[var(--ops-canvas)]">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
