import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { AppShell } from "@/components/layout/app-shell";
import { Footer } from "@/components/layout/footer";
import { MarketTickerBar } from "@/components/agent-app/MarketTickerBar";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
});

export const metadata: Metadata = {
  title: "Ilyon | The safe way to trade Solana",
  description:
    "Trade any Solana token safely — Ilyon auto-screens every token for rugs before you buy. Paste a token, get an instant safety verdict, and buy or sell in one tap.",
  keywords: [
    "Solana trading",
    "Solana token safety",
    "rug checker",
    "rugpull detector",
    "honeypot detector",
    "memecoin scanner",
    "Solana swap",
    "Jupiter swap",
    "token risk score",
    "safe trading",
    "crypto AI",
    "Solana wallet",
    "SPL token",
  ],
  icons: {
    icon: "/shield.png",
    apple: "/shield.png",
  },
  openGraph: {
    title: "Ilyon | The safe way to trade Solana",
    description:
      "Every Solana token auto-screened for rugs before you buy. Paste a token → safety verdict → one-tap trade.",
    type: "website",
    siteName: "Ilyon",
  },
  twitter: {
    card: "summary_large_image",
    title: "Ilyon | The safe way to trade Solana",
    description:
      "Every Solana token auto-screened for rugs before you buy. Paste a token → safety verdict → one-tap trade.",
  },
};

// NOTE: deliberately NO `viewport-fit=cover`. It exposes env(safe-area-inset-*) for
// mobile, but on a notched Mac in fullscreen it lets the page paint UNDER the notch,
// pushing the fixed ticker over the top banner (desktop overlap). Prod ships without
// it; match that. The mobile composer fix relies on dvh + nav-height reservation, and
// the env(...) usages all carry a 0px fallback, so they degrade cleanly to no-op.

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${inter.variable} ${jetbrains.variable} font-sans antialiased h-screen`}
      >
        <Providers>
          <div className="relative min-h-screen flex flex-col">
            {/* Hero gradient background */}
            <div className="fixed inset-0 hero-gradient pointer-events-none" />

            {/* Global market ticker — visible on every page */}
            <MarketTickerBar />

            <div className="flex-1 flex flex-col min-h-0 pt-8">
              <AppShell>
                {/* Main content */}
                <main className="flex-1 relative z-10 flex flex-col min-h-0">{children}</main>

                {/* Footer */}
                <Footer />
              </AppShell>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
