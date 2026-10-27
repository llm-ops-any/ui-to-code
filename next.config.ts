import type {NextConfig} from 'next'

const nextConfig: NextConfig = {
  // CR-16102702/FR-04：容器运行只需要 standalone 产物，避免镜像带完整 node_modules
  output: 'standalone',
  /* config options here */
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '*',
        port: '',
        pathname: '/**',
        search: '',
      },
    ],
  },
}

export default nextConfig
