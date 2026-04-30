const pages = [...document.querySelectorAll(".page")];
const navButtons = [...document.querySelectorAll(".nav-button")];
const startForm = document.querySelector("#start-form");
const moneyDisplay = document.querySelector("#money-display");
const submitBid = document.querySelector("#submit-bid");
const resultLogo = document.querySelector("#result-logo");
const resultTitle = document.querySelector("#result-title");
const robotBid1 = document.querySelector("#robot-bid-1");
const robotBid2 = document.querySelector("#robot-bid-2");
const totalPayout = document.querySelector("#total-payout");
const documentationJson = document.querySelector("#documentation-json");
const copyDocumentation = document.querySelector("#copy-documentation");
const downloadDocumentation = document.querySelector("#download-documentation");
const resetApp = document.querySelector("#reset-app");

let cents = 0;
let latestDocumentation = {};

function showPage(name) {
  pages.forEach((page) => page.classList.toggle("active", page.id === name));
  navButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.page === name);
  });
}

function formatMoney(value) {
  return `$${Number(value).toFixed(2)}`;
}

function updateMoney() {
  moneyDisplay.value = formatMoney(cents / 100);
  submitBid.disabled = cents === 0;
}

async function postJson(url, payload = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Request failed.");
  }
  return data;
}

async function refreshDocumentation() {
  const response = await fetch("/api/documentation");
  latestDocumentation = await response.json();
  documentationJson.textContent = JSON.stringify(latestDocumentation, null, 2);
}

function renderResult(state) {
  resultLogo.src = state.didWin ? "/figs/won_logo.png" : "/figs/lost_logo.png";
  resultLogo.alt = state.didWin ? "You won" : "You lost";
  resultTitle.textContent = state.didWin
    ? `Winning Bid: ${formatMoney(state.subjectBid)}`
    : `Your Bid: ${formatMoney(state.subjectBid)}`;
  robotBid1.textContent = formatMoney(state.robotBids[0] || 0);
  robotBid2.textContent = formatMoney(state.robotBids[1] || 0);
  totalPayout.textContent = `Total Payout: ${formatMoney(state.totalPayout)}`;
  refreshDocumentation();
}

navButtons.forEach((button) => {
  button.addEventListener("click", () => showPage(button.dataset.page));
});

startForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(startForm);
  await postJson("/api/start", Object.fromEntries(form.entries()));
  cents = 0;
  updateMoney();
  showPage("bid");
});

document.querySelector(".keypad").addEventListener("click", (event) => {
  if (!(event.target instanceof HTMLButtonElement)) {
    return;
  }

  const key = event.target.dataset.key || event.target.textContent;
  if (key === "clear") {
    cents = 0;
  } else if (key === "delete") {
    cents = Math.floor(cents / 10);
  } else {
    cents = cents * 10 + Number(key);
  }
  updateMoney();
});

submitBid.addEventListener("click", async () => {
  const state = await postJson("/api/bid", { cents });
  renderResult(state);
  showPage("result");
});

copyDocumentation.addEventListener("click", async () => {
  await navigator.clipboard.writeText(JSON.stringify(latestDocumentation, null, 2));
});

downloadDocumentation.addEventListener("click", () => {
  const body = JSON.stringify(latestDocumentation, null, 2);
  const blob = new Blob([body], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const sessionId = latestDocumentation.session?.id || "session";
  link.href = url;
  link.download = `vspavic-${sessionId}.json`;
  link.click();
  URL.revokeObjectURL(url);
});

resetApp.addEventListener("click", async () => {
  const state = await postJson("/api/reset");
  cents = 0;
  startForm.reset();
  updateMoney();
  renderResult(state);
  showPage("start");
});

fetch("/api/state")
  .then((response) => response.json())
  .then(renderResult);

updateMoney();
