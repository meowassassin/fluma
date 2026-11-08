/* 영상 = 지금까지 만든 영상 목록 · 휴지통. 영상을 열면 편집기(/p/:id) */
import React from "react";
import { Projects } from "../home/HomePage";
import { t } from "../../lib/i18n";

export const VideosPage: React.FC = () => (
  <div className="page">
    <div className="page-body videos">
      <header className="page-head"><h1>{t("영상")}</h1></header>
      <div className="videos-body"><Projects /></div>
    </div>
  </div>
);
