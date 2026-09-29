# 每日简报 · 维护说明（给 Claude）

用户（伦敦 Canning Town，GTV 申请中，摄影师）通过手机对话（打字/语音）让你管理日程。
你要把口头的新安排写进 `data/*.json`，其余由 GitHub Actions 自动生成 `docs/`（GitHub Pages）。

## 数据文件
- `data/tasks.json`：`tasks[]` 单次安排 `{id,date(YYYY-MM-DD),time(HH:MM 可空),duration_min,title,type,done}`；`daily[]` 每日/每周重复（`weekdays` 0=周一）。
- `data/gtv.json`：`stages[]` 的 `status` ∈ todo / in_progress / done / blocked，`due`、`next_step`。
- `data/competitions.json`：`{name,deadline,theme,status(watching/preparing/submitted/closed),url}`。
- `data/events.json`：伦敦活动 `{title,start,end,place,note,url}`。
- `data/profile.json`：出发地、最佳拍摄窗口。

## 规则
- 时区 Europe/London，日期 ISO。用户说“下周三”“明天”时先换算成具体日期再写入。
- **16:00–18:00 是最佳拍摄光线，不是出门时间**；出门需提前 1–2 小时，16:00 前到达机位（脚本已按此倒排）。
- 有冲突（如 14:00–18:00 有会议）时先告诉用户，再决定是否移动外拍。
- 改完数据：运行 `python scripts/build_brief.py` 自查，然后提交并推送到 `main`（推送 `data/**` 会自动触发重建页面）。回复用户时简短确认改了什么。
- 用户问“今天有什么安排”时，读 `docs/brief.json` 直接回答。
