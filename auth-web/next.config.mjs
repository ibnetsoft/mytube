
import dotenv from 'dotenv'
import { existsSync, readFileSync } from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

function loadEnvIfExists(envPath) {
    if (existsSync(envPath)) {
        const parsed = dotenv.parse(readFileSync(envPath))
        for (const [key, value] of Object.entries(parsed)) {
            if (!process.env[key]) {
                process.env[key] = value
            }
        }
    }
}

// Keep deployment/runtime env authoritative, then fill local gaps from
// auth-web/.env.local and finally the repository-root .env used by workers.
loadEnvIfExists(path.join(__dirname, '.env.local'))
loadEnvIfExists(path.join(__dirname, '..', '.env'))

/** @type {import('next').NextConfig} */
const nextConfig = {
    eslint: {
        // 빌드 시 린트 에러를 무시합니다 (배포 테스트용)
        ignoreDuringBuilds: true,
    },
    typescript: {
        // 빌드 시 타입 에러를 무시합니다 (배포 테스트용)
        ignoreBuildErrors: true,
    },
    async redirects() {
        return [
            {
                source: '/',
                destination: '/std',
                permanent: false,
            },
        ];
    },
};

export default nextConfig;
