import { useState } from "react";
import type { FormEvent } from "react";
import {
  DEFAULT_USER_NAME,
  MAX_USER_NAME_LENGTH,
  loadUserName,
} from "../userName";

type Props = {
  /** 「手紙を書く」が押されたとき。name は入力されたまま（空のこともある）。 */
  onStart: (name: string) => void;
};

/** 最初の画面。ユーザーネームを入れて、書く画面へ進む。 */
export function StartPage({ onStart }: Props) {
  // 前に入れた名前があれば、入った状態で始める
  const [name, setName] = useState(() => loadUserName() ?? "");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onStart(name);
  }

  return (
    <main className="start">
      <h1>ITO〜良い「と」〜</h1>
      <p>手紙を書くと靴下が届きます</p>
      <form onSubmit={handleSubmit}>
        <label htmlFor="user-name">ユーザーネームを入れてください</label>
        <input
          id="user-name"
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={DEFAULT_USER_NAME}
          maxLength={MAX_USER_NAME_LENGTH}
          autoComplete="off"
        />
        <button type="submit">手紙を書く</button>
      </form>
    </main>
  );
}
