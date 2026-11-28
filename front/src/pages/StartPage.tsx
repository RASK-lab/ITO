import { useState } from "react";
import type { FormEvent } from "react";
import {
  DEFAULT_USER_NAME,
  MAX_USER_NAME_LENGTH,
  loadUserName,
} from "../userName";
type Props = {
  onStart: (name: string) => void;
};

export function StartPage({ onStart }: Props) {
  const [name, setName] = useState(() => loadUserName() ?? "");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onStart(name);
  }

  return (
    <div className="start-scene">
      {/* 机の背景画像 */}
      <img src="/desk-bg.png" alt="" aria-hidden="true" className="start-bg" />

      {/* 中央のコンテンツ（手紙 + ボタン） */}
      <div className="start-center">
        <div className="start-letter">
          <p className="start-letter__catch">一筆にあなたが宿る</p>
          <p className="start-letter__catch">いい「と」を刻もう。</p>
          <div className="start-letter__divider" />
          <p className="start-ito-logo">ITO</p>

          <form className="start-form" onSubmit={handleSubmit}>
            <label htmlFor="user-name" className="start-form__label">
              ユーザーネーム
            </label>
            <input
              id="user-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={DEFAULT_USER_NAME}
              maxLength={MAX_USER_NAME_LENGTH}
              autoComplete="off"
              className="start-form__input"
            />
            <button type="submit" className="start-form__btn">
              手紙を書く
            </button>
          </form>
        </div>

      </div>
    </div>
  );
}
