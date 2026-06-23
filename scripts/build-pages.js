const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const src = path.join(root, "static");
const dest = path.join(root, "dist");

if (!fs.existsSync(src)) {
  console.error("static/ 目录不存在，无法构建");
  process.exit(1);
}

fs.rmSync(dest, { recursive: true, force: true });
fs.mkdirSync(dest, { recursive: true });
fs.cpSync(src, dest, { recursive: true });

console.log("已将 static/ 复制到 dist/，供 Cloudflare Pages 发布。");
