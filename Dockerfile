# CR-16102702：多阶段构建，运行镜像只带 standalone 产物与静态资源
# 基础镜像用 debian-slim(glibc)：package-lock.json 记录了 @tailwindcss/oxide-linux-x64-gnu，
# 用 alpine(musl) 会缺 oxide-linux-x64-musl 条目导致 next build 报 "Cannot find module"。
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# 严格按 lock 安装，保证构建可重复（NFR-02）
RUN npm ci --no-audit --no-fund

# 构建阶段：产物走 next.config.ts 里的 output=standalone（FR-04）
FROM node:22-slim AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# 运行阶段：仅 standalone + 静态资源 + public，不含源码与 devDependencies
FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# 以非 root 运行
RUN groupadd -g 1001 nodejs && useradd -u 1001 -g nodejs -m nextjs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
