"""本番の /label/ で付けたラベルを、R2 から直接読んで保存する（読むだけ。R2 の中身は変えない）。

本番の API（/api/label/export）と同じ形の JSON にするので、そのまま書き出しに使える:
  python ml/tools/fetch_labels_r2.py
  python ml/tools/export_dataset.py --labels ml/data/labels/r2-latest.json

R2 の鍵の渡し方: ml/r2.env というファイルに書く（Git には入らない。.gitignore 済み）か、同じ名前の環境変数にする。
もらったものによって、次のどちらか。

A. Cloudflare の API トークン（curl ... -H "Authorization: Bearer <トークン>" の形でもらったとき）
     R2_API_TOKEN=<Bearer のあとの文字列>
     R2_ACCOUNT_ID=<Cloudflare のアカウント ID（32 文字の英数字）>   # わからなければ書かない（自動で探す）
   トークンから R2 の鍵の組を作る（Cloudflare の決まり: アクセスキー ID ＝ トークンの ID、
   シークレット ＝ トークンの SHA-256）。トークンに R2 を読む権限が要る。
B. R2 の鍵の組（アクセスキー ID とシークレットアクセスキー）でもらったとき
     R2_ACCOUNT_ID=<アカウント ID>
     R2_ACCESS_KEY_ID=<アクセスキー ID>
     R2_SECRET_ACCESS_KEY=<シークレットアクセスキー>
どちらも、R2_BUCKET（省略すると ito-drawing）と、アカウント ID の代わりの
R2_ENDPOINT=https://<アカウントID>.r2.cloudflarestorage.com が使える。

置き場（back/src/labeling.py が書く）:
  labels/<label_set>/raters.json      {"raters": {キー: 名前}}
  labels/<label_set>/r/<キー>.json     {"rater": 名前, "labels": {画像の id: {"label", "ms", "at"}}}

要るもの: python -m pip install boto3
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ito_ml.manifest import DATA_DIR, ML_DIR  # noqa: E402

ENV_FILE = ML_DIR / "r2.env"
OUT_DIR = DATA_DIR / "labels"


def read_settings() -> dict[str, str]:
    settings = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                key, value = line.split("=", 1)
                settings[key.strip()] = value.strip().strip('"').strip("'")
    for key in ("R2_API_TOKEN", "R2_ACCOUNT_ID", "R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
                "R2_BUCKET"):
        if os.environ.get(key):
            settings[key] = os.environ[key]
    settings.setdefault("R2_BUCKET", "ito-drawing")
    token = settings.get("R2_API_TOKEN")
    if token and not settings.get("R2_ACCESS_KEY_ID"):
        settings.update(keys_from_token(token))
        if not settings.get("R2_ENDPOINT") and not settings.get("R2_ACCOUNT_ID"):
            settings["R2_ACCOUNT_ID"] = find_account_id(token)
    if not settings.get("R2_ENDPOINT") and settings.get("R2_ACCOUNT_ID"):
        settings["R2_ENDPOINT"] = f"https://{settings['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
    missing = [k for k in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY") if not settings.get(k)]
    if missing:
        raise SystemExit(f"R2 の設定が足りません: {', '.join(missing)}（{ENV_FILE} に書く。使い方はこのファイルの先頭）")
    return settings


def _cloudflare_api(path: str, token: str) -> dict:
    request = urllib.request.Request(f"https://api.cloudflare.com/client/v4/{path}",
                                     headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        body = json.loads(error.read() or b"{}")
        messages = "; ".join(e.get("message", "") for e in body.get("errors", []))
        raise SystemExit(f"Cloudflare の API がエラーを返しました（{error.code}: {messages}）。"
                         "トークンの写し間違い（前後の空白など）か、期限切れ・取り消しを確かめる") from None


def keys_from_token(token: str) -> dict[str, str]:
    """API トークンから、R2（S3 の形の API）の鍵の組を作る"""
    result = _cloudflare_api("user/tokens/verify", token)["result"]
    if result.get("status") != "active":
        raise SystemExit(f"トークンが使えない状態です（{result.get('status')}）")
    return {"R2_ACCESS_KEY_ID": result["id"], "R2_SECRET_ACCESS_KEY": hashlib.sha256(token.encode()).hexdigest()}


def find_account_id(token: str) -> str:
    """トークンで見えるアカウントが 1 つなら、その ID"""
    accounts = _cloudflare_api("accounts", token).get("result") or []
    if len(accounts) == 1:
        return accounts[0]["id"]
    raise SystemExit("アカウント ID がわかりません。R2_ACCOUNT_ID を ml/r2.env に書く"
                     "（インフラ担当に聞くか、Cloudflare の画面の R2 の概要ページの右側にある）")


def to_export(label_set: str, raters: dict[str, str], files: dict[str, dict]) -> dict:
    """R2 のファイルを、/api/label/export と同じ形にする。files: {キー: r/<キー>.json の中身}"""
    rows = []
    for key, name in raters.items():
        data = files.get(key)
        if not data:
            continue
        for item_id, entry in data.get("labels", {}).items():
            rows.append({"item_id": item_id, "rater": data.get("rater", name), **entry})
    rows.sort(key=lambda r: r.get("at") or "")
    return {"label_set": label_set, "labels": rows}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    import boto3
    from botocore.exceptions import ClientError

    settings = read_settings()
    label_set = json.loads((ML_DIR / "labeling" / "config.json").read_text(encoding="utf-8"))["label_set"]
    s3 = boto3.client("s3", endpoint_url=settings["R2_ENDPOINT"], region_name="auto",
                      aws_access_key_id=settings["R2_ACCESS_KEY_ID"],
                      aws_secret_access_key=settings["R2_SECRET_ACCESS_KEY"])
    bucket, prefix = settings["R2_BUCKET"], f"labels/{label_set}"

    def get(key: str) -> dict | None:
        try:
            return json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise

    index = get(f"{prefix}/raters.json")
    if index is None:
        raise SystemExit(f"{bucket}/{prefix}/raters.json がありません（まだだれも付けていないか、label_set が違う）")
    files = {key: get(f"{prefix}/r/{key}.json") for key in index["raters"]}
    export = to_export(label_set, index["raters"], files)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(export, ensure_ascii=False)
    path = OUT_DIR / f"r2-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(text, encoding="utf-8")
    (OUT_DIR / "r2-latest.json").write_text(text, encoding="utf-8")
    counts = {}
    for row in export["labels"]:
        counts[row["rater"]] = counts.get(row["rater"], 0) + 1
    print(f"ラベル {len(export['labels'])} 個（{len(index['raters'])} 人: {counts}）→ {path}")
    print(f"  同じものを {OUT_DIR / 'r2-latest.json'} にも置いた")


if __name__ == "__main__":
    main()
