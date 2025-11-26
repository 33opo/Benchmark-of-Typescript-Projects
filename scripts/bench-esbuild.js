const { execSync } = require("child_process");
const { readdirSync, writeFileSync, statSync } = require("fs");
const { join, basename } = require("path");

const ROOT = process.cwd();
const PROJECTS_DIR = join(ROOT, "projects");
const LOGS_DIR = join(ROOT, "logs");

const entries = readdirSync(PROJECTS_DIR).filter(n => {
    try { return statSync(join(PROJECTS_DIR, n)).isDirectory(); } catch { return false; }
});

const results = [];
for (const name of entries) {
    const dir = join(PROJECTS_DIR, name);
    const label = `${name}__esbuild`;
    console.log(`=== ${name}: esbuild ===`);
    
    // Find all TS files to use as entry points (simplistic, but effective for benchmarking)
    let tsFiles = execSync(`find . -name "*.ts" -not -path "./node_modules/*" -not -path "./dist/*"`, { cwd: dir, encoding: "utf8" }).split('\n').filter(Boolean);
    if (tsFiles.length === 0) {
        console.log(`No .ts files found for ${name}, skipping.`);
        continue;
    }
    
    // Execute esbuild.
    // The main metric is wall clock time (t1 - t0) and output file size.
    const t0 = Date.now();
    let exitCode = 0;
    let outputSizeKB = 0;
    let log = '';
    
    try {
        // Use esbuild's --bundle, --outdir=out_esbuild, and suppress stdout
        const esbuild_command = `npx --yes -p esbuild@latest esbuild ${tsFiles.join(' ')} --bundle --outdir=out_esbuild --platform=node --format=cjs`;
        execSync(esbuild_command, { cwd: dir, stdio: 'pipe' });
        
        // Calculate output directory size
        const outDir = join(dir, 'out_esbuild');
        const sizeBytes = parseInt(execSync(`du -sh ${outDir} | cut -f1`, { encoding: 'utf8' }).replace(/k/i, '000'), 10);
        outputSizeKB = Math.round(sizeBytes / 1024);
    } catch (e) {
        exitCode = 1;
        log = e.message;
        console.warn(`esbuild failed for ${name}: ${e.message}`);
    }
    const t1 = Date.now();
    
    results.push({ 
        project: name, 
        tool: "esbuild", 
        exitCode: exitCode, 
        wallMs: t1 - t0, 
        outputSizeKB: outputSizeKB,
        log: log 
    });
}

writeFileSync(join(LOGS_DIR, "esbuild-summary.json"), JSON.stringify(results, null, 2));
console.log("\nWrote logs/esbuild-summary.json");