FROM node:20-alpine AS build
WORKDIR /src
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
ARG VITE_GRPC_WEB_URL=http://localhost:8080
ENV VITE_GRPC_WEB_URL=$VITE_GRPC_WEB_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80
