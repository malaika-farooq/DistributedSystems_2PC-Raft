const listingEl = document.getElementById("listing");
const qtyEl = document.getElementById("qty");
const addBtn = document.getElementById("addToCart");
const cartStatus = document.getElementById("cartStatus");

async function loadItem() {
  const params = new URLSearchParams(window.location.search);
  const id = params.get("id");
  if (!id) {
    listingEl.textContent = "Missing ?id=";
    return;
  }

  listingEl.textContent = "Loading...";
  const res = await fetch(`/api/listing?id=${encodeURIComponent(id)}`);
  if (!res.ok) {
    listingEl.textContent = "Item not found.";
    return;
  }
  const data = await res.json();
  const item = data.item;

  listingEl.innerHTML = `
    <div class="listing">
      <img src="${item.image_url}" alt="">
      <div class="title"></div>
      <div class="price">$${Number(item.price).toFixed(2)}</div>
    </div>
  `;
  listingEl.querySelector(".title").textContent = item.title;

  addBtn.onclick = async () => {
    cartStatus.textContent = "Adding...";
    const qty = Number(qtyEl.value || 1);

    const r = await fetch("/api/cart/add", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ item_id: Number(id), quantity: qty })
    });

    const resp = await r.json().catch(() => ({ ok: false, message: "Bad response" }));
    cartStatus.textContent = resp.ok ? "Added!" : (resp.message || "Failed");
  };
}

loadItem();
