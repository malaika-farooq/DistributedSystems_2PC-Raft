const grid     = document.getElementById("cartGrid");
const totalEl  = document.getElementById("total");
const statusEl = document.getElementById("status");
const placeBtn = document.getElementById("placeOrder");

// ── Modal ──────────────────────────────────────────────────────────────────
function showModal(title, message, isSuccess, txnData) {
  const existing = document.getElementById("twopc-modal");
  if (existing) existing.remove();

  const nodes = [
    { id: "coordinator",     role: "Coordinator (Node 1)" },
    { id: "orders-node",     role: "Orders Participant (Node 2)" },
    { id: "carts-node",      role: "Carts Participant (Node 3)" },
    { id: "inventory-node",  role: "Inventory Participant (Node 4)" },
    { id: "payment-node",    role: "Payment Participant (Node 5)" },
  ];

  const nodesHtml = nodes.map(n =>
    `<div style="display:flex;align-items:center;gap:8px;padding:4px 0;">
       <span style="width:12px;height:12px;border-radius:50%;background:${isSuccess?'#4caf50':'#ef5350'};display:inline-block;flex-shrink:0;"></span>
       <span style="font-size:12px;"><strong>${n.id}</strong> — ${n.role}</span>
     </div>`
  ).join("");

  const protocolSteps = isSuccess ? `
    <div style="font-size:12px;font-family:monospace;line-height:1.8;">
      <strong>VOTING PHASE:</strong><br>
      1. coordinator → all 4 nodes: <em>RequestVote</em><br>
      2. All 4 nodes → coordinator: <em>vote-COMMIT</em><br>
      <br>
      <strong>DECISION PHASE:</strong><br>
      3. coordinator → all 4 nodes: <em>global-COMMIT</em><br>
      4. Each node: voting phase → decision phase: <em>DoCommit</em> (intra-node gRPC)<br>
      5. orders-node: Order saved ✓ &nbsp; Cart cleared ✓
    </div>` : `
    <div style="font-size:12px;font-family:monospace;line-height:1.8;">
      <strong>VOTING PHASE:</strong><br>
      1. coordinator → all 4 nodes: <em>RequestVote</em><br>
      2. At least one node voted: <em>ABORT</em><br>
      <br>
      <strong>DECISION PHASE:</strong><br>
      3. coordinator → all 4 nodes: <em>global-ABORT</em><br>
      4. Each node: voting phase → decision phase: <em>DoAbort</em> (intra-node gRPC)<br>
      5. No changes made — transaction rolled back
    </div>`;

  const modal = document.createElement("div");
  modal.id = "twopc-modal";
  modal.style.cssText = `
    position:fixed;top:0;left:0;width:100%;height:100%;
    background:rgba(0,0,0,0.65);display:flex;align-items:center;
    justify-content:center;z-index:9999;
  `;
  modal.innerHTML = `
    <div style="background:#fff;border-radius:10px;padding:32px;max-width:520px;
                width:92%;box-shadow:0 8px 40px rgba(0,0,0,0.35);overflow-y:auto;max-height:90vh;">
      <div style="text-align:center;margin-bottom:16px;">
        <div style="font-size:52px;">${isSuccess ? "✅" : "❌"}</div>
        <h2 style="margin:8px 0;color:${isSuccess?"#2e7d32":"#c62828"};">${title}</h2>
        <p style="color:#555;margin:0;">${message}</p>
      </div>

      <hr style="border:none;border-top:1px solid #eee;margin:16px 0;">

      <div style="margin-bottom:16px;">
        <strong style="font-size:13px;">5-Node 2PC Cluster:</strong>
        <div style="margin-top:8px;background:#f9f9f9;padding:10px;border-radius:6px;">
          ${nodesHtml}
        </div>
      </div>

      <div style="margin-bottom:20px;">
        <strong style="font-size:13px;">Protocol Execution:</strong>
        <div style="margin-top:8px;background:#f5f5f5;padding:12px;border-radius:6px;">
          ${protocolSteps}
        </div>
      </div>

      <p style="font-size:11px;color:#888;margin-bottom:16px;text-align:center;">
        📋 Full phase logs printed in Docker terminal (coordinator + all participant containers)
      </p>

      <div style="text-align:center;">
        <button onclick="document.getElementById('twopc-modal').remove()"
                style="background:#1565c0;color:#fff;border:none;padding:10px 32px;
                       border-radius:6px;font-size:15px;cursor:pointer;font-weight:bold;">
          Close
        </button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  modal.addEventListener("click", e => { if (e.target === modal) modal.remove(); });
}


// ── Cart loader ────────────────────────────────────────────────────────────
async function loadCart() {
  statusEl.textContent = "Loading...";
  grid.innerHTML = "";

  const res = await fetch("/api/cart");
  if (!res.ok) { statusEl.textContent = "Please log in."; return; }
  const data = await res.json();
  if (!data.ok) { statusEl.textContent = data.message || "Failed to load cart"; return; }

  for (const it of data.items) {
    const card = document.createElement("div");
    card.className = "card";
    const options = ['<option value="all" selected>All</option>']
      .concat(Array.from({ length: it.qty }, (_, i) =>
        `<option value="${i+1}">${i+1}</option>`))
      .join("");

    // image_url already has /images/ prefix from server API
    card.innerHTML = `
      <a href="/listing?id=${it.id}">
        <img src="${it.image_url}" alt="${it.title}"
             style="width:100%;height:160px;object-fit:cover;border-radius:4px;">
      </a>
      <div class="title"></div>
      <div>$${it.price.toFixed(2)} × ${it.qty}</div>
      <div><strong>$${it.line_total.toFixed(2)}</strong></div>
      <div class="row">
        <label>Remove:
          <select class="removeQty">${options}</select>
        </label>
        <button class="removeBtn" type="button">Remove</button>
      </div>
    `;
    card.querySelector(".title").textContent = it.title;

    const selectEl = card.querySelector(".removeQty");
    card.querySelector(".removeBtn").addEventListener("click", async () => {
      statusEl.textContent = "Removing...";
      const val = selectEl.value;
      const payload = val === "all"
        ? { item_id: it.id, remove_all: true }
        : { item_id: it.id, remove_all: false, quantity: Number(val) };
      const r = await fetch("/api/cart/remove", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const resp = await r.json().catch(() => ({ ok: false, message: "Error" }));
      statusEl.textContent = resp.ok ? "Removed" : (resp.message || "Failed");
      await loadCart();
    });
    grid.appendChild(card);
  }

  totalEl.textContent = `$${Number(data.total).toFixed(2)}`;
  statusEl.textContent = data.items.length ? "" : "Cart is empty.";
}


// ── Place Order via 2PC ────────────────────────────────────────────────────
placeBtn.addEventListener("click", async () => {
  statusEl.textContent = "Running 2PC transaction across 5 nodes...";
  placeBtn.disabled = true;

  try {
    const res  = await fetch("/api/order/place", { method: "POST" });
    const data = await res.json().catch(() => ({ ok: false, message: "Bad response" }));

    if (data.ok) {
      showModal(
        "Order Placed Successfully!",
        "All 5 nodes voted COMMIT. The transaction was committed across the entire cluster.",
        true
      );
      await loadCart();
    } else {
      showModal(
        "Transaction Aborted",
        `Reason: ${data.message || "One or more nodes voted ABORT."}`,
        false
      );
    }
  } catch (err) {
    showModal("Connection Error", `Could not reach coordinator: ${err.message}`, false);
  } finally {
    statusEl.textContent = "";
    placeBtn.disabled = false;
  }
});

loadCart();
