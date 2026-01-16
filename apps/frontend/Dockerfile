FROM node:20-alpine as builder
WORKDIR /app
ARG NPM_REGISTRY=https://registry.npmmirror.com
COPY package*.json ./
RUN npm config set registry ${NPM_REGISTRY} \
  && npm config set fetch-timeout 120000 \
  && npm config set fetch-retries 5 \
  && npm config set fetch-retry-factor 2 \
  && npm config set fetch-retry-mintimeout 20000 \
  && npm config set fetch-retry-maxtimeout 120000 \
  && if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY . .
RUN npm run build

FROM nginx:stable-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
