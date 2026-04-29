import { Outlet } from "react-router-dom";

import { ScrollArrows } from "./ScrollArrows";
import { CardsSubnav } from "../components/CardsSubnav.tsx";

export function CardsLayout() {
  return (
    <>
      <header>
        <nav className="navbar" id="head">
          <a href="/materials"> Materials </a>
          <a href="/reading_logs"> Reading log </a>
          <a href="/notes"> Notes </a>
          <a href="/cards"> Cards </a>
          <a href="/system"> System </a>
        </nav>
        <CardsSubnav />
      </header>
      <main>
        <div id="loader" />
        <Outlet />
        <ScrollArrows />
      </main>
      <footer id="footer" />
    </>
  );
}
