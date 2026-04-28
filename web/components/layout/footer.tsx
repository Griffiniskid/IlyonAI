"use client";

export function Footer() {
  return (
    <footer className="border-t border-border/50 py-6 mt-auto relative z-10">
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
  );
}
