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

# 国コード → 国名（国または地域名称）
COUNTRY_CODE_MAP = {
    "0060": "マレーシア",
    "0062": "インドネシア",
    "0063": "フィリピン",
    "0065": "シンガポール",
    "0066": "タイ",
    "0082": "大韓民国／韓国",
    "0084": "ベトナム",
    "0086": "中華人民共和国／中国",
    "0091": "インド",
    "0092": "パキスタン",
    "0094": "スリランカ",
    "0095": "ミャンマー",
    "0670": "東ティモール",
    "0673": "ブルネイ",
    "0850": "北朝鮮",
    "0852": "香港",
    "0853": "マカオ",
    "0855": "カンボジア",
    "0856": "ラオス",
    "0880": "バングラデシュ",
    "0886": "台湾",
    "0960": "モルディブ",
    "0975": "ブータン",
    "0976": "モンゴル",
    "0977": "ネパール",

    "0061": "オーストラリア／豪州",
    "0064": "ニュージーランド",
    "0674": "ナウル",
    "0675": "パプアニューギニア",
    "0676": "トンガ",
    "0677": "ソロモン諸島",
    "0678": "バヌアツ",
    "0679": "フィジー",
    "0680": "パラオ",
    "0682": "クック諸島",
    "0683": "ニウエ",
    "0685": "サモア独立国",
    "0686": "キリバス",
    "0687": "ニューカレドニア（仏領）",
    "0688": "ツバル",
    "0691": "ミクロネシア",
    "0692": "マーシャル諸島",
    "1001": "アメリカ合衆国／米国（北マリアナ諸島）",
    "1002": "アメリカ合衆国／米国（グアム）",
    "1684": "サモア（米領）",
    "9689": "タヒチ（仏領ポリネシア）",

    "1000": "アメリカ合衆国／米国（本土）",
    "1808": "アメリカ合衆国／米国（ハワイ）",
    "9001": "カナダ",

    "0051": "ペルー",
    "0052": "メキシコ",
    "0053": "キューバ",
    "0054": "アルゼンチン",
    "0055": "ブラジル",
    "0056": "チリ",
    "0057": "コロンビア",
    "0058": "ベネズエラ",
    "0473": "グレナダ",
    "0501": "ベリーズ",
    "0502": "グアテマラ",
    "0503": "エルサルバドル",
    "0504": "ホンジュラス",
    "0505": "ニカラグア",
    "0506": "コスタリカ",
    "0507": "パナマ",
    "0509": "ハイチ",
    "0591": "ボリビア",
    "0592": "ガイアナ",
    "0593": "エクアドル",
    "0595": "パラグアイ",
    "0597": "スリナム",
    "0598": "ウルグアイ",
    "0758": "セントルシア",
    "0767": "ドミニカ国",
    "0784": "セントビンセント及びグレナディーン諸島",
    "0809": "ドミニカ共和国",
    "0868": "トリニダード・トバゴ",
    "0869": "セントクリストファー・ネービス",
    "0876": "ジャマイカ",
    "1242": "バハマ",
    "1246": "バルバドス",
    "1268": "アンティグア・バーブーダ",

    "0007": "カザフスタン",
    "0030": "ギリシャ",
    "0031": "オランダ",
    "0032": "ベルギー",
    "0033": "フランス",
    "0034": "スペイン",
    "0036": "ハンガリー",
    "0039": "イタリア",
    "0040": "ルーマニア",
    "0041": "スイス",
    "0043": "オーストリア",
    "0044": "英国／イギリス／グレートブリテン及び北部アイルランド連合王国",
    "0045": "デンマーク",
    "0046": "スウェーデン",
    "0047": "ノルウェー",
    "0048": "ポーランド",
    "0049": "ドイツ",
    "0351": "ポルトガル",
    "0352": "ルクセンブルク",
    "0353": "アイルランド",
    "0354": "アイスランド",
    "0355": "アルバニア",
    "0356": "マルタ",
    "0357": "キプロス／サイプラス",
    "0358": "フィンランド",
    "0359": "ブルガリア",
    "0370": "リトアニア",
    "0371": "ラトビア",
    "0372": "エストニア",
    "0373": "モルドバ",
    "0374": "アルメニア",
    "0375": "ベラルーシ",
    "0376": "アンドラ",
    "0377": "モナコ",
    "0378": "サンマリノ",
    "0380": "ウクライナ",
    "0381": "セルビア",
    "0382": "モンテネグロ",
    "0385": "クロアチア",
    "0386": "スロベニア",
    "0387": "ボスニア・ヘルツェゴビナ",
    "0389": "北マケドニア共和国",
    "0420": "チェコ",
    "0421": "スロバキア",
    "0423": "リヒテンシュタイン",
    "0992": "タジキスタン",
    "0993": "トルクメニスタン",
    "0994": "アゼルバイジャン",
    "0995": "ジョージア（旧グルジア）",
    "0996": "キルギス",
    "0998": "ウズベキスタン",
    "9007": "ロシア",
    "9039": "バチカン市国",
    "9381": "コソボ",

    "0090": "トルコ",
    "0093": "アフガニスタン",
    "0098": "イラン",
    "0961": "レバノン",
    "0962": "ヨルダン",
    "0963": "シリア",
    "0964": "イラク",
    "0965": "クウェート",
    "0966": "サウジアラビア",
    "0967": "イエメン",
    "0968": "オマーン",
    "0970": "パレスチナ",
    "0971": "アラブ首長国連邦",
    "0972": "イスラエル",
    "0973": "バーレーン",
    "0974": "カタール",

    "0020": "エジプト",
    "0027": "南アフリカ共和国",
    "0211": "南スーダン",
    "0212": "モロッコ",
    "0213": "アルジェリア",
    "0216": "チュニジア",
    "0218": "リビア",
    "0220": "ガンビア",
    "0221": "セネガル",
    "0222": "モーリタニア",
    "0223": "マリ",
    "0224": "ギニア",
    "0225": "コートジボワール",
    "0226": "ブルキナファソ",
    "0227": "ニジェール",
    "0228": "トーゴ",
    "0229": "ベナン",
    "0230": "モーリシャス",
    "0231": "リベリア",
    "0232": "シエラレオネ",
    "0233": "ガーナ",
    "0234": "ナイジェリア",
    "0235": "チャド",
    "0236": "中央アフリカ",
    "0237": "カメルーン",
    "0238": "カーボベルデ",
    "0239": "サントメ・プリンシペ",
    "0240": "赤道ギニア",
    "0241": "ガボン",
    "0242": "コンゴ共和国",
    "0243": "コンゴ民主共和国",
    "0244": "アンゴラ",
    "0245": "ギニアビサウ",
    "0248": "セーシェル",
    "0249": "スーダン",
    "0250": "ルワンダ",
    "0251": "エチオピア",
    "0252": "ソマリア",
    "0253": "ジブチ",
    "0254": "ケニア",
    "0255": "タンザニア",
    "0256": "ウガンダ",
    "0257": "ブルンジ",
    "0258": "モザンビーク",
    "0260": "ザンビア",
    "0261": "マダガスカル",
    "0263": "ジンバブエ",
    "0264": "ナミビア",
    "0265": "マラウイ",
    "0266": "レソト",
    "0267": "ボツワナ",
    "0268": "エスワティニ",
    "0269": "コモロ",
    "0291": "エリトリア",
    "9212": "西サハラ",
}

# 種別コード → 種別名
INFO_TYPE_MAP = {
    "T40": "危険情報",
    "T81": "感染症危険情報",
    "C30": "スポット情報",
    "C31": "スポット情報(感染症)",
    "C50": "広域情報",
    "C51": "広域情報(感染症)",
    "R10": "領事メール(一般)",
    "R20": "領事メール(緊急)",
}


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
        code = m["country_cd"] or ""
        # 国名（コード→対応表→なければXMLのcountry_name）
        country_name_from_map = COUNTRY_CODE_MAP.get(code)
        base_country_label = f"国コード: {code}" if code else (m["country_name"] or "国不明")

        # () の中に表示する国名（対応表 → country_name → 空）
        paren_country = country_name_from_map or m["country_name"] or ""

        # 行頭の国表示
        if paren_country:
            first_line_country = f"*{base_country_label}*（{paren_country}）"
        else:
            first_line_country = f"*{base_country_label}*"

        area = m["area_name"] or ""
        ld_str = m["leave_dt"].strftime("%Y/%m/%d %H:%M") if m["leave_dt"] else m["leave_date"]

        # 種別コード → 種別名
        info_type_code = m["info_type"]
        info_type_label = INFO_TYPE_MAP.get(info_type_code)
        if info_type_label:
            type_text = f"{info_type_code}（{info_type_label}）"
        else:
            # infoNameLong が入っていることも多いので fallback で
            fallback = m["info_name_long"] or m["info_name"] or info_type_code
            type_text = f"{info_type_code}（{fallback}）"

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
            f"• {first_line_country}（{area}）\n"
            f"　種別: {type_text}\n"
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
