import { Outlet } from "react-router-dom";

import { MobileNav } from "./MobileNav";
import { NotesSubnav } from "./NotesSubnav";
import { ScrollArrows } from "./ScrollArrows";

export function NotesLayout() {
  return (
    <>
      <header>
        <MobileNav />
        <nav className="navbar" id="head">
          <a href="/materials"> Materials </a>
          <a href="/reading_logs"> Reading log </a>
          <a href="/notes"> Notes </a>
          <a href="/cards"> Cards </a>
          <a href="/system"> System </a>
        </nav>
        <NotesSubnav />
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
