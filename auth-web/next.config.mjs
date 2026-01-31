
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
};

export default nextConfig;
