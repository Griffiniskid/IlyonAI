"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Search, Loader2, ArrowRight } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { isValidSolanaAddress } from "@/lib/utils";

interface TokenSearchProps {
  size?: "default" | "large";
  placeholder?: string;
  autoFocus?: boolean;
}

export function TokenSearch({
  size = "default",
  placeholder = "Enter Solana token address...",
  autoFocus = false,
}: TokenSearchProps) {
  const router = useRouter();
  const [address, setAddress] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);

      const trimmedAddress = address.trim();

      if (!trimmedAddress) {
        setError("Please enter a token address");
        return;
      }

      if (!isValidSolanaAddress(trimmedAddress)) {
        setError("Invalid Solana address format");
        return;
      }

      setIsLoading(true);

      try {
        router.push(`/token/${trimmedAddress}`);
      } catch (err) {
        setError("Failed to navigate");
        setIsLoading(false);
      }
    },
    [address, router]
  );

  const isLarge = size === "large";

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className={`relative ${isLarge ? "max-w-2xl mx-auto" : ""}`}>
        <div className="relative flex items-center">
          <Search
            className={`absolute left-4 text-muted-foreground ${
              isLarge ? "h-5 w-5" : "h-4 w-4"
            }`}
          />
          <Input
            type="text"
            value={address}
            onChange={(e) => {
              setAddress(e.target.value);
              setError(null);
            }}
            placeholder={placeholder}
            autoFocus={autoFocus}
            className={`
              ${isLarge ? "h-14 text-base pl-12 pr-32" : "h-12 pl-10 pr-24"}
              ${error ? "border-red-500 focus-visible:ring-red-500" : ""}
            `}
          />
          <Button
            type="submit"
            disabled={isLoading || !address.trim()}
            variant={isLarge ? "glow" : "default"}
            className={`absolute right-2 ${isLarge ? "h-10" : "h-8"}`}
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <>
                Scan
                <ArrowRight className="h-4 w-4 ml-1" />
              </>
            )}
          </Button>
        </div>

        {error && (
          <p className="text-red-400 text-sm mt-2 pl-1">{error}</p>
        )}
      </div>
    </form>
  );
}
