// Builds the browser interface into the Python package, where the server delivers it.
// File names have no hash: the page adds ?v=<content hash> itself, and a stable name keeps
// the committed build easy to compare in the CI.
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  base: "/static/app/",
  build: {
    outDir: "../src/oslo/web/static/app",
    emptyOutDir: true,
    sourcemap: false,
    // One style sheet for all pages (app.css), linked by app_page.html.
    cssCodeSplit: false,
    rollupOptions: {
      input: {
        landscape: "src/landscape/main.tsx",
        activity: "src/activity/main.tsx",
        templates: "src/templates/main.tsx",
        overview: "src/overview/main.tsx",
        activities: "src/activities/main.tsx",
        configuration: "src/configuration/main.tsx",
        operations: "src/operations/main.tsx",
        administration: "src/administration/main.tsx",
        account: "src/account/main.tsx",
      },
      output: {
        entryFileNames: "[name].js",
        // Code shared by the pages (React, API, texts).
        chunkFileNames: "shared-[name].js",
        assetFileNames: (asset) => (asset.names?.[0]?.endsWith(".css") ? "app.css" : "[name][extname]"),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
