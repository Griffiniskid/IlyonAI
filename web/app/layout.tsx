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
  title: "Ilyon AI | Your AI-Powered DeFi Trading Assistant",
  description:
    "AI-powered DeFi trading assistant across Solana, Ethereum, Base, Arbitrum, BSC, Polygon, Optimism, and Avalanche. Ask in natural language to check balances, find swap routes, bridge assets, track portfolios, and analyze tokens — all from one chat interface.",
  keywords: [
    "DeFi security",
    "multi-chain",
    "token scanner",
    "smart contract audit",
    "rugpull detector",
    "honeypot detector",
    "approval manager",
    "yield farming",
    "crypto security",
    "AI analysis",
    "AI trading assistant",
    "DeFi assistant",
    "natural language trading",
    "crypto AI",
    "wallet assistant",
    "Ethereum",
    "Solana",
    "Base",
  ],
  icons: {
    icon: "/shield.png",
    apple: "/shield.png",
  },
  openGraph: {
    title: "Ilyon AI | Your AI-Powered DeFi Trading Assistant",
    description: "AI-powered DeFi trading assistant across all major chains",
    type: "website",
    siteName: "Ilyon AI",
  },
  twitter: {
    card: "summary_large_image",
    title: "Ilyon AI | Your AI-Powered DeFi Trading Assistant",
    description: "AI-powered DeFi trading assistant across all major chains",
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
