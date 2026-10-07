FROM node:24.14.1-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
ARG API_URL=http://api:8000
ENV API_URL=$API_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:24.14.1-alpine
WORKDIR /app
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000 NEXT_TELEMETRY_DISABLED=1
RUN addgroup -g 10001 operations && adduser -D -u 10001 -G operations operations
COPY --from=build --chown=operations:operations /app/.next/standalone ./
COPY --from=build --chown=operations:operations /app/.next/static ./.next/static
USER operations
EXPOSE 3000
CMD ["node","server.js"]
