/**
 * Disappearing scrollbars: any element with the `auto-scrollbar` class gets `is-scrolling` while it
 * scrolls, and loses it shortly after scrolling stops. The CSS shows the scrollbar only in that state.
 */
const HIDE_AFTER_MS = 900;
const timers = new WeakMap<Element, number>();

function onScroll(event: Event) {
  const element = event.target;
  if (!(element instanceof HTMLElement) || !element.classList.contains("auto-scrollbar")) return;
  element.classList.add("is-scrolling");
  window.clearTimeout(timers.get(element));
  timers.set(element, window.setTimeout(() => element.classList.remove("is-scrolling"), HIDE_AFTER_MS));
}

// Scroll events do not bubble, so listen in the capture phase to catch every scrolling element.
document.addEventListener("scroll", onScroll, { capture: true, passive: true });
