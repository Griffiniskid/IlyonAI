import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Header } from "@/components/layout/header";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
});

export const metadata: Metadata = {
  title: "Ilyon AI | Multi-Chain Token And Pool Intelligence",
  description:
    "AI-powered token and pool intelligence across Ethereum, Base, Arbitrum, BSC, Polygon, Optimism, Avalanche, and Solana. Analyze token security, pool sustainability, contract risk, and wallet approvals from one surface.",
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
    "Ethereum",
    "Solana",
    "Base",
  ],
  icons: {
    icon: "/shield.png",
    apple: "/shield.png",
  },
  openGraph: {
    title: "Ilyon AI | Multi-Chain Token And Pool Intelligence",
    description: "AI-powered token security and pool intelligence across all major chains",
    type: "website",
    siteName: "Ilyon AI",
  },
  twitter: {
    card: "summary_large_image",
    title: "Ilyon AI | Multi-Chain Token And Pool Intelligence",
    description: "AI-powered token security and pool intelligence across all major chains",
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
                  <div className="flex items-center">
                    <img src="/logo.png" alt="Ilyon AI" className="h-14 sm:h-[72px] w-auto" />
                  </div>
                  <div className="text-sm text-muted-foreground">
                    Multi-chain token and pool intelligence
                  </div>
                  <div className="flex items-center gap-4 text-sm text-muted-foreground">
                    <a href="/docs" className="hover:text-foreground transition">
                      Documentation
                    </a>
                    <a
                      href="https://x.com/ilyonProtocol"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:text-foreground transition"
                    >
                      Twitter
                    </a>
                    <a
                      href="https://t.me/ilyonProtocol"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:text-foreground transition"
                    >
                      Telegram
                    </a>
                  </div>
                </div>
              </div>
            </footer>
          </div>
        </Providers>
      </body>
    </html>
  );
}
