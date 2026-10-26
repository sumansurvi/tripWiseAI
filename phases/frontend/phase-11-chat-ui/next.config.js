/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: [],
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      "@research": require("path").resolve(__dirname, "../phase-12-research-ui/src"),
    };
    return config;
  },
};

module.exports = nextConfig;
