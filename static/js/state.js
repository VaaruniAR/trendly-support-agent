export const STORAGE_KEY = "aria_session";
export const SIDEBAR_KEY = "aria_sidebar_collapsed";
export const CUSTOMER_KEY = "aria_customer_email";

export const $ = (id) => document.getElementById(id);

export const els = {
  app: $("app"),
  messages: $("messages"),
  composer: $("composer"),
  input: $("message-input"),
  sendBtn: $("send-btn"),
  prompts: $("quick-prompts"),
  orders: $("order-hints"),
  ordersMore: $("orders-more"),
  history: $("chat-history"),
  historyCount: $("history-count"),
  historySearch: $("history-search"),
  chatTitle: $("chat-title"),
  escalation: $("escalation-banner"),
  ticket: $("ticket-display"),
  copyTicket: $("copy-ticket"),
  statusDot: $("status-dot"),
  statusText: $("status-text"),
  setup: $("setup-banner"),
  setupHint: $("setup-hint"),
  scrollBtn: $("scroll-bottom"),
  charCount: $("char-count"),
  toast: $("toast"),
  sidebar: $("sidebar"),
  sidebarToggle: $("sidebar-toggle"),
  panelHistory: $("panel-history"),
  panelOrders: $("panel-orders"),
  overlay: $("overlay"),
  menuToggle: $("menu-toggle"),
  chatSidebarBtn: $("chat-sidebar-btn"),
  sidebarPanel: document.querySelector(".sidebar-panel"),
  accountBtn: $("account-btn"),
  accountMenu: $("account-menu"),
  accountAvatar: $("account-avatar"),
  accountName: $("account-name"),
  accountSub: $("account-sub"),
  ordersEmptyHint: $("orders-empty-hint"),
  orderModalOverlay: $("order-modal-overlay"),
  orderModal: $("order-modal"),
  orderModalBody: $("order-modal-body"),
  orderModalClose: $("order-modal-close"),
  scenarioOverlay: $("scenario-order-overlay"),
  scenarioModal: $("scenario-order-modal"),
  scenarioList: $("scenario-order-list"),
  scenarioClose: $("scenario-order-close"),
  chooseOrderBtn: $("choose-order-btn"),
  ariaHome: $("aria-home"),
  scenarioTitle: $("scenario-order-title"),
  scenarioDescription: $("scenario-order-description"),
  evidenceInput: $("evidence-input"),
};

export let sessionId = localStorage.getItem(STORAGE_KEY);
export let loading = false;
export let assistant = "Aria";
export let store = "Trendly";
export let lastTicket = "";
export let scenarios = [];
export let orderList = [];
export let allOrders = [];
export let ordersShown = 5;
export const ORDERS_PAGE = 5;
export let allSessions = [];
export let customers = [];
export let currentCustomer = null; // { customer_id, name, email, order_count }

export function setSessionId(id) {
  sessionId = id;
  if (id) localStorage.setItem(STORAGE_KEY, id);
  else localStorage.removeItem(STORAGE_KEY);
}

export function setAssistant(name) {
  assistant = name;
}

export function setStore(name) {
  store = name;
}

export function setScenarios(items) {
  scenarios = items;
}

export function setOrderList(items) {
  orderList = items;
}

export function setAllOrders(items) {
  allOrders = items;
  ordersShown = ORDERS_PAGE;
}

export function growOrdersShown() {
  ordersShown = Math.min(ordersShown + ORDERS_PAGE, allOrders.length);
  return ordersShown;
}

export function getOrdersVisible() {
  return allOrders.slice(0, ordersShown);
}

export function ordersRemaining() {
  return Math.max(0, allOrders.length - ordersShown);
}

export function setAllSessions(items) {
  allSessions = items;
}

export function setLastTicket(ticket) {
  lastTicket = ticket || "";
}

export function setLoadingState(on) {
  loading = on;
}

export function setCustomers(items) {
  customers = items || [];
}

export function setCurrentCustomer(customer) {
  currentCustomer = customer || null;
  if (customer) localStorage.setItem(CUSTOMER_KEY, customer.email);
  else localStorage.removeItem(CUSTOMER_KEY);
}

export function getSavedCustomerEmail() {
  return localStorage.getItem(CUSTOMER_KEY);
}
