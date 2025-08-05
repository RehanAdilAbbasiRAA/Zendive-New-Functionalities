@router.post("/migrate-account/")
async def migrate_mt5_account(
    old_login: int,
    profit: int,
    balance: int,
    user_id: str,
    plan: str,
    state: str,
    password: str,
    username: str,
    investor_password: str,
    phase_1_complete: bool = False,
    phase_2_complete: bool = False,
    breached_loss_limit:  bool = False,
    upgrade_acc: bool = False,
    active: bool = False,
    EA_add_on: bool = False,
    workingDaysAddOn: bool = False,
    profit_split: Optional[str] = None
):
    try:
        user_id_obj = ObjectId(user_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    user = await users_collection.find_one({"_id": user_id_obj})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    plan_id = ObjectId(plan)
    payment_plan = await payment_plans_collection.find_one({"_id": plan_id})
    if not payment_plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    plan_amount = payment_plan["fundingOptions"]["amount"]
    plan_type = payment_plan.get("planType")

    group_mapping = {
        "HFT": {
            "Evaluation": r"demo\contest1\test1",
            "Funded": r"demo\contest1\test3",
            "Breached": r"demo\contest1\test6"
        },
        "2-step-Challenge": {
            "Evaluation": r"demo\contest1\test2",
            "Funded": r"demo\contest1\test3",
            "Breached": r"demo\contest1\test6"
        }
    }

    previous_doc = await mt5_credentials_collection.find_one({"login": old_login})
    if not previous_doc:
        raise HTTPException(status_code=404, detail="Old account not found")

    # balance = previous_doc.get("balance", plan_amount)
    # equity = previous_doc.get("equity", plan_amount)

    # Determine group
    if state == "Funded":
        group_type = "Funded"
    elif state == "Breached":
        group_type = "Breached"
    else:
        group_type = "Evaluation"

    group = group_mapping.get(plan_type, {}).get(group_type)
    if not group:
        raise HTTPException(status_code=400, detail="Invalid group mapping")
    # manager= await return_manager()
    if not manager:
        raise HTTPException(status_code=500, detail="MT5 manager not available")
    print(f" Group {group}")
    # username = await generate_unique_username(username)
    account_data = {
        'username': username,
        'password': password,
        'investor_password': investor_password,
        'group': group,
        'first_name': user['firstName'],
        'last_name': user['lastName'],
        'leverage': 100
    }
    # print(f" Acoount Data {account_data}")
    # print(f"[DEBUG] manager type before DealerBalance: {type(manager)}")

    # login = 111
    login = await create_trader_account(manager, account_data)
    print(f"New  login: {login}?????  {EA_add_on}")

    if EA_add_on:
        await enable_algo_trading(manager, login)
    else:
        await disable_algo_trading(manager, login)

    # deal_id=333
    deal_id = manager.DealerBalance(login, balance, MT5Manager.MTDeal.EnDealAction.DEAL_BALANCE, "Initial Balance")

    creation_date = datetime.utcnow()
    expiry_date = creation_date + timedelta(days=30)

    doc = {
        "user_id": user_id_obj,
        "login": login,
        "previous_login": old_login,
        "remaning_account":True,
        "plan": plan,
        "username": username,
        "password": password,
        "investor_password": investor_password,
        "breached_loss_limit": breached_loss_limit,
        "upgrade_acc": upgrade_acc,
        "group": group,
        "plan_amount": plan_amount,
        "creation_date": creation_date,
        "expiry_date": expiry_date,
        "deal_id": deal_id,
        "active": active,
        "state": state,
        "balance": balance,
        "equity": balance,
        "margin": balance,
        "profit": profit,
        "addOns": {
            "payout7Days": workingDaysAddOn,
            "eAAllowed": EA_add_on,
            "profitSplit": profit_split or ""
        },
        "name": user["firstName"] + " " + user["lastName"],
        "timestamp": datetime.now(tz=pytz.UTC),
        "group_type": group_type
    }

    if plan_type == "HFT":
        doc["phase_1_complete"] = phase_1_complete
    elif plan_type == "2-step-Challenge":
        doc["phase_1_complete"] = phase_1_complete
        doc["phase_2_complete"] = phase_2_complete

    copy_fields = ["ArbTrading", "Hedging", "CopyBetting", "AIBTrading", "payoutRequestCount", "breach_reason", "breach_at","unbreach_date","dailyDrawDown_breach_count","singleTrdae_breach_count","equityLossLimit_breach_count","multi_trade_breach_count"]
    for field in copy_fields:
        if field in previous_doc:
            doc[field] = previous_doc[field]

    await mt5_credentials_collection.insert_one(doc)

    await mt5_credentials_collection.update_one({"login": old_login}, {
        "$set": {
            "remaning": True,
            "new_login": login,
            "mt5_rehan_check_pass": True,
            "migrated_at": datetime.utcnow()
        }
    })

    await balance_equity_collection.insert_one({
        "user_id": user_id,
        "login": login,
        "balance": balance,
        "equity": balance,
        "timestamp": datetime.utcnow()
    })

    # Email templates
    if plan_type == "HFT" and phase_1_complete:
        template = "templates/the_pride_funding___Funded Account_Credential.html"
    elif plan_type == "2-step-Challenge":
        if phase_2_complete:
            template = "templates/the_pride_funding___Funded Account_Credential.html"
        elif phase_1_complete:
            template = "templates/the_pride_funding___phase_2_credential.html"
        else:
            template = "templates/the_pride_funding___phase_1_credential.html"
    else:
        template = "templates/the_pride_funding___phase_1_credential.html"

    await send_email(
        recipient_email=user['email'],
        # recipient_email="rehandil900@gmail.com",
        login=login,
        username=username,
        password=password,
        firstname=user['firstName'],
        plan=plan_amount,
        template_type=template,
        discount_price="N/A",phasenumber="N/A" ,paymentMethod="N/A",used_code="N/A",
        cc=["rehanadil041@gmail.com"]
        # cc=["rehanadil041@gmail.com", "gamerzakiullah@gmail.com"]
    )
    # if state == "Breached":
    #     await disable_mt5_trading(manager, login)

    return {
        "message": "Migration completed",
        "login": login,
        "email_sent": True,
        "group": group
    }

@router.post("/bulk-migrate-from-json")
async def bulk_migrate_from_json(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") != ADMIN_USERNAME:
            raise HTTPException(status_code=401, detail="Unauthorized")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # ✅ Your target logins
    target_logins = {
        1001246, 1001254, 1001255, 1001258, 1001262, 1001267, 1001268, 1001269,
        1001272, 1001274, 1001275, 1001284, 1001287, 1001288, 1001586, 1001589,
        1001199, 1001216, 1001218, 1001232, 1001233
    }

    # ✅ Load JSON data
    with open('PRIDE_FUNDING.mt5_credentials_1st_batch.json', 'r') as file:
        data = json.load(file)
        if isinstance(data, dict):
            data = [data]

    migrated = []
    skipped = []

    for account in data:
        login = account.get("login")
        if login not in target_logins:
            continue

        try:
            print(f"✅ Migrating login from JSON: {login}")
            plan_amount = account.get("plan_amount", 0)

            result = await migrate_mt5_account(
                old_login=login,
                user_id=str(account["user_id"]["$oid"]),
                plan=account["plan"],
                state=account["state"],
                breached_loss_limit=account.get("breached_loss_limit", False),
                upgrade_acc=account.get("upgrade_acc", False),
                active=account.get("active", True),
                profit=account.get("profit", 0),
                balance=account.get("plan_amount", 0),
                password=account["password"],
                username=account["username"],
                investor_password=account["investor_password"],
                phase_1_complete=account.get("phase_1_complete", False),
                phase_2_complete=account.get("phase_2_complete", False),
                EA_add_on=account.get("addOns", {}).get("eAAllowed", False),
                workingDaysAddOn=account.get("addOns", {}).get("payout7Days", False),
                profit_split=account.get("addOns", {}).get("profitSplit", "")
            )

            migrated.append({
                "old_login": login,
                "new_login": result.get("login"),
                "group_added": result.get("group"),
                "email_sent": result.get("email_sent", False)
            })

        except Exception as e:
            print(f"❌ Failed for login {login}: {str(e)}")
            skipped.append({
                "old_login": login,
                "error": str(e)
            })

    return {
        "migrated": migrated,
        "skipped": skipped,
        "total": len(migrated) + len(skipped),
        "done": len(migrated),
        "failed": len(skipped)
    }



import json

# Your target logins (23 in total)
target_logins = {
    1001217, 1001246, 1001254, 1001255, 1001258, 1001262, 1001267, 1001268, 1001269,
    1001272, 1001274, 1001275, 1001284, 1001287, 1001288, 1001586, 1001589,
    1001199, 1001216, 1001218, 1001232, 1001233
}

# Load JSON data once
with open('PRIDE_FUNDING.mt5_credentials_1st_batch.json', 'r') as file:
    data = json.load(file)
    if isinstance(data, dict):
        data = [data]

# Create a lookup set of all logins in the JSON
json_logins = {entry.get("login") for entry in data if entry.get("login") is not None}


@router.get("/check_logins")
async def check_logins():
    found_logins = []
    matched_logins_set = set()

    # Find matched logins and extract info
    for entry in data:
        login = entry.get("login")
        if login in target_logins:
            matched_logins_set.add(login)
            found_logins.append({
                "login": login,
                "group_type": entry.get("group_type", "N/A"),
                "state": entry.get("state", "N/A")
            })

    # Determine unmatched logins
    unmatched_logins = sorted(target_logins - matched_logins_set)

    # Print matched results
    print("✅ Matched Logins:")
    for info in found_logins:
        print(f"Login: {info['login']} | Group Type: {info['group_type']} | State: {info['state']}")

    print(f"\n✅ Total matched logins: {len(found_logins)} out of {len(target_logins)}")

    # Print unmatched results
    print("\n❌ Not Found Logins:")
    for login in unmatched_logins:
        print(f"Login: {login}")

    # Optionally return as JSON response
    return {
        "matched": found_logins,
        "unmatched": unmatched_logins,
        "matched_count": len(found_logins),
        "unmatched_count": len(unmatched_logins)
    }


@router.delete("/delete-migrated-accounts")
async def delete_migrated_accounts(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") != ADMIN_USERNAME:
            raise HTTPException(status_code=401, detail="Unauthorized")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # 🔴 Manually paste your batch here
    BATCH_LOGINS = [

    # 1001422, please add he login on  your own
        # ... up to 95 logins

            1001217, 1001246, 1001254, 1001255, 1001258, 1001262, 1001267, 1001268, 1001269,
    1001272, 1001274, 1001275, 1001284, 1001287, 1001288, 1001586, 1001589,
    1001199, 1001216, 1001218, 1001232, 1001233
    ]

    delete_result = await mt5_credentials_collection.delete_many({
        "login": { "$in": BATCH_LOGINS }
    })

    return {
        "deleted_count": delete_result.deleted_count,
        "status": f"Deleted {len(BATCH_LOGINS)} accounts by login list"
    }