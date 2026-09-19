FROM node:24-alpine@sha256:50c8e8ca1d27439048670df5883f32d57cf81cff6233222c893fd0d9884cbd81 AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM dependencies AS build
COPY . .
RUN npm run build

FROM node:24-alpine@sha256:50c8e8ca1d27439048670df5883f32d57cf81cff6233222c893fd0d9884cbd81 AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
RUN apk upgrade --no-cache \
    && rm -rf /opt/yarn-v* /usr/local/lib/node_modules/corepack /usr/local/lib/node_modules/npm \
    && rm -f /usr/local/bin/corepack /usr/local/bin/npm /usr/local/bin/npx \
      /usr/local/bin/yarn /usr/local/bin/yarnpkg \
    && addgroup --system --gid 10001 mmrag \
    && adduser --system --uid 10001 --ingroup mmrag mmrag
COPY --from=build --chown=mmrag:mmrag /app/.next/standalone ./
COPY --from=build --chown=mmrag:mmrag /app/.next/static ./.next/static
USER mmrag
EXPOSE 3000
CMD ["node", "server.js"]
