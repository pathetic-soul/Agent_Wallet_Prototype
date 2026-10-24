import fs from "node:fs";

fs.rmSync("out", { recursive: true, force: true });
fs.rmSync("cache", { recursive: true, force: true });

