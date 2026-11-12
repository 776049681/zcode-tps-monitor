#!/usr/bin/env python3
"""ZCode 菜单栏 TPS/首字延迟监控（跟随当前会话版）。

只读 ~/.zcode/cli/db/db.sqlite，零权限、零注入、不碰 ZCode 本体：
- 当前会话 = session.time_updated 最新的会话（在新会话发出第一条消息后自动跟随）
- 菜单栏标题：该会话最近一次有效调用的 模型 / 首字延迟(0.1s) / 纯解码 TPS
- 点开菜单：本次调用明细 + 今日各模型汇总

依赖：pyobjc-framework-Cocoa（macOS 自带 python3 可跑，需 pip 装这一个包）
用法：python3 zmenu_tps.py          # 启动菜单栏监控
      python3 zmenu_tps.py --once   # 打印当前状态并退出（调试用）
"""
import datetime
import os
import sqlite3
import sys
import time

import AppKit as A
import Foundation as F

DB = os.path.expanduser("~/.zcode/cli/db/db.sqlite")
POLL_SECONDS = 2.0
# 免费渠道识别关键字（provider_id 里含它就标"免费"，可按需增删）
FREE_PROVIDER_KEYWORDS = ("start-plan",)

# pyobjc 的坑：方法名以下划线结尾会被当成 action 选择器注册，导致
# BadPrototypeError。所以辅助方法一律不用下划线结尾（如 _add_item 而非 _add）。
MODEL_SHORT = {
    "glm-5.3": "5.3",
    "glm-5.3-flash": "Flash",
    "glm-5.3-flashx": "FlashX",
}


def n(x):
    return x or 0


def ago(age_s):
    if age_s < 60:
        return "刚刚"
    if age_s < 3600:
        return f"{age_s/60:.0f}分"
    if age_s < 86400:
        return f"{age_s/3600:.0f}时"
    return f"{age_s/86400:.0f}天"


def short(model):
    return MODEL_SHORT.get((model or "").lower(), (model or "?")[:8])


def is_free(provider):
    return any(k in (provider or "") for k in FREE_PROVIDER_KEYWORDS)


def fetch():
    """(当前会话 dict, 今日模型摘要 list)；DB 不可读返回 (False, None)。"""
    try:
        db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    except sqlite3.Error:
        return False, None
    midnight = int(datetime.datetime.combine(
        datetime.date.today(), datetime.time.min).timestamp() * 1000)
    try:
        sess = db.execute(
            """SELECT id, title FROM session
               WHERE time_deleted IS NULL ORDER BY time_updated DESC LIMIT 1""").fetchone()
        cur = None
        if sess:
            cnt = db.execute(
                """SELECT count(*) FROM model_usage
                   WHERE session_id=? AND status='completed' AND started_at>=?""",
                (sess[0], midnight)).fetchone()[0]
            cur = {"id": sess[0], "title": sess[1] or "", "today": n(cnt)}
            # 本会话级统计：全部有效调用的加权平均（不限今天）
            agg = db.execute(
                """SELECT count(*), sum(duration_ms), sum(time_to_first_token_ms),
                          sum(output_tokens)
                   FROM model_usage WHERE session_id=? AND status='completed'
                     AND time_to_first_token_ms IS NOT NULL AND time_to_first_token_ms>0""",
                (sess[0],)).fetchone()
            ac, ad, at, ao = n(agg[0]), n(agg[1]) / 1000, n(agg[2]) / 1000, n(agg[3])
            cur.update({
                "avg_count": ac,
                "avg_ttft": at / ac if ac else None,
                "avg_pure": ao / (ad - at) if ac and ad > at > 0 else None,
            })
            # ttft 为 NULL/0 的短应答调用（如一两个 token 的确认回复）无法算
            # 首字/纯解码，直接跳过取上一次有效调用
            row = db.execute(
                """SELECT started_at, duration_ms, time_to_first_token_ms,
                          output_tokens, input_tokens, cache_read_input_tokens,
                          model_id, provider_id
                   FROM model_usage WHERE session_id=? AND status='completed'
                     AND time_to_first_token_ms IS NOT NULL AND time_to_first_token_ms>0
                   ORDER BY started_at DESC LIMIT 1""", (sess[0],)).fetchone()
            if row:
                d, t, o = n(row[1]) / 1000, n(row[2]) / 1000, n(row[3])
                cur.update({
                    "age": time.time() - row[0] / 1000,
                    "model": row[6], "free": is_free(row[7]),
                    "ttft": t if n(row[2]) else None,
                    "pure": o / (d - t) if o and d > t > 0 else None,
                    "e2e": o / d if o and d > 0 else None,
                    "hit": n(row[5]) / n(row[4]) * 100 if n(row[4]) else None,
                })
        models = []
        for r in db.execute(
                """SELECT model_id, provider_id, count(*), sum(duration_ms),
                          sum(time_to_first_token_ms), sum(output_tokens)
                   FROM model_usage WHERE started_at>=? AND status='completed'
                   GROUP BY model_id, provider_id ORDER BY max(started_at) DESC""",
                (midnight,)):
            d, t, o = n(r[3]) / 1000, n(r[4]) / 1000, n(r[5])
            models.append({
                "model": r[0], "free": is_free(r[1]), "count": n(r[2]),
                "pure": o / (d - t) if o and d > t > 0 else None,
            })
    except sqlite3.Error:
        return False, None
    finally:
        db.close()
    return cur, models


def render_text(cur, models):
    """与菜单栏一致的数据整理成多行文本（--once 调试用）。"""
    lines = []
    if cur is False:
        return ["数据库不可读: " + DB]
    if not cur or "model" not in cur:
        head = cur["title"] if cur else "当前会话未知"
        lines.append(f"● {head}")
        lines.append("该会话还没有完成的有效调用")
    else:
        c = cur
        t = f"{c['ttft']:.1f}s" if c.get("ttft") is not None else "—"
        p = f"{c['pure']:.0f}tps" if c.get("pure") else "—"
        name = short(c["model"]) + ("·免" if c.get("free") else "")
        lines.append(f"菜单栏: {name} {t} {p}")
        lines.append(f"● {c['title'][:30]}  ({ago(c['age'])})")
        lines.append(f"模型  {c['model']}" + ("（免费）" if c["free"] else ""))
        lines.append(f"首字延迟  {t}")
        lines.append("TPS 纯解码  " + (f"{c['pure']:.1f}" if c.get("pure") else "—"))
        lines.append("TPS 端到端  " + (f"{c['e2e']:.1f}" if c.get("e2e") else "—"))
        if c.get("hit") is not None:
            lines.append(f"缓存命中  {c['hit']:.0f}%")
        lines.append(f"本会话今日  {c['today']} 次")
        if c.get("avg_count"):
            at = f"{c['avg_ttft']:.1f}s" if c.get("avg_ttft") is not None else "—"
            ap = f"{c['avg_pure']:.1f}" if c.get("avg_pure") is not None else "—"
            lines.append(f"本会话平均  首 {at} · 纯解码 {ap}tps ({c['avg_count']:.0f}次)")
    lines.append("-" * 24)
    for m in models or []:
        tag = "（免费）" if m["free"] else ""
        p = f"{m['pure']:.0f}" if m["pure"] else "—"
        lines.append(f"今日 {short(m['model'])}{tag}  {m['count']}次 · {p}tps")
    return lines


class Delegate(A.NSObject):
    def applicationDidFinishLaunching_(self, note):
        app = A.NSApplication.sharedApplication()
        app.setActivationPolicy_(A.NSApplicationActivationPolicyAccessory)
        self.st = A.NSStatusBar.systemStatusBar().statusItemWithLength_(
            A.NSVariableStatusItemLength)
        self.st.button().setTitle_("Z…")
        self.menu = A.NSMenu.alloc().init()
        self.menu.setDelegate_(self)
        self.menu.setAutoenablesItems_(False)
        self.st.setMenu_(self.menu)
        self.cur = None
        self.models = None
        F.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            POLL_SECONDS, self, "tick:", None, True)
        self.tick_(None)

    def tick_(self, timer):
        cur, models = fetch()
        if cur is False:
            self.cur, self.models = False, None
            self.st.button().setTitle_("Z?")
            return
        self.cur, self.models = cur, models
        if not cur or "model" not in cur:
            self.st.button().setTitle_("Z—")
            return
        t = f"{cur['ttft']:.1f}s" if cur.get("ttft") is not None else "—"
        p = f"{cur['pure']:.0f}tps" if cur.get("pure") else "—"
        name = short(cur["model"]) + ("·免" if cur.get("free") else "")
        self.st.button().setTitle_(f"{name} {t} {p}")

    def _add_item(self, menu, title, action):
        it = A.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            title, action, "")
        it.setEnabled_(action is not None)
        menu.addItem_(it)

    def menuNeedsUpdate_(self, menu):
        while menu.numberOfItems():
            menu.removeItemAtIndex_(0)
        if self.cur is False:
            self._add_item(menu, "数据库不可读", None)
        elif not self.cur or "model" not in self.cur:
            head = f"● {self.cur['title'][:30]}" if self.cur else "当前会话未知"
            self._add_item(menu, head, None)
            self._add_item(menu, "该会话还没有完成的调用", None)
        else:
            c = self.cur
            self._add_item(menu, f"● {c['title'][:30]}  ({ago(c['age'])})", None)
            self._add_item(menu, f"模型  {c['model']}" + ("（免费）" if c["free"] else ""), None)
            t = f"{c['ttft']:.1f}s" if c.get("ttft") is not None else "—"
            self._add_item(menu, f"首字延迟  {t}", None)
            self._add_item(menu, f"TPS 纯解码  {c['pure']:.1f}" if c.get("pure")
                           else "TPS 纯解码  —", None)
            self._add_item(menu, f"TPS 端到端  {c['e2e']:.1f}" if c.get("e2e")
                           else "TPS 端到端  —", None)
            if c.get("hit") is not None:
                self._add_item(menu, f"缓存命中  {c['hit']:.0f}%", None)
            self._add_item(menu, f"本会话今日  {c['today']} 次", None)
            if c.get("avg_count"):
                at = f"{c['avg_ttft']:.1f}s" if c.get("avg_ttft") is not None else "—"
                ap = f"{c['avg_pure']:.1f}" if c.get("avg_pure") is not None else "—"
                self._add_item(menu,
                               f"本会话平均  首 {at} · 纯解码 {ap}tps ({c['avg_count']:.0f}次)",
                               None)
        menu.addItem_(A.NSMenuItem.separatorItem())
        for m in self.models or []:
            tag = "（免费）" if m["free"] else ""
            p = f"{m['pure']:.0f}" if m["pure"] else "—"
            self._add_item(menu, f"今日 {short(m['model'])}{tag}  {m['count']}次 · {p}tps", None)
        if self.models:
            menu.addItem_(A.NSMenuItem.separatorItem())
        self._add_item(menu, "退出", "terminate:")


def main():
    if "--once" in sys.argv:
        for line in render_text(*fetch()):
            print(line)
        return
    app = A.NSApplication.sharedApplication()
    dlg = Delegate.alloc().init()
    app.setDelegate_(dlg)
    app.run()


if __name__ == "__main__":
    main()
