import type { Sock } from "./api/drawings";

/** シェアする画像の大きさ（Instagram の縦長の投稿と同じ 4:5） */
export const CARD_WIDTH = 1080;
export const CARD_HEIGHT = 1350;

const FONT = "system-ui, sans-serif";

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`画像を読めません: ${src}`));
    image.src = src;
  });
}

/** 幅に収まるよう、1 文字ずつ見て行を分ける（日本語は単語の切れ目がないため） */
function wrap(ctx: CanvasRenderingContext2D, text: string, maxWidth: number) {
  const lines: string[] = [];
  let line = "";
  for (const ch of text) {
    // 句読点や閉じかっこは、行の頭に送らない
    if (
      line !== "" &&
      !"。、」".includes(ch) &&
      ctx.measureText(line + ch).width > maxWidth
    ) {
      lines.push(line);
      line = ch;
    } else {
      line += ch;
    }
  }
  if (line !== "") lines.push(line);
  return lines;
}

/**
 * シェアする画像（PNG）を作る。白地に、くつした、書いた「と」、レアリティ、名前、説明を並べる。
 * 見た目は仮のもの。デザインが決まったら、この関数の中身を差し替える。
 *
 * @param drawingImage 書いた「と」の画像（白地に黒の正方形。data URL）
 */
export async function makeShareCard(
  sock: Sock,
  drawingImage: string,
): Promise<Blob> {
  const [sockImage, drawing] = await Promise.all([
    loadImage(sock.image),
    loadImage(drawingImage),
  ]);

  const canvas = document.createElement("canvas");
  canvas.width = CARD_WIDTH;
  canvas.height = CARD_HEIGHT;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas を使えません");
  const center = CARD_WIDTH / 2;

  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, CARD_WIDTH, CARD_HEIGHT);

  // 左にくつした、右に書いた「と」
  ctx.drawImage(sockImage, 50, 110, 660, 660);
  ctx.drawImage(drawing, 730, 290, 290, 290);
  ctx.strokeStyle = "#999";
  ctx.lineWidth = 2;
  ctx.strokeRect(730, 290, 290, 290);

  ctx.textAlign = "center";
  ctx.fillStyle = "#555";
  ctx.font = `30px ${FONT}`;
  ctx.fillText("書いた「と」", 875, 630);

  ctx.font = `36px ${FONT}`;
  ctx.fillText(sock.rarity, center, 890);

  ctx.fillStyle = "#222";
  ctx.font = `bold 72px ${FONT}`;
  ctx.fillText(sock.name, center, 990);

  ctx.font = `36px ${FONT}`;
  wrap(ctx, sock.comment, CARD_WIDTH - 240)
    .slice(0, 3)
    .forEach((line, i) => ctx.fillText(line, center, 1070 + i * 56));

  ctx.fillStyle = "#555";
  ctx.font = `30px ${FONT}`;
  ctx.fillText("ITO", center, 1290);

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("画像を作れません"))),
      "image/png",
    );
  });
}

/**
 * くつしたごとのシェア用のアドレス（例: https://…/s/worn-01/）。
 * このページには、X などがカードとして出す画像の指定（OGP）が書いてある。
 * 人が開くと、最初の画面に移る。ページは scripts/build-share.py が作る。
 */
export function sharePageUrl(sock: Sock): string {
  return `${window.location.origin}/s/${sock.id.toLowerCase()}/`;
}
