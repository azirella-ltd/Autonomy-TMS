import path from "node:path";
import url from "node:url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = url.fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const compat = new FlatCompat({ baseDirectory: __dirname });

const compatConfigs = compat.config({
  extends: ["react-app", "react-app/jest"],
});

const config = [
  {
    ignores: ["build", "node_modules"],
  },
  ...compatConfigs.map((configItem) => ({
    ...configItem,
    files: configItem.files ?? ["**/*.{js,jsx,ts,tsx}"],
  })),
];

export default config;
