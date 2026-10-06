const form = document.getElementById("search-form");
const queryInput = document.getElementById("q");
const stateSelect = document.getElementById("state");
const nationalOnly = document.getElementById("national-only");
const errorEl = document.getElementById("error");
const resultEl = document.getElementById("result");
const button = form.querySelector("button[type=submit]");

const $ = (id) => document.getElementById(id);
const shownParks = new Map();

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
  resultEl.hidden = true;
}

function renderInsights(data) {
  const summary = $("summary");
  summary.innerHTML = "";
  for (const line of data.summary) summary.appendChild(el("li", "", line));
  $("alerts-note").hidden = data.alerts_available;

  const activities = $("activities");
  activities.innerHTML = "";
  for (const item of data.analysis.top_activities) {
    const li = el("li");
    li.innerHTML = `
      <div class="row"><span class="label"></span><span class="count"></span></div>
      <div class="bar"><div class="fill"></div></div>`;
    li.querySelector(".label").textContent = item.name;
    li.querySelector(".count").textContent = `${item.count} · ${item.percent}%`;
    li.querySelector(".fill").style.width = `${item.percent}%`;
    activities.appendChild(li);
  }

  const states = $("states-list");
  states.innerHTML = "";
  for (const s of data.analysis.top_states) states.appendChild(el("li", "pill", `${s.state} · ${s.count}`));
  $("states-heading").hidden = data.analysis.top_states.length === 0;
}

function favoriteButton(park) {
  const btn = el("button", "favorite-btn", park.favorite ? "★ Saved" : "☆ Save");
  btn.type = "button";
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      if (park.favorite) {
        const resp = await fetch(`/api/favorites/${park.park_code}`, { method: "DELETE" });
        if (!resp.ok && resp.status !== 404) throw new Error();
        park.favorite = false;
      } else {
        const resp = await fetch("/api/favorites", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ park_code: park.park_code }),
        });
        if (!resp.ok) throw new Error();
        park.favorite = true;
      }
      btn.textContent = park.favorite ? "★ Saved" : "☆ Save";
      await refreshFavorites();
    } catch {
      alert("Could not update favorites. Please try again.");
    } finally {
      btn.disabled = false;
    }
  });
  return btn;
}

function renderPark(park) {
  const card = el("article", "card park");
  if (park.image_url) {
    const img = el("img", "park-image");
    img.src = park.image_url;
    img.alt = park.image_alt || park.name;
    img.loading = "lazy";
    card.appendChild(img);
  }

  const head = el("div", "park-head");
  const titleBlock = el("div");
  const title = el("h3", "park-name");
  const link = el("a", "", park.name);
  link.href = park.url;
  link.target = "_blank";
  link.rel = "noopener";
  title.appendChild(link);
  titleBlock.appendChild(title);
  titleBlock.appendChild(el("p", "park-meta", [park.designation, park.states.join(", ")].filter(Boolean).join(" · ")));
  head.appendChild(titleBlock);
  const button = favoriteButton(park);
  shownParks.set(park.park_code, { park, button });
  head.appendChild(button);
  card.appendChild(head);

  card.appendChild(el("p", "park-desc", park.description));

  if (park.alerts.length) {
    const alerts = el("div", "alerts");
    alerts.appendChild(el("p", "alerts-title", `${park.alerts.length} current alert${park.alerts.length === 1 ? "" : "s"}`));
    const list = el("ul");
    for (const a of park.alerts.slice(0, 3)) {
      const li = el("li");
      li.appendChild(el("span", `tag tag-${a.category.toLowerCase().replace(/\s+/g, "-")}`, a.category));
      li.appendChild(document.createTextNode(` ${a.title}`));
      list.appendChild(li);
    }
    alerts.appendChild(list);
    card.appendChild(alerts);
  }

  if (park.activities.length) {
    const acts = el("ul", "pill-list");
    for (const name of park.activities.slice(0, 12)) acts.appendChild(el("li", "pill", name));
    if (park.activities.length > 12) acts.appendChild(el("li", "pill muted", `+${park.activities.length - 12} more`));
    card.appendChild(acts);
  }
  return card;
}

async function refreshFavorites() {
  const resp = await fetch("/api/favorites");
  if (!resp.ok) return;
  const { favorites } = await resp.json();
  const list = $("favorites");
  list.innerHTML = "";
  for (const park of favorites) {
    const li = el("li");
    li.dataset.code = park.park_code;
    const label = el("span");
    label.appendChild(el("strong", "", park.name));
    if (park.note) label.appendChild(document.createTextNode(` — ${park.note}`));
    const remove = el("button", "link remove-favorite", "Remove");
    remove.type = "button";
    remove.dataset.code = park.park_code;
    li.append(label, remove);
    list.appendChild(li);
  }
  $("no-favorites").hidden = favorites.length > 0;
}

$("favorites").addEventListener("click", async (event) => {
  const btn = event.target.closest(".remove-favorite");
  if (!btn) return;
  await fetch(`/api/favorites/${btn.dataset.code}`, { method: "DELETE" });
  const shown = shownParks.get(btn.dataset.code);
  if (shown) {
    shown.park.favorite = false;
    shown.button.textContent = "☆ Save";
  }
  await refreshFavorites();
});

for (const chip of document.querySelectorAll(".chip")) {
  chip.addEventListener("click", () => {
    queryInput.value = chip.dataset.q || "";
    stateSelect.value = chip.dataset.state || "";
    nationalOnly.checked = chip.dataset.national === "1";
    selectedCode = null;
    form.requestSubmit();
  });
}

const suggestionsEl = $("suggestions");
let suggestions = [];
let activeIndex = -1;
let selectedCode = null;
let suggestTimer = null;
let suggestRequest = 0;

function closeSuggestions() {
  suggestionsEl.hidden = true;
  suggestionsEl.innerHTML = "";
  queryInput.setAttribute("aria-expanded", "false");
  queryInput.removeAttribute("aria-activedescendant");
  suggestions = [];
  activeIndex = -1;
}

function highlight(text, query) {
  const frag = document.createDocumentFragment();
  const start = text.toLowerCase().indexOf(query.toLowerCase());
  if (start < 0 || !query) {
    frag.append(text);
    return frag;
  }
  frag.append(text.slice(0, start), el("mark", "", text.slice(start, start + query.length)),
    text.slice(start + query.length));
  return frag;
}

function renderSuggestions(items, query) {
  suggestions = items;
  activeIndex = -1;
  suggestionsEl.innerHTML = "";
  if (!items.length) {
    closeSuggestions();
    return;
  }
  items.forEach((item, i) => {
    const li = el("li", "suggestion");
    li.id = `suggestion-${i}`;
    li.setAttribute("role", "option");
    const name = el("span", "suggestion-name");
    name.appendChild(highlight(item.name, query));
    li.appendChild(name);
    li.appendChild(el("span", "suggestion-meta", [item.designation, item.states.join(", ")].filter(Boolean).join(" · ")));
    li.addEventListener("mousedown", (event) => {
      event.preventDefault();
      chooseSuggestion(i);
    });
    suggestionsEl.appendChild(li);
  });
  suggestionsEl.hidden = false;
  queryInput.setAttribute("aria-expanded", "true");
}

function setActive(index) {
  const items = suggestionsEl.querySelectorAll(".suggestion");
  if (!items.length) return;
  activeIndex = (index + items.length) % items.length;
  items.forEach((li, i) => li.classList.toggle("active", i === activeIndex));
  queryInput.setAttribute("aria-activedescendant", items[activeIndex].id);
  items[activeIndex].scrollIntoView({ block: "nearest" });
}

function chooseSuggestion(index) {
  const item = suggestions[index];
  if (!item) return;
  queryInput.value = item.name;
  selectedCode = item.park_code;
  closeSuggestions();
  form.requestSubmit();
}

async function loadSuggestions(query) {
  const requestId = ++suggestRequest;
  try {
    const resp = await fetch(`/api/parks/suggest?q=${encodeURIComponent(query)}`);
    if (!resp.ok || requestId !== suggestRequest) return;
    const data = await resp.json();
    if (requestId === suggestRequest && queryInput.value.trim() === query) renderSuggestions(data.suggestions, query);
  } catch {
    closeSuggestions();
  }
}

queryInput.addEventListener("input", () => {
  selectedCode = null;
  clearTimeout(suggestTimer);
  const query = queryInput.value.trim();
  if (query.length < 2) {
    suggestRequest++;
    closeSuggestions();
    return;
  }
  suggestTimer = setTimeout(() => loadSuggestions(query), 200);
});

queryInput.addEventListener("keydown", (event) => {
  if (suggestionsEl.hidden) return;
  if (event.key === "ArrowDown") {
    event.preventDefault();
    setActive(activeIndex + 1);
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    setActive(activeIndex - 1);
  } else if (event.key === "Enter" && activeIndex >= 0) {
    event.preventDefault();
    chooseSuggestion(activeIndex);
  } else if (event.key === "Escape") {
    closeSuggestions();
  }
});

queryInput.addEventListener("blur", closeSuggestions);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearTimeout(suggestTimer);
  suggestRequest++;
  closeSuggestions();
  const params = new URLSearchParams();
  if (selectedCode) {
    params.set("code", selectedCode);
  } else if (queryInput.value.trim()) {
    params.set("q", queryInput.value.trim());
  }
  if (stateSelect.value) params.set("state", stateSelect.value);
  if (nationalOnly.checked) params.set("national_only", "1");

  errorEl.hidden = true;
  button.disabled = true;
  button.textContent = "Searching…";

  try {
    const resp = await fetch(`/api/parks?${params}`);
    const data = await resp.json().catch(() => ({ error: `The server ran into an error (HTTP ${resp.status}).` }));
    if (!resp.ok) {
      showError(data.error || "Something went wrong.");
      return;
    }
    renderInsights(data);
    const parks = $("parks");
    parks.innerHTML = "";
    shownParks.clear();
    for (const park of data.parks) parks.appendChild(renderPark(park));
    resultEl.hidden = false;
  } catch {
    showError("Could not reach the server. Please try again.");
  } finally {
    button.disabled = false;
    button.textContent = "Search";
  }
});
