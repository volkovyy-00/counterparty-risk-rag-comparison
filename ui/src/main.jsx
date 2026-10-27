import { render } from "preact";
import "./styles.css";
import { setData } from "./lib/data.js";
import { App } from "./App.jsx";

fetch("data.json").then(r => r.json()).then(d => { setData(d); render(<App />, document.getElementById("app")); })
  .catch(e => { document.getElementById("app").textContent = `Could not load data.json (${e}). Run: make console`; });
