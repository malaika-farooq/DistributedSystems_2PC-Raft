
const grid = document.getElementById("grid");
const sortEl = document.getElementById("sort");
const featuredEl = document.getElementById("featured");
const refreshBtn = document.getElementById("refresh");
const statusEl = document.getElementById("status");
const typeEl = document.getElementById("type");
var init = true;
async function loadItems() {
  if (!grid) return;

  grid.innerHTML = "Loading...";

  const params = new URLSearchParams();

  if(init){
    const paramfilter = new URLSearchParams(window.location.search);
    const filter = paramfilter.get("filter");

    if (filter) {
      params.set("type", filter);
      if (typeEl && !typeEl.value) {
        typeEl.value = filter;
      }
    }
    init = false;
  }

  // 👇 check if page requests featured-only
  if (grid.dataset.featuredOnly === "true") {
    params.set("featured", "true");
  }
  
  if (featuredEl && featuredEl.checked) {
    params.set("featured", "true");
  }

  const sortEl = document.getElementById("sort");
  if (sortEl && sortEl.value) {
    params.set("sort", sortEl.value);
  }

  // const typeEl = document.getElementById("type");

  if (typeEl && typeEl.value) {
    params.set("type", typeEl.value);
  }

  const response = await fetch(`/api/items?${params.toString()}`);
  const items = await response.json();

  grid.innerHTML = "";

  for (const item of items) {
    const card = document.createElement("div");
    card.className = "card";

    card.innerHTML = `
      <a href="/listing?id=${item.id}"><img src="${item.image_url}" alt=""></a>
      <a class="title" href="/listing?id=${item.id}">${item.title}</a>
      <div class="price">$${item.price.toFixed(2)}</div>
    `;

    grid.appendChild(card);
  }
}

loadItems();

refreshBtn.addEventListener("click", loadItems);
sortEl.addEventListener("change", loadItems);
typeEl.addEventListener("change", loadItems);
featuredEl.addEventListener("change", loadItems);

// initial load
loadItems();