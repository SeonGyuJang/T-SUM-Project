import next from "eslint-config-next";

const config = [
  ...next,
  { ignores: [".next/**", ".next-*/**", "public/mockServiceWorker.js", "playwright-report/**", "test-results/**"] },
];
export default config;
