import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";

import "./styles/style.css";
import "./styles/materials/reading.css";
import "./styles/materials/completed.css";
import "./styles/materials/repeating_queue.css";
import "./styles/materials/add_material.css";
import "./styles/notes/notes.css";
import "./styles/notes/add_note.css";
import "./styles/cards/cards_list.css";
import "./styles/cards/add_card.css";
import "./styles/system/system.css";

const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("root element missing");
}

createRoot(rootEl).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
