#!/usr/bin/env python3
"""Generate the daily brief (docs/index.html + docs/brief.json) from data/*.json.

Usage:
  python scripts/build_brief.py                  # today, live weather (Open-Meteo)
  python scripts/build_brief.py --date 2026-10-02
  python scripts/build_brief.py --mock clear|partly|cloudy|rain   # offline test weather
"""
import argparse
import html
import json
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
STATUS_LABEL = {"done": "已完成", "in_progress": "进行中", "todo": "未开始", "blocked": "受阻"}
STATUS_WEIGHT = {"done": 1.0, "in_progress": 0.5, "todo": 0.0, "blocked": 0.0}


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def hm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def fmt(minutes):
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# ---------------------------------------------------------------- weather
def fetch_weather(profile, day):
    home = profile["home"]
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={home['lat']}&longitude={home['lon']}"
        "&hourly=temperature_2m,precipitation_probability,cloud_cover,visibility,weather_code"
        "&daily=sunrise,sunset,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        f"&timezone={profile['timezone']}&start_date={day}&end_date={day}"
    )
    with urllib.request.urlopen(url, timeout=20) as r:
        raw = json.load(r)
    hourly = {}
    for i, t in enumerate(raw["hourly"]["time"]):
        hourly[int(t[11:13])] = {
            "temp": raw["hourly"]["temperature_2m"][i],
            "rain": raw["hourly"]["precipitation_probability"][i] or 0,
            "cloud": raw["hourly"]["cloud_cover"][i] or 0,
            "vis": raw["hourly"]["visibility"][i] or 10000,
        }
    d = raw["daily"]
    return {
        "source": "Open-Meteo",
        "sunrise": d["sunrise"][0][11:16],
        "sunset": d["sunset"][0][11:16],
        "tmax": d["temperature_2m_max"][0],
        "tmin": d["temperature_2m_min"][0],
        "rain_max": d["precipitation_probability_max"][0],
        "hourly": hourly,
    }


def mock_weather(kind, day):
    presets = {
        "clear": (5, 0, 12000, 17),
        "partly": (45, 10, 15000, 16),
        "cloudy": (90, 20, 12000, 15),
        "rain": (100, 80, 4000, 13),
    }
    cloud, rain, vis, temp = presets[kind]
    return {
        "source": f"mock:{kind}",
        "sunrise": "06:55",
        "sunset": "18:30",
        "tmax": temp + 2,
        "tmin": temp - 4,
        "rain_max": rain,
        "hourly": {h: {"temp": temp, "rain": rain, "cloud": cloud, "vis": vis} for h in range(24)},
    }


def shoot_assessment(weather, window, min_score):
    """Score the best-light window 0-100 and label the sky."""
    hrs = range(hm(window["start"]) // 60, (hm(window["end"]) + 59) // 60)
    pts = [weather["hourly"][h] for h in hrs if h in weather["hourly"]]
    if not pts:
        return None
    rain = max(p["rain"] for p in pts)
    cloud = sum(p["cloud"] for p in pts) / len(pts)
    vis = min(p["vis"] for p in pts)
    score = 100.0
    score -= rain * 0.8
    # some cloud is good for drama; a fully overcast or fully empty sky is slightly worse
    score -= abs(cloud - 40) * 0.25
    if vis < 8000:
        score -= (8000 - vis) / 100
    score = max(0, min(100, round(score)))
    if rain >= 50:
        sky = "rain"
    elif cloud < 25:
        sky = "clear"
    elif cloud < 70:
        sky = "partly"
    else:
        sky = "cloudy"
    return {"score": score, "sky": sky, "rain": rain, "cloud": round(cloud), "vis": vis,
            "good": score >= min_score and sky != "rain"}


# ------------------------------------------------------------------ logic
def tasks_for(day, tasks_data):
    iso = day.isoformat()
    out = [t for t in tasks_data.get("tasks", []) if t.get("date") == iso]
    for t in tasks_data.get("daily", []):
        days = t.get("weekdays")  # optional list of 0-6 (Mon=0)
        if days is None or day.weekday() in days:
            out.append({**t, "date": iso})
    return sorted(out, key=lambda t: t.get("time") or "99:99")


def conflicts(task_list, start, end):
    hit = []
    for t in task_list:
        if t.get("done") or not t.get("time"):
            continue
        s = hm(t["time"])
        e = s + int(t.get("duration_min", 60))
        if s < end and e > start:
            hit.append(t)
    return hit


def plan_route(day, profile, weather, assessment, task_list, templates):
    win = profile["best_light_window"]
    w_start, w_end = hm(win["start"]), hm(win["end"])
    buffer_min = profile.get("leave_early_min", 90)
    if assessment is None:
        return {"go": False, "reason": "暂无天气数据，无法判断是否适合拍摄。"}
    if not assessment["good"]:
        why = "下雨概率高" if assessment["sky"] == "rain" else "光线/能见度评分偏低"
        return {"go": False, "reason": f"{why}（评分 {assessment['score']}），建议改为室内或看展。",
                "indoor": next((t for t in templates if t["id"] == "indoor"), None)}
    pool = [t for t in templates if assessment["sky"] in t["best_for"]] or templates
    pick = pool[day.toordinal() % len(pool)]  # rotate so days differ
    depart = w_start - pick["travel_min"] - buffer_min
    clash = conflicts(task_list, depart, w_end)
    if clash:
        names = "、".join(f"{t['time']} {t['title']}" for t in clash)
        return {"go": False, "reason": f"{fmt(depart)}–{fmt(w_end)} 与日程冲突：{names}。"}
    return {
        "go": True,
        "route": pick,
        "depart": fmt(depart),
        "arrive": fmt(depart + pick["travel_min"]),
        "spot_ready": fmt(w_start - 15),
        "shoot_start": win["start"],
        "shoot_end": win["end"],
        "sunset": weather["sunset"],
        "buffer_min": buffer_min,
    }


def gtv_summary(gtv):
    stages = gtv["stages"]
    pct = round(100 * sum(STATUS_WEIGHT.get(s["status"], 0) for s in stages) / max(1, len(stages)))
    return pct


def upcoming(items, day, key, horizon=60):
    out = []
    for it in items:
        try:
            d = date.fromisoformat(it[key])
        except (KeyError, ValueError, TypeError):
            continue
        delta = (d - day).days
        if 0 <= delta <= horizon:
            out.append({**it, "days_left": delta})
    return sorted(out, key=lambda x: x["days_left"])


def build(day, weather, profile):
    gtv = load("gtv.json")
    comps = load("competitions.json")["competitions"]
    tasks_data = load("tasks.json")
    events = load("events.json")["events"]
    templates = json.loads((ROOT / "scripts" / "route_templates.json").read_text(encoding="utf-8"))

    task_list = tasks_for(day, tasks_data)
    assessment = shoot_assessment(weather, profile["best_light_window"], profile["min_shoot_score"]) if weather else None
    route = plan_route(day, profile, weather, assessment, task_list, templates)

    today_events = [e for e in events if e.get("start", "") <= day.isoformat() <= e.get("end", e.get("start", ""))]
    soon_events = [e for e in upcoming(events, day, "start", 14) if e not in today_events and e["days_left"] > 0]
    active_comps = [c for c in comps if c.get("status") not in ("submitted", "closed")]

    return {
        "date": day.isoformat(),
        "weekday": WEEKDAYS[day.weekday()],
        "generated_at": datetime.now(ZoneInfo(profile["timezone"])).isoformat(timespec="minutes"),
        "weather": {k: v for k, v in (weather or {}).items() if k != "hourly"} if weather else None,
        "shoot": assessment,
        "tasks": task_list,
        "gtv": {**gtv, "percent": gtv_summary(gtv)},
        "competitions": upcoming(active_comps, day, "deadline", 90),
        "events_today": today_events,
        "events_soon": soon_events,
        "route": route,
    }


# ------------------------------------------------------------------- html
def e(x):
    return html.escape(str(x))


def render(b):
    parts = []
    w, s, r = b["weather"], b["shoot"], b["route"]

    # weather
    if w and s:
        sky = {"clear": "晴朗", "partly": "多云间晴", "cloudy": "阴天", "rain": "有雨"}[s["sky"]]
        verdict = "适合拍摄" if s["good"] else "不太适合户外拍摄"
        parts.append(
            f'<section><h2>🌤 天气 · 拍摄条件</h2><p class="big">{sky} · {w["tmin"]:.0f}–{w["tmax"]:.0f}°C</p>'
            f'<p>16–18 点：降雨概率 {s["rain"]}% · 云量 {s["cloud"]}% · 评分 <b>{s["score"]}</b>（{verdict}）</p>'
            f'<p class="muted">日出 {w["sunrise"]} · 日落 {w["sunset"]}</p></section>'
        )
    else:
        parts.append('<section><h2>🌤 天气</h2><p class="muted">天气数据暂时获取失败。</p></section>')

    # route
    if r["go"]:
        rt = r["route"]
        spots = "".join(f"<li>{e(x)}</li>" for x in rt["spots"])
        parts.append(
            f'<section class="hl"><h2>📷 今日拍摄路线</h2><p class="big">{e(rt["name"])}</p>'
            f'<ul class="times"><li><b>{r["depart"]}</b> 从 Canning Town 出发（提前约 {r["buffer_min"]} 分钟缓冲）</li>'
            f'<li><b>{r["arrive"]}</b> 到达 · {e(rt["transport"])}</li>'
            f'<li><b>{r["spot_ready"]}</b> 选好机位、踩点完毕</li>'
            f'<li><b>{r["shoot_start"]}–{r["shoot_end"]}</b> 最佳光线拍摄（日落 {r["sunset"]}）</li></ul>'
            f'<p>机位：</p><ul>{spots}</ul><p class="muted">{e(rt["tip"])}</p></section>'
        )
    else:
        alt = ""
        if r.get("indoor"):
            i = r["indoor"]
            alt = f'<p>备选：{e(i["name"])}（{e(i["tip"])}）</p>'
        parts.append(f'<section><h2>📷 今日拍摄</h2><p>今天不安排外拍。{e(r["reason"])}</p>{alt}</section>')

    # tasks
    if b["tasks"]:
        items = "".join(
            f'<li class="{"done" if t.get("done") else ""}"><b>{e(t.get("time") or "全天")}</b> {e(t["title"])}</li>'
            for t in b["tasks"]
        )
    else:
        items = '<li class="muted">今天没有安排，告诉 Claude 添加即可。</li>'
    parts.append(f'<section><h2>✅ 今日日程</h2><ul>{items}</ul></section>')

    # gtv
    g = b["gtv"]
    rows = "".join(
        f'<li><span class="tag {e(st["status"])}">{STATUS_LABEL.get(st["status"], st["status"])}</span> '
        f'{e(st["name"])}{" · 截止 " + e(st["due"]) if st.get("due") else ""}'
        f'<div class="muted">{e(st.get("next_step", ""))}</div></li>'
        for st in g["stages"]
    )
    parts.append(
        f'<section><h2>🛂 GTV 申请进度 · {g["percent"]}%</h2>'
        f'<div class="bar"><i style="width:{g["percent"]}%"></i></div><ul>{rows}</ul></section>'
    )

    # competitions
    if b["competitions"]:
        rows = "".join(
            f'<li><b>{c["days_left"]} 天</b> {e(c["name"])} · 截止 {e(c["deadline"])}'
            f'{" · " + e(c["theme"]) if c.get("theme") else ""}</li>'
            for c in b["competitions"]
        )
    else:
        rows = '<li class="muted">暂无即将截止的比赛。</li>'
    parts.append(f'<section><h2>🏆 摄影比赛</h2><ul>{rows}</ul></section>')

    # events
    ev = "".join(
        f'<li><b>今天</b> {e(x["title"])} · {e(x.get("place", ""))}<div class="muted">{e(x.get("note", ""))}</div></li>'
        for x in b["events_today"]
    ) + "".join(
        f'<li><b>{x["days_left"]} 天后</b> {e(x["title"])} · {e(x.get("place", ""))}</li>' for x in b["events_soon"]
    )
    parts.append(f'<section><h2>🎟 伦敦活动</h2><ul>{ev or "<li class=muted>近期没有记录的活动。</li>"}</ul></section>')

    body = "\n".join(parts)
    return TEMPLATE.replace("{{TITLE}}", f'{b["date"]} {b["weekday"]}').replace("{{BODY}}", body).replace(
        "{{GEN}}", e(b["generated_at"])
    )


TEMPLATE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>每日简报</title>
<link rel="manifest" href="manifest.json">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="每日简报">
<meta name="theme-color" content="#111827">
<style>
:root{--bg:#f6f7f9;--card:#fff;--fg:#111827;--mut:#6b7280;--acc:#2563eb;--line:#e5e7eb}
@media (prefers-color-scheme:dark){:root{--bg:#0b0f17;--card:#141a25;--fg:#e5e7eb;--mut:#9ca3af;--acc:#60a5fa;--line:#232b3a}}
*{box-sizing:border-box;overflow-wrap:anywhere}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,system-ui,sans-serif;padding:16px}
main{max-width:640px;margin:0 auto}h1{font-size:22px;margin:8px 0 16px}
section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin-bottom:12px}
section.hl{border-color:var(--acc)}h2{font-size:15px;margin:0 0 8px}ul{margin:6px 0;padding-left:20px}
.times{list-style:none;padding:0}.big{font-size:18px;font-weight:600;margin:4px 0}.muted{color:var(--mut);font-size:14px}
.done{text-decoration:line-through;color:var(--mut)}.bar{height:8px;background:var(--line);border-radius:6px;overflow:hidden;margin:6px 0 10px}
.bar i{display:block;height:100%;background:var(--acc)}.tag{font-size:12px;padding:1px 8px;border-radius:9px;background:var(--line)}
.tag.done{background:#16a34a;color:#fff;text-decoration:none}.tag.in_progress{background:var(--acc);color:#fff}
footer{text-align:center;color:var(--mut);font-size:12px;margin:16px 0 32px}
</style></head><body><main>
<h1>📅 {{TITLE}}</h1>
{{BODY}}
<footer>生成于 {{GEN}}</footer>
</main></body></html>
"""

MANIFEST = {
    "name": "每日简报",
    "short_name": "简报",
    "start_url": "./index.html",
    "display": "standalone",
    "background_color": "#111827",
    "theme_color": "#111827",
    "icons": [],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--mock", choices=["clear", "partly", "cloudy", "rain"])
    ap.add_argument("--out", default=str(DOCS))
    args = ap.parse_args()

    profile = load("profile.json")
    tz = ZoneInfo(profile["timezone"])
    day = date.fromisoformat(args.date) if args.date else datetime.now(tz).date()

    weather = None
    try:
        weather = mock_weather(args.mock, day) if args.mock else fetch_weather(profile, day)
    except Exception as exc:  # network failure must not block the brief
        print(f"weather unavailable: {exc}")

    brief = build(day, weather, profile)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "brief.json").write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "index.html").write_text(render(brief), encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(MANIFEST, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"brief written for {day} -> {out}")


if __name__ == "__main__":
    main()
