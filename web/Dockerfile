# Ilyon AI Web - Production Dockerfile
# Multi-stage build for optimized Next.js deployment

# Stage 1: Install dependencies
FROM node:18-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# Stage 2: Build the application
FROM node:18-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build-time environment variables (baked into JS bundle)
ARG NEXT_DIST_DIR=.next
ARG NEXT_PUBLIC_API_URL=https://ilyonai.com
ARG NEXT_PUBLIC_SOLANA_NETWORK=mainnet-beta
ARG NEXT_PUBLIC_SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
ARG NEXT_PUBLIC_COMING_SOON=false
ARG API_REWRITE_TARGET=http://api:8080
ARG ASSISTANT_API_TARGET=http://assistant-api:8000

ENV NEXT_DIST_DIR=$NEXT_DIST_DIR
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_SOLANA_NETWORK=$NEXT_PUBLIC_SOLANA_NETWORK
ENV NEXT_PUBLIC_SOLANA_RPC_URL=$NEXT_PUBLIC_SOLANA_RPC_URL
ENV NEXT_PUBLIC_COMING_SOON=$NEXT_PUBLIC_COMING_SOON
ENV API_REWRITE_TARGET=$API_REWRITE_TARGET
ENV ASSISTANT_API_TARGET=$ASSISTANT_API_TARGET
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# Stage 3: Production runner
FROM node:18-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000 || exit 1

CMD ["node", "server.js"]

LABEL maintainer="Ilyon AI Team"
LABEL version="1.0"
LABEL description="Ilyon AI Web Frontend"
