FROM node:22-slim AS base
WORKDIR /app
COPY frontend/package.json ./
RUN npm install
COPY frontend ./

# --- dev target: Vite dev server with HMR ---
FROM base AS dev
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# --- build target: static assets for the nginx prod profile ---
FROM base AS build
RUN npm run build

FROM scratch AS build-output
COPY --from=build /app/dist /dist
