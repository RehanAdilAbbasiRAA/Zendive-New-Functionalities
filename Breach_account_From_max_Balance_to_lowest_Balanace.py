
@router.get("/delete_accounts_exceeding_loss_limit")
async def delete_accounts_exceeding_loss_limit():
    logging.info("😊😊Cron job for deleting accounts has started.")
    startTime=datetime.now()
    print(f"[START]⌚⌚ delete_accounts_exceeding_loss_limit at {startTime}")
    global manager
    if not manager:
        return {"Error": "Could not connect to Manager"}

    now = datetime.utcnow().replace(tzinfo=pytz.UTC)
    utc_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    accounts = await mt5_credentials_collection.find({"breached_loss_limit": False}).to_list(None)
    for account in accounts:
        login = account.get("login")
        user_id = account.get("user_id")
        this_plan = account.get("plan")
        plan_amount = account.get("plan_amount")
        account_state = account.get("state","Active")


        if not plan_amount:
            logging.error(f"Missing plan_amount for login: {login}")
            continue

        plan_details = await payment_plans_collection.find_one({"_id": ObjectId(this_plan)})
        if not plan_details:
            logging.error(f"Plan details not found for plan ID: {this_plan}")
            continue

        planType = plan_details.get("planType", "Unknown")
        funding_opts = plan_details.get("fundingOptions", {})
        daily_limit_pct = funding_opts.get("maxDailyLoss", 0) * 0.01
        max_limit_pct = funding_opts.get("maxTotalLoss", 0) * 0.01
        daily_limit_abs = plan_amount * daily_limit_pct
        max_limit_abs = plan_amount * max_limit_pct

        creation_date = account.get("unbreach_date") or account.get("creation_date")
        if isinstance(creation_date, str):
            creation_date = datetime.fromisoformat(creation_date.replace("Z", "+00:00"))
        if creation_date.tzinfo is None:
            creation_date = creation_date.replace(tzinfo=pytz.UTC)
            
        # 🔁 Use only for daily check — NOT monthly
        daily_check_start_time = max(utc_midnight, creation_date)
        # print("daily_check_start_time ",daily_check_start_time)
        # Fetch minimum balances efficiently
        daily_min_doc = await balance_equity_collection.find_one(
            {"login": login, "timestamp": {"$gte": daily_check_start_time}},sort=[("balance", 1)])
        # monthly_min_doc = await balance_equity_collection.find_one(
        #     {"login": login, "timestamp": {"$gte": creation_date}, "balance": {"$ne": 0}},
        #     sort=[("balance", 1)]
        # )
        # if daily_min_doc:
        #     print(f"✅ Found daily_min_doc with balance: {daily_min_doc['balance']} at {daily_min_doc['timestamp']}   {daily_min_doc['balance']}")
        daily_min_balance = daily_min_doc['balance'] if daily_min_doc else plan_amount
        # monthly_min_balance = monthly_min_doc['balance'] if monthly_min_doc else plan_amount

        breached = False
        if daily_min_doc:
            first_daily_doc = await balance_equity_collection.find_one(
                {"login": login, "timestamp": {"$gte": daily_check_start_time}},sort=[("timestamp", 1)])
            if first_daily_doc:
                first_balance = first_daily_doc['balance']
                threshold = first_balance * (1 - daily_limit_pct)
                if daily_min_balance <= threshold:
                    loss_description = f"{'HFT' if planType == 'HFT' else ('Two-Step Phase 1' if not account.get('phase_1_complete') else 'Two-Step Phase 2')} Daily Drawdown Exceeds {daily_limit_pct * 100:.2f}%"
                    breached = True
                    # print(f"Breached triggered for login Daily loss{login}>>>>>>>>>>>>")
                    continue
        # ✅ New Max Drawdown Logic (Based on Highest -> Lowest equity)
        # Step 1: Get document with highest equity/balance (descending sort)
        highest_doc = await balance_equity_collection.find_one(
            {"login": login, "timestamp": {"$gte": creation_date}},
            sort=[("equity", -1)]
        )
        if highest_doc:
            highest_value = highest_doc["equity"]
            highest_time = highest_doc["timestamp"]

            # Step 2: Get lowest equity after the highest was achieved
            lowest_after_highest_doc = await balance_equity_collection.find_one(
                {"login": login, "timestamp": {"$gte": highest_time}},
                sort=[("equity", 1)]
            )

            if lowest_after_highest_doc:
                lowest_value = lowest_after_highest_doc["equity"]

                # Step 3: Calculate drawdown percentage
                drawdown_pct = ((highest_value - lowest_value) / highest_value) * 100

                if drawdown_pct >= (max_limit_pct * 100):  # Convert max_limit_pct to % for comparison
                    loss_description = f"{'HFT' if planType == 'HFT' else ('Two-Step Phase 1' if not account.get('phase_1_complete') else 'Two-Step Phase 2')} Max Drawdown Exceeds {max_limit_pct * 100:.2f}%"
                    breached = True
                    print(f"Breached triggered for login MAX DRAWDOWN (actual equity drop): {login}")
                    # print(f"{highest_doc} {lowest_after_highest_doc} {login}    {highest_value-lowest_value}")
            # print(f"Breached triggered for login MAX Draw Down loss{login}>>>>>>>>>>>>")

        if not breached:
            continue
    # :white_check_mark: If funded, update group in MT5 and DB
        if account_state == "Funded":
            try:
                user_info = manager.UserGet(int(login))
                if not user_info:
                    logging.warning(f"[MT5] User not found for login: {login}")
                else:
                    user_info.Group = BREACHED_FUNDED_GROUP
                    updated = manager.UserUpdate(user_info)
                    if updated:
                        logging.info(f"[MT5] User group changed to breachedAcc for login {login}")
                        # :white_check_mark: Also update group in DB
                        await mt5_credentials_collection.update_one(
                            {"login": login},
                            {"$set": {"group": BREACHED_FUNDED_GROUP}}
                        )
                        logging.info(f"[DB] Group updated in DB to '{BREACHED_FUNDED_GROUP}' for login {login}")
                    else:
                        logging.warning(f"[MT5] Failed to update group for login {login}")
            except Exception as e:
                logging.error(f"[MT5] Error while updating group for funded account {login}: {str(e)}")
        # Apply breach to DB
        await mt5_credentials_collection.update_one(
            {"login": login},
            {"$set": {
                "breached_loss_limit": True,
                "active": False,
                "state": "Breached","breach_reason": "Account Breached By Exceeding Balance loss limit Crons","breach_at": datetime.utcnow()
            },
            "$inc": {"dailyDrawDown_breach_count": 1}}
        )
        manager = await return_manager()
        if manager is None:
            raise HTTPException(status_code=500, detail="Failed to connect to MT5 Manager")
        # Load the user's current details
        await disable_mt5_trading(login, manager)
        logging.info(f"User {login} marked as breached: {loss_description}")
        await u_sink.remove_login_from_cache(login)#✅✅✅

        # Disable trading + Notify via email
        user_doc = await users_collection.find_one({"_id": ObjectId( user_id)})
        if user_doc:
            email = user_doc.get("email", "")
            username = user_doc.get("userName", "")
            firstname = user_doc.get("firstname", "Customer")

            await send_breach_email(
                recipient_email=email,
                login=login,
                username=username,
                loss_rule=loss_description,
                firstname=firstname
            )
        else:
            logging.warning(f"No user document found for user_id: {user_id}")
        # print("Breached Trigered for User {login}>>>>>>>>>>>>>>>>>>>>>>>>")
    print(f"[END] ⏲️⏲️ delete_accounts_exceeding_loss_limit at {datetime.now()-startTime}")
    logging.info("Cron job for deleting accounts has ended.😒😒")
