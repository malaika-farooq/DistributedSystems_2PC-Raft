const grid = document.getElementById("grid");
const statusEl = document.getElementById("status");

const titleEl = document.getElementById("title");
const priceEl = document.getElementById("price");
const imageEl = document.getElementById("image_url");
const typeEl  = document.getElementById("type");
const featuredEl = document.getElementById("is_featured");

const saveBtn = document.getElementById("save");
const clearBtn = document.getElementById("clear");

let editingId = null;

function formData() {
  return {
    title: titleEl.value.trim(),
    price: Number(priceEl.value || 0),
    image_url: imageEl.value.trim(),
    type: typeEl.value.trim(),
    is_featured: featuredEl.checked
  };
}

function setForm(item) {
  editingId = item?.id ?? null;
  titleEl.value = item?.title ?? "";
  priceEl.value = item?.price ?? "";
  imageEl.value = item?.image_url ?? "";
  typeEl.value  = item?.type ?? "";
  featuredEl.checked = !!item?.is_featured;
}

async function load() {
  grid.innerHTML = "";
  const res = await fetch("/api/admin/items");
  const items = await res.json();

  for (const it of items) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <img src="${it.image_url}" alt="">
      <div class="title"></div>
      <div>$${Number(it.price).toFixed(2)} · ${it.type}</div>
      <div style="margin-top:8px; display:flex; gap:8px;">
        <button class="edit" type="button">Edit</button>
        <button class="del" type="button">Delete</button>
      </div>
    `;
    card.querySelector(".title").textContent = it.title;

    card.querySelector(".edit").onclick = () => {
      setForm(it);
      statusEl.textContent = `Editing #${it.id}`;
    };

    card.querySelector(".del").onclick = async () => {
      statusEl.textContent = "Deleting...";
      const r = await fetch(`/api/admin/items/${it.id}`, { method: "DELETE" });
      const out = await r.json().catch(() => ({ ok:false, message:"Bad response"}));
      statusEl.textContent = out.ok ? "Deleted" : (out.message || "Failed");
      await load();
    };

    grid.appendChild(card);
  }
}

saveBtn.onclick = async () => {
  statusEl.textContent = "Saving...";
  const payload = formData();

  const url = editingId ? `/api/admin/items/${editingId}` : `/api/admin/items`;
  const method = editingId ? "PUT" : "POST";

  const r = await fetch(url, {
    method,
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  });

  const out = await r.json().catch(() => ({ ok:false, message:"Bad response"}));
  statusEl.textContent = out.ok ? "Saved" : (out.message || "Failed");

  if (out.ok) setForm(null);
  await load();
};

clearBtn.onclick = () => {
  setForm(null);
  statusEl.textContent = "";
};

load();