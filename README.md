# 每日 8:00 简报

每天伦敦时间 8:00 由 GitHub Actions 生成 `docs/index.html`：今日日程、GTV 进度、摄影比赛倒计时、天气（Open-Meteo）、伦敦活动，
以及适合外拍时从 Canning Town 出发的路线（16:00–18:00 最佳光线，提前 1–2 小时出发）。

## 一次性设置
1. 把本分支合并到 `main`（定时任务只在默认分支运行）。
2. Settings → Pages → Source: `main` / `/docs`。
3. iPhone Safari 打开 `https://<用户名>.github.io/<仓库名>/` → 分享 → 添加到主屏幕。
4. （可选）secrets：`ANTHROPIC_API_KEY` 启用自动搜索活动；`NTFY_TOPIC` + iPhone 安装 ntfy 启用 8 点推送。

## 更新日程
在 iPhone 的 Claude App 里对本仓库会话直接说话/打字即可，见 `CLAUDE.md`。

本地试跑：`python scripts/build_brief.py --mock clear`
