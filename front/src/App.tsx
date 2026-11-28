import { useEffect, useState } from "react";
import { StartPage } from "./pages/StartPage";
import { WritePage } from "./pages/WritePage";
import { loadUserName, saveUserName } from "./userName";

/** 書く画面のアドレス（例: http://localhost:5173/#write）。最初の画面は # なし。 */
const WRITE_HASH = "#write";

type Screen = "start" | "write";

/**
 * いまのアドレスから、出す画面を決める。
 * 書く画面を出すのは、最初の画面で「手紙を書く」を押したことがあるときだけ。
 * それ以外のアドレスは、最初の画面のアドレス（# なし）に直す。
 */
function screenFromAddress(): Screen {
  if (window.location.hash === WRITE_HASH && loadUserName() !== null) {
    return "write";
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

  return screen === "write" ? (
    <WritePage />
  ) : (
    <StartPage onStart={handleStart} />
  );
}

export default App;
