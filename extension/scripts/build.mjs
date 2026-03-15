import { build } from "esbuild";
import { copyFile, mkdir, readFile, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const extensionRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(extensionRoot, "..");
const distDir = path.join(extensionRoot, "dist");
const distPopupDir = path.join(distDir, "popup");

const frontendEnv = await loadMergedEnvFiles([
  path.join(repoRoot, "frontend", ".env"),
  path.join(repoRoot, "frontend", ".env.local"),
]);

const extensionSupabaseUrl = resolveEnvValue({
  processPrimaryKey: "EXTENSION_SUPABASE_URL",
  processFallbackKey: "VITE_SUPABASE_URL",
  fileEnv: frontendEnv,
  filePrimaryKey: "EXTENSION_SUPABASE_URL",
  fileFallbackKey: "VITE_SUPABASE_URL",
});

const extensionSupabaseAnonKey = resolveEnvValue({
  processPrimaryKey: "EXTENSION_SUPABASE_ANON_KEY",
  processFallbackKey: "VITE_SUPABASE_ANON_KEY",
  fileEnv: frontendEnv,
  filePrimaryKey: "EXTENSION_SUPABASE_ANON_KEY",
  fileFallbackKey: "VITE_SUPABASE_ANON_KEY",
});

const sharedBuildOptions = {
  bundle: true,
  sourcemap: true,
  minify: false,
  platform: "browser",
  target: ["chrome114"],
  format: "iife",
  logLevel: "info",
  define: {
    "globalThis.__EXTENSION_SUPABASE_URL__": JSON.stringify(extensionSupabaseUrl),
    "globalThis.__EXTENSION_SUPABASE_ANON_KEY__": JSON.stringify(extensionSupabaseAnonKey),
  },
};

await rm(distDir, { recursive: true, force: true });
await mkdir(distPopupDir, { recursive: true });

await Promise.all([
  build({
    ...sharedBuildOptions,
    entryPoints: [path.join(extensionRoot, "background.service-worker.ts")],
    outfile: path.join(distDir, "background.service-worker.js"),
  }),
  build({
    ...sharedBuildOptions,
    entryPoints: [path.join(extensionRoot, "contentScript.ts")],
    outfile: path.join(distDir, "contentScript.js"),
  }),
  build({
    ...sharedBuildOptions,
    entryPoints: [path.join(extensionRoot, "popup", "index.ts")],
    outfile: path.join(distPopupDir, "index.js"),
  }),
]);

await copyFile(
  path.join(extensionRoot, "popup", "index.html"),
  path.join(distPopupDir, "index.html"),
);

console.log("Extension build completed.");
console.log(`Load unpacked extension from: ${extensionRoot}`);
if (!extensionSupabaseUrl || !extensionSupabaseAnonKey) {
  console.log(
    "Warning: Supabase auth config is empty. Set EXTENSION_SUPABASE_URL/EXTENSION_SUPABASE_ANON_KEY or frontend VITE_SUPABASE_* before build.",
  );
}

async function loadMergedEnvFiles(filePaths) {
  const merged = {};

  for (const filePath of filePaths) {
    const parsed = await readEnvFile(filePath);
    Object.assign(merged, parsed);
  }

  return merged;
}

async function readEnvFile(filePath) {
  try {
    const raw = await readFile(filePath, "utf8");
    return parseDotEnv(raw);
  } catch (error) {
    if (error && typeof error === "object" && "code" in error && error.code === "ENOENT") {
      return {};
    }
    throw error;
  }
}

function parseDotEnv(raw) {
  const parsed = {};

  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const separatorIndex = trimmed.indexOf("=");
    if (separatorIndex < 0) {
      continue;
    }

    const key = trimmed.slice(0, separatorIndex).trim();
    if (!key) {
      continue;
    }

    let value = trimmed.slice(separatorIndex + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    parsed[key] = value;
  }

  return parsed;
}

function resolveEnvValue({
  processPrimaryKey,
  processFallbackKey,
  fileEnv,
  filePrimaryKey,
  fileFallbackKey,
}) {
  const fromProcessPrimary = readString(process.env[processPrimaryKey]);
  if (fromProcessPrimary) {
    return fromProcessPrimary;
  }

  const fromProcessFallback = readString(process.env[processFallbackKey]);
  if (fromProcessFallback) {
    return fromProcessFallback;
  }

  const fromFilePrimary = readString(fileEnv[filePrimaryKey]);
  if (fromFilePrimary) {
    return fromFilePrimary;
  }

  const fromFileFallback = readString(fileEnv[fileFallbackKey]);
  if (fromFileFallback) {
    return fromFileFallback;
  }

  return "";
}

function readString(value) {
  return typeof value === "string" ? value.trim() : "";
}
