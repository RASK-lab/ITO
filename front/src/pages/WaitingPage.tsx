/**
 * 待機中の画面（仮）。「確定」を押してから、結果が届くまで出す。
 * デザインを入れるまでは、文を 1 行出すだけにする。
 */
export function WaitingPage() {
  return (
    <main className="waiting">
      <p role="status">お手紙を届けています…</p>
    </main>
  );
}
