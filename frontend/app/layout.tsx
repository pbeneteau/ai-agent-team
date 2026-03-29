import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Toaster } from "sonner";
import { ThemeProvider } from "@/components/theme-provider";
import { QueryProvider } from "@/components/query-provider";
import { WebSocketProvider } from "@/components/websocket-provider";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "AI Agent Team",
  description: "You write the brief. We deliver the work. You review the diff.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        {/* Skip-to-content link — TDD-05 Section 19 */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[200] focus:rounded-[var(--radius-md)] focus:bg-[var(--color-accent)] focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-[var(--color-text-inverse)]"
        >
          Skip to content
        </a>
        <ThemeProvider>
          <QueryProvider>
            <WebSocketProvider>
              {children}
              <Toaster position="bottom-right" richColors />
            </WebSocketProvider>
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
