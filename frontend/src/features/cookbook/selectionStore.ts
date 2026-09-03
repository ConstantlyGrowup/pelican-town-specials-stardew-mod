type Listener = () => void;

let selected = new Set<string>();
const listeners = new Set<Listener>();

function emit() {
  for (const listener of listeners) {
    listener();
  }
}

/** Selection holds only unique dishIds, never full DTOs or local paths. */
export function toggleSelection(dishId: string) {
  const next = new Set(selected);
  if (next.has(dishId)) {
    next.delete(dishId);
  } else {
    next.add(dishId);
  }
  selected = next;
  emit();
}

/** Clears the whole selection, e.g. after a successful batch action. */
export function clearSelection() {
  if (selected.size === 0) {
    return;
  }
  selected = new Set<string>();
  emit();
}

export function clearSelectionFor(dishId: string) {
  if (!selected.has(dishId)) {
    return;
  }
  const next = new Set(selected);
  next.delete(dishId);
  selected = next;
  emit();
}

export function getSelectedDishIds(): ReadonlySet<string> {
  return selected;
}

/** Test helper: clears module-level selection between tests. */
export function resetSelectionStore() {
  selected = new Set<string>();
  emit();
}

export function subscribeSelection(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
