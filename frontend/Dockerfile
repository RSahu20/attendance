FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY index.html tsconfig.json vite.config.ts vitest.config.ts ./
COPY src ./src
COPY public ./public

EXPOSE 5173

CMD ["npm", "run", "dev"]
