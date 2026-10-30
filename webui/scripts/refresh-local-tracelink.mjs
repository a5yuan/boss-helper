import { spawnSync } from "node:child_process";
import {
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  renameSync,
  rmSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sdkDir = resolve(projectDir, "../../../debug_project/Trace_Link");
const packageDir = join(projectDir, ".local-packages");
const tarballPath = join(packageDir, "tracelink-dev.tgz");
const extractionPath = join(packageDir, `.tracelink-extract-${process.pid}`);
const installedPackagePath = join(projectDir, "node_modules", "tracelink");
const packageLockPath = join(projectDir, "package-lock.json");
const binDir = join(projectDir, "node_modules", ".bin");
const npmCliPath = process.env.npm_execpath;

if (!existsSync(join(sdkDir, "package.json"))) {
  throw new Error(`TraceLink SDK not found: ${sdkDir}`);
}

function npm(args, cwd, captureOutput = false) {
  const npmCmd = npmCliPath ? process.execPath : (process.platform === "win32" ? "npm.cmd" : "npm");
  const npmArgs = npmCliPath ? [npmCliPath, ...args] : args;

  const result = spawnSync(npmCmd, npmArgs, {
    cwd,
    encoding: "utf8",
    stdio: captureOutput ? "pipe" : "inherit",
  });

  if (result.error) throw result.error;
  if (result.status !== 0) {
    if (captureOutput) {
      if (result.stdout) process.stdout.write(result.stdout);
      if (result.stderr) process.stderr.write(result.stderr);
    }
    throw new Error(`npm ${args.join(" ")} failed with exit code ${result.status ?? 1}`);
  }

  return result.stdout ?? "";
}

function removePackage(path) {
  if (!existsSync(path)) return;
  if (lstatSync(path).isSymbolicLink()) {
    unlinkSync(path);
  } else {
    rmSync(path, { recursive: true, force: true });
  }
}

function invalidateInstalledPackageMetadata() {
  if (existsSync(packageLockPath)) {
    const lock = JSON.parse(readFileSync(packageLockPath, "utf8"));
    if (lock.packages) delete lock.packages["node_modules/tracelink"];
    if (lock.dependencies) delete lock.dependencies.tracelink;
    writeFileSync(packageLockPath, `${JSON.stringify(lock, null, 2)}\n`, "utf8");
  }
  for (const suffix of ["", ".cmd", ".ps1"]) {
    rmSync(join(binDir, `tracelink${suffix}`), { force: true });
  }
}

function extractAndValidatePackage() {
  rmSync(extractionPath, { recursive: true, force: true });
  mkdirSync(extractionPath, { recursive: true });

  const tarCommand = process.platform === "win32" ? "tar.exe" : "tar";
  const result = spawnSync(
    tarCommand,
    ["-xf", tarballPath, "-C", extractionPath, "--strip-components=1"],
    { cwd: projectDir, encoding: "utf8", stdio: "pipe" },
  );

  if (result.error) throw result.error;
  if (result.status !== 0) {
    if (result.stdout) process.stdout.write(result.stdout);
    if (result.stderr) process.stderr.write(result.stderr);
    throw new Error(`Failed to extract ${tarballPath}`);
  }

  const manifestPath = join(extractionPath, "package.json");
  if (!existsSync(manifestPath)) throw new Error("Packed TraceLink is missing package.json");

  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  if (manifest.name !== "tracelink") {
    throw new Error(`Unexpected package in tarball: ${manifest.name ?? "unknown"}`);
  }
}

mkdirSync(packageDir, { recursive: true });

console.log("[sdk:refresh] build TraceLink");
npm(["run", "build"], sdkDir);

console.log("[sdk:refresh] pack TraceLink");
const output = npm(
  ["pack", sdkDir, "--silent", "--pack-destination", packageDir],
  projectDir,
  true,
);
const filename = output.trim().split(/\r?\n/).at(-1);
if (!filename?.endsWith(".tgz")) throw new Error("npm pack did not return a tarball");

rmSync(tarballPath, { force: true });
renameSync(join(packageDir, filename), tarballPath);

try {
  console.log("[sdk:refresh] validate local tarball");
  extractAndValidatePackage();

  removePackage(installedPackagePath);
  invalidateInstalledPackageMetadata();
  console.log("[sdk:refresh] install local tarball dependencies");
  npm(["install", "--no-audit", "--no-fund"], projectDir);

  removePackage(installedPackagePath);
  cpSync(extractionPath, installedPackagePath, { recursive: true, force: true });
  console.log("[sdk:refresh] installed verified local package");
} finally {
  rmSync(extractionPath, { recursive: true, force: true });
}
