"""Optional sample shop so a new owner can click around before typing in their own stock."""
from datetime import date, timedelta

from . import stock

CATS = [("Beverages", "#38bdf8", "🥤"), ("Dairy & Eggs", "#fbbf24", "🥛"), ("Snacks & Biscuits", "#f87171", "🍪"),
        ("Grains & Cereals", "#34d399", "🌾"), ("Household", "#a78bfa", "🧼"), ("Fresh Produce", "#fb923c", "🥕"),
        ("Frozen Foods", "#22d3ee", "🧊"), ("Personal Care", "#f472b6", "🧴"), ("Condiments", "#a3e635", "🧂"),
        ("Baby Products", "#fb7185", "🍼")]

# name, barcode, category, cost, price (naira), qty, min, expiry offset (days), weighed, tax_exempt, brand
P = [
    ("Coca-Cola 50cl", "5449000000996", "Beverages", 120, 180, 250, 24, 200, 0, 0, "Coca-Cola"),
    ("Pepsi 50cl", "8901234567891", "Beverages", 115, 170, 200, 24, 180, 0, 0, "Pepsi"),
    ("Fanta Orange 50cl", "8901234567892", "Beverages", 115, 170, 180, 24, 180, 0, 0, "Coca-Cola"),
    ("Malta Guinness 33cl", "8901234567893", "Beverages", 200, 300, 120, 12, 300, 0, 0, "Guinness"),
    ("Eva Table Water 75cl", "8901234567895", "Beverages", 80, 120, 300, 36, 400, 0, 1, "Eva"),
    ("Chi Exotic Juice 1L", "8901234567894", "Beverages", 700, 1100, 40, 8, 120, 0, 0, "Chi"),
    ("Peak Milk Tin 400g", "8901234567700", "Dairy & Eggs", 900, 1350, 100, 15, 500, 0, 0, "Peak"),
    ("Cowbell Milk 400g", "8901234567701", "Dairy & Eggs", 850, 1250, 80, 15, 450, 0, 0, "Cowbell"),
    ("Eggs (crate of 30)", "8901234567702", "Dairy & Eggs", 2500, 3500, 30, 5, 21, 0, 1, "Local"),
    ("Hollandia Yoghurt 500ml", "8901234567703", "Dairy & Eggs", 600, 900, 50, 10, 14, 0, 0, "Hollandia"),
    ("Pringles Original 165g", "8901234567800", "Snacks & Biscuits", 800, 1200, 60, 10, 240, 0, 0, "Pringles"),
    ("Digestive Biscuits 400g", "8901234567801", "Snacks & Biscuits", 450, 650, 80, 10, 200, 0, 0, "McVitie's"),
    ("Indomie Noodles 70g", "8901234567802", "Grains & Cereals", 100, 150, 500, 50, 300, 0, 1, "Indomie"),
    ("Golden Morn 900g", "8901234567803", "Grains & Cereals", 700, 1050, 70, 10, 250, 0, 0, "Nestlé"),
    ("Milo Tin 400g", "8901234567400", "Grains & Cereals", 1500, 2200, 0, 10, 300, 0, 0, "Nestlé"),
    ("Rice (loose, per kg)", "2000000000015", "Grains & Cereals", 800, 1200, 120, 20, None, 1, 1, "Local"),
    ("Beans (loose, per kg)", "2000000000022", "Grains & Cereals", 1100, 1600, 80, 15, None, 1, 1, "Local"),
    ("Garri (loose, per kg)", "2000000000039", "Grains & Cereals", 500, 800, 90, 15, None, 1, 1, "Local"),
    ("Tomatoes (per kg)", "2000000000046", "Fresh Produce", 600, 1000, 25, 8, 6, 1, 1, "Local"),
    ("Onions (per kg)", "2000000000053", "Fresh Produce", 700, 1100, 35, 8, 20, 1, 1, "Local"),
    ("Omo Detergent 500g", "8901234567600", "Household", 500, 750, 120, 20, 700, 0, 0, "Unilever"),
    ("Ariel Washing Powder 1kg", "8901234567601", "Household", 900, 1300, 80, 15, 700, 0, 0, "P&G"),
    ("Dettol Soap 110g", "8901234567602", "Personal Care", 250, 400, 200, 30, 700, 0, 0, "Dettol"),
    ("Close-Up Toothpaste 125ml", "8901234567603", "Personal Care", 380, 550, 90, 15, 600, 0, 0, "Close-Up"),
    ("Gino Tomato Paste 70g", "8901234567500", "Condiments", 80, 130, 4, 10, 400, 0, 0, "Gino"),
    ("Knorr Chicken Cubes (8)", "8901234567501", "Condiments", 120, 200, 3, 15, 500, 0, 0, "Knorr"),
    ("Frozen Chicken (per kg)", "2000000000060", "Frozen Foods", 3200, 4200, 40, 8, 90, 1, 1, "Local"),
    ("Pampers Size 3 (30)", "8901234567300", "Baby Products", 4500, 6200, 25, 5, 900, 0, 0, "Pampers"),
]


def load(conn, user_id=None):
    cats = {}
    for n, color, emoji in CATS:
        cur = conn.execute("INSERT OR IGNORE INTO categories(name,color,emoji) VALUES (?,?,?)", (n, color, emoji))
        cats[n] = conn.execute("SELECT id FROM categories WHERE name=?", (n,)).fetchone()["id"]
    for name, bc, cat, cost, price, qty, mn, exp, weighed, exempt, brand in P:
        if conn.execute("SELECT 1 FROM products WHERE barcode=?", (bc,)).fetchone():
            continue
        cur = conn.execute(
            "INSERT INTO products(name,barcode,sku,category_id,brand,unit,is_weighed,cost_kobo,price_kobo,tax_exempt,min_stock)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (name, bc, f"SKU-{bc[-5:]}", cats[cat], brand, "kg" if weighed else "pcs", weighed, cost * 100, price * 100, exempt, mn))
        if qty > 0:
            expiry = (date.today() + timedelta(days=exp)).isoformat() if exp else None
            if exp and exp <= 30:               # a second, older batch so the expiry alerts have something to show
                stock.add_stock(conn, cur.lastrowid, max(1, qty // 3), reason="opening", expiry=(date.today() + timedelta(days=exp // 2)).isoformat(), user_id=user_id)
                qty -= max(1, qty // 3)
            stock.add_stock(conn, cur.lastrowid, qty, reason="opening", expiry=expiry, user_id=user_id)
    for n, ph in (("Walk-in regular", None), ("Mrs. Adaeze Okafor", "08031234567"), ("Mr. Tunde Bakare", "08052345678")):
        conn.execute("INSERT OR IGNORE INTO customers(name,phone,credit_limit_kobo) VALUES (?,?,?)",
                     (n, ph, 5000000 if ph else 0))
    conn.execute("INSERT OR IGNORE INTO suppliers(name,company,phone) VALUES ('Nestlé Nigeria','Nestlé Nigeria PLC','07012345678')")
    conn.execute("INSERT OR IGNORE INTO suppliers(name,company,phone) VALUES ('Dangote Foods','Dangote Group','08023456789')")
