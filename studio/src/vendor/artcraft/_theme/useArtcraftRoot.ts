// ArtCraft 부품을 띄우는 호스트 화면용: 떠 있는 동안 document.body 에 "ac-root" 를 단다.
// 이유: Radix · headless UI 포털과 createPortal(document.body) 로 뜨는 메뉴 · 툴팁 · 모달은 body 바로 아래에 붙어
// 화면의 .ac-root 컨테이너 밖에 있다 — body 에 클래스가 있어야 Tailwind 범위(important) · 변수 · 초기화가 적용된다.
// 초기화 규칙은 :where() 로 특이도 0 이라 Fluma 자체 화면에는 영향이 없다(같은 이름의 Tailwind 클래스를 쓰지 않는 한).
import { useEffect } from "react";
import "./artcraft-fluma.css";

let holders = 0;

export function useArtcraftRoot(): void {
  useEffect(() => {
    holders += 1;
    document.body.classList.add("ac-root");
    return () => {
      holders -= 1;
      if (holders === 0) document.body.classList.remove("ac-root");
    };
  }, []);
}
