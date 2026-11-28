import { useEffect, useState } from "react";
import { StartPage } from "./pages/StartPage";
import { WritePage } from "./pages/WritePage";
import { CollectionPage } from "./pages/CollectionPage";
import { CollectPage } from "./pages/CollectPage";
import { loadUserName, saveUserName } from "./userName";

/** 書く画面のアドレス（例: http://localhost:5173/#write）。最初の画面は # なし。 */
const WRITE_HASH = "#write";
const COLLECTION_HASH = "#collection";
/**
 * 学習データ集めの画面（docs/collect.md）。最初の画面からはつながず、このアドレスを配る。
 * 例: https://<公開しているサイト>/#collect
 */
const COLLECT_HASH = "#collect";

/** 学習データ集めの画面を開いたタブの目印（タブを閉じるまで残る） */
const COLLECT_ONLY_KEY = "ito.collectOnly";

function isCollectOnly(): boolean {
  try {
    return sessionStorage.getItem(COLLECT_ONLY_KEY) === "1";
  } catch {
    return false;
  }
}

function markCollectOnly(): void {
  try {
    sessionStorage.setItem(COLLECT_ONLY_KEY, "1");
  } catch {
    // 覚えられないとき（プライベートウィンドウなど）は、アドレスが #collect の間だけ収集の画面になる
  }
}

type Screen = "start" | "write" | "collection" | "collect";

/**
 * いまのアドレスから、出す画面を決める。
 * 書く画面を出すのは、最初の画面で「手紙を書く」を押したことがあるときだけ。
 * それ以外のアドレスは、最初の画面のアドレス（# なし）に直す。
 */
function screenFromAddress(): Screen {
  // 学習データ集めの画面を開いたタブでは、アドレスを書き換えても、戻っても、
  // アプリ本体の画面には移らない（集めるための人に、本体を見せないため）。
  if (window.location.hash === COLLECT_HASH || isCollectOnly()) {
    markCollectOnly();
    if (window.location.hash !== COLLECT_HASH) {
      window.history.replaceState(null, "", COLLECT_HASH);
    }
    return "collect";
  }
  if (window.location.hash === WRITE_HASH && loadUserName() !== null) {
    return "write";
  }
  if (window.location.hash === COLLECTION_HASH) {
    return "collection";
  }
  if (window.location.hash !== "") {
    window.history.replaceState(
      null,
      "",
      window.location.pathname + window.location.search,
    );
  }
  return "start";
}

function App() {
  const [screen, setScreen] = useState(screenFromAddress);

  // ブラウザの「戻る」「進む」や、アドレスの書き換えに合わせる
  useEffect(() => {
    const update = () => setScreen(screenFromAddress());
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);

  function handleStart(name: string) {
    saveUserName(name);
    // 履歴を 1 つ進める。書く画面でブラウザの「戻る」を押すと、最初の画面に戻る。
    window.location.hash = WRITE_HASH;
  }

  // 開発中だけの近道。書く画面から、最初の画面に戻る。
  function handleBack() {
    window.history.pushState(
      null,
      "",
      window.location.pathname + window.location.search,
    );
    setScreen("start");
  }

  if (screen === "start") return (
    <StartPage
      onStart={handleStart}
      onCollection={() => { window.location.hash = COLLECTION_HASH; }}
    />
  );

  if (screen === "collect") return <CollectPage />;

  if (screen === "collection") return (
    <CollectionPage onBack={() => { window.location.hash = ""; }} />
  );

  return (
    <>
      {/* 画面の左上に重ねて置く。ほかの部品の位置は動かさない。 */}
      <button
        type="button"
        onClick={handleBack}
        style={{ position: "fixed", top: "1rem", left: "1rem", font: "inherit" }}
      >
        戻る
      </button>
      <WritePage />
    </>
  );
}

export default App;
