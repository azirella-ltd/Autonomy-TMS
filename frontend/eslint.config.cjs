const browserGlobals = Object.fromEntries(
  [
    "window",
    "document",
    "navigator",
    "localStorage",
    "sessionStorage",
    "console",
    "setTimeout",
    "clearTimeout",
    "setInterval",
    "clearInterval",
    "requestAnimationFrame",
    "cancelAnimationFrame",
    "fetch",
    "Headers",
    "FormData",
    "URL",
    "URLSearchParams",
    "Blob",
    "File",
    "FileReader",
    "CustomEvent",
    "Event",
    "MouseEvent",
    "KeyboardEvent",
    "HTMLElement",
    "Node",
    "NodeList",
    "history",
    "Image",
    "performance",
    "structuredClone",
    "Intl",
    "WebSocket",
    "Response",
    "Request",
    "RequestInfo",
    "RequestInit",
  ].map((name) => [name, "readonly"])
);

const jestGlobals = Object.fromEntries(
  [
    "describe",
    "test",
    "it",
    "expect",
    "beforeEach",
    "afterEach",
    "beforeAll",
    "afterAll",
    "jest",
  ].map((name) => [name, "readonly"])
);

module.exports = [
  {
    ignores: [
      "node_modules/",
      "build/",
      "dist/",
      "coverage/",
      ".cache/",
      "vite.config.ts",
      "public/",
      "**/*.min.js",
      "backend/",
      "scripts/",
      "**/*.ts",
      "**/*.tsx",
    ],
  },
  {
    files: ["**/*.{js,jsx}", "!*eslint.config.*"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: {
        ...browserGlobals,
        React: "readonly",
        process: "readonly",
        module: "readonly",
        require: "readonly",
        __dirname: "readonly",
        global: "readonly",
      },
    },
    plugins: {
      "react-hooks": {
        rules: {
          "exhaustive-deps": {
            meta: {
              type: "problem",
              docs: {
                description: "No-op rule stub so legacy disable directives remain valid",
              },
            },
            create: () => ({}),
          },
        },
      },
    },
    rules: {
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "react-hooks/exhaustive-deps": "off",
    },
  },
  {
    files: ["**/*.{test,spec}.{js,jsx}", "**/__tests__/**/*.{js,jsx}"],
    languageOptions: {
      globals: {
        ...browserGlobals,
        ...jestGlobals,
        jest: "readonly",
      },
    },
  },
  {
    files: ["**/setupTests.{js,jsx}", "**/setupTests.*.js"],
    languageOptions: {
      globals: {
        ...browserGlobals,
        ...jestGlobals,
        jest: "readonly",
      },
    },
  },
];
