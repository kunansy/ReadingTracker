import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";

import "../../static/style.css";
import "../../static/materials/queue.css";
import "../../static/materials/reading.css";
import "../../static/materials/completed.css";
import "../../static/materials/repeating_queue.css";
import "../../static/materials/add_material.css";
import "../../static/notes/notes.css";
import "../../static/notes/add_note.css";
import "../../static/reading_log/reading_log.css";
import "../../static/reading_log/add_log_record.css";
import "../../static/cards/cards_list.css";
import "../../static/cards/add_card.css";
import "../../static/system/system.css";

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
