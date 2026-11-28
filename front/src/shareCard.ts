import type { Sock } from "./api/drawings";

/** シェアする画像の大きさ（Instagram の縦長の投稿と同じ 4:5） */
export const CARD_WIDTH = 1080;
export const CARD_HEIGHT = 1350;

/**
 * X のカード用の画像の大きさ。X の大きなカード（summary_large_image）に合う横長。
 * バックエンド（back/src/share.py の CARD_WIDTH と CARD_HEIGHT）と同じ値にする。
 */
export const X_CARD_WIDTH = 1200;
export const X_CARD_HEIGHT = 630;

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

function toBlob(
  canvas: HTMLCanvasElement,
  type: string,
  quality?: number,
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("画像を作れません"))),
      type,
      quality,
    );
  });
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

  return toBlob(canvas, "image/png");
}

/**
 * X のカード用の画像（JPEG。100〜200KB ほど）を作る。makeShareCard の横長版。
 * 白地の左にくつした、右に書いた「と」、レアリティ、名前を並べる。見た目は仮のもの。
 *
 * X の小さな表示でも読めるよう、文字を大きくし、説明は載せない（説明は、ページの
 * カードの指定のほうに入る）。X は画像を中央寄りで切り抜くことがあり、左下には題の札を
 * 重ねるので、端と左下には大事なものを置かない。
 *
 * @param drawingImage 書いた「と」の画像（白地に黒の正方形。data URL）
 */
export async function makeXCard(
  sock: Sock,
  drawingImage: string,
): Promise<Blob> {
  const [sockImage, drawing] = await Promise.all([
    loadImage(sock.image),
    loadImage(drawingImage),
  ]);

  const canvas = document.createElement("canvas");
  canvas.width = X_CARD_WIDTH;
  canvas.height = X_CARD_HEIGHT;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas を使えません");

  // JPEG は透明を持てないので、必ず白で塗ってから描く
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, X_CARD_WIDTH, X_CARD_HEIGHT);

  // 左にくつした
  ctx.drawImage(sockImage, 50, 65, 500, 500);

  // 右の列（幅 560）。上から、書いた「と」、レアリティ、名前。
  const center = 870;
  const columnWidth = 560;
  ctx.drawImage(drawing, 730, 45, 280, 280);
  ctx.strokeStyle = "#999";
  ctx.lineWidth = 2;
  ctx.strokeRect(730, 45, 280, 280);

  ctx.textAlign = "center";
  ctx.fillStyle = "#555";
  ctx.font = `30px ${FONT}`;
  ctx.fillText("書いた「と」", center, 368);

  ctx.font = `36px ${FONT}`;
  ctx.fillText(sock.rarity, center, 442);

  // 名前は 1 行。長い名前は、列の幅に収まるまで文字を小さくする。
  ctx.fillStyle = "#222";
  let nameSize = 68;
  ctx.font = `bold ${nameSize}px ${FONT}`;
  while (nameSize > 40 && ctx.measureText(sock.name).width > columnWidth) {
    nameSize -= 2;
    ctx.font = `bold ${nameSize}px ${FONT}`;
  }
  ctx.fillText(sock.name, center, 522, columnWidth);

  ctx.fillStyle = "#555";
  ctx.font = `30px ${FONT}`;
  ctx.fillText("ITO", center, 588);

  return toBlob(canvas, "image/jpeg", 0.85);
}

/**
 * シェア用のアドレスの末尾に付ける番号。
 * X は、一度読んだアドレスのカードを 1 週間ほど覚えている。カードの画像や文を直したのに
 * 古いカードが出続けるときは、この番号を上げる（別のアドレスとして読み直される）。
 */
const SHARE_PAGE_VERSION = 2;

/**
 * くつしたごとのシェア用のアドレス（例: https://…/s/worn-01/?v=2）。
 * このページには、X などがカードとして出す画像の指定（OGP）が書いてある。
 * 人が開くと、最初の画面に移る。ページは scripts/build-share.py が作る。
 */
export function sharePageUrl(sock: Sock): string {
  return `${window.location.origin}/s/${sock.id.toLowerCase()}/?v=${SHARE_PAGE_VERSION}`;
}
