FROM node:18 AS build
WORKDIR /app

# install dependencies
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

# copy source and build
COPY frontend ./
RUN npm run build

FROM nginx:stable-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
