import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Header } from "@/components/layout/header";
import { Toaster } from "@/components/ui/toaster";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
});

export const metadata: Metadata = {
  title: "AI Sentinel | Solana Token Security Scanner",
  description:
    "AI-powered security analysis for Solana tokens. Detect rugpulls, honeypots, and scams before investing. Advanced wallet forensics and real-time risk assessment.",
  keywords: [
    "Solana",
    "token scanner",
    "rugpull detector",
    "honeypot detector",
    "DeFi security",
    "crypto security",
    "AI analysis",
  ],
  openGraph: {
    title: "AI Sentinel | Solana Token Security",
    description: "AI-powered security analysis for Solana tokens",
    type: "website",
    siteName: "AI Sentinel",
  },
  twitter: {
    card: "summary_large_image",
    title: "AI Sentinel | Solana Token Security",
    description: "AI-powered security analysis for Solana tokens",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${inter.variable} ${jetbrains.variable} font-sans antialiased min-h-screen`}
      >
        <Providers>
          <div className="relative min-h-screen flex flex-col">
            {/* Hero gradient background */}
            <div className="fixed inset-0 hero-gradient pointer-events-none" />

            {/* Header */}
            <Header />

            {/* Main content */}
            <main className="flex-1 relative z-10">{children}</main>

            {/* Footer */}
            <footer className="border-t border-border/50 py-6 mt-auto">
              <div className="container mx-auto px-4">
                <div className="flex flex-col md:flex-row items-center justify-between gap-4">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">🛡️</span>
                    <span className="font-semibold">AI Sentinel</span>
                  </div>
                  <div className="text-sm text-muted-foreground">
                    Built for the Solana ecosystem
                  </div>
                  <div className="flex items-center gap-4 text-sm text-muted-foreground">
                    <a href="/docs" className="hover:text-foreground transition">
                      Documentation
                    </a>
                    <a
                      href="https://twitter.com/aisentinel"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:text-foreground transition"
                    >
                      Twitter
                    </a>
                    <a
                      href="https://github.com/aisentinel"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:text-foreground transition"
                    >
                      GitHub
                    </a>
                  </div>
                </div>
              </div>
            </footer>
          </div>
          <Toaster />
        </Providers>
      </body>
    </html>
  );
}
