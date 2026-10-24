"""End-to-end checks through the real web layer (no browser needed). Run:  python -m pytest tests -q"""
import os
import re
import tempfile

import pytest

os.environ["AURORA_DATA_DIR"] = tempfile.mkdtemp(prefix="aurora-test-")

from aurora.app import create_app  # noqa: E402


class Client:
    def __init__(self, app):
        self.c = app.test_client()
        self.csrf = ""

    def page(self, url="/login"):
        r = self.c.get(url)
        m = re.search(r'data-csrf="([^"]+)"', r.get_data(as_text=True))
        if m:
            self.csrf = m.group(1)
        return r

    def req(self, method, url, data=None):
        return getattr(self.c, method)(url, json=data, headers={"X-CSRF-Token": self.csrf, "X-Requested-With": "fetch"})

    def get(self, u): return self.req("get", u)
    def post(self, u, d=None): return self.req("post", u, d or {})
    def put(self, u, d=None): return self.req("put", u, d or {})
    def delete(self, u): return self.req("delete", u)


@pytest.fixture(scope="module")
def app():
    return create_app(testing=True)


@pytest.fixture(scope="module")
def owner(app):
    c = Client(app)
    c.page("/setup")
    r = c.post("/api/setup", {"store_name": "Test Mart", "name": "Ada", "username": "ada", "password": "secret1", "pin": "1234", "load_demo": True})
    assert r.status_code == 200, r.get_json()
    c.page("/")
    return c


def test_everything_requires_login(app):
    c = Client(app)
    assert c.get("/api/products").status_code == 401
    assert c.page("/products").status_code in (302, 401)


def test_csrf_blocks_forged_posts(owner):
    r = owner.c.post("/api/customers", json={"name": "x"})            # no token
    assert r.status_code == 400


def test_all_pages_render(owner):
    for url in ["/", "/pos", "/products", "/suppliers", "/purchases", "/stocktake", "/customers", "/sales", "/shifts",
                "/expenses", "/reports", "/notifications", "/users", "/audit", "/settings"]:
        r = owner.page(url)
        assert r.status_code == 200, url
        assert "Aurora OS" in r.get_data(as_text=True)


def test_sale_flow_and_math(owner):
    assert owner.post("/api/shift/open", {"float": "5000"}).status_code == 200
    prods = owner.get("/api/products?limit=500").get_json()
    coke = next(p for p in prods if p["name"].startswith("Coca-Cola"))
    rice = next(p for p in prods if p["name"].startswith("Rice"))
    items = [{"product_id": coke["id"], "qty": 3}, {"product_id": rice["id"], "qty": 1.5}]
    q = owner.post("/api/pos/quote", {"items": items}).get_json()
    # coke 3 x 180 = 540 (VAT inclusive); rice 1.5kg x 1200 = 1800 (VAT exempt)
    assert q["total_kobo"] == 54000 + 180000
    assert q["tax_kobo"] == round(54000 * 7.5 / 107.5)
    r = owner.post("/api/pos/checkout", {"items": items, "payments": [{"method": "cash", "amount_kobo": 250000}]})
    assert r.status_code == 200, r.get_json()
    j = r.get_json()
    assert j["change_kobo"] == 250000 - 234000
    after = owner.get("/api/products/%d" % coke["id"]).get_json()
    assert after["qty"] == coke["qty"] - 3
    # cannot pay short
    bad = owner.post("/api/pos/checkout", {"items": items, "payments": [{"method": "cash", "amount_kobo": 1000}]})
    assert bad.status_code == 400
    # cannot sell more than we have
    huge = owner.post("/api/pos/checkout", {"items": [{"product_id": coke["id"], "qty": 99999}], "payments": [{"method": "cash", "amount_kobo": 10**10}]})
    assert huge.status_code == 400 and "stock" in huge.get_json()["error"].lower()
    # browser can't set its own price without approval... owner may, but a forged price from a cashier needs a PIN
    assert j["sale_id"]


def test_refund_restocks_and_shift_balances(owner):
    sales = owner.get("/api/sales").get_json()
    sid = sales[0]["id"]
    d = owner.get("/api/sales/%d" % sid).get_json()
    line = d["items"][0]
    before = owner.get("/api/products/%d" % line["product_id"]).get_json()["qty"]
    r = owner.post("/api/sales/%d/refund" % sid, {"lines": [{"sale_item_id": line["id"], "qty": 1, "restock": True}], "method": "cash", "reason": "test"})
    assert r.status_code == 200, r.get_json()
    after = owner.get("/api/products/%d" % line["product_id"]).get_json()["qty"]
    assert after == before + 1
    s = owner.get("/api/shift").get_json()
    # float 5000 + cash 2340 - change... cash kept = total 2340 ; minus refund
    assert s["expected_cash_kobo"] == 500000 + 234000 - r.get_json()["total_kobo"]
    c = owner.post("/api/shift/close", {"counted": str(s["expected_cash_kobo"] / 100)}).get_json()
    assert c["difference_kobo"] == 0


def test_cashier_limits(app, owner):
    assert owner.post("/api/users", {"name": "Bola", "username": "bola", "role": "cashier", "password": "cash123"}).status_code == 200
    c = Client(app)
    c.page("/login")
    assert c.post("/api/login", {"username": "bola", "password": "cash123"}).status_code == 200
    c.page("/pos")
    assert c.get("/api/settings").status_code == 403
    assert c.get("/api/users").status_code == 403
    assert c.get("/api/reports/summary").status_code == 403
    assert c.post("/api/products", {"name": "x", "price": "5"}).status_code == 403
    prods = c.get("/api/products?limit=5").get_json()
    assert "cost_kobo" not in prods[0]                      # cashiers never see cost prices
    c.post("/api/shift/open", {"float": "0"})
    pid = prods[0]["id"]
    forged = c.post("/api/pos/checkout", {"items": [{"product_id": pid, "qty": 1, "price_kobo": 1}], "payments": [{"method": "cash", "amount_kobo": 100000}]})
    assert forged.get_json().get("need_pin")                # price change needs manager approval
    big = c.post("/api/pos/checkout", {"items": [{"product_id": pid, "qty": 1, "discount_pct": 50}], "payments": [{"method": "cash", "amount_kobo": 100000}]})
    assert big.get_json().get("need_pin")
    ok = c.post("/api/pos/checkout", {"items": [{"product_id": pid, "qty": 1, "discount_pct": 50}], "pin": "1234", "payments": [{"method": "cash", "amount_kobo": 100000}]})
    assert ok.status_code == 200, ok.get_json()
    wrong = c.post("/api/pos/checkout", {"items": [{"product_id": pid, "qty": 1, "discount_pct": 50}], "pin": "9999", "payments": [{"method": "cash", "amount_kobo": 100000}]})
    assert wrong.status_code == 400
    # a cashier can't refund without a PIN
    sid = c.get("/api/sales").get_json()[0]["id"]
    it = c.get("/api/sales/%d" % sid).get_json()["items"][0]
    r = c.post("/api/sales/%d/refund" % sid, {"lines": [{"sale_item_id": it["id"], "qty": 1}], "method": "cash", "reason": "x"})
    assert r.get_json().get("need_pin")
    # and can't see other cashiers' sales
    assert all(s["cashier_name"] == "Bola" for s in c.get("/api/sales").get_json())


def test_credit_and_points(owner):
    cid = owner.post("/api/customers", {"name": "Credit Carl", "phone": "08000000001", "credit_limit": "1000"}).get_json()["id"]
    owner.post("/api/shift/open", {"float": "0"})
    pid = next(p for p in owner.get("/api/products?limit=500").get_json() if p["name"].startswith("Pepsi"))["id"]
    r = owner.post("/api/pos/checkout", {"items": [{"product_id": pid, "qty": 2}], "customer_id": cid, "payments": [{"method": "credit", "amount_kobo": 34000}]})
    assert r.status_code == 200, r.get_json()
    over = owner.post("/api/pos/checkout", {"items": [{"product_id": pid, "qty": 10}], "customer_id": cid, "payments": [{"method": "credit", "amount_kobo": 170000}]})
    assert over.status_code == 400 and "limit" in over.get_json()["error"]
    assert owner.post(f"/api/customers/{cid}/pay", {"amount": "100", "method": "cash"}).status_code == 200
    c = owner.get(f"/api/customers/{cid}").get_json()
    assert c["balance_kobo"] == 34000 - 10000


def test_purchase_receive_and_stocktake(owner):
    p = next(p for p in owner.get("/api/products?limit=500").get_json() if p["name"].startswith("Milo"))
    assert p["qty"] == 0
    oid = owner.post("/api/purchases", {"status": "ordered", "items": [{"product_id": p["id"], "qty": 10, "cost": "1500"}]}).get_json()["id"]
    po = owner.get(f"/api/purchases/{oid}").get_json()
    r = owner.post(f"/api/purchases/{oid}/receive", {"lines": [{"item_id": po["items"][0]["id"], "qty": 10, "expiry_date": "2027-12-31"}]})
    assert r.status_code == 200, r.get_json()
    assert owner.get(f"/api/products/{p['id']}").get_json()["qty"] == 10
    assert owner.get(f"/api/purchases/{oid}").get_json()["status"] == "received"
    tid = owner.post("/api/stocktakes", {"name": "T"}).get_json()["id"]
    owner.put(f"/api/stocktakes/{tid}/count", {"product_id": p["id"], "counted": 8})
    res = owner.post(f"/api/stocktakes/{tid}/apply").get_json()
    assert res["changed"] == 1 and res["shrinkage_kobo"] == 2 * 150000
    assert owner.get(f"/api/products/{p['id']}").get_json()["qty"] == 8


def test_reports_and_dashboard(owner):
    d = owner.get("/api/dashboard").get_json()
    assert d["today"]["sales"] >= 1 and "profit_kobo" in d["today"]
    r = owner.get("/api/reports/summary").get_json()
    assert r["revenue_kobo"] > 0 and r["net_profit_kobo"] is not None
    assert owner.get("/api/reports/sales.csv").status_code == 200


def test_csv_import_export(owner):
    csv_text = "name,barcode,category,cost,price,qty\nImported Tin,9990001,Snacks,100,150,12\n=EVIL(),9990002,Snacks,1,2,1\n"
    r = owner.post("/api/products/import", {"csv": csv_text}).get_json()
    assert r["added"] == 2
    out = owner.get("/api/products/export.csv").get_data(as_text=True)
    assert "Imported Tin" in out and "'=EVIL()" in out          # formulas are neutralised


def test_backup_and_restore(owner):
    assert owner.post("/api/backups").status_code == 200
    name = owner.get("/api/backups").get_json()[0]["name"]
    assert owner.post(f"/api/backups/{name}/restore", {"confirm": "nope"}).status_code == 400
    assert owner.post(f"/api/backups/{name}/restore", {"confirm": "RESTORE"}).status_code == 200
    owner.page("/login")


def test_lockout(app):
    c = Client(app)
    c.page("/login")
    for _ in range(5):
        c.post("/api/login", {"username": "bola", "password": "wrong"})
    r = c.post("/api/login", {"username": "bola", "password": "cash123"})
    assert r.status_code == 401 and "Too many" in r.get_json()["error"]
