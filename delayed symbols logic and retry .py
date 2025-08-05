# delayed symbols logic and retry  


def delayed_symbol_check(self, login):
    time.sleep(1.2)  # Wait for positions to stabilize

    try:
        retry_count = 0
        positions = manager.PositionGet(login)

        while not positions and retry_count < 3:
            logging.info(f"⏳ No positions found for login {login}, retrying ({retry_count + 1})...")
            time.sleep(0.2)
            positions = manager.PositionGet(login)
            retry_count += 1

        if not positions:
            logging.info(f"✅ Still no open trades for login: {login} after {retry_count} retries. Skipping check.")
            return

        symbols = [getattr(pos, "Symbol", "") for pos in positions]
        symbol_counter = Counter(symbols)

        for symbol, count in symbol_counter.items():
            logging.info(f"🔍 Symbol '{symbol}' has {count} open positions.")

        duplicate_symbols = [s for s, count in symbol_counter.items() if count >= 3]
        if not duplicate_symbols:
            logging.info(f"✅ No breach found for login {login}, symbols are within limits.")
            return

        logging.warning(f"🚨 Breach triggered for login {login} due to symbols: {duplicate_symbols}")
        self.breach_in_progress.add(login)

        # 🚀 Run async handler on main event loop
        self.loop.create_task(self.async_breach_handler(login, duplicate_symbols))

    except Exception as e:
        logging.error(f"❌ Exception in delayed_symbol_check for login {login}: {e}", exc_info=True)