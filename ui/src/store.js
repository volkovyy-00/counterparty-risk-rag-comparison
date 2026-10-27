import { createContext } from "preact";
import { useContext } from "preact/hooks";

// One app state object, patched with set({...}). Screens read it through useApp().
export const AppCtx = createContext(null);
export const useApp = () => useContext(AppCtx);

export const SCREENS = [
  { id: "question", key: "1", label: "Question", group: "Setup" },
  { id: "data", key: "2", label: "Data gate", group: "Setup" },
  { id: "rag", key: "3", label: "Plain RAG", group: "Ask", n: "1" },
  { id: "graph", key: "4", label: "GraphRAG", group: "Ask", n: "2" },
  { id: "taxonomy", key: "5", label: "Taxonomy-first", group: "Ask", n: "3" },
  { id: "scorecard", key: "6", label: "Scorecard", group: "Compare" },
  { id: "decision", key: "7", label: "Decision", group: "Compare" },
  { id: "governance", key: "G", label: "Governance", group: "Compare" },
];
