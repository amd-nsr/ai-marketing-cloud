"use client";

import { useCallback, useReducer } from "react";

interface State<T> {
  present: T;
  past: T[];
  future: T[];
  /** Key of the last coalescable change (e.g. typing in one field). */
  lastKey: string | null;
  lastAt: number;
}

type Action<T> =
  | { type: "set"; value: T; key?: string }
  | { type: "reset"; value: T }
  | { type: "undo" }
  | { type: "redo" };

const LIMIT = 100;
const COALESCE_MS = 800;

function reducer<T>(state: State<T>, action: Action<T>): State<T> {
  switch (action.type) {
    case "set": {
      const now = Date.now();
      const coalesce =
        action.key !== undefined &&
        action.key === state.lastKey &&
        now - state.lastAt < COALESCE_MS;
      return {
        present: action.value,
        past: coalesce ? state.past : [...state.past, state.present].slice(-LIMIT),
        future: [],
        lastKey: action.key ?? null,
        lastAt: now,
      };
    }
    case "reset":
      return { present: action.value, past: [], future: [], lastKey: null, lastAt: 0 };
    case "undo": {
      const previous = state.past.at(-1);
      if (previous === undefined) return state;
      return {
        present: previous,
        past: state.past.slice(0, -1),
        future: [state.present, ...state.future],
        lastKey: null,
        lastAt: 0,
      };
    }
    case "redo": {
      const next = state.future[0];
      if (next === undefined) return state;
      return {
        present: next,
        past: [...state.past, state.present],
        future: state.future.slice(1),
        lastKey: null,
        lastAt: 0,
      };
    }
  }
}

/** Undo/redo history for an immutable value. ``key`` merges rapid edits (typing). */
export function useHistory<T>(initial: T) {
  const [state, dispatch] = useReducer(reducer<T>, {
    present: initial,
    past: [],
    future: [],
    lastKey: null,
    lastAt: 0,
  });
  const set = useCallback((value: T, key?: string) => dispatch({ type: "set", value, key }), []);
  const reset = useCallback((value: T) => dispatch({ type: "reset", value }), []);
  const undo = useCallback(() => dispatch({ type: "undo" }), []);
  const redo = useCallback(() => dispatch({ type: "redo" }), []);
  return {
    value: state.present,
    set,
    reset,
    undo,
    redo,
    canUndo: state.past.length > 0,
    canRedo: state.future.length > 0,
  };
}
