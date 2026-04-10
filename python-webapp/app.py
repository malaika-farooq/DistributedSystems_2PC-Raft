from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import grpc
import os

import auth_pb2
import auth_pb2_grpc

import productlisting_pb2
import productlisting_pb2_grpc

import usercarts_pb2
import usercarts_pb2_grpc

import orders_pb2
import orders_pb2_grpc

import admin_pb2
import admin_pb2_grpc

import twopc_pb2
import twopc_pb2_grpc



PRODUCTS_GRPC_TARGET = os.environ.get("PRODUCTS_GRPC_TARGET", "microservice-productlisting:50052")

# (optional) create one channel and reuse it
_products_channel = grpc.insecure_channel(PRODUCTS_GRPC_TARGET)
_products_stub = productlisting_pb2_grpc.ProductListingServiceStub(_products_channel)

CARTS_GRPC_TARGET = os.environ.get("CARTS_GRPC_TARGET", "microservice-usercarts:50053")
_carts_channel = grpc.insecure_channel(CARTS_GRPC_TARGET)
_carts_stub = usercarts_pb2_grpc.UserCartsServiceStub(_carts_channel)

ORDERS_GRPC_TARGET = os.environ.get("ORDERS_GRPC_TARGET", "microservice-orders:50054")
_orders_channel = grpc.insecure_channel(ORDERS_GRPC_TARGET)
_orders_stub = orders_pb2_grpc.OrdersServiceStub(_orders_channel)

COORDINATOR_GRPC_TARGET = os.environ.get("COORDINATOR_GRPC_TARGET", "microservice-2pc-coordinator:50060")
_coordinator_channel = grpc.insecure_channel(COORDINATOR_GRPC_TARGET)
_coordinator_stub = twopc_pb2_grpc.CoordinatorServiceStub(_coordinator_channel)

ADMIN_GRPC_TARGET = os.environ.get("ADMIN_GRPC_TARGET", "microservice-admin:50055")
_admin_channel = grpc.insecure_channel(ADMIN_GRPC_TARGET)
_admin_stub = admin_pb2_grpc.AdminServiceStub(_admin_channel)

from functools import wraps
from flask import abort

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("user") != "admin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

app = Flask(__name__)
app.secret_key = "change-this"

AUTH_TARGET = "microservice-userauth:50051"

import requests
from flask import Response

IMAGES_BASE = os.environ.get("IMAGES_BASE", "http://microservice-images")

def make_image_url(raw):
    """Convert bare filename to /images/ path; leave full URLs alone."""
    if not raw:
        return raw
    if raw.startswith("http") or raw.startswith("/"):
        return raw
    return f"/images/{raw}"


@app.get("/images/<path:filename>")
def images_proxy(filename):
    r = requests.get(f"{IMAGES_BASE}/{filename}", stream=True, timeout=5)
    return Response(r.content, status=r.status_code, content_type=r.headers.get("Content-Type"))


def check_login_via_grpc(username: str, password: str):
    # You can reuse the channel globally for efficiency; this is simplest.
    with grpc.insecure_channel(AUTH_TARGET) as channel:
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        resp = stub.CheckLogin(auth_pb2.CheckLoginRequest(username=username, password=password))
        return resp


@app.get("/")
def index():
    return render_template("index.html")

@app.get("/products")
def products():
    return render_template("products.html")

@app.get("/listing")
def listing_page():
    return render_template("listing.html")

@app.get("/cart")
def cart_page():
    return render_template("cart.html")

@app.get("/admin")
@admin_required
def admin_page():
    return render_template("admin.html")

@app.get("/__routes")
def __routes():
    return "\n".join(sorted([str(r) for r in app.url_map.iter_rules()]))

@app.post("/login")
def login():
    username = request.form.get("user", "")
    password = request.form.get("password", "")

    resp = check_login_via_grpc(username, password)
    if resp.ok:
        session["user"] = username
        session["user_id"] = resp.user_id
        return redirect(url_for("index"))

    flash(resp.message or "Login failed")
    return redirect(url_for("index"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.get("/register")
def register_page():
    return render_template("register.html")

@app.post("/register")
def register_post():
    username = request.form.get("user", "")
    password = request.form.get("password", "")

    # call auth microservice
    with grpc.insecure_channel(AUTH_TARGET) as channel:
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        resp = stub.Register(auth_pb2.RegisterRequest(username=username, password=password))

    if resp.ok:
        # log them in immediately (optional)
        session["user"] = username
        session["user_id"] = resp.user_id
        return redirect(url_for("index"))

    flash(resp.message or "Registration failed")
    return redirect(url_for("register_page"))

@app.get("/api/items")
def api_items_grpc():
    sort = request.args.get("sort", "")
    featured = request.args.get("featured", "false").lower() == "true"
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    type_filter = request.args.get("type", "")

    resp = _products_stub.ListItems(productlisting_pb2.ListItemsRequest(
        sort=sort,
        featured_only=featured,
        type=type_filter,
        limit=limit,
        offset=offset,
    ))

    # Convert protobuf -> JSON for the browser
    return jsonify([
        {
            "id": it.id,
            "title": it.title,
            "price": it.price,
            "image_url": make_image_url(it.image_url),
            "isFeatured": it.is_featured,
        }
        for it in resp.items
    ])

@app.get("/api/listing")
def api_listing():
    try:
        item_id = int(request.args.get("id", ""))
    except ValueError:
        return jsonify({"error": "id must be an integer"}), 400

    resp = _products_stub.GetItem(productlisting_pb2.GetItemRequest(id=item_id))

    if not resp.found:
        return jsonify({"found": False}), 404

    it = resp.item
    return jsonify({
        "found": True,
        "item": {
            "id": it.id,
            "title": it.title,
            "price": it.price,
            "image_url": make_image_url(it.image_url),
            "isFeatured": it.is_featured,
            "type": it.type,  # include if you have it
        }
    })

@app.post("/api/cart/add")
def api_cart_add():
    # Require login
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"ok": False, "message": "Not logged in"}), 401

    data = request.get_json(silent=True) or {}
    try:
        item_id = int(data.get("item_id", 0))
        quantity = int(data.get("quantity", 1))
    except ValueError:
        return jsonify({"ok": False, "message": "Invalid payload"}), 400

    resp = _carts_stub.AddToCart(usercarts_pb2.AddToCartRequest(
        user_id=str(user_id),
        item_id=item_id,
        quantity=quantity,
    ))

    return jsonify({"ok": resp.ok, "message": resp.message}), (200 if resp.ok else 400)

@app.get("/api/cart")
def api_cart():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"ok": False, "message": "Not logged in"}), 401

    cart = _carts_stub.GetCart(usercarts_pb2.GetCartRequest(user_id=str(user_id)))

    items = []
    total = 0.0

    for ci in cart.items:
        # product info
        pr = _products_stub.GetItem(productlisting_pb2.GetItemRequest(id=ci.item_id))
        if not pr.found:
            continue
        p = pr.item
        line_total = float(p.price) * int(ci.quantity)
        total += line_total
        items.append({
            "id": p.id,
            "title": p.title,
            "price": float(p.price),
            "qty": int(ci.quantity),
            "image_url": make_image_url(p.image_url),
            "line_total": line_total,
        })

    return jsonify({"ok": True, "items": items, "total": total})

@app.post("/api/cart/remove")
def api_cart_remove_qty():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"ok": False, "message": "Not logged in"}), 401

    data = request.get_json(silent=True) or {}
    try:
        item_id = int(data.get("item_id", 0))
    except ValueError:
        return jsonify({"ok": False, "message": "Invalid item_id"}), 400

    remove_all = bool(data.get("remove_all", True))
    quantity = int(data.get("quantity", 1) or 1)

    resp = _carts_stub.RemoveFromCart(usercarts_pb2.RemoveFromCartRequest(
        user_id=str(user_id),
        item_id=item_id,
        remove_all=remove_all,
        quantity=quantity,
    ))

    return jsonify({"ok": resp.ok, "message": resp.message, "new_quantity": resp.new_quantity}), (200 if resp.ok else 400)

@app.post("/api/order/place")
def api_place_order():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"ok": False, "message": "Not logged in"}), 401

    import uuid
    resp = _coordinator_stub.PlaceOrderTransaction(
        twopc_pb2.TransactionRequest(
            transaction_id=str(uuid.uuid4()),
            user_id=str(user_id),
        )
    )
    return jsonify({"ok": resp.ok, "message": resp.message}), (200 if resp.ok else 400)

@app.get("/api/admin/items")
@admin_required
def api_admin_list():
    resp = _admin_stub.ListItems(admin_pb2.ListItemsRequest())
    return jsonify([{
        "id": it.id,
        "title": it.title,
        "price": it.price,
        "image_url": make_image_url(it.image_url),
        "type": it.type,
        "is_featured": it.is_featured,
    } for it in resp.items])

@app.post("/api/admin/items")
@admin_required
def api_admin_create():
    data = request.get_json(silent=True) or {}
    resp = _admin_stub.CreateItem(admin_pb2.CreateItemRequest(
        title=data.get("title",""),
        price=float(data.get("price", 0)),
        image_url=data.get("image_url",""),
        type=data.get("type",""),
        is_featured=bool(data.get("is_featured", False)),
    ))
    return jsonify({"ok": resp.ok, "message": resp.message}), (200 if resp.ok else 400)

@app.put("/api/admin/items/<int:item_id>")
@admin_required
def api_admin_update(item_id):
    data = request.get_json(silent=True) or {}
    resp = _admin_stub.UpdateItem(admin_pb2.UpdateItemRequest(
        id=item_id,
        title=data.get("title",""),
        price=float(data.get("price", 0)),
        image_url=data.get("image_url",""),
        type=data.get("type",""),
        is_featured=bool(data.get("is_featured", False)),
    ))
    return jsonify({"ok": resp.ok, "message": resp.message}), (200 if resp.ok else 400)

@app.delete("/api/admin/items/<int:item_id>")
@admin_required
def api_admin_delete(item_id):
    resp = _admin_stub.DeleteItem(admin_pb2.DeleteItemRequest(id=item_id))
    return jsonify({"ok": resp.ok, "message": resp.message}), (200 if resp.ok else 404)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)