import { SIDEBAR_KEY, els } from "./state.js";

export function isSidebarCollapsed() {
  return els.app.classList.contains("sidebar-collapsed");
}

export function setSidebarCollapsed(collapsed) {
  els.app.classList.toggle("sidebar-collapsed", collapsed);
  els.sidebarToggle?.setAttribute("aria-expanded", collapsed ? "false" : "true");
  if (els.chatSidebarBtn) els.chatSidebarBtn.hidden = !collapsed;
  localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
}

export function expandSidebar() {
  if (isSidebarCollapsed()) setSidebarCollapsed(false);
}

export function toggleSidebar() {
  setSidebarCollapsed(!isSidebarCollapsed());
}

export function focusPanel(section) {
  expandSidebar();
  if (!section) return;
  const panel = els.sidebarPanel;
  if (panel) {
    window.requestAnimationFrame(() => {
      const top = section.offsetTop - panel.offsetTop;
      panel.scrollTo({ top: Math.max(0, top - 8), behavior: "smooth" });
    });
  } else {
    section.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  section.classList.add("panel-focus");
  clearTimeout(focusPanel._t);
  focusPanel._t = setTimeout(() => section.classList.remove("panel-focus"), 900);
}

export function initSidebar() {
  setSidebarCollapsed(localStorage.getItem(SIDEBAR_KEY) === "1");
}

export function closeMobileSidebar() {
  els.sidebar?.classList.remove("open");
  els.overlay?.classList.remove("show");
}

export function openMobileSidebar() {
  expandSidebar();
  els.sidebar?.classList.add("open");
  els.overlay?.classList.add("show");
}

export function bindRailActions({ onNewChat, onSearch, onOrders }) {
  document.querySelector(".sidebar-rail")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".rail-btn");
    if (!btn) return;
    if (btn.id === "sidebar-toggle") toggleSidebar();
    else if (btn.id === "rail-new-chat") { expandSidebar(); onNewChat(); }
    else if (btn.id === "rail-search") {
      expandSidebar();
      els.historySearch?.focus();
      onSearch();
    }
    else if (btn.id === "rail-orders") onOrders();
  });
}
