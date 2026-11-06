FROM node:20-alpine

# libc6-compat keeps Next.js tooling happy on Alpine.
RUN apk add --no-cache libc6-compat

WORKDIR /app

# .npmrc carries legacy-peer-deps so the lockfile resolves like CI does.
COPY package.json package-lock.json .npmrc ./
RUN npm ci

COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
# NEXT_PUBLIC_* values are inlined at build time — pass them as build args:
#   docker build --build-arg NEXT_PUBLIC_API_URL=https://api.example.com .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL

RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
