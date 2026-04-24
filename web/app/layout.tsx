import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { AppShell } from "@/components/layout/app-shell";
import { Footer } from "@/components/layout/footer";

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
          <div className="relative min-h-screen">
            {/* Hero gradient background */}
            <div className="fixed inset-0 hero-gradient pointer-events-none" />

            <AppShell>
              {/* Main content */}
              <main className="flex-1 relative z-10">{children}</main>

              {/* Footer */}
              <Footer />
            </AppShell>
          </div>
        </Providers>
      </body>
    </html>
  );
}
