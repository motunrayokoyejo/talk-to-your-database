"""Create and seed the fictional e-commerce database (shop.db).

Deterministic: a fixed random seed means everyone gets identical data.
Run:  python seed_db.py
"""

import random
import sqlite3
from datetime import date, timedelta

from config import DB_PATH

SEED = 42
DATA_START = date(2024, 1, 1)
DATA_END = date(2026, 10, 31)

SCHEMA = """
CREATE TABLE customers (
    id           INTEGER PRIMARY KEY,
    first_name   TEXT NOT NULL,
    last_name    TEXT NOT NULL,
    email        TEXT NOT NULL UNIQUE,
    city         TEXT NOT NULL,
    country      TEXT NOT NULL,
    signup_date  DATE NOT NULL            -- YYYY-MM-DD
);

CREATE TABLE products (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL,
    category  TEXT NOT NULL,
    price     REAL NOT NULL               -- current list price, USD
);

CREATE TABLE orders (
    id           INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    order_date   DATE NOT NULL,           -- YYYY-MM-DD
    status       TEXT NOT NULL CHECK (status IN
                 ('completed', 'shipped', 'pending', 'cancelled', 'refunded'))
);

CREATE TABLE order_items (
    id          INTEGER PRIMARY KEY,
    order_id    INTEGER NOT NULL REFERENCES orders(id),
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    unit_price  REAL NOT NULL             -- price paid per unit, USD
);

CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_items_product ON order_items(product_id);
"""

FIRST_NAMES = [
    "Amara", "Tunde", "Chioma", "Kwame", "Zainab", "Emeka", "Fatima", "Kofi",
    "Ngozi", "Sipho", "Aisha", "Daniel", "Grace", "Samuel", "Esther", "David",
    "Funmi", "Ibrahim", "Leila", "Musa", "Nia", "Oluwaseun", "Priya", "James",
    "Sofia", "Lucas", "Mei", "Hannah", "Omar", "Yemi", "Thandiwe", "Carlos",
    "Elena", "Kemi", "Joseph", "Adaeze", "Ravi", "Sarah", "Victor", "Wanjiru",
]
LAST_NAMES = [
    "Okafor", "Adeyemi", "Mensah", "Nwosu", "Bello", "Mwangi", "Okonkwo",
    "Abubakar", "Boateng", "Dlamini", "Eze", "Afolabi", "Kamau", "Owusu",
    "Ibekwe", "Haruna", "Ndlovu", "Achebe", "Balogun", "Otieno", "Smith",
    "Garcia", "Chen", "Patel", "Müller", "Rossi", "Johnson", "Silva",
]
CITIES = [
    ("Lagos", "Nigeria", 18), ("Abuja", "Nigeria", 8), ("Ibadan", "Nigeria", 5),
    ("Port Harcourt", "Nigeria", 4), ("Accra", "Ghana", 7), ("Nairobi", "Kenya", 7),
    ("Kigali", "Rwanda", 3), ("Johannesburg", "South Africa", 5),
    ("Cape Town", "South Africa", 4), ("Cairo", "Egypt", 3),
    ("London", "United Kingdom", 5), ("Toronto", "Canada", 3),
    ("New York", "United States", 4), ("Berlin", "Germany", 2),
]

PRODUCTS = {
    "Electronics": [
        ("Wireless Earbuds Pro", 129.00), ("Smartwatch S3", 249.00),
        ("Bluetooth Speaker Mini", 49.99), ("Noise-Cancelling Headphones", 299.00),
        ("USB-C Fast Charger 65W", 39.99), ("Portable Power Bank 20000mAh", 59.99),
        ("4K Action Camera", 199.00), ("Mechanical Keyboard", 109.00),
    ],
    "Home & Kitchen": [
        ("Air Fryer 5L", 119.00), ("Stainless Steel Cookware Set", 189.00),
        ("Electric Kettle", 34.99), ("Espresso Machine", 349.00),
        ("Non-stick Frying Pan", 29.99), ("Blender 1200W", 89.00),
        ("Scented Candle Set", 24.99), ("Cotton Bedsheet Set", 64.99),
    ],
    "Fashion": [
        ("Ankara Print Shirt", 45.00), ("Leather Sneakers", 95.00),
        ("Denim Jacket", 79.00), ("Canvas Backpack", 55.00),
        ("Silk Scarf", 35.00), ("Classic Sunglasses", 65.00),
        ("Running Shorts", 25.00), ("Leather Wallet", 40.00),
    ],
    "Sports & Outdoors": [
        ("Yoga Mat", 32.00), ("Adjustable Dumbbells", 179.00),
        ("Camping Tent 2-Person", 139.00), ("Insulated Water Bottle", 27.99),
        ("Football (Size 5)", 29.00), ("Resistance Bands Set", 22.00),
        ("Cycling Helmet", 69.00), ("Hiking Boots", 129.00),
    ],
    "Beauty": [
        ("Shea Butter Body Cream", 18.00), ("Vitamin C Serum", 32.00),
        ("Hair Growth Oil", 21.00), ("Matte Lipstick Set", 28.00),
        ("Sunscreen SPF 50", 19.50), ("Beard Grooming Kit", 39.00),
        ("Perfume Eau de Parfum", 85.00), ("Facial Cleanser", 16.00),
    ],
}

STATUSES = ["completed", "shipped", "pending", "cancelled", "refunded"]
STATUS_WEIGHTS = [78, 6, 3, 9, 4]


def random_date(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def build(db_path=DB_PATH) -> None:
    rng = random.Random(SEED)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)

    # --- products ---------------------------------------------------------
    product_rows = []
    for category, items in PRODUCTS.items():
        for name, price in items:
            product_rows.append((len(product_rows) + 1, name, category, price))
    conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", product_rows)

    # --- customers --------------------------------------------------------
    # 232 customers across 2024-01 .. 2026-09, plus 18 who signed up in Oct 2026.
    signup_dates = [random_date(rng, DATA_START, date(2026, 9, 30)) for _ in range(232)]
    signup_dates += [random_date(rng, date(2026, 10, 1), DATA_END) for _ in range(18)]
    signup_dates.sort()

    city_choices = [(c, k) for c, k, _ in CITIES]
    city_weights = [w for _, _, w in CITIES]
    customer_rows = []
    for i, signup in enumerate(signup_dates, start=1):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        city, country = rng.choices(city_choices, weights=city_weights)[0]
        email = f"{first.lower()}.{last.lower()}{i}@example.com".replace("ü", "u")
        customer_rows.append((i, first, last, email, city, country, signup.isoformat()))
    conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?)", customer_rows)

    # --- orders & items ---------------------------------------------------
    # Product popularity varies so "top products" has a clear answer.
    popularity = [rng.uniform(0.3, 3.0) for _ in product_rows]
    order_rows, item_rows = [], []
    for cust_id, *_, signup_str in customer_rows:
        signup = date.fromisoformat(signup_str)
        segment = rng.random()
        if segment < 0.10:      # loyal regulars
            n_orders = rng.randint(8, 16)
        elif segment < 0.55:    # occasional shoppers
            n_orders = rng.randint(2, 6)
        else:                   # one-off or not yet purchased
            n_orders = rng.randint(0, 2)

        for _ in range(n_orders):
            order_date = random_date(rng, signup, DATA_END)
            if (DATA_END - order_date).days < 10:
                status = rng.choice(["pending", "shipped", "completed"])
            else:
                status = rng.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
            order_id = len(order_rows) + 1
            order_rows.append((order_id, cust_id, order_date.isoformat(), status))

            n_items = rng.choices([1, 2, 3, 4], weights=[45, 30, 17, 8])[0]
            chosen = set()
            while len(chosen) < n_items:
                chosen.add(rng.choices(product_rows, weights=popularity)[0])
            for pid, _name, _cat, price in sorted(chosen):
                qty = rng.choices([1, 2, 3], weights=[75, 20, 5])[0]
                item_rows.append((len(item_rows) + 1, order_id, pid, qty, price))

    # Insert orders in date order so ids increase with time (more realistic).
    order_rows.sort(key=lambda r: (r[2], r[0]))
    remap = {old_id: new_id for new_id, (old_id, *_rest) in enumerate(order_rows, start=1)}
    conn.executemany(
        "INSERT INTO orders VALUES (?, ?, ?, ?)",
        [(remap[oid], cid, d, s) for oid, cid, d, s in order_rows],
    )
    conn.executemany(
        "INSERT INTO order_items VALUES (?, ?, ?, ?, ?)",
        [(iid, remap[oid], pid, q, p) for iid, oid, pid, q, p in item_rows],
    )

    conn.commit()
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("customers", "products", "orders", "order_items")}
    conn.close()
    print(f"Created {db_path}")
    for table, n in counts.items():
        print(f"  {table:<12} {n:>6} rows")


if __name__ == "__main__":
    build()
