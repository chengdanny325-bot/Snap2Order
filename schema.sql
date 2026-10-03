PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('merchant','customer')), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stores (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL UNIQUE REFERENCES users(id), name TEXT NOT NULL,
 published INTEGER NOT NULL DEFAULT 0 CHECK(published IN (0,1)),
 draft_json TEXT NOT NULL DEFAULT '[]', draft_source_id TEXT, draft_name TEXT,
 brand_json TEXT NOT NULL DEFAULT '{}', brand_draft_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 csrf_token TEXT NOT NULL, expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS menu_items (
 id TEXT PRIMARY KEY, store_id TEXT NOT NULL REFERENCES stores(id),
 name TEXT NOT NULL, price_cents INTEGER NOT NULL CHECK(price_cents > 0 AND price_cents <= 999999),
 category TEXT NOT NULL, available INTEGER NOT NULL CHECK(available IN (0,1)),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), position INTEGER NOT NULL,
 confidence REAL, source_id TEXT, image_url TEXT, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS menu_store ON menu_items(store_id,active,position);
CREATE TABLE IF NOT EXISTS orders (
 id TEXT PRIMARY KEY, store_id TEXT NOT NULL REFERENCES stores(id),
 customer_id TEXT NOT NULL REFERENCES users(id),
 total_cents INTEGER NOT NULL CHECK(total_cents > 0), note TEXT NOT NULL DEFAULT '',
 payment_status TEXT NOT NULL DEFAULT 'unpaid' CHECK(payment_status IN ('unpaid','demo_paid')),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','preparing','completed')),
 idempotency_key TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(customer_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS orders_store ON orders(store_id,created_at DESC);
CREATE INDEX IF NOT EXISTS orders_customer ON orders(customer_id,created_at DESC);
CREATE TABLE IF NOT EXISTS order_items (
 id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL REFERENCES orders(id),
 menu_item_id TEXT NOT NULL REFERENCES menu_items(id), name_snapshot TEXT NOT NULL,
 price_cents_snapshot INTEGER NOT NULL CHECK(price_cents_snapshot > 0), quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 99)
);
CREATE INDEX IF NOT EXISTS order_items_order ON order_items(order_id);
CREATE TABLE IF NOT EXISTS ocr_sources (
 id TEXT PRIMARY KEY, store_id TEXT NOT NULL REFERENCES stores(id), mime TEXT NOT NULL,
 image BLOB NOT NULL, status TEXT NOT NULL CHECK(status IN ('processing','done','failed')),
 result_json TEXT, error TEXT, provider TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ocr_sources_store ON ocr_sources(store_id,created_at DESC);
CREATE TABLE IF NOT EXISTS rate_limits (
 bucket TEXT NOT NULL, window INTEGER NOT NULL, count INTEGER NOT NULL DEFAULT 1,
 PRIMARY KEY(bucket,window)
);
CREATE TABLE IF NOT EXISTS wechat_identities (
 openid TEXT PRIMARY KEY, user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS dish_images (
 id TEXT PRIMARY KEY, store_id TEXT NOT NULL REFERENCES stores(id),
 mime TEXT NOT NULL CHECK(mime IN ('image/jpeg','image/png')), image BLOB NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS dish_images_store ON dish_images(store_id);
CREATE TABLE IF NOT EXISTS store_logos (
 id TEXT PRIMARY KEY, store_id TEXT NOT NULL REFERENCES stores(id),
 mime TEXT NOT NULL CHECK(mime IN ('image/jpeg','image/png')), image BLOB NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS store_logos_store ON store_logos(store_id);
CREATE TABLE IF NOT EXISTS members (
 store_id TEXT NOT NULL REFERENCES stores(id), customer_id TEXT NOT NULL REFERENCES users(id),
 points INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, PRIMARY KEY(store_id,customer_id)
);
CREATE TABLE IF NOT EXISTS coupons (
 id TEXT PRIMARY KEY, store_id TEXT NOT NULL REFERENCES stores(id), customer_id TEXT NOT NULL REFERENCES users(id),
 amount_cents INTEGER NOT NULL, minimum_cents INTEGER NOT NULL, used_order TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS coupons_owner ON coupons(store_id,customer_id);
CREATE TABLE IF NOT EXISTS benefit_claims (
 store_id TEXT NOT NULL REFERENCES stores(id), customer_id TEXT NOT NULL REFERENCES users(id),
 kind TEXT NOT NULL, day TEXT NOT NULL, PRIMARY KEY(store_id,customer_id,kind,day)
);
PRAGMA user_version = 5;
