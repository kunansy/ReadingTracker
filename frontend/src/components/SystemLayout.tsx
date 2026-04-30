import { Outlet } from "react-router-dom";

import { ScrollArrows } from "./ScrollArrows";
import { SystemSubnav } from "./SystemSubnav";

export function SystemLayout() {
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
        <SystemSubnav />
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

