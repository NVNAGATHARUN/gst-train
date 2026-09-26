FROM node:22.19.0-alpine3.22 AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22.19.0-alpine3.22 AS builder
WORKDIR /app
ARG RAILSYNC_API_ORIGIN=http://api:8000
ENV NEXT_TELEMETRY_DISABLED=1 \
    RAILSYNC_API_ORIGIN=${RAILSYNC_API_ORIGIN}
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22.19.0-alpine3.22 AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /app
RUN addgroup -S railsync && adduser -S railsync -G railsync
COPY --from=builder --chown=railsync:railsync /app/.next/standalone ./
COPY --from=builder --chown=railsync:railsync /app/.next/static ./.next/static
USER railsync
EXPOSE 3000
CMD ["node", "server.js"]
