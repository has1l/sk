import { createRoot } from "react-dom/client";

import App from "./App";
import { applyTheme, storedTheme } from "./theme";
import { Boundary } from "./components/Boundary";
import "./styles.css";

applyTheme(storedTheme());

createRoot(document.getElementById("root")!).render(
  <Boundary>
    <App />
  </Boundary>,
);
