# 判定エンジン（AI 担当）

手書きの「と」（十・都・戸・徒・ト・と）を採点する。

- 幾何スコア: KanjiVG のお手本と照合（画数・書き順・運筆方向・形・バランス・線質・止め/はね/払い）
- LLM（Claude）: ①お題を伏せたブラインド判読と印象、②師範「伊藤先生」の講評
- 統合: `final = 0.45 × 幾何 + 0.35 × LLM美しさ + 0.20 × 意図`。判読がお題と違えば上限 60 点

## API

Swagger UI（`/docs`）に型が出ます。

| メソッド | パス | 内容 |
|---|---|---|
| POST | `/api/judge/geometry` | 幾何スコアのみ（約 100ms） |
| POST | `/api/judge/full` | 幾何 + LLM + 統合（数秒） |
| GET | `/api/refs/{char}` | お手本の点列（0〜1 座標、書き順どおり） |
| POST | `/api/dev/samples` | 検証サンプルを `back/src/eval_data/` に保存（`DEV=1` のときだけ） |

リクエスト例:

```json
{
  "target": "都",
  "intent": "chikarazuyosa",
  "canvas": { "width": 512, "height": 512 },
  "strokes": [
    { "pointerType": "pen", "points": [[x, y, t_ms, pressure], ...] }
  ]
}
```

- 1 画 = `pointerdown` から `pointerup` まで。`getCoalescedEvents()` で点を取ると速度が安定する
- `t` は書き始めからの経過ミリ秒（画ごとにリセットしない）
- `pressure` は省略可
- `intent`: `chikarazuyosa`（力強く）/ `yasashisa`（やさしく）/ `teinei`（丁寧に）/ `genki`（元気よく）/ `yuuga`（優雅に）

## 環境変数

`.env.example` を参照。`ANTHROPIC_API_KEY` が無いと LLM を呼ばず、`degraded: true` で幾何スコアだけを返す。

## 開発（Docker）

```bash
docker compose exec backend python -m pytest src/tests
```

pytest などの開発用ライブラリは `back/requirements-dev.txt` にある（本番イメージには入れない）。

## 開発（Docker が使えない場合、`back/` で）

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # macOS/Linux は .venv/bin/python
.venv/Scripts/python -m pytest src/tests
.venv/Scripts/python -m uvicorn src.main:app --reload --port 8000
```

## お手本データの再生成

```bash
python -m src.judge.tools.build_refs
```

`refs/*.json` を KanjiVG（CC BY-SA 3.0）から生成する。終筆の正解は `refs/endings.yaml` に手で書いている。
