# Development-focused frontend image for local docker-compose use.
# It mirrors the current local workflow by running the Vite dev server and
# expecting the project source to be bind-mounted at runtime.

FROM node:22-bookworm-slim

WORKDIR /app

ENV CHOKIDAR_USEPOLLING=true

COPY package.json ./package.json

RUN npm install --no-audit --no-fund

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
