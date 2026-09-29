# 每日简报 · 维护说明（给 Claude）

用户（伦敦 Canning Town，GTV 申请中，摄影师）通过手机对话（打字/语音）让你管理日程。
你要把口头的新安排写进 `data/*.json`，其余由 GitHub Actions 自动生成 `docs/`（GitHub Pages）。

## 数据文件
- `data/tasks.json`：`tasks[]` 单次安排 `{id,date(YYYY-MM-DD),time(HH:MM 可空),duration_min,title,type,done}`；`daily[]` 每日/每周重复（`weekdays` 0=周一）。
- `data/gtv.json`：`tracks[]`（A–E），每个含 `items[]`：`{name,status,note}`，`status` ∈ done / submitted / in_progress / todo / watching / blocked。
- `data/competitions.json`：`{name,deadline(可null),theme,status(watching/preparing/submitted/closed),url}`。
- `data/events.json`：伦敦活动 `{title,start,end,place,note,url}`。
- `data/profile.json`：出发地、最佳拍摄窗口。

## 规则
- 时区 Europe/London，日期 ISO。用户说“下周三”“明天”时先换算成具体日期再写入。
- **16:00–18:00 是最佳拍摄光线，不是出门时间**；出门需提前 1–2 小时，16:00 前到达机位（脚本已按此倒排）。
- 有冲突（如 14:00–18:00 有会议）时先告诉用户，再决定是否移动外拍。
- 改完数据：运行 `python scripts/build_brief.py` 自查，然后提交并推送到 `main`（推送 `data/**` 会自动触发重建页面）。回复用户时简短确认改了什么。
- 用户问“今天有什么安排”时，读 `docs/brief.json` 直接回答。

## 每日同步 GTV（Google Drive → 仓库）
- 唯一数据源：用户 Google Drive 里的文档「GTV申请进度」（用 Drive 连接器按标题搜索；表格「GTV申请计划进度」已弃用，不要读）。
- 每天早上（伦敦时间约 07:20，赶在 08:00 简报之前）：读该文档，与 `data/gtv.json`、`data/competitions.json` 对比；有变化才更新并推送到 `main`，无变化不提交。
- **仓库是公开的**：只同步进度状态和事项名称。不要写入用户姓名、推荐人姓名、花费金额、地址等个人信息。
- 文档里的 Track 项映射到 `gtv.json` 的 `tracks[].items[]`；奖项的投递状态同步到 `competitions.json`。更新 `synced` 为当天日期。
