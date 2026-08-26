import { els } from "./state.js";

export const truthy = (v) => v === true || v === "True" || v === "true";

export function esc(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

// Minimal, safe markdown: escapes HTML first, then only turns **bold** into <strong>.
export function mdLite(s) {
  return esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

export function relTime(iso) {
  if (!iso) return "";
  const m = Math.floor((Date.now() - new Date(iso)) / 60000);
  if (m < 1) return "now";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return h < 24 ? `${h}h` : new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function toast(msg, duration = 2800, variant = "") {
  els.toast.textContent = msg;
  els.toast.classList.remove("toast-warn", "toast-error");
  if (variant) els.toast.classList.add(`toast-${variant}`);
  els.toast.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => {
    els.toast.classList.remove("show", "toast-warn", "toast-error");
  }, duration);
}

export function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function fmtINR(amount) {
  if (amount === null || amount === undefined || amount === "") return "—";
  const n = Number(amount);
  if (Number.isNaN(n)) return String(amount);
  return "₹" + n.toLocaleString("en-IN");
}

export function statusClass(status) {
  return `st-${(status || "unknown").toString().toLowerCase()}`;
}

const KEYWORD_ICON = [
  [/dress|gown/i, "dress", "pink"],
  [/jean|denim|trouser|pant/i, "pants", "indigo"],
  [/jacket|bomber|coat|blazer/i, "jacket", "olive"],
  [/sock/i, "socks", "teal"],
  [/tote|backpack|handbag|\bbag\b/i, "bag", "brown"],
  [/scarf|shawl|stole/i, "scarf", "rose"],
  [/sneaker|shoe|boot|sandal|loafer/i, "shoe", "slate"],
  [/earring|necklace|\bring\b|jewel|pendant|bracelet/i, "jewel", "gold"],
  [/belt/i, "belt", "brown"],
  [/shirt|tee|t-shirt|kurta|top|blouse|polo/i, "shirt", "amber"],
];

const CATEGORY_FALLBACK = {
  footwear: ["shoe", "slate"],
  jewellery: ["jewel", "gold"],
  accessories: ["bag", "brown"],
  innerwear: ["shirt", "teal"],
  apparel: ["shirt", "amber"],
};

const PRODUCT_EMOJI = {
  dress: "👗",
  pants: "👖",
  jacket: "🧥",
  shirt: "👕",
  socks: "🧦",
  bag: "👜",
  scarf: "🧣",
  shoe: "👟",
  jewel: "💎",
  belt: "",
  box: "📦",
};

export function itemVisual(name, category) {
  const n = name || "";
  for (const [re, key, tint] of KEYWORD_ICON) {
    if (re.test(n)) return { emoji: PRODUCT_EMOJI[key], key, tint };
  }
  const [key, tint] = CATEGORY_FALLBACK[(category || "").toLowerCase()] || ["box", "neutral"];
  return { emoji: PRODUCT_EMOJI[key], key, tint };
}

export const MESSAGE_MAX = 4000;

let _limitToastAt = 0;

export function toastMessageLimit() {
  if (Date.now() - _limitToastAt < 3000) return;
  _limitToastAt = Date.now();
  toast(`Message limit reached (${MESSAGE_MAX.toLocaleString()} characters).`, 3000, "warn");
}

export function wouldExceedMessageLimit(input, insertLength, selectionStart, selectionEnd) {
  const removed = selectionEnd - selectionStart;
  return input.value.length - removed + insertLength > MESSAGE_MAX;
}

export function isTextInputKey(e) {
  if (e.ctrlKey || e.metaKey || e.altKey) return false;
  if (e.key === "Enter" && e.shiftKey) return true;
  return e.key.length === 1;
}

export async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const d = err.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join(", ") : `Error ${res.status}`);
  }
  return res.json();
}
