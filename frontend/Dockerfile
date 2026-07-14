FROM node:22-alpine AS build
WORKDIR /app
ARG VITE_AGENT_API_BASE_URL=""
ARG VITE_AMAP_JS_KEY=""
ARG VITE_AMAP_SECURITY_JS_CODE=""
ENV VITE_AGENT_API_BASE_URL=${VITE_AGENT_API_BASE_URL}
ENV VITE_AMAP_JS_KEY=${VITE_AMAP_JS_KEY}
ENV VITE_AMAP_SECURITY_JS_CODE=${VITE_AMAP_SECURITY_JS_CODE}
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
