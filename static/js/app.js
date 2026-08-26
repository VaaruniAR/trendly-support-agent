import { $, customers, els, lastTicket, orderList, scenarios } from "./state.js";
import {
  closeOrderModal,
  closeScenarioPicker,
  deleteSession,
  fillPrompt,
  filterAndRenderHistory,
  initApp,
  loadSession,
  openOrderModal,
  openOrderChooser,
  openScenarioPicker,
  pickScenarioOrder,
  selectCustomer,
  sendMessage,
  startNewChat,
  toggleAccountMenu,
  updateCharCount,
  showMoreOrders,
  scrollEnd,
  uploadEvidence,
} from "./chat.js";
import {
  bindRailActions,
  closeMobileSidebar,
  expandSidebar,
  focusPanel,
  openMobileSidebar,
  toggleSidebar,
} from "./sidebar.js";
import { toast, toastMessageLimit, wouldExceedMessageLimit, isTextInputKey, MESSAGE_MAX } from "./util.js";

els.composer?.addEventListener("submit", (e) => { e.preventDefault(); sendMessage(); });
els.input?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); return; }
  if (els.input.value.length >= MESSAGE_MAX && isTextInputKey(e)) {
    e.preventDefault();
    toastMessageLimit();
  }
});
els.input?.addEventListener("paste", (e) => {
  const text = e.clipboardData?.getData("text") || "";
  if (wouldExceedMessageLimit(els.input, text.length, els.input.selectionStart, els.input.selectionEnd)) {
    toastMessageLimit();
  }
});
els.input?.addEventListener("beforeinput", (e) => {
  if (e.inputType.startsWith("delete") || e.inputType.startsWith("history")) return;
  if (e.inputType === "insertFromPaste") return;
  const insertLen = e.data?.length ?? 0;
  if (
    insertLen > 0
    && wouldExceedMessageLimit(els.input, insertLen, els.input.selectionStart, els.input.selectionEnd)
  ) {
    e.preventDefault();
    toastMessageLimit();
  }
});
els.input?.addEventListener("input", () => {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(els.input.scrollHeight, 120) + "px";
  updateCharCount();
});
els.scrollBtn?.addEventListener("click", () => scrollEnd(true));
els.ariaHome?.addEventListener("click", startNewChat);
els.evidenceInput?.addEventListener("change", (e) => uploadEvidence(e.target.files?.[0]));
els.messages?.addEventListener("scroll", () => scrollEnd(false), { passive: true });

els.prompts?.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-i]");
  const scenario = btn && scenarios[btn.dataset.i];
  if (!scenario) return;
  if (scenario.needs_order) openScenarioPicker(scenario);
  else fillPrompt(scenario.message);
});

els.scenarioOverlay?.addEventListener("click", (e) => {
  if (e.target === els.scenarioOverlay) closeScenarioPicker();
});
els.scenarioClose?.addEventListener("click", closeScenarioPicker);
els.scenarioList?.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-order]");
  if (btn) pickScenarioOrder(btn.dataset.order);
});
els.chooseOrderBtn?.addEventListener("click", openOrderChooser);
els.panelOrders?.addEventListener("click", (e) => {
  if (e.target.closest("#orders-more")) {
    e.preventDefault();
    showMoreOrders();
    return;
  }
  const li = e.target.closest("[data-i]");
  const order = li && orderList[li.dataset.i];
  if (order) openOrderModal(order);
});

els.accountBtn?.addEventListener("click", (e) => {
  e.stopPropagation();
  toggleAccountMenu();
});
els.accountMenu?.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-email]");
  if (!btn) return;
  const customer = customers.find((c) => c.email === btn.dataset.email);
  if (customer) selectCustomer(customer);
});
document.addEventListener("click", (e) => {
  if (!els.accountMenu || els.accountMenu.hidden) return;
  if (e.target.closest(".account-switcher")) return;
  toggleAccountMenu(false);
});

els.orderModalOverlay?.addEventListener("click", (e) => {
  if (e.target === els.orderModalOverlay) closeOrderModal();
});
els.orderModalClose?.addEventListener("click", closeOrderModal);
els.orderModalBody?.addEventListener("click", (e) => {
  const btn = e.target.closest("#order-modal-ask");
  if (!btn) return;
  closeOrderModal();
  sendMessage(`Please give me a full update on order ${btn.dataset.order}.`);
});
els.history?.addEventListener("click", (e) => {
  const del = e.target.closest("[data-del]");
  if (del) return deleteSession(del.dataset.del);
  const btn = e.target.closest("[data-id]");
  if (btn) loadSession(btn.dataset.id);
});
els.historySearch?.addEventListener("input", (e) => {
  filterAndRenderHistory(e.target.value);
});
els.messages?.addEventListener("click", (e) => {
  const prompt = e.target.closest("[data-welcome-i]");
  if (prompt) {
    const scenario = scenarios[prompt.dataset.welcomeI];
    if (scenario?.needs_order) openScenarioPicker(scenario);
    else if (scenario) fillPrompt(scenario.message);
    return;
  }
  if (e.target.closest("[data-upload-evidence]")) {
    els.evidenceInput?.click();
    return;
  }
  const returnChoice = e.target.closest("[data-return-choice]");
  if (returnChoice) {
    const group = returnChoice.closest(".return-choices");
    group?.querySelectorAll("button").forEach((button) => { button.disabled = true; });
    returnChoice.classList.add("selected");
    sendMessage(returnChoice.dataset.returnChoice);
    return;
  }
  const btn = e.target.closest(".copy-msg");
  if (!btn) return;
  const text = btn.closest(".msg")?.querySelector(".bubble")?.textContent;
  if (text) { navigator.clipboard.writeText(text); toast("Copied"); }
});
els.copyTicket?.addEventListener("click", () => {
  if (lastTicket) { navigator.clipboard.writeText(lastTicket); toast("Reference copied"); }
});

els.menuToggle?.addEventListener("click", () => {
  if (els.sidebar?.classList.contains("open")) closeMobileSidebar();
  else openMobileSidebar();
});
els.overlay?.addEventListener("click", closeMobileSidebar);
els.chatSidebarBtn?.addEventListener("click", () => expandSidebar());

bindRailActions({
  onNewChat: startNewChat,
  onSearch: () => focusPanel(els.panelHistory),
  onOrders: () => focusPanel(els.panelOrders),
});

document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); startNewChat(); }
  if ((e.metaKey || e.ctrlKey) && e.key === "b") { e.preventDefault(); toggleSidebar(); }
  if (e.key === "Escape") {
    if (els.scenarioOverlay && !els.scenarioOverlay.hidden) closeScenarioPicker();
    else if (els.orderModalOverlay && !els.orderModalOverlay.hidden) closeOrderModal();
    else toggleAccountMenu(false);
  }
});

initApp();
