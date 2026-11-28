import { useEffect, useRef, useState } from "react";
import type { Sock } from "../api/drawings";
import {
  CARD_HEIGHT,
  CARD_WIDTH,
  makeShareCard,
  sharePageUrl,
} from "../shareCard";

type Props = {
  sock: Sock;
  /** 書いた「と」の画像（data URL） */
  drawingImage: string;
  onClose: () => void;
};

/** 保存するときのファイル名 */
const FILE_NAME = "ito-sock.png";

/** スマホやタブレット（指で操作する端末）か。出すボタンと、LINE の開き方を変える。 */
const isTouch = window.matchMedia("(pointer: coarse)").matches;

/**
 * iPhone・iPad か。ダウンロードすると「ファイル」に入り「写真」に入らないので、
 * 画像の長押しで保存してもらう。iPad は Mac と名乗るので、指で触れるかどうかでも見る。
 */
const isIos =
  /iPhone|iPad|iPod/.test(navigator.userAgent) ||
  (navigator.userAgent.includes("Macintosh") && navigator.maxTouchPoints > 1);

/**
 * 端末の共有の画面に、画像を渡せるか（スマホとタブレットで、ブラウザが対応しているとき）。
 * 渡せるなら、「画像つきで共有」のボタンを出す。
 */
const canShareImage =
  isTouch &&
  typeof navigator.canShare === "function" &&
  navigator.canShare({
    files: [new File([], "ito-sock.png", { type: "image/png" })],
  });

const SAVE_BY_LONG_PRESS =
  "上の画像を長押しして、「写真に保存」を選んでください。";

/**
 * シェアの画面。シェアする画像と、行き先のボタンを出す。
 * 端末の共有の画面は、スマホの「画像つきで共有」だけで使う（画像をアプリに渡すため）。
 * スマホでは下から、パソコンでは中央に出る（index.css）。
 */
export function ShareDialog({ sock, drawingImage, onClose }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  /** シェアする画像。作り終わるまで null。 */
  const [card, setCard] = useState<{ blob: Blob; url: string } | null>(null);
  const [note, setNote] = useState("");
  /** Instagram を押したあとに出す、Instagram を開くリンク */
  const [showInstagramLink, setShowInstagramLink] = useState(false);

  // 開いたら showModal で出す。Esc と、外側を押したときも閉じる。
  useEffect(() => {
    dialogRef.current?.showModal();
  }, []);

  useEffect(() => {
    let url = "";
    let cancelled = false;
    makeShareCard(sock, drawingImage)
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setCard({ blob, url });
      })
      .catch((error) => {
        console.error(error);
        if (!cancelled) setNote("画像を作れませんでした。");
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [sock, drawingImage]);

  const text = `「と」を書いたら、くつした「${sock.name}」が届きました。`;
  const pageUrl = sharePageUrl(sock);

  /** 画像を保存する。iPhone・iPad では、長押しの案内を出す。 */
  function save() {
    if (!card) return;
    if (isIos) {
      setNote(SAVE_BY_LONG_PRESS);
      return;
    }
    const a = document.createElement("a");
    a.href = card.url;
    a.download = FILE_NAME;
    a.click();
    setNote("画像を保存しました。");
  }

  function handleSave() {
    setShowInstagramLink(false);
    save();
  }

  /** Web からは Instagram に画像を渡せない。保存してもらい、Instagram で選んでもらう。 */
  function handleInstagram() {
    save();
    setNote(
      isIos
        ? `${SAVE_BY_LONG_PRESS}そのあと、Instagram で選んでください。`
        : "画像を保存しました。Instagram で選んでください。",
    );
    setShowInstagramLink(true);
  }

  async function handleCopy() {
    if (!card) return;
    setShowInstagramLink(false);
    try {
      await navigator.clipboard.write([
        new ClipboardItem({ "image/png": card.blob }),
      ]);
      setNote("画像をコピーしました。投稿の画面に貼り付けられます。");
    } catch (error) {
      console.error(error);
      setNote("コピーできませんでした。「画像を保存」を使ってください。");
    }
  }

  /** X の、文とアドレスを入れた投稿の画面。画像は、アドレスのカードとして出る。 */
  const xUrl = `https://x.com/intent/post?${new URLSearchParams({ text, url: pageUrl })}`;

  /**
   * スマホで、端末の共有の画面を出して、選んだアプリに画像と文を渡す。
   * Web から X などのアプリに画像を直接渡す方法はなく、端末の共有の画面を通すのが
   * 唯一の方法。どのアプリが並ぶかは端末しだいで、こちらからは X を指定できない。
   * 共有の画面を出せない端末では、このボタンを出さない（canShareImage）。
   */
  async function handleShareImage() {
    if (!card) return;
    setShowInstagramLink(false);
    try {
      await navigator.share({
        files: [new File([card.blob], FILE_NAME, { type: "image/png" })],
        // アドレスは文の中に入れる（画像と一緒だと、url の欄を捨てるアプリがあるため）
        text: `${text} ${pageUrl}`,
      });
    } catch (error) {
      // 利用者が共有の画面を閉じただけなら、何も出さない
      if (error instanceof DOMException && error.name === "AbortError") return;
      console.error(error);
      setNote("共有の画面を開けませんでした。「画像を保存」を使ってください。");
    }
  }

  /** スマホでは LINE のアプリ、パソコンではブラウザ用の共有のページを開く */
  function handleLine() {
    const url = isTouch
      ? `https://line.me/R/share?${new URLSearchParams({ text: `${text} ${pageUrl}` })}`
      : `https://social-plugins.line.me/lineit/share?${new URLSearchParams({ url: pageUrl, text })}`;
    window.open(url, "_blank", "noopener");
  }

  return (
    <dialog
      ref={dialogRef}
      className="share"
      onClose={onClose}
      onClick={(event) => {
        // 外側（暗いところ）を押したら閉じる
        if (event.target === event.currentTarget) event.currentTarget.close();
      }}
    >
      <div className="share-body">
        {/* 画像を作る前から場所を取っておく */}
        <img
          className="share-card"
          src={card?.url}
          alt="シェアする画像"
          width={CARD_WIDTH}
          height={CARD_HEIGHT}
        />
        <div className="share-buttons">
          <h2>シェア</h2>
          {isTouch ? (
            <button type="button" onClick={handleInstagram} disabled={!card}>
              Instagram
            </button>
          ) : (
            <button type="button" onClick={handleCopy} disabled={!card}>
              画像をコピー
            </button>
          )}
          <button type="button" onClick={handleSave} disabled={!card}>
            画像を保存
          </button>
          {/*
            X は、文とアドレスを入れた投稿の画面を直接開く（画像は、アドレスのカードとして出る）。
            ボタンではなくリンクにする。スマホでは、利用者が自分で押したリンクのときだけ、
            X のアプリが開く（window.open だと、アプリがあってもブラウザで開く）。
          */}
          <a
            className="share-link"
            href={xUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            X
          </a>
          <button type="button" onClick={handleLine}>
            LINE
          </button>
          {canShareImage && (
            // スマホ: 端末の共有の画面を出す。そこで選んだアプリに、画像そのものを渡せる
            // （X を選ぶと、画像が付いた投稿の画面になる）。
            <button
              type="button"
              className="share-wide"
              onClick={handleShareImage}
              disabled={!card}
            >
              画像つきで共有
            </button>
          )}
          <button type="button" onClick={() => dialogRef.current?.close()}>
            とじる
          </button>
          <p className="share-note" role="status">
            {note}
            {showInstagramLink && (
              <>
                {" "}
                <a
                  href="https://www.instagram.com/"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Instagram を開く
                </a>
              </>
            )}
          </p>
        </div>
      </div>
    </dialog>
  );
}
