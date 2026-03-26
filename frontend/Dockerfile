FROM node:20-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN npm ci --no-audit --no-fund

COPY . .

# Download AI models for offline PWA use.
# Set DOWNLOAD_MODELS=1 in docker-compose build args to bundle them into the image.
ARG DOWNLOAD_MODELS=0
RUN if [ "${DOWNLOAD_MODELS}" = "1" ]; then \
      apk add --no-cache python3 py3-pip && \
      pip3 install huggingface_hub --break-system-packages --quiet && \
      python3 scripts/download_models.py; \
    fi

RUN npm run build

FROM nginx:1.27-alpine AS runtime

# SPA fallback and secure defaults for static hosting.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
