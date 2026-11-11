"""Core logic: Trie categoriser, sliding-window stats, anomaly detectors, demo data."""
import re
from collections import deque
 
import numpy as np
import pandas as pd
 
# --------------------------------------------------------------------------
# 1. TRIE: merchant normalisation + longest-prefix categorisation
# --------------------------------------------------------------------------
NOISE = {
    "POS", "DEBIT", "PURCHASE", "CARD", "PAYMENT", "ONLINE", "US", "WWW", "COM",
    "UPI", "IMPS", "NEFT", "RTGS", "ACH", "INB", "MB", "ECOM", "BBPS", "BILLDESK",
    "TXN", "REF", "CR", "DR", "TRF", "TRANSFER", "WDL", "ATM", "PAYTM", "GPAY",
    "PHONEPE", "RAZORPAY", "CRED", "NET", "IN", "LTD", "PVT", "CORP", "INC"
}


def clean(desc: str) -> str:
    """'AMZN MKTP US*2K4LM 123' -> 'AMZN MKTP'"""
    desc = re.sub(r"[^A-Z ]", " ", str(desc).upper())
    return " ".join(t for t in desc.split() if t not in NOISE and len(t) > 1)


class Trie:
    def __init__(self):
        self.root = {}

    def insert(self, prefix: str, value: tuple):
        node = self.root
        for ch in prefix.upper():
            node = node.setdefault(ch, {})
        node["$"] = value

    def longest_prefix(self, text: str):
        """Walk the trie, remember the deepest terminal node. O(L)."""
        node, best = self.root, None
        for ch in text:
            if ch not in node:
                break
            node = node[ch]
            if "$" in node:
                best = node["$"]
        return best


MERCHANTS = {
    # ── Food ─────────────────────────────────────────────────────────────────
    "SWIGGY": ("Swiggy", "Food"),
    "ZOMATO": ("Zomato", "Food"),
    "BIGBASKET": ("BigBasket", "Food"),
    "DMART": ("DMart", "Food"),
    "BLINKIT": ("Blinkit", "Food"),
    "ZEPTO": ("Zepto", "Food"),
    "INSTAMART": ("Instamart", "Food"),
    "DUNZO": ("Dunzo", "Food"),
    "STARBUCKS": ("Starbucks", "Food"),
    "MCDONALD": ("McDonald's", "Food"),
    "MCDONALDS": ("McDonald's", "Food"),
    "KFC": ("KFC", "Food"),
    "BURGER KING": ("Burger King", "Food"),
    "DOMINOS": ("Domino's", "Food"),
    "PIZZA HUT": ("Pizza Hut", "Food"),
    "SUBWAY": ("Subway", "Food"),
    "HALDIRAM": ("Haldiram's", "Food"),
    "CHAAYOS": ("Chaayos", "Food"),
    "CHAI POINT": ("Chai Point", "Food"),
    "BARBEQUE NATION": ("Barbeque Nation", "Food"),
    "NATURES BASKET": ("Nature's Basket", "Food"),
    "SPENCERS": ("Spencer's", "Food"),
    "MORE RETAIL": ("More Supermarket", "Food"),
    "RELIANCE FRESH": ("Reliance Fresh", "Food"),
    "RELIANCE SMART": ("Reliance Smart", "Food"),

    # ── Transport ────────────────────────────────────────────────────────────
    "UBER": ("Uber", "Transport"),
    "OLA": ("Ola", "Transport"),
    "RAPIDO": ("Rapido", "Transport"),
    "SHELL": ("Shell", "Transport"),
    "HPCL": ("HPCL", "Transport"),
    "BPCL": ("BPCL", "Transport"),
    "IOCL": ("Indian Oil", "Transport"),
    "INDIAN OIL": ("Indian Oil", "Transport"),
    "BHARAT PETROLEUM": ("Bharat Petroleum", "Transport"),
    "HINDUSTAN PETROLEUM": ("Hindustan Petroleum", "Transport"),
    "FASTAG": ("Fastag", "Transport"),
    "NHAI TOLL": ("NHAI Toll", "Transport"),
    "METRO": ("Metro Transit", "Transport"),
    "IRCTC": ("IRCTC", "Transport"),
    "INDIAN RAILWAY": ("Indian Railways", "Transport"),
    "REDBUS": ("RedBus", "Transport"),
    "INDIGO": ("IndiGo", "Transport"),
    "AIR INDIA": ("Air India", "Transport"),
    "SPICEJET": ("SpiceJet", "Transport"),
    "VISTARA": ("Vistara", "Transport"),
    "AKASA": ("Akasa Air", "Transport"),

    # ── Shopping ─────────────────────────────────────────────────────────────
    "AMZN MKTP": ("Amazon", "Shopping"),
    "AMAZON": ("Amazon", "Shopping"),
    "AMZN": ("Amazon", "Shopping"),
    "FLIPKART": ("Flipkart", "Shopping"),
    "MYNTRA": ("Myntra", "Shopping"),
    "AJIO": ("Ajio", "Shopping"),
    "MEESHO": ("Meesho", "Shopping"),
    "TATA CLIQ": ("Tata CLiQ", "Shopping"),
    "NYKAA": ("Nykaa", "Shopping"),
    "ZARA": ("Zara", "Shopping"),
    "H&M": ("H&M", "Shopping"),
    "UNIQLO": ("Uniqlo", "Shopping"),
    "MARKS SPENCER": ("Marks & Spencer", "Shopping"),
    "DECATHLON": ("Decathlon", "Shopping"),
    "IKEA": ("IKEA", "Shopping"),
    "CROMA": ("Croma", "Shopping"),
    "RELIANCE DIGITAL": ("Reliance Digital", "Shopping"),
    "VIJAY SALES": ("Vijay Sales", "Shopping"),
    "SHOPPERS STOP": ("Shoppers Stop", "Shopping"),
    "LIFESTYLE": ("Lifestyle", "Shopping"),
    "PANTALOONS": ("Pantaloons", "Shopping"),
    "WESTSIDE": ("Westside", "Shopping"),

    # ── Bills ────────────────────────────────────────────────────────────────
    "AIRTEL": ("Airtel", "Bills"),
    "JIO": ("Jio", "Bills"),
    "VODAFONE": ("Vodafone Idea", "Bills"),
    "VI": ("Vodafone Idea", "Bills"),
    "ACT FIBERNET": ("ACT Fibernet", "Bills"),
    "HATHWAY": ("Hathway", "Bills"),
    "BESCOM": ("BESCOM Electricity", "Bills"),
    "TATA POWER": ("Tata Power", "Bills"),
    "ADANI ELECTRICITY": ("Adani Electricity", "Bills"),
    "BSES": ("BSES Electricity", "Bills"),
    "TORRENT POWER": ("Torrent Power", "Bills"),
    "MAHANAGAR GAS": ("Mahanagar Gas", "Bills"),
    "IGL": ("IGL Gas", "Bills"),
    "MGL": ("MGL Gas", "Bills"),
    "LIC": ("LIC Insurance", "Bills"),
    "HDFC LIFE": ("HDFC Life", "Bills"),
    "ICICI PRU": ("ICICI Prudential", "Bills"),
    "MAX LIFE": ("Max Life Insurance", "Bills"),
    "STAR HEALTH": ("Star Health", "Bills"),
    "BILLDESK": ("BillDesk", "Bills"),
    "BBPS": ("BBPS Bill", "Bills"),

    # ── Entertainment ────────────────────────────────────────────────────────
    "NETFLIX": ("Netflix", "Entertainment"),
    "SPOTIFY": ("Spotify", "Entertainment"),
    "AMAZON PRIME": ("Amazon Prime", "Entertainment"),
    "PRIME VIDEO": ("Prime Video", "Entertainment"),
    "APPLE BILL": ("Apple Services", "Entertainment"),
    "APPLE": ("Apple Services", "Entertainment"),
    "HOTSTAR": ("Disney+ Hotstar", "Entertainment"),
    "DISNEY": ("Disney+ Hotstar", "Entertainment"),
    "YOUTUBE": ("YouTube Premium", "Entertainment"),
    "SONYLIV": ("SonyLIV", "Entertainment"),
    "ZEE5": ("Zee5", "Entertainment"),
    "JIOCINEMA": ("JioCinema", "Entertainment"),
    "BOOKMYSHOW": ("BookMyShow", "Entertainment"),
    "PVR": ("PVR Cinemas", "Entertainment"),
    "INOX": ("INOX Cinemas", "Entertainment"),
    "CINEPOLIS": ("Cinépolis", "Entertainment"),
    "STEAM": ("Steam", "Entertainment"),
    "PLAYSTATION": ("PlayStation", "Entertainment"),
    "ANYTIME FITNESS": ("Anytime Fitness", "Entertainment"),
    "CULTFIT": ("Cult.fit", "Entertainment"),
    "CULT FIT": ("Cult.fit", "Entertainment"),

    # ── Healthcare ───────────────────────────────────────────────────────────
    "APOLLO PHARMACY": ("Apollo Pharmacy", "Healthcare"),
    "APOLLO": ("Apollo Pharmacy", "Healthcare"),
    "MEDPLUS": ("MedPlus", "Healthcare"),
    "PHARMEASY": ("PharmEasy", "Healthcare"),
    "1MG": ("Tata 1mg", "Healthcare"),
    "TATA 1MG": ("Tata 1mg", "Healthcare"),
    "NETMEDS": ("Netmeds", "Healthcare"),
    "PRACTO": ("Practo", "Healthcare"),
    "FORTIS": ("Fortis Healthcare", "Healthcare"),
    "MAX HEALTHCARE": ("Max Healthcare", "Healthcare"),
    "MANIPAL": ("Manipal Hospital", "Healthcare"),
    "DR LAL": ("Dr Lal PathLabs", "Healthcare"),
    "METROPOLIS": ("Metropolis Healthcare", "Healthcare"),
    "LENSKART": ("Lenskart", "Healthcare"),
}

CATEGORY_KEYWORDS = {
    "Food": [
        "SWIGGY", "ZOMATO", "RESTAURANT", "CAFE", "BAKERY", "FOOD", "DINING",
        "KITCHEN", "PIZZA", "BURGER", "DHABA", "BISTRO", "SWEETS", "EATERY",
        "GROCERY", "GROCERIES", "SUPERMARKET", "KIRANA", "PROVISION",
        "BIGBASKET", "DMART", "BLINKIT", "ZEPTO", "INSTAMART", "DUNZO"
    ],
    "Transport": [
        "UBER", "OLA", "RAPIDO", "TAXI", "CAB", "AUTO", "METRO", "IRCTC",
        "RAILWAY", "TRAIN", "BUS", "REDBUS", "TRANSIT", "AIRLINE", "FLIGHT",
        "INDIGO", "SPICEJET", "VISTARA", "PETROL", "DIESEL", "FUEL", "GAS STATION",
        "SHELL", "HPCL", "BPCL", "IOCL", "INDIAN OIL", "FASTAG", "TOLL", "PARKING"
    ],
    "Shopping": [
        "AMAZON", "AMZN", "FLIPKART", "MYNTRA", "AJIO", "MEESHO", "TATA CLIQ",
        "NYKAA", "ZARA", "H&M", "UNIQLO", "DECATHLON", "IKEA", "CROMA",
        "RELIANCE DIGITAL", "SHOPPERS STOP", "LIFESTYLE", "PANTALOONS",
        "SHOPPING", "RETAIL", "BOUTIQUE", "MALL", "STORE", "CLOTHING", "FASHION"
    ],
    "Bills": [
        "ELECTRICITY", "POWER", "BESCOM", "TATA POWER", "ADANI ELECTRICITY",
        "WATER", "JAL BOARD", "GAS BILL", "IGL", "MGL", "UTILITY", "RECHARGE",
        "AIRTEL", "JIO", "VODAFONE", "VI", "BROADBAND", "WIFI", "FIBERNET",
        "RENT", "MAINTENANCE", "SOCIETY", "INSURANCE", "LIC", "PREMIUM",
        "BILLDESK", "BBPS", "CREDIT CARD", "EMI", "LOAN"
    ],
    "Entertainment": [
        "NETFLIX", "SPOTIFY", "PRIME VIDEO", "AMAZON PRIME", "HOTSTAR", "DISNEY",
        "YOUTUBE", "SONYLIV", "ZEE5", "AUDIBLE", "BOOKMYSHOW", "PVR", "INOX",
        "CINEPOLIS", "CINEMA", "MOVIE", "THEATER", "THEATRE", "CONCERT",
        "STEAM", "PLAYSTATION", "PSN", "XBOX", "GAMING", "GAME",
        "ANYTIME FITNESS", "CULTFIT", "CULT FIT", "GYM", "FITNESS"
    ],
    "Healthcare": [
        "APOLLO", "MEDPLUS", "PHARMEASY", "1MG", "NETMEDS", "PRACTO",
        "FORTIS", "MAX HEALTHCARE", "MANIPAL", "HOSPITAL", "CLINIC", "DOCTOR",
        "DENTAL", "DIAGNOSTIC", "MEDICAL", "MEDICINE", "PHARMACY", "CHEMIST",
        "LAB", "PATHOLOGY", "METROPOLIS", "DR LAL", "LENSKART", "HEALTHCARE"
    ],
}

CATEGORY_NORM_MAP = {
    "food": "Food", "dining": "Food", "food delivery": "Food", "groceries": "Food", "grocery": "Food", "supermarket": "Food",
    "transport": "Transport", "transportation": "Transport", "travel": "Transport", "fuel": "Transport", "cab": "Transport",
    "shopping": "Shopping", "retail": "Shopping", "clothing": "Shopping", "ecommerce": "Shopping",
    "bills": "Bills", "bill": "Bills", "utilities": "Bills", "utility": "Bills", "telecom": "Bills",
    "entertainment": "Entertainment", "subscriptions": "Entertainment", "subscription": "Entertainment", "fitness": "Entertainment",
    "healthcare": "Healthcare", "health": "Healthcare", "medical": "Healthcare", "pharmacy": "Healthcare",
    "other": "Others", "others": "Others", "misc": "Others", "miscellaneous": "Others"
}

SORTED_MERCHANTS = sorted(MERCHANTS.items(), key=lambda x: len(x[0]), reverse=True)


def build_trie() -> Trie:
    t = Trie()
    for k, v in MERCHANTS.items():
        t.insert(k, v)
    return t


def match_single_transaction(raw_desc: str, trie: Trie) -> tuple:
    s = str(raw_desc).upper()
    cleaned = clean(s)

    # 1. Longest prefix matching with Trie on cleaned text
    if cleaned:
        hit = trie.longest_prefix(cleaned)
        if hit:
            return hit[0], hit[1]

    # 2. Key matching against MERCHANTS (sorted by length descending)
    for key, val in SORTED_MERCHANTS:
        if key in s or (cleaned and key in cleaned):
            return val[0], val[1]

    # 3. Category keyword fallback
    for cat_name, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in s:
                merchant = cleaned.title() if cleaned else raw_desc.strip().title()
                return merchant or "Merchant", cat_name

    # 4. Uncategorised fallback -> "Others"
    merchant = cleaned.title() if cleaned else (raw_desc.strip().title() or "Unknown Transaction")
    return merchant, "Others"


def categorise(df: pd.DataFrame, trie: Trie) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"].abs()

    has_cat = "category" in df.columns
    merchants = []
    categories = []

    for _, row in df.iterrows():
        desc = str(row.get("description", ""))
        existing_cat = str(row.get("category", "")).strip() if has_cat else ""
        norm_cat = CATEGORY_NORM_MAP.get(existing_cat.lower())

        m_name, c_name = match_single_transaction(desc, trie)

        if norm_cat and norm_cat != "Others":
            categories.append(norm_cat)
            merchants.append(m_name)
        else:
            categories.append(c_name)
            merchants.append(m_name)

    df["merchant"] = merchants
    df["category"] = categories
    return df.sort_values("date").reset_index(drop=True)


# --------------------------------------------------------------------------
# 2. SLIDING WINDOW: O(1) rolling mean / std via running sums
# --------------------------------------------------------------------------
class RollingStats:
    def __init__(self, size: int):
        self.size, self.q, self.s, self.s2 = size, deque(), 0.0, 0.0
 
    def push(self, x: float):
        self.q.append(x)
        self.s += x
        self.s2 += x * x
        if len(self.q) > self.size:
            old = self.q.popleft()
            self.s -= old
            self.s2 -= old * old
 
    @property
    def mean(self):
        return self.s / len(self.q) if self.q else 0.0
 
    @property
    def std(self):
        n = len(self.q)
        if n < 2:
            return 0.0
        return max(self.s2 / n - self.mean**2, 0) ** 0.5
 
 
def rolling_30d(df: pd.DataFrame) -> pd.Series:
    """Rolling 30-day spend, maintained with a deque (evict old days)."""
    daily = df.groupby("date")["amount"].sum().asfreq("D", fill_value=0)
    window, total, out = deque(), 0.0, []
    for d, amt in daily.items():
        window.append((d, amt))
        total += amt
        while (d - window[0][0]).days >= 30:
            total -= window.popleft()[1]
        out.append(total)
    return pd.Series(out, index=daily.index)
 
 
# --------------------------------------------------------------------------
# 3. DETECTORS -> list of "story events"
# --------------------------------------------------------------------------
def _event(date, kind, sev, title, why, series=None, yearly=0.0, merchant=None):
    return dict(date=pd.Timestamp(date), kind=kind, severity=sev, title=title,
                why=why, series=series, yearly=yearly, merchant=merchant)
 
 
def find_subscriptions(df: pd.DataFrame, last_date) -> pd.DataFrame:
    rows = []
    sub_regex = re.compile(
        r"\b(subscription|subscriptions|membership|recurring|autopay|netflix|spotify|streamflix|disney|hotstar|hulu|patreon|substack|icloud|gym|fitness)\b"
        r"|apple\.com/bill|amazon\s*prime|prime\s*video|youtube\s*premium|google\s*one",
        re.IGNORECASE
    )

    for m, g in df.groupby("merchant"):
        g = g.sort_values("date")
        m_str = str(m)
        desc_sample = " ".join(g["description"].astype(str).tolist()[:3]) if "description" in g.columns else ""
        full_text = f"{m_str} {desc_sample}".lower()
        is_known_sub = bool(sub_regex.search(full_text)) or (g["category"].iloc[0] == "Subscriptions")

        if len(g) >= 2:
            gaps = g["date"].diff().dt.days.dropna()
            is_monthly = (len(gaps) > 0 and gaps.between(25, 36).mean() >= 0.65)
            amt_std = g["amount"].std()
            amt_stable = (amt_std < g["amount"].mean() * 0.6) if not pd.isna(amt_std) else True

            if (is_monthly and amt_stable) or is_known_sub:
                days_since = (last_date - g["date"].iloc[-1]).days
                rows.append(dict(
                    merchant=m, category=g["category"].iloc[0],
                    first=g["date"].iloc[0], last=g["date"].iloc[-1],
                    first_amount=g["amount"].iloc[0], amount=g["amount"].iloc[-1],
                    active=days_since <= 60, charges=len(g)
                ))
        elif len(g) == 1 and is_known_sub:
            days_since = (last_date - g["date"].iloc[-1]).days
            rows.append(dict(
                merchant=m, category=g["category"].iloc[0],
                first=g["date"].iloc[0], last=g["date"].iloc[-1],
                first_amount=g["amount"].iloc[0], amount=g["amount"].iloc[-1],
                active=days_since <= 60, charges=1
            ))

    return pd.DataFrame(rows)
 
 
def detect(df: pd.DataFrame, z_thresh: float = 2.5, drift_pct: float = 4.0):
    events, last = [], df["date"].max()
    subs = find_subscriptions(df, last)
    start = df["date"].min()

    # a) subscription creep + b) new recurring
    for _, s in subs.iterrows():
        g = df[df.merchant == s.merchant].sort_values("date")
        amts = g["amount"].round(2).tolist()
        changes = g[g["amount"].round(2).diff().fillna(0).abs() > 0.01]
        for _, c in changes.iterrows():
            prev = g[g.date < c.date]["amount"].iloc[-1]
            events.append(_event(
                c.date, "creep", 2 if c.amount / prev > 1.2 else 1,
                f"{s.merchant} quietly rose from ₹{prev:.2f} to ₹{c.amount:.2f}",
                f"Price up {100 * (c.amount / prev - 1):.0f}% on a recurring charge "
                f"(₹{(c.amount - prev) * 12:.0f}/year extra).",
                amts, (c.amount - prev) * 12, s.merchant))
        if s["first"] > start + pd.Timedelta(days=45):
            events.append(_event(
                s["first"], "new", 2,
                f"A new ₹{s.amount:.2f}/month charge from {s.merchant} appeared",
                f"Charged {s.charges} times at ~30-day intervals. Still need it?",
                amts, s.amount * 12, s.merchant))

    # c) duplicate charges: same merchant + amount within 48h (skip subscriptions)
    sub_names = set(subs.merchant) if len(subs) else set()
    dup_keys = set()
    for m, g in df[~df.merchant.isin(sub_names)].groupby("merchant"):
        g = g.sort_values("date")
        dup = g[(g["amount"].diff().abs() < 0.01) & (g["date"].diff().dt.days <= 2)]
        for _, r in dup.iterrows():
            events.append(_event(r.date, "dup", 2,
                                 f"Possible double charge at {m}",
                                 f"₹{r.amount:.2f} charged twice within 48 hours.",
                                 None, r.amount, m))
            dup_keys.add((str(r.date)[:10], m, round(float(r.amount), 2)))

    # d) Transaction-level spending anomalies (modified z-score)
    # Sensitive to sudden high purchases; threshold controlled by z_thresh
    debit_df = df[df["amount"] > 0].copy()
    amts = debit_df["amount"].astype(float).values
    if len(amts) >= 3:
        med = float(np.median(amts))
        mad = float(np.median(np.abs(amts - med)))
        if mad == 0:
            mad = 0.6745 * float(np.std(amts)) or 1.0

        for _, r in debit_df.iterrows():
            amt = float(r["amount"])
            m_key = (str(r["date"])[:10], r["merchant"], round(amt, 2))
            if amt > med and m_key not in dup_keys:
                mz = 0.6745 * (amt - med) / mad
                if mz >= z_thresh:
                    events.append(_event(
                        r["date"], "spike", 3 if mz >= z_thresh * 1.5 else 2,
                        f"Unusual ₹{amt:,.2f} spend at {r['merchant']}",
                        f"Sudden high purchase with modified z-score {mz:.1f} (typical baseline spend ₹{med:,.0f}).",
                        [amt], 0, r["merchant"]
                    ))

    # e) category drift (linear slope on monthly totals) + f) spikes (modified z)
    monthly = (df.set_index("date").groupby("category")["amount"]
               .resample("MS").sum().unstack(0).fillna(0))
    if last.day < 25 and len(monthly) > 1:
        monthly = monthly.iloc[:-1]  # drop partial month if multi-month statement
    for cat in monthly.columns:
        if cat in ("Subscriptions", "Others", "Other") or len(monthly) < 2:
            continue
        y = monthly[cat].values
        if len(y) >= 4:
            slope = np.polyfit(np.arange(len(y)), y, 1)[0]
            pct = 100 * slope / max(y[:2].mean(), 1)
        else:
            slope = y[-1] - y[0]
            pct = 100 * (y[-1] - y[0]) / max(y[0], 1)

        if pct >= drift_pct and y[-1] > y[0] * 1.15:
            events.append(_event(
                monthly.index[-1], "drift", 3 if y[-1] > y[0] * 1.5 else 2,
                f"{cat} crept up {100 * (y[-1] / max(y[0], 1) - 1):.0f}% since {monthly.index[0]:%B}",
                f"Rising ~{pct:.0f}% of baseline every month: from ₹{y[0]:,.0f} to ₹{y[-1]:,.0f}. "
                f"That is ₹{y[-1] - y[0]:,.0f} more per month than when you started.",
                y.tolist(), (y[-1] - y[0]) * 12, cat))

        if len(y) >= 3:
            base = y[:-1]
            med_cat = np.median(base)
            mad_cat = np.median(np.abs(base - med_cat)) or 1
            mz_cat = 0.6745 * (y[-1] - med_cat) / mad_cat
            if mz_cat >= z_thresh and not any(e["kind"] == "drift" and e["merchant"] == cat for e in events):
                events.append(_event(monthly.index[-1], "spike", 2,
                                     f"{cat} spiked in {monthly.index[-1]:%B}",
                                     f"Category monthly modified z-score {mz_cat:.1f} (typical ₹{med_cat:,.0f}, this month ₹{y[-1]:,.0f}).",
                                     y.tolist(), 0, cat))
    return sorted(events, key=lambda e: e["date"]), subs, monthly
 
 
# --------------------------------------------------------------------------
# 4. SYNTHETIC DEMO DATA with injected anomalies
# --------------------------------------------------------------------------
def demo_data(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    months = pd.date_range("2026-01-01", periods=9, freq="MS")
    for i, m in enumerate(months):
        # fixed subscriptions
        netflix = [499, 499, 499, 649, 649, 649, 799, 799, 799][i]  # price creep
        rows.append((m + pd.Timedelta(days=4), "NETFLIX.COM 866-579", -netflix))
        rows.append((m + pd.Timedelta(days=9), "SPOTIFY P2A1B", -119))
        if i >= 4:  # new, easy-to-forget charge
            rows.append((m + pd.Timedelta(days=14), "APPLE.COM/BILL 8X9", -299))
        if i <= 4:  # gym used then forgotten (still billing: stays active)
            pass
        rows.append((m + pd.Timedelta(days=2), "ANYTIME FITNESS 4471", -1499))
        # food delivery drifts upward
        for _ in range(int(3 + i * 0.5)):
            d = m + pd.Timedelta(days=int(rng.integers(0, 28)))
            rows.append((d, f"SWIGGY*{rng.integers(1000, 9999)}", -float(rng.integers(250, 480))))
        # stable groceries
        for _ in range(6):
            d = m + pd.Timedelta(days=int(rng.integers(0, 28)))
            rows.append((d, f"BIGBASKET {rng.integers(100, 999)}", -float(rng.integers(500, 900))))
        # transport
        for _ in range(5):
            d = m + pd.Timedelta(days=int(rng.integers(0, 28)))
            rows.append((d, f"UBER *TRIP {rng.integers(100, 999)}", -float(rng.integers(120, 300))))
        # shopping noise
        for _ in range(3):
            d = m + pd.Timedelta(days=int(rng.integers(0, 28)))
            rows.append((d, f"AMZN MKTP US*{rng.integers(1000, 9999)}", -float(rng.integers(300, 1500))))
    # injected duplicate charge
    rows.append((pd.Timestamp("2026-06-12"), "UBER *TRIP 555", -245.0))
    rows.append((pd.Timestamp("2026-06-13"), "UBER *TRIP 556", -245.0))
    return pd.DataFrame(rows, columns=["date", "description", "amount"])
# --------------------------------------------------------------------------
# 5. UNIFIED ANALYSIS PIPELINE
# --------------------------------------------------------------------------

def analyze_transactions(df: pd.DataFrame, z_thresh: float = 3.0, drift_pct: float = 4.0) -> dict:
    """Run the complete financial transaction analysis pipeline."""

    if not isinstance(df, pd.DataFrame):
        raise TypeError("Input must be a pandas DataFrame.")

    if df.empty:
        raise ValueError("The uploaded file contains no transactions.")

    transactions = df.copy()

    transactions.columns = [
        str(column).strip().lower()
        for column in transactions.columns
    ]

    required = {"date", "description", "amount"}
    missing = required - set(transactions.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    transactions["date"] = pd.to_datetime(
        transactions["date"], errors="coerce"
    )
    transactions["amount"] = pd.to_numeric(
        transactions["amount"], errors="coerce"
    )
    transactions["description"] = (
        transactions["description"]
        .fillna("Unknown transaction")
        .astype(str)
        .str.strip()
    )

    transactions = transactions.dropna(
        subset=["date", "amount"]
    ).copy()

    if transactions.empty:
        raise ValueError("No valid transactions were found.")

    if not np.isfinite(transactions["amount"]).all():
        raise ValueError("Transaction amounts contain invalid numbers.")

    # Retain the original signed values and stable row IDs.
    transactions = transactions.reset_index(drop=True)
    transactions["_row_id"] = range(len(transactions))
    transactions["_original_amount"] = transactions["amount"]

    # The existing categoriser converts amounts to absolute values.
    # Use it on a separate copy, then restore signed amounts by row ID.
    trie = build_trie()

    categorised = categorise(
        transactions.drop(columns=["_original_amount"]),
        trie
    )

    # categorise() sorts and resets the index, so carry row IDs through
    # the categorisation step to restore the original amount correctly.
    source = transactions.set_index("_row_id")
    categorised = categorise(
        transactions.drop(columns=["_original_amount"]),
        trie
    )

    categorised["original_amount"] = categorised["_row_id"].map(
        source["_original_amount"]
    )

    # Use absolute values for spending pattern analysis.
    spending_data = categorised.copy()
    spending_data["amount"] = spending_data["amount"].abs()

    events, subscriptions, monthly = detect(spending_data, z_thresh=z_thresh, drift_pct=drift_pct)

    amounts = spending_data["amount"].astype(float)
    mean_amount = float(amounts.mean())
    std_amount = float(amounts.std(ddof=0))

    if len(amounts) >= 5 and std_amount > 0:
        z_scores = (amounts - mean_amount) / std_amount
        spending_data["z_score"] = z_scores
        spending_data["is_anomaly"] = z_scores.abs() >= z_thresh
    else:
        spending_data["z_score"] = 0.0
        spending_data["is_anomaly"] = False

    anomaly_records = []

    for _, row in spending_data[
        spending_data["is_anomaly"]
    ].iterrows():
        anomaly_records.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "description": row["description"],
            "merchant": row["merchant"],
            "category": row["category"],
            "amount": round(float(row["amount"]), 2),
            "z_score": round(float(row["z_score"]), 2),
            "reason": (
                "Transaction amount differs significantly "
                "from the dataset average."
            )
        })

    category_totals = (
        spending_data.groupby("category")["amount"]
        .sum().sort_values(ascending=False)
    )

    merchant_totals = (
        spending_data.groupby("merchant")["amount"]
        .sum().sort_values(ascending=False)
    )

    transaction_output = spending_data.copy()
    transaction_output["date"] = (
        transaction_output["date"].dt.strftime("%Y-%m-%d")
    )
    transaction_output = transaction_output.drop(
        columns=["_row_id", "_original_amount"],
        errors="ignore"
    ).replace({np.nan: None})

    event_records = []

    for event in events:
        item = dict(event)

        if item.get("date") is not None:
            item["date"] = pd.Timestamp(
                item["date"]
            ).strftime("%Y-%m-%d")

        if item.get("series") is not None:
            item["series"] = [
                float(value) for value in item["series"]
            ]

        event_records.append(item)

    subscription_records = []

    for subscription in subscriptions.to_dict("records"):
        item = dict(subscription)

        for key, value in item.items():
            if isinstance(value, pd.Timestamp):
                item[key] = value.strftime("%Y-%m-%d")
            elif isinstance(value, np.generic):
                item[key] = value.item()

        subscription_records.append(item)

    monthly_records = []

    for date, row in monthly.iterrows():
        monthly_records.append({
            "month": date.strftime("%Y-%m"),
            "categories": {
                str(category): round(float(value), 2)
                for category, value in row.items()
            }
        })

    return {
        "summary": {
            "total_transactions": len(spending_data),
            "total_spending": round(
                float(spending_data["amount"].sum()), 2
            ),
            "average_transaction": round(
                float(spending_data["amount"].mean()), 2
            ),
            "date_from": spending_data["date"].min().strftime(
                "%Y-%m-%d"
            ),
            "date_to": spending_data["date"].max().strftime(
                "%Y-%m-%d"
            ),
            "category_totals": {
                str(key): round(float(value), 2)
                for key, value in category_totals.items()
            },
            "merchant_totals": {
                str(key): round(float(value), 2)
                for key, value in merchant_totals.items()
            }
        },
        "transactions": transaction_output.to_dict("records"),
        "anomalies": anomaly_records,
        "events": event_records,
        "subscriptions": subscription_records,
        "monthly_spending": monthly_records
    }


def generate_two_month_stories(df: pd.DataFrame) -> dict:
    """Generate financial stories analyzing transactions from the most recent two months available."""
    if df is None or len(df) == 0:
        return {
            "has_enough_data": False,
            "message": "No transaction data available. Upload a bank statement to generate financial stories.",
            "stories": []
        }

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    df = df[df["amount"] > 0]

    if len(df) == 0:
        return {
            "has_enough_data": False,
            "message": "No valid spending transactions found.",
            "stories": []
        }

    df["month_period"] = df["date"].dt.to_period("M")
    unique_months = sorted(df["month_period"].unique())

    if len(unique_months) < 2:
        single_m_name = unique_months[0].strftime("%B %Y") if unique_months else "current month"
        return {
            "has_enough_data": False,
            "message": f"Only 1 month of transactions available ({single_m_name}). Upload statements covering at least two months to unlock month-over-month Financial Stories.",
            "stories": [],
            "available_months": [m.strftime("%Y-%m") for m in unique_months]
        }

    # Focus on the most recent two months available
    m_prev = unique_months[-2]
    m_curr = unique_months[-1]
    prev_label = m_prev.strftime("%B %Y")
    curr_label = m_curr.strftime("%B %Y")

    df_prev = df[df["month_period"] == m_prev]
    df_curr = df[df["month_period"] == m_curr]

    tot_prev = float(df_prev["amount"].sum())
    tot_curr = float(df_curr["amount"].sum())
    diff_tot = tot_curr - tot_prev
    pct_tot = round((diff_tot / tot_prev * 100), 1) if tot_prev > 0 else 0.0

    stories = []

    # 1. Increasing spending pattern / MoM trend
    if diff_tot > 0:
        stories.append({
            "kind": "trend",
            "icon": "📈",
            "severity": 2 if pct_tot > 15 else 1,
            "title": f"Spending climbed by {pct_tot:+0.1f}% in {curr_label}",
            "description": f"You spent ₹{tot_curr:,.0f} in {curr_label}, an increase of ₹{diff_tot:,.0f} compared to ₹{tot_prev:,.0f} in {prev_label}. Setting a monthly budget target can help keep overall spending balanced.",
            "amount": round(abs(diff_tot), 2),
            "amount_fmt": f"₹{abs(diff_tot):,.0f}",
            "category": "Overall Spending",
            "date": curr_label
        })
    elif diff_tot < 0:
        stories.append({
            "kind": "trend",
            "icon": "📉",
            "severity": 1,
            "title": f"Disciplined spending: down by {abs(pct_tot):0.1f}% in {curr_label}",
            "description": f"Great job! Total spending fell from ₹{tot_prev:,.0f} in {prev_label} to ₹{tot_curr:,.0f} in {curr_label}, keeping an extra ₹{abs(diff_tot):,.0f} in your pocket.",
            "amount": round(abs(diff_tot), 2),
            "amount_fmt": f"₹{abs(diff_tot):,.0f}",
            "category": "Overall Spending",
            "date": curr_label
        })
    else:
        stories.append({
            "kind": "trend",
            "icon": "⚖️",
            "severity": 1,
            "title": f"Consistent spending between {prev_label} and {curr_label}",
            "description": f"Your total expenditure remained virtually identical at ₹{tot_curr:,.0f} across both months.",
            "amount": round(tot_curr, 2),
            "amount_fmt": f"₹{tot_curr:,.0f}",
            "category": "Overall Spending",
            "date": curr_label
        })

    # 2. Unusual expenses in the latest two months
    df_2m = df[df["month_period"].isin([m_prev, m_curr])]
    median_amt = df_2m["amount"].median()
    spike_candidates = df_curr[df_curr["amount"] >= max(median_amt * 2.5, 2000)].sort_values("amount", ascending=False)
    if len(spike_candidates) > 0:
        top_spike = spike_candidates.iloc[0]
        spk_amt = float(top_spike["amount"])
        spk_merch = str(top_spike.get("merchant", top_spike.get("description", "Unknown")))
        spk_cat = str(top_spike.get("category", "Others"))
        spk_date = str(top_spike["date"])[:10]
        stories.append({
            "kind": "spike",
            "icon": "⚡",
            "severity": 2,
            "title": f"Unusual expense of ₹{spk_amt:,.0f} at {spk_merch}",
            "description": f"A standout charge of ₹{spk_amt:,.0f} on {spk_date} was significantly higher than typical transactions in {spk_cat}. Verify this transaction to ensure it was planned.",
            "amount": round(spk_amt, 2),
            "amount_fmt": f"₹{spk_amt:,.0f}",
            "category": spk_cat,
            "date": spk_date
        })

    # 3. High-spending categories
    cat_curr = df_curr.groupby("category")["amount"].sum().sort_values(ascending=False)
    cat_prev = df_prev.groupby("category")["amount"].sum()
    if len(cat_curr) > 0:
        top_cat_name = cat_curr.index[0]
        top_cat_amt = float(cat_curr.iloc[0])
        top_cat_prev = float(cat_prev.get(top_cat_name, 0.0))
        top_cat_pct = round(top_cat_amt / max(tot_curr, 1) * 100, 1)
        cat_chg = top_cat_amt - top_cat_prev
        stories.append({
            "kind": "category",
            "icon": "🗂️",
            "severity": 2 if top_cat_pct > 35 else 1,
            "title": f"{top_cat_name} dominated spending ({top_cat_pct}% of total)",
            "description": f"{top_cat_name} was your largest expenditure category in {curr_label} at ₹{top_cat_amt:,.0f} (vs ₹{top_cat_prev:,.0f} in {prev_label}, {cat_chg:+,.0f}). Trimming 15% here would save ₹{top_cat_amt * 0.15:,.0f}.",
            "amount": round(top_cat_amt, 2),
            "amount_fmt": f"₹{top_cat_amt:,.0f}",
            "category": top_cat_name,
            "date": curr_label
        })

    # 4. Subscription creep
    creep_items = []
    for merch, g in df_2m.groupby("merchant"):
        g_prev = g[g["month_period"] == m_prev]
        g_curr = g[g["month_period"] == m_curr]
        if len(g_prev) > 0 and len(g_curr) > 0:
            a_prev = float(g_prev["amount"].iloc[-1])
            a_curr = float(g_curr["amount"].iloc[-1])
            if a_curr > a_prev and (a_curr - a_prev) >= 10:
                creep_diff = a_curr - a_prev
                creep_pct = round((creep_diff / a_prev) * 100, 1)
                creep_items.append({
                    "diff": creep_diff,
                    "story": {
                        "kind": "creep",
                        "icon": "🔺",
                        "severity": 2,
                        "title": f"Subscription creep: {merch} price rose by ₹{creep_diff:,.0f}/mo",
                        "description": f"{merch} increased from ₹{a_prev:,.0f} in {prev_label} to ₹{a_curr:,.0f} in {curr_label} (+{creep_pct}%). That adds up to ₹{creep_diff * 12:,.0f} extra per year.",
                        "amount": round(creep_diff * 12, 2),
                        "amount_fmt": f"₹{creep_diff * 12:,.0f}/yr",
                        "category": str(g_curr["category"].iloc[0]),
                        "date": str(g_curr["date"].iloc[-1])[:10]
                    }
                })

    if creep_items:
        creep_items.sort(key=lambda x: x["diff"], reverse=True)
        for item in creep_items[:2]:
            stories.append(item["story"])
    else:
        stories.append({
            "kind": "creep",
            "icon": "🛡️",
            "severity": 1,
            "title": f"No stealth price hikes detected in {curr_label}",
            "description": f"Recurring bills and subscriptions remained stable in price between {prev_label} and {curr_label}.",
            "amount": 0.0,
            "amount_fmt": "₹0 extra",
            "category": "Subscriptions",
            "date": curr_label
        })

    # 5. Gradual increases in spending (Category Drift)
    drift_cats = []
    for c_name, c_amt in cat_curr.items():
        if c_name in ("Others", "Other"):
            continue
        prev_amt = float(cat_prev.get(c_name, 0.0))
        if prev_amt > 500 and c_amt > prev_amt * 1.15:
            drift_cats.append((c_name, c_amt - prev_amt, round((c_amt - prev_amt) / prev_amt * 100, 1), c_amt, prev_amt))

    if drift_cats:
        drift_cats.sort(key=lambda x: x[1], reverse=True)
        top_d = drift_cats[0]
        stories.append({
            "kind": "drift",
            "icon": "📊",
            "severity": 2,
            "title": f"Gradual spending drift in {top_d[0]} (+{top_d[2]}%)",
            "description": f"Spending on {top_d[0]} drifted upwards from ₹{top_d[4]:,.0f} in {prev_label} to ₹{top_d[3]:,.0f} in {curr_label} (+₹{top_d[1]:,.0f}). Keep an eye on lifestyle inflation in this area.",
            "amount": round(top_d[1], 2),
            "amount_fmt": f"+₹{top_d[1]:,.0f}",
            "category": top_d[0],
            "date": curr_label
        })

    # 6. Potential savings opportunities
    savings_text = []
    annual_potential = 0.0
    if len(cat_curr) > 0 and top_cat_amt > 3000:
        annual_potential += top_cat_amt * 0.10 * 12
        savings_text.append(f"A 10% reduction in {top_cat_name} can free up ₹{top_cat_amt * 0.10 * 12:,.0f}/year")
    sub_spends = df_curr[df_curr["category"].isin(["Entertainment", "Bills"])]
    if len(sub_spends) > 0:
        sub_tot = float(sub_spends["amount"].sum())
        annual_potential += sub_tot * 0.2 * 12
        savings_text.append(f"auditing recurring subscriptions could save another ₹{sub_tot * 0.2 * 12:,.0f}/year")

    potential_savings = max(annual_potential, 3000.0)
    stories.append({
        "kind": "savings",
        "icon": "💡",
        "severity": 1,
        "title": f"Identified savings opportunity: ~₹{potential_savings:,.0f}/year",
        "description": f"Based on {prev_label} and {curr_label} data, {', and '.join(savings_text) if savings_text else 'optimizing monthly discretionary expenses can help save substantial cash'}.",
        "amount": round(potential_savings, 2),
        "amount_fmt": f"₹{potential_savings:,.0f}/yr",
        "category": "Savings",
        "date": curr_label
    })

    return {
        "has_enough_data": True,
        "months": [prev_label, curr_label],
        "month_keys": [m_prev.strftime("%Y-%m"), m_curr.strftime("%Y-%m")],
        "total_prev": round(tot_prev, 2),
        "total_curr": round(tot_curr, 2),
        "diff_total": round(diff_tot, 2),
        "pct_total": pct_tot,
        "stories": stories
    }

def analyse(raw, z=2.5, dp=4.0, user_id=None):
    """Run full analysis pipeline on raw transaction DataFrame with given z and drift thresholds."""
    from charts import (
        generate_monthly_chart,
        generate_category_chart,
        generate_rolling_chart,
        generate_anomaly_chart,
        generate_whatif_chart
    )
    raw = raw.copy()
    raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()
    df = categorise(raw, TRIE)
    events, subs, monthly = detect(df, z, dp)
    r30 = rolling_30d(df)
    total = float(df["amount"].sum())
    leak = sum(e["yearly"] for e in events if e["kind"] in ("creep", "new", "drift"))
    score = min(100, int(leak / max(total, 1) * 600))
    act = subs[subs["active"]] if len(subs) else pd.DataFrame()
    sm = float(act["amount"].sum()) if len(act) else 0.0
    cats = df[df["amount"] > 0].groupby("category")["amount"].sum().sort_values(ascending=False)
    cat_d = [{"category": c, "total": round(float(a), 2), "pct": round(100 * float(a) / max(total, 1), 1)} for c, a in cats.items() if a > 0]

    # Dynamically group expense transactions by month from actual transaction dates
    expense_df = df[df["amount"] > 0].copy()
    if len(expense_df) > 0:
        expense_df["month_key"] = expense_df["date"].dt.to_period("M")
        monthly_spend = expense_df.groupby("month_key")["amount"].sum().sort_index()
        # Only include months that actually have transaction data (no zeros, no artificial resampling)
        mt_d = [{"month": str(p), "total": round(float(amt), 2)} for p, amt in monthly_spend.items() if amt > 0]
    else:
        mt_d = []

    daily_s = df[df["amount"] > 0].groupby(df["date"].dt.strftime("%Y-%m-%d"))["amount"].sum()
    daily_d = [{"date": d, "amount": round(float(a), 2)} for d, a in daily_s.items()]
    rd = [{"date": str(i)[:10], "amount": round(float(v), 2)} for i, v in r30.items()]
    ICON = {"creep": "🔺", "new": "🆕", "dup": "👯", "drift": "📈", "spike": "⚡"}
    SL = {1: "Worth a look", 2: "Notable", 3: "Important"}
    ev_d = [{
        "date": str(e["date"])[:10],
        "month": "{:%B %Y}".format(e["date"]),
        "kind": e["kind"],
        "icon": ICON.get(e["kind"], "ℹ"),
        "severity": e["severity"],
        "sev_label": SL.get(e["severity"], ""),
        "title": e["title"],
        "why": e["why"],
        "series": e["series"] or [],
        "yearly": round(float(e["yearly"]), 2),
        "merchant": e["merchant"] or "",
    } for e in events]
    subs_d = [{
        "merchant": s["merchant"],
        "category": s["category"],
        "first": str(s["first"])[:10],
        "last": str(s["last"])[:10],
        "first_amount": round(float(s["first_amount"]), 2),
        "amount": round(float(s["amount"]), 2),
        "active": bool(s["active"]),
        "charges": int(s["charges"]),
        "yearly": round(float(s["amount"]) * 12, 2),
    } for _, s in subs.iterrows()]
    top = df.nlargest(10, "amount")[["date", "merchant", "category", "amount"]].copy()
    top["date"] = top["date"].astype(str).str[:10]
    anom = [e for e in ev_d if e["kind"] in ("dup", "spike", "creep", "new", "drift")]
    m = list(range(13))
    keep = [round(sm * k, 2) for k in m]
    chart_urls = {
        "monthly": generate_monthly_chart(mt_d, daily_data=daily_d, user_id=user_id),
        "category": generate_category_chart(cat_d, user_id=user_id),
        "rolling": generate_rolling_chart(rd, user_id=user_id),
        "anomalies": generate_anomaly_chart(ev_d, user_id=user_id),
        "whatif": generate_whatif_chart(m, keep, keep, user_id=user_id)
    }

    ds = df.sort_values("date", ascending=False).head(50)
    all_tx = [{"date": str(r["date"])[:10], "description": r["description"], "merchant": r["merchant"], "category": r["category"], "amount": round(float(r["amount"]), 2)} for _, r in ds.iterrows()]
    return {
        "summary": {
            "total_spend": round(total, 2), "total_spend_fmt": f"₹{total:,.2f}",
            "leak_year": round(leak, 2), "leak_year_fmt": f"₹{leak:,.2f}",
            "leak_score": score,
            "sub_monthly": round(sm, 2), "sub_monthly_fmt": f"₹{sm:,.2f}", "sub_yearly_fmt": f"₹{sm * 12:,.2f}",
            "alert_count": len(events), "tx_count": len(df),
            "date_from": str(df["date"].min())[:10], "date_to": str(df["date"].max())[:10],
            "active_sub_count": len(act),
        },
        "category_data": cat_d, "monthly_trend": mt_d, "rolling_data": rd,
        "events": ev_d, "anomalies": anom, "subscriptions": subs_d,
        "charts": chart_urls,
        "top_transactions": top.to_dict(orient="records"), "all_transactions": all_tx,
        "z": z, "drift": dp
    }
