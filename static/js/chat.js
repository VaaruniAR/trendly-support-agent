import {
  $, allOrders, allSessions, assistant, currentCustomer, customers, els, loading, orderList, scenarios, sessionId,
  setAllSessions, setAssistant, setLastTicket, setLoadingState,
  setAllOrders, setOrderList, setScenarios, setSessionId, setStore, store,
  growOrdersShown, getOrdersVisible, ordersRemaining, ORDERS_PAGE,
  setCustomers, setCurrentCustomer, getSavedCustomerEmail,
} from "./state.js";
import { expandSidebar, initSidebar } from "./sidebar.js";
import { api, esc, mdLite, relTime, toast, truthy, fmtDate, fmtINR, itemVisual, statusClass, MESSAGE_MAX } from "./util.js";

export function updateCharCount() {
  const n = els.input.value.length;
  els.charCount.textContent = `${n}/${MESSAGE_MAX}`;
  els.charCount.classList.toggle("warn", n > MESSAGE_MAX - 200);
}

export function scrollEnd(force) {
  const near = els.messages.scrollHeight - els.messages.scrollTop - els.messages.clientHeight < 48;
  if (force) els.messages.scrollTop = els.messages.scrollHeight;
  els.scrollBtn.hidden = near;
}

export function setEscalation(on, ticket) {
  setLastTicket(ticket);
  els.escalation.classList.toggle("hidden", !(on && ticket));
  els.ticket.textContent = ticket || "";
}

export function setLoading(on) {
  setLoadingState(on);
  els.input.disabled = on;
  els.sendBtn.disabled = on;
}

export function setEvidenceUpload(on) {
  const lastAssistant = els.messages.querySelector(".msg.assistant:last-of-type .body");
  const existing = lastAssistant?.querySelector(".evidence-action");
  if (!on || existing || !lastAssistant) return;
  lastAssistant.insertAdjacentHTML("beforeend", `
    <button type="button" class="evidence-action" data-upload-evidence>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 7a2 2 0 012-2h2l1.2-1.5h5.6L16 5h2a2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V7z"/><circle cx="12" cy="12.5" r="3.2"/></svg>
      Add photo
    </button>`);
}

export function setSetup(on, hint) {
  els.setup.classList.toggle("hidden", !on);
  if (on) {
    els.setupHint.textContent = hint || "Set GROQ_API_KEY=gsk_... in .env — you can still type, but replies need the key.";
  } else if (!loading) {
    els.input.disabled = false;
    els.sendBtn.disabled = false;
  }
}

export function showWelcome() {
  const firstName = currentCustomer ? currentCustomer.name.split(" ")[0] : null;
  const suggested = scenarios.slice(0, 3).map((scenario, index) =>
    `<button type="button" class="welcome-prompt" data-welcome-i="${index}"><span>${esc(scenario.label)}</span><b aria-hidden="true">→</b></button>`
  ).join("");
  els.messages.innerHTML = `
    <div class="welcome">
      <p class="welcome-eyebrow">ARIA CUSTOMER SUPPORT</p>
      <h3>${firstName ? `Hello, ${esc(firstName)}. How can I help?` : "How can I help?"}</h3>
      <p>I can check where an order is, help with a return or exchange, explain the policy, or connect you with a person.</p>
      <div class="welcome-ask">
        <span>Try asking</span>
        <div class="welcome-prompts" id="welcome-prompts">${suggested}</div>
      </div>
    </div>`;
  els.chatTitle.textContent = firstName ? `Hi ${firstName}, how can we help?` : "How can we help?";
}

export function appendMsg(role, text, idx = 0, orderPreview = null, choices = [], imagePreview = null) {
  const wasNearBottom = els.messages.scrollHeight - els.messages.scrollTop - els.messages.clientHeight < 96;
  els.messages.querySelector(".welcome")?.remove();
  const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.style.animationDelay = `${Math.min(idx * 40, 200)}ms`;
  el.innerHTML = role === "assistant"
    ? `<div class="avatar">${assistant[0]}</div><div class="body"><div class="bubble">${mdLite(text)}</div>${returnChoicesHtml(choices)}${orderPreviewHtml(orderPreview)}<div class="meta"><span>${assistant}</span><span>${time}</span><button type="button" class="copy-msg" title="Copy">⎘</button></div></div>`
    : `<div class="body"><div class="bubble">${esc(text)}${imagePreviewHtml(imagePreview)}</div><div class="meta"><span>You</span><span>${time}</span></div></div>`;
  els.messages.appendChild(el);
  scrollEnd(wasNearBottom);
}

function imagePreviewHtml(dataUrl) {
  if (typeof dataUrl !== "string" || !dataUrl.startsWith("data:image/")) return "";
  return `<img class="evidence-preview" src="${dataUrl}" alt="Photo uploaded for return review">`;
}

function returnChoicesHtml(choices) {
  if (!choices?.length) return "";
  return `<div class="return-choices" aria-label="Choose a return option">${choices.map((choice) =>
    `<button type="button" class="return-choice" data-return-choice="${esc(choice.value)}">${esc(choice.label)}</button>`
  ).join("")}</div>`;
}

function typing(on) {
  const wasNearBottom = els.messages.scrollHeight - els.messages.scrollTop - els.messages.clientHeight < 96;
  document.getElementById("typing")?.remove();
  if (!on) return;
  const el = document.createElement("div");
  el.id = "typing";
  el.className = "msg assistant";
  el.innerHTML = `<div class="avatar">${assistant[0]}</div><div class="body"><div class="typing"><span></span><span></span><span></span></div></div>`;
  els.messages.appendChild(el);
  scrollEnd(wasNearBottom);
}

export function renderPrompts(items) {
  setScenarios(items.slice(0, 6));
  els.prompts.innerHTML = scenarios.map((s, i) =>
    `<button type="button" class="chip" data-i="${i}">${esc(s.label)}</button>`
  ).join("");
  const welcomePrompts = document.getElementById("welcome-prompts");
  if (welcomePrompts) {
    welcomePrompts.innerHTML = scenarios.slice(0, 3).map((s, i) =>
      `<button type="button" class="welcome-prompt" data-welcome-i="${i}"><span>${esc(s.label)}</span><b aria-hidden="true">→</b></button>`
    ).join("");
  }
}

export function renderOrders(items) {
  setAllOrders(items || []);
  paintOrders();
}

export function showMoreOrders() {
  growOrdersShown();
  paintOrders();
}

function paintOrders() {
  const visible = getOrdersVisible();
  setOrderList(visible);
  els.orders.innerHTML = visible.map((o, i) => {
    const primary = o.items?.[0];
    const visual = primary ? itemVisual(primary.name, primary.category) : null;
    return `<li data-i="${i}" class="order-mini-card">
      <span class="order-card-head"><span><strong class="oid">${esc(o.order_id)}</strong><small>${esc(orderDateLabel(o))}</small></span><span class="status-badge ${statusClass(o.status)}">${esc(o.status_label)}</span></span>
      <span class="order-card-products">${(o.items || []).map((item) => orderMiniProduct(item)).join("")}</span>
      <span class="order-card-foot"><span>${o.item_count} item${o.item_count === 1 ? "" : "s"}</span><strong>${fmtINR(o.total_amount)}</strong><em>Choose</em></span>
    </li>`;
  }).join("");
  const remaining = ordersRemaining();
  const moreBtn = els.ordersMore || document.getElementById("orders-more");
  if (moreBtn) {
    moreBtn.hidden = remaining <= 0;
    moreBtn.textContent = remaining > 0
      ? `View more (${Math.min(ORDERS_PAGE, remaining)} more)`
      : "View more";
  }
  if (els.ordersEmptyHint) {
    els.ordersEmptyHint.classList.toggle("hidden", !!currentCustomer);
  }
}

function orderDateLabel(order) {
  if (order.delivered_at) return `Delivered ${fmtDate(order.delivered_at)}`;
  if (order.expected_delivery) return `Expected ${fmtDate(order.expected_delivery)}`;
  if (order.placed_at) return `Placed ${fmtDate(order.placed_at)}`;
  return order.status_label;
}

function orderMiniProduct(item) {
  const visual = itemVisual(item.name, item.category);
  return `<span class="order-card-product">
    <span class="order-mini-image tint-${visual.tint} product-${visual.key}" aria-hidden="true">${productVisualHtml(visual)}</span>
    <span class="order-mini-body"><span class="order-mini-name">${esc(item.name)}</span><span class="ost">Size ${esc(item.size || "—")}${item.qty > 1 ? ` · Qty ${item.qty}` : ""}</span></span>
    <strong class="order-item-price">${fmtINR(item.price)}</strong>
  </span>`;
}

function productVisualHtml(visual) {
  return visual.key === "belt" ? '<span class="belt-visual"><i></i></span>' : visual.emoji;
}

function initials(name) {
  return (name || "?").trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() || "").join("");
}

export function renderAccountMenu() {
  if (!els.accountMenu) return;
  els.accountMenu.innerHTML = customers.map((c) => `
    <button type="button" class="account-item${currentCustomer?.email === c.email ? " active" : ""}" data-email="${esc(c.email)}">
      <span class="account-avatar">${esc(initials(c.name))}</span>
      <span class="account-info">
        <span class="account-name">${esc(c.name)}</span>
      </span>
    </button>`).join("");
}

export function toggleAccountMenu(show) {
  if (!els.accountMenu || !els.accountBtn) return;
  const next = show ?? els.accountMenu.hidden;
  els.accountMenu.hidden = !next;
  els.accountBtn.setAttribute("aria-expanded", String(next));
}

export async function loadCustomers() {
  try {
    const data = await api("/customers");
    setCustomers(data.customers || []);
    renderAccountMenu();
  } catch { /* optional */ }
}

export async function refreshOrdersForCustomer() {
  try {
    const q = currentCustomer ? `?customer_email=${encodeURIComponent(currentCustomer.email)}` : "";
    const cat = await api(`/catalog${q}`);
    renderOrders(cat.orders || []);
  } catch { /* optional */ }
}

export async function selectCustomer(customer) {
  setCurrentCustomer(customer);
  if (els.accountAvatar) els.accountAvatar.textContent = initials(customer.name);
  if (els.accountName) els.accountName.textContent = customer.name;
  if (els.accountSub) { els.accountSub.textContent = ""; els.accountSub.hidden = true; }
  renderAccountMenu();
  toggleAccountMenu(false);
  await refreshOrdersForCustomer();
  startNewChat();
}

function orderItemsHtml(items, variant = "") {
  return (items || []).map((it) => {
    const visual = itemVisual(it.name, it.category);
    const meta = [
      it.size ? `Size ${esc(it.size)}` : "",
      it.qty > 1 ? `Qty ${it.qty}` : "",
      it.final_sale ? "Final sale" : "",
      it.shipped === false ? "Not yet shipped" : "",
    ].filter(Boolean).join(" · ");
    return `
      <li class="oi-row ${variant}">
        <span class="oi-thumb tint-${visual.tint} product-${visual.key}" aria-hidden="true">${productVisualHtml(visual)}</span>
        <span class="oi-info">
          <span class="oi-name">${esc(it.name)}</span>
          <span class="oi-meta">${meta}</span>
          ${it.backorder_eta ? `<span class="oi-backorder">Back in stock around ${fmtDate(it.backorder_eta)}</span>` : ""}
        </span>
        <span class="oi-price">${fmtINR((it.price || 0) * (it.qty || 1))}</span>
      </li>`;
  }).join("");
}

function orderPreviewHtml(order) {
  if (!order) return "";
  const date = order.delivered_at
    ? `Delivered ${fmtDate(order.delivered_at)}`
    : order.expected_delivery
      ? `Expected by ${fmtDate(order.expected_delivery)}`
      : `Placed ${fmtDate(order.placed_at)}`;
  const fulfilment = [order.carrier, order.tracking_number ? `Tracking ${order.tracking_number}` : ""]
    .filter(Boolean).join(" · ");
  return `
    <section class="order-preview" aria-label="Order preview ${esc(order.order_id)}">
      <div class="order-preview-head">
        <div>
          <p class="order-preview-label">Order overview</p>
          <h3>${esc(order.order_id)}</h3>
        </div>
        <span class="status-badge ${statusClass(order.status)}">${esc(order.status_label)}</span>
      </div>
      <div class="order-preview-date">${esc(date)}</div>
      <ul class="oi-list order-preview-items">${orderItemsHtml(order.items, "oi-row-lg")}</ul>
      <dl class="order-preview-facts">
        <div><dt>Order total</dt><dd>${fmtINR(order.total_amount)}</dd></div>
        ${fulfilment ? `<div><dt>Delivery</dt><dd>${esc(fulfilment)}</dd></div>` : ""}
        ${order.payment_method ? `<div><dt>Payment</dt><dd>${esc(order.payment_method.replaceAll("_", " "))}</dd></div>` : ""}
      </dl>
    </section>`;
}

export function openOrderModal(order) {
  if (!els.orderModalBody || !order) return;
  const facts = [
    ["Total", fmtINR(order.total_amount)],
    ["Placed", fmtDate(order.placed_at)],
    order.delivered_at && ["Delivered", fmtDate(order.delivered_at)],
    !order.delivered_at && order.expected_delivery && ["Expected", fmtDate(order.expected_delivery)],
    order.carrier && ["Carrier", order.carrier],
    order.tracking_number && ["Tracking", order.tracking_number],
    order.payment_method && ["Payment", order.payment_method.replaceAll("_", " ")],
  ].filter(Boolean);
  els.orderModalBody.innerHTML = `
    <div class="om-head">
      <div>
        <h3 id="order-modal-title">${esc(order.order_id)}</h3>
        <p class="om-sub">${order.item_count} item${order.item_count === 1 ? "" : "s"}</p>
      </div>
      <span class="status-badge ${statusClass(order.status)}">${esc(order.status_label)}</span>
    </div>
    <p class="om-status">${esc(order.delivered_at ? `Delivered ${fmtDate(order.delivered_at)}` : order.expected_delivery ? `Expected by ${fmtDate(order.expected_delivery)}` : "Order status available")}</p>
    <ul class="oi-list oi-list--modal">${orderItemsHtml(order.items, "oi-row-lg")}</ul>
    <dl class="om-facts">
      ${facts.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`).join("")}
    </dl>
    <button type="button" class="btn-new-chat om-ask" id="order-modal-ask" data-order="${esc(order.order_id)}">Ask ${esc(assistant)} about this order</button>
  `;
  els.orderModalOverlay.hidden = false;
  document.body.style.overflow = "hidden";
}

export function closeOrderModal() {
  if (!els.orderModalOverlay) return;
  els.orderModalOverlay.hidden = true;
  document.body.style.overflow = "";
}

let pendingScenario = null;

function renderOrderPicker() {
  els.scenarioList.innerHTML = allOrders.map((o) => `
    <li>
      <button type="button" class="sp-item" data-order="${esc(o.order_id)}">
        <span class="sp-top">
          <span class="sp-info">
            <span class="sp-oid">${esc(o.order_id)}</span>
            <span class="sp-ost">${esc(orderDateLabel(o))}</span>
          </span>
          <span class="status-badge ${statusClass(o.status)}">${esc(o.status_label)}</span>
        </span>
        <span class="sp-products">${orderItemsHtml(o.items, "oi-row-picker")}</span>
        <span class="sp-choose"><span>${o.item_count} item${o.item_count === 1 ? "" : "s"}</span><strong>${fmtINR(o.total_amount)}</strong><em>Choose</em></span>
      </button>
    </li>`).join("");
}

export function openOrderChooser() {
  if (!currentCustomer) {
    toast("Choose a customer first so I can show their orders");
    toggleAccountMenu(true);
    return;
  }
  if (!allOrders.length) {
    toast("No orders found for this customer");
    return;
  }
  pendingScenario = null;
  els.scenarioTitle.textContent = "Which order can I help with?";
  els.scenarioDescription.textContent = "Choose an order to see its full status, delivery details, and every item.";
  els.scenarioModal?.classList.add("order-chooser");
  renderOrderPicker();
  els.scenarioOverlay.hidden = false;
  document.body.style.overflow = "hidden";
}

export function openScenarioPicker(scenario) {
  if (!els.scenarioOverlay || !els.scenarioList) {
    fillPrompt(scenario.message);
    return;
  }
  if (!currentCustomer) {
    toast("Choose a profile first so I can show your orders");
    toggleAccountMenu(true);
    return;
  }
  if (!allOrders.length) {
    toast("No orders found for this profile — type the order ID");
    fillPrompt(scenario.message);
    return;
  }
  pendingScenario = scenario;
  els.scenarioTitle.textContent = "Which order is this about?";
  els.scenarioDescription.textContent = "Choose an order so Aria can use the correct details.";
  els.scenarioModal?.classList.remove("order-chooser");
  renderOrderPicker();
  els.scenarioOverlay.hidden = false;
  document.body.style.overflow = "hidden";
}

export function closeScenarioPicker() {
  if (!els.scenarioOverlay) return;
  els.scenarioOverlay.hidden = true;
  document.body.style.overflow = "";
  pendingScenario = null;
  els.scenarioModal?.classList.remove("order-chooser");
}

export function pickScenarioOrder(orderId) {
  if (!pendingScenario) {
    const order = allOrders.find((item) => item.order_id === orderId);
    closeScenarioPicker();
    if (order) openOrderModal(order);
    return;
  }
  const msg = pendingScenario.message.trim() + " " + orderId;
  closeScenarioPicker();
  fillPrompt(msg);
}

function filterSessions(query) {
  const q = query.trim().toLowerCase();
  if (!q) return allSessions;
  return allSessions.filter((s) => (s.search_text || s.title || "").includes(q));
}

function renderHistoryList(sessions) {
  if (!allSessions.length) {
    els.history.innerHTML = `<li class="empty">No chats yet</li>`;
    return;
  }
  if (!sessions.length) {
    els.history.innerHTML = `<li class="empty">No matches</li>`;
    return;
  }
  els.history.innerHTML = sessions.map((s) => `
    <li class="hist${s.session_id === sessionId ? " active" : ""}">
      <button type="button" class="hist-btn" data-id="${s.session_id}">
        <span class="hist-title">${esc(s.title)}</span>
        <span class="hist-meta">${s.message_count} · ${relTime(s.updated_at)}</span>
      </button>
      <button type="button" class="hist-del" data-del="${s.session_id}" title="Delete">×</button>
    </li>`).join("");
}

export function filterAndRenderHistory(query) {
  renderHistoryList(filterSessions(query));
}

export async function refreshHistory() {
  if (!currentCustomer) {
    setAllSessions([]);
    els.historyCount.textContent = "0";
    els.historyCount.classList.add("hidden");
    renderHistoryList([]);
    return;
  }
  try {
    const q = `?customer_email=${encodeURIComponent(currentCustomer.email)}`;
    const { sessions = [], count } = await api(`/sessions${q}`);
    setAllSessions(sessions);
    const n = count ?? sessions.length;
    els.historyCount.textContent = String(n);
    els.historyCount.classList.toggle("hidden", n === 0);
    renderHistoryList(filterSessions(els.historySearch?.value || ""));
  } catch { /* ignore */ }
}

export async function loadSession(id) {
  if (loading) return;
  try {
    const q = currentCustomer ? `?customer_email=${encodeURIComponent(currentCustomer.email)}` : "";
    const data = await api(`/session/${id}${q}`);
    setSessionId(data.session_id);
    els.chatTitle.textContent = data.title || "Chat";
    els.messages.innerHTML = "";
    (data.messages || []).forEach((m, i) => appendMsg(m.role, m.content, i));
    if (!data.messages?.length) showWelcome();
    setEscalation(data.escalated, data.ticket_id);
    setEvidenceUpload(data.awaiting_evidence);
    await refreshHistory();
    scrollEnd(true);
  } catch {
    setSessionId(null);
    showWelcome();
    toast("Chat not found");
  }
}

export async function deleteSession(id) {
  if (!confirm("Delete this chat?")) return;
  await fetch(`/session/${id}`, { method: "DELETE" });
  if (sessionId === id) startNewChat();
  await refreshHistory();
}

export function fillPrompt(text) {
  els.input.value = text;
  els.input.style.height = "auto";
  els.input.style.height = Math.min(els.input.scrollHeight, 120) + "px";
  updateCharCount();
  els.input.focus();
  const len = text.length;
  els.input.setSelectionRange(len, len);
  expandSidebar();
}

export async function sendMessage(text) {
  const msg = (text || els.input.value).trim();
  if (!msg || loading) return;

  els.input.value = "";
  els.input.style.height = "auto";
  updateCharCount();
  appendMsg("user", msg);
  setLoading(true);
  typing(true);

  try {
    const data = await api("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: msg,
        session_id: sessionId,
        customer_email: currentCustomer?.email || null,
        customer_name: currentCustomer?.name || null,
      }),
    });
    typing(false);
    setSessionId(data.session_id);
    const fullUpdate = /\b(?:full\s+(?:order\s+)?(?:update|details|status)|complete\s+update|everything\s+about)\b/i.test(msg);
    const mentionedOrder = msg.match(/\bTR[-\s]?(\d{4})\b/i);
    const orderId = mentionedOrder ? `TR-${mentionedOrder[1]}`.toUpperCase() : null;
    const preview = fullUpdate && orderId
      ? allOrders.find((order) => order.order_id.toUpperCase() === orderId)
      : null;
    appendMsg("assistant", data.reply, 0, preview, data.choices || []);
    setEscalation(data.escalated, data.ticket_id);
    setEvidenceUpload(data.awaiting_evidence);
    els.chatTitle.textContent = msg.length > 42 ? msg.slice(0, 42) + "…" : msg;
    await refreshHistory();
  } catch (e) {
    typing(false);
    if (e.message.includes("GROQ")) checkHealth();
    toast(e.message);
  } finally {
    setLoading(false);
    els.input.focus();
  }
}

export function startNewChat() {
  setSessionId(null);
  els.escalation.classList.add("hidden");
  setEvidenceUpload(false);
  showWelcome();
  refreshHistory();
  els.input.focus();
}

export async function uploadEvidence(file) {
  if (!file || loading || !sessionId) return;
  const allowed = ["image/jpeg", "image/png", "image/webp"];
  if (!allowed.includes(file.type) || file.size > 5 * 1024 * 1024) {
    toast("Choose a JPG, PNG, or WebP photo under 5 MB");
    return;
  }
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
  appendMsg("user", "Photo uploaded for return review", 0, null, [], dataUrl);
  setLoading(true);
  try {
    const data = await api("/evidence", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, data_url: dataUrl }),
    });
    appendMsg("assistant", data.reply);
    setEscalation(data.escalated, data.ticket_id);
    setEvidenceUpload(data.awaiting_evidence);
    await refreshHistory();
  } catch (e) {
    toast(e.message || "Could not upload the photo");
  } finally {
    setLoading(false);
    if (els.evidenceInput) els.evidenceInput.value = "";
  }
}

export async function checkHealth() {
  try {
    const h = await api("/health");
    const key = truthy(h.groq_key_set);
    const ready = truthy(h.llm_configured);
    els.statusDot.className = `status-dot ${key && ready ? "on" : key ? "wait" : "off"}`;
    if (!key) { els.statusText.textContent = "Key needed"; setSetup(true, h.setup_hint); }
    else if (!ready) { els.statusText.textContent = "Restart"; setSetup(true, "Restart ./run.sh"); }
    else { els.statusText.textContent = "Online"; setSetup(false); }
  } catch {
    els.statusDot.className = "status-dot off";
    els.statusText.textContent = "Offline";
  }
}

export async function initApp() {
  initSidebar();
  try {
    const cfg = await api("/config/ui");
    setAssistant(cfg.assistant_name || assistant);
    setStore(cfg.store_name || store);
    const brandName = $("brand-name");
    const brandMark = $("brand-mark");
    if (brandName) brandName.textContent = assistant;
    if (brandMark) brandMark.textContent = assistant[0];
    document.title = `${assistant} — Support`;
  } catch { /* defaults */ }

  await checkHealth();

  await loadCustomers();
  const savedEmail = getSavedCustomerEmail();
  const saved = savedEmail && customers.find((c) => c.email === savedEmail);
  if (saved) {
    setCurrentCustomer(saved);
    if (els.accountAvatar) els.accountAvatar.textContent = initials(saved.name);
    if (els.accountName) els.accountName.textContent = saved.name;
    if (els.accountSub) { els.accountSub.textContent = ""; els.accountSub.hidden = true; }
    renderAccountMenu();
  } else {
    // No profile could be resolved — a locally-saved session id can't be
    // attributed to anyone, so don't let it leak another profile's chat.
    setSessionId(null);
  }

  try {
    const cat = await api(`/catalog${currentCustomer ? `?customer_email=${encodeURIComponent(currentCustomer.email)}` : ""}`);
    renderPrompts(cat.scenarios || []);
    renderOrders(cat.orders || []);
  } catch { /* optional */ }

  await refreshHistory();
  if (sessionId) await loadSession(sessionId);
  else showWelcome();

  els.input.focus();
}
