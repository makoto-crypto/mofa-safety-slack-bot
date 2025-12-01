#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
外務省 海外安全情報オープンデータ newarrivalL.xml を見て、
海外安全情報(危険/感染症危険/スポット/広域)＋在外公館メール(一般/緊急)
が新しく出るたびに Slack に通知するスクリプト。

・対象: newarrivalL.xml に含まれる全 infoType
  - C30: スポット情報
  - T40: 危険情報
  - T41: 感染症危険情報
  - C50: 広域情報
  - R10: 領事メール(一般)
  - R20: 領事メール(緊急)
・GitHub Actions で 5分おき実行を想定
  → 直近 WINDOW_MINUTES 分以内に出たものだけを通知
"""

import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    ZoneInfo = None

# newarrival (軽量版)
MOFA_NEWARRIVAL_URL = "https://www.ezairyu.mofa.go.jp/opendata/area/newarrivalL.xml"

# 「新着」とみなす時間幅（分）
# GitHub Actions を 5 分おきに動かす前提で、少し余裕を持って 10 分に。
WINDOW_MINUTES = 1440

# Slack Webhook URL（GitHub Secret から渡す想定）
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")


def get_now_jst():
    """JSTの現在時刻を返す"""
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo("Asia/Tokyo"))
    else:
        # 古いPythonの場合はUTCのまま使う（多少ずれても致命的ではない）
        return datetime.utcnow()


def fetch_mofa_newarrival():
    """MOFAの新着情報XMLを取得して ElementTree root を返す"""
    resp = requests.get(MOFA_NEWARRIVAL_URL, timeout=10)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    root = ET.fromstring(resp.text)
    return root


def parse_leave_date(leave_date_str: str):
    """leaveDate（YYYY/MM/DD HH:MM:SS）を datetime(JST想定) に変換"""
    if not leave_date_str:
        return None
    try:
        dt = datetime.strptime(leave_date_str, "%Y/%m/%d %H:%M:%S")
        if ZoneInfo is not None:
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Tokyo"))
        return dt
    except Exception:
        return None


def build_slack_text(mails):
    """Slackに送るテキストをまとめて組み立てる"""
    if not mails:
        return None

    now_jst = get_now_jst().strftime("%Y-%m-%d %H:%M")
    lines = [
        "*【外務省 海外安全情報オープンデータ 新着】*",
        f"取得時刻（JST）: {now_jst}",
        "",
    ]

    # 古い順に並び替え
    mails = sorted(mails, key=lambda m: m["leave_dt"])

    for m in mails:
        country = m["country_name"] or f"国コード: {m['country_cd']}"
        area = m["area_name"] or ""
        ld_str = m["leave_dt"].strftime("%Y/%m/%d %H:%M") if m["leave_dt"] else m["leave_date"]

        # infoNameLong 例:
        #   海外安全情報(危険情報)
        #   海外安全情報(スポット情報)
        #   領事メール(一般)
        #   領事メール(緊急)
        info_label = m["info_name_long"] or m["info_name"] or m["info_type"]

        koukan = ""
        if m.get("koukan_name"):
            koukan = f"　発出公館: {m['koukan_name']}（{m.get('koukan_cd','')}）\n"

        # 危険レベル・感染症レベル（Y/N）
        level_parts = []
        if any(m.get(f"risk_level{lv}") == "Y" for lv in (1, 2, 3, 4)):
            lv_str = " / ".join(
                f"L{lv}" for lv in (4, 3, 2, 1) if m.get(f"risk_level{lv}") == "Y"
            )
            level_parts.append(f"危険情報レベル: {lv_str}")
        if any(m.get(f"infection_level{lv}") == "Y" for lv in (1, 2, 3, 4)):
            lv_str_inf = " / ".join(
                f"L{lv}" for lv in (4, 3, 2, 1) if m.get(f"infection_level{lv}") == "Y"
            )
            level_parts.append(f"感染症危険レベル: {lv_str_inf}")
        level_text = ""
        if level_parts:
            level_text = "　" + " / ".join(level_parts) + "\n"

        line = (
            f"• *{country}*（{area}）\n"
            f"　種別: {info_label}（{m['info_type']}）\n"
            f"　日時: {ld_str}\n"
            f"{koukan}"
            f"{level_text}"
            f"　タイトル: {m['title']}\n"
            f"　詳細: {m['info_url']}\n"
        )
        lines.append(line)

    return "\n".join(lines)


def post_to_slack(text: str):
    """Webhook経由でSlackに投稿"""
    if not SLACK_WEBHOOK_URL:
        raise RuntimeError("SLACK_WEBHOOK_URL が環境変数に設定されていません。")

    payload = {
        "text": text,
        # 好みで Bot 名やアイコン設定も可
        # "username": "MOFA Bot",
        # "icon_emoji": ":rotating_light:",
    }
    resp = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
    resp.raise_for_status()


def main():
    root = fetch_mofa_newarrival()
    now_jst = get_now_jst()
    threshold = now_jst - timedelta(minutes=WINDOW_MINUTES)

    target_mails = []

    for mail in root.findall(".//mail"):
        info_type = mail.findtext("infoType", default="")
        info_name = mail.findtext("infoName", default="")
        info_name_long = mail.findtext("infoNameLong", default="")
        leave_date = mail.findtext("leaveDate", default="")
        leave_dt = parse_leave_date(leave_date)

        # WINDOW_MINUTES 以内の新着だけ拾う
        if leave_dt is None or leave_dt < threshold:
            continue

        country_name = mail.findtext("./country/name", default="")
        country_cd = mail.findtext("./country/cd", default="")
        area_name = mail.findtext("./area/name", default="")
        title = mail.findtext("title", default="")
        info_url = mail.findtext("infoUrl", default="")
        koukan_cd = mail.findtext("koukanCd", default="")
        koukan_name = mail.findtext("koukanName", default="")

        # 危険レベル / 感染症レベル（Y/N）
        risk_levels = {
            lv: mail.findtext(f"riskLevel{lv}", default="")
            for lv in (1, 2, 3, 4)
        }
        infection_levels = {
            lv: mail.findtext(f"infectionLevel{lv}", default="")
            for lv in (1, 2, 3, 4)
        }

        obj = {
            "info_type": info_type,
            "info_name": info_name,
            "info_name_long": info_name_long,
            "leave_date": leave_date,
            "leave_dt": leave_dt,
            "country_name": country_name,
            "country_cd": country_cd,
            "area_name": area_name,
            "title": title,
            "info_url": info_url,
            "koukan_cd": koukan_cd,
            "koukan_name": koukan_name,
        }
        # レベル情報を展開
        for lv, val in risk_levels.items():
            obj[f"risk_level{lv}"] = val
        for lv, val in infection_levels.items():
            obj[f"infection_level{lv}"] = val

        target_mails.append(obj)

    if not target_mails:
        print("新着情報（海外安全情報・在外公館メール）はありませんでした。")
        return

    text = build_slack_text(target_mails)
    if text:
        post_to_slack(text)
        print(f"{len(target_mails)} 件の情報を Slack に送信しました。")


if __name__ == "__main__":
    main()
