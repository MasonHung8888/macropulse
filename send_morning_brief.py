#!/usr/bin/env python3
"""
MacroPulse 每日 07:30 晨報推播腳本 (Telegram / Discord Webhook)
讀取最新驗證通過的 bond_war_room_data.json、tw_bottom_data.json 與 macro_live_data.json，
組合繁體中文摘要並推播至環境變數設定的 Webhook；未設定密鑰時安全略過（exit 0）。
"""

import json
import os
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _load(name: str) -> dict:
    path = os.path.join(SCRIPT_DIR, name)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_brief() -> str:
    bw = _load("bond_war_room_data.json")
    tw = _load("tw_bottom_data.json")
    macro = _load("macro_live_data.json")

    bw_sum = bw.get("summary", {})
    yc = bw.get("yield_curve", {})
    tw_score = tw.get("model_score", {})
    taiex = tw.get("indices", {}).get("twse", {}).get("taiex", {})
    erp = macro.get("equity_risk_premium", {})

    lines = [
        f"📊 **MacroPulse 每日晨報 ({bw.get('as_of', '—')})**",
        "",
        f"🛡 **美債戰情室**：壓力 **{bw_sum.get('stress_score', '—')}/100** · {bw_sum.get('regime', '—')}",
        f"   └ {bw_sum.get('conclusion', '')}",
        f"📈 **美債 2s10s 利差**：{yc.get('spread_2s10s_bps', '—')} bps（{'倒掛' if yc.get('is_inverted') else '正斜率'}）",
        f"⚖️ **美股 ERP**：{erp.get('erp', '—')}%（SPY P/E {erp.get('sp500_forward_pe', '—')}x vs 10Y {erp.get('us10y_yield', '—')}%）",
        f"🇹🇼 **台股加權 (TAIEX)**：{taiex.get('close', '—')}（{taiex.get('change_pct', '—')}%）｜底部評分 **{tw_score.get('total_score', '—')}/100**（{tw_score.get('stage', '—')}）",
    ]
    return "\n".join(lines)


def send_telegram(text: str, token: str, chat_id: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        print("Telegram 推播完成:", r.status)


def send_discord(text: str, webhook_url: str):
    payload = json.dumps({"content": text}).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "MacroPulse/2.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        print("Discord 推播完成:", r.status)


def main():
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    dc_hook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

    brief = build_brief()
    print(brief)
    if tg_token and tg_chat:
        try:
            send_telegram(brief, tg_token, tg_chat)
        except Exception as exc:
            print(f"Telegram 推播失敗: {exc}")
    if dc_hook:
        try:
            send_discord(brief, dc_hook)
        except Exception as exc:
            print(f"Discord 推播失敗: {exc}")
    if not (tg_token and tg_chat) and not dc_hook:
        print("未設定 TELEGRAM_BOT_TOKEN / DISCORD_WEBHOOK_URL，略過外部推播。")


if __name__ == "__main__":
    main()
