import os, time, logging, requests

CONFIG = {
    "min_edge": 0.08,
    "take_profit_pct": 0.25,
    "stop_loss_pct": 0.15,
    "position_size_usdc": 20,
    "max_positions": 5,
    "scan_interval": 10,
    "min_volume": 10000,
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("polybot")

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
positions = {}

def fetch_markets():
    try:
        r = requests.get(f"{GAMMA_API}/markets", params={
            "active": "true", "closed": "false",
            "limit": 100, "order": "volume24hr", "ascending": "false"
        }, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.error(f"Fetch error: {e}")
    return []

def get_clob_price(token_id):
    try:
        r = requests.get(f"{CLOB_API}/midpoint", params={"token_id": token_id}, timeout=5)
        if r.status_code == 200:
            return float(r.json().get("mid", 0))
    except:
        pass
    return None

def find_opportunities(markets):
    opps = []
    for m in markets:
        try:
            if float(m.get("volume", 0)) < CONFIG["min_volume"]:
                continue
            tokens = m.get("tokens", [])
            yes = next((t for t in tokens if t.get("outcome") == "Yes"), None)
            no = next((t for t in tokens if t.get("outcome") == "No"), None)
            if not yes or not no:
                continue
            gamma_price = float(yes.get("price", 0))
            if gamma_price <= 0.02 or gamma_price >= 0.98:
                continue
            token_id = yes.get("token_id")
            if not token_id:
                continue
            clob_price = get_clob_price(token_id)
            if not clob_price:
                continue
            edge = clob_price - gamma_price
            if abs(edge) >= CONFIG["min_edge"]:
                opps.append({
                    "question": m.get("question", "Unknown")[:60],
                    "token_id": token_id,
                    "gamma_price": gamma_price,
                    "clob_price": clob_price,
                    "edge": round(abs(edge), 4),
                    "direction": "YES" if edge > 0 else "NO",
                })
        except:
            continue
    return sorted(opps, key=lambda x: x["edge"], reverse=True)

def run():
    log.info("Polymarket Bot STARTED - DRY RUN MODE")
    log.info(f"Edge: {CONFIG['min_edge']:.0%} | TP: {CONFIG['take_profit_pct']:.0%} | SL: {CONFIG['stop_loss_pct']:.0%}")
    scan = 0
    while True:
        scan += 1
        log.info(f"--- Scan #{scan} | Positions: {len(positions)} ---")
        for tid in list(positions.keys()):
            pos = positions[tid]
            current = get_clob_price(tid)
            if not current:
                continue
            gain = (current - pos["entry"]) / pos["entry"]
            if gain >= CONFIG["take_profit_pct"]:
                log.info(f"TAKE PROFIT | {pos['question']} | +{gain:.1%} | +${gain * CONFIG['position_size_usdc']:.2f}")
                del positions[tid]
            elif gain <= -CONFIG["stop_loss_pct"]:
                log.info(f"STOP LOSS | {pos['question']} | {gain:.1%}")
                del positions[tid]
        if len(positions) < CONFIG["max_positions"]:
            markets = fetch_markets()
            opps = find_opportunities(markets)
            log.info(f"Scanned: {len(markets)} | Opportunities: {len(opps)}")
            for opp in opps[:3]:
                if opp["token_id"] in positions or len(positions) >= CONFIG["max_positions"]:
                    break
                log.info(f"OPPORTUNITY | {opp['question']} | Edge: {opp['edge']:.1%} | {opp['direction']}")
                log.info(f"[DRY RUN] BUY ${CONFIG['position_size_usdc']} @ {opp['clob_price']:.3f}")
                positions[opp["token_id"]] = {
                    "question": opp["question"],
                    "entry": opp["clob_price"],
                    "direction": opp["direction"],
                }
        time.sleep(CONFIG["scan_interval"])

run()
