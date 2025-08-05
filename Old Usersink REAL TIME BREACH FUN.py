#Old Usersink REAL TIME BREACH FUN

async def start_real_time_monitor(self, interval: int = 30):
    print("🚀 Starting real-time UserSink breach monitor loop...")
    while True:
        try:
            for login, data in list(self.login_to_id.items()):
                if login in self.breach_in_progress:
                    continue
                plan_doc = await mt5_credentials_collection.find_one({"login": login})
                if not plan_doc or plan_doc.get("state") == "Breached":
                    continue  # 🔒 Already breached, skip this login

                account = manager.UserAccountGet(login)
                if not account:
                    logging.warning(f"⚠️ Could not get account info for login: {login}")
                    continue

                equity = getattr(account, "Equity", None)
                balance = getattr(account, "Balance", None)
                if equity is None or balance is None:
                    continue

                plan_id = data.get("plan_id")
                plan_amount = data.get("plan_amount")

                if not plan_id or not plan_amount:
                    continue

                plan_details = await payment_plans_collection.find_one({"_id": ObjectId(plan_id)})
                if not plan_details:
                    continue

                plan_type = plan_details.get("planType", "")
                funding_opts = plan_details.get("fundingOptions", {})

                # Phase logic
                if plan_type == "2-step-Challenge":
                    plan_doc = await mt5_credentials_collection.find_one({"login": login})
                    if plan_doc.get("phase_1_complete") is not True:
                        phase = funding_opts.get("phase1", {})
                    elif plan_doc.get("phase_2_complete") is not True:
                        phase = funding_opts.get("phase2", {})
                    else:
                        phase = funding_opts.get("funded", {})
                elif plan_type == "HFT":
                    phase = funding_opts.get("phase1", {})
                else:
                    phase = funding_opts.get("funded", {})

                daily_dd_pct = float(phase.get("maxDailyDrawdown", "0").replace("%", "")) / 100
                max_dd_pct = float(phase.get("maxDrawdown", "0").replace("%", "")) / 100

                daily_limit_abs = plan_amount * daily_dd_pct
                max_limit_abs = plan_amount * max_dd_pct

                equity_loss = max(0, balance - equity)
                balance_loss = max(0, plan_amount - balance)
                total_loss = balance_loss + equity_loss
                # Determine which limit was breached and its percentage
                if total_loss >= daily_limit_abs:
                    breached_pct = daily_dd_pct * 100
                else:
                    breached_pct = max_dd_pct * 100

                if total_loss >= daily_limit_abs or total_loss >= max_limit_abs:
                    logging.warning(f"🔥 [Loop] Breach triggered for login: {login}")
                    self.breach_in_progress.add(login)
                    update_operation = {
                        "$set": {"breach_at": datetime.utcnow()}
                    }
                    asyncio.create_task(self.breach_account(login, update_operation,breached_pct))

        except Exception as e:
            logging.error(f"❌ Error in real-time breach monitor: {e}", exc_info=True)

        await asyncio.sleep(interval)