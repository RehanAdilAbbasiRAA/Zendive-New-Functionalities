# from fastapi import APIRouter, HTTPException, Depends
# from typing import Optional
# from datetime import datetime, timedelta
# from bson import ObjectId
# import pytz

# router = APIRouter()

@router.post("/migrate-account/")
async def migrate_mt5_account(
    old_login: int,
    profit: int,
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

    balance = previous_doc.get("balance", plan_amount)
    equity = previous_doc.get("equity", plan_amount)

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

    login = await create_trader_account(manager, account_data)
    print(f"New  login: {login}?????  {EA_add_on}")

    if EA_add_on:
        await enable_algo_trading(manager, login)
    else:
        await disable_algo_trading(manager, login)

    deal_id = manager.DealerBalance(login, balance, MT5Manager.MTDeal.EnDealAction.DEAL_BALANCE, "Initial Balance")

    creation_date = datetime.utcnow()
    expiry_date = creation_date + timedelta(days=30)

    doc = {
        "user_id": user_id_obj,
        "login": login,
        "previous_login": old_login,
        "off_trading_rigts":True,
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

    copy_fields = ["ArbTrading", "Hedging", "CopyBetting", "AIBTrading", "payoutRequestCount", "breach_reason", "breached_at","unbreach_date","dailyDrawDown_breach_count","singleTrdae_breach_count","equityLossLimit_breach_count","multi_trade_breach_count"]
    for field in copy_fields:
        if field in previous_doc:
            doc[field] = previous_doc[field]

    await mt5_credentials_collection.insert_one(doc)

    await mt5_credentials_collection.update_one({"login": old_login}, {
        "$set": {
            "is_migrated": True,
            "new_login": login,
            "mt5_rehan_check_pass": True,
            "migrated_at": datetime.utcnow()
        }
    })

    await balance_equity_collection.insert_one({
        "user_id": user_id,
        "login": login,
        "balance": balance,
        "equity": equity,
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


@router.post("/bulk-migrate-active-accounts")
async def bulk_migrate_accounts(login:int,token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") != ADMIN_USERNAME:
            raise HTTPException(status_code=401, detail="Unauthorized")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    

    # user_id = ObjectId("682b8bb2f3eb28294117e074")  # Fixed for your own account

    # ✅ Fetch all matching accounts for this user
    # accounts_cursor = mt5_credentials_collection.find({
    #     "active": True,
    #     "breached_loss_limit": False
    # })

    migrated = []
    skipped = []
    count=0
    accounts = await mt5_credentials_collection.find({"login": {"$in":[    1001472,
    1001473,
    1001474,
    1001475,
    1001476,
    1001479,
    1001484,
    1001486,
    1001487,
    1001488,
    1001489,
    1001490,
    1001491,
    1001492,
    1001493,
    1001494,
    1001495,
    1001496,
    1001497,
    1001500,
    1001503,
    1001504,
    1001511,
    1001513,
    1001515,
    1001519,
    1001520,
    1001522,
    1001524,
    1001525,
    1001530,
    1001538,
    1001539,
    1001540,
    1001541,
    1001542,
    1001543,
    1001544,
    1001547,
    1001548,
    1001549,
    1001550,
    1001551,
    1001552,
    1001553,
    1001557,
    1001558,
    1001559,
    1001560,
    1001561,
    1001562,
    1001563,
    1001564,
    1001565,
    1001566,
    1001567,
    1001568,
    1001569,
    1001570,
    1001571,
    1001572,
    1001573,
    1001574,
    1001575,
    1001576,
    1001577,
    1001578,
    1001579,
    1001580,
    1001581,
    1001582,
    1001583,
    1001584,
    1001587,
    1001588,
    1001591,
    1001592,
    1001595,
    110720,
    110721,
    110722,
    110723,
    110724,
    110725,
    110726,
    110727,
    110728,
    110729,
    110730,
    110731,
    110732,
    110733,
    110734,
    110735,
    110736,
    110737]}}).to_list(None)
    for account in accounts:
    # async for account in mt5_credentials_collection.find({
    #             # "active": True,
    #             # "breached_loss_limit": False,
    #             "login":login
    #         }):
        try:
            print(f"Migrating login: {account['login']}")
            count=count+1
            result = await migrate_mt5_account(
                old_login=account["login"],
                user_id=str(account["user_id"]),
                plan=account["plan"],
                state=account["state"],
                breached_loss_limit=account.get("breached_loss_limit",False),
                upgrade_acc=account.get("upgrade_acc",False),
                active=account.get("active",True),
                profit=account.get("profit",0),
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
                "old_login": account["login"],
                "new_login": result.get("login"),
                "email_sent": result.get("email_sent", False),
                "group_added": result.get("group")
            })

        except Exception as e:
            skipped.append({
                "old_login": account["login"],
                "error": str(e)
            })

    return {
        "migrated": migrated,
        "skipped": skipped,
        "total": len(migrated) + len(skipped),
        "total login": count
    }




# @router.delete("/delete-migrated-accounts")
# async def delete_migrated_accounts(token: str = Depends(oauth2_scheme)):
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         if payload.get("sub") != ADMIN_USERNAME:
#             raise HTTPException(status_code=401, detail="Unauthorized")
#     except JWTError:
#         raise HTTPException(status_code=401, detail="Invalid token")

#     # Delete all documents with the marker
#     delete_result = await mt5_credentials_collection.delete_many({
#         "mt5_rehan_check_pass": True
#     })

#     return {
#         "deleted_count": delete_result.deleted_count,
#         "status": "Accounts with 'mt5_rehan_check_pass' field deleted"
#     }


# @router.delete("/delete-migrated-accounts")
# async def delete_migrated_accounts(token: str = Depends(oauth2_scheme)):
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         if payload.get("sub") != ADMIN_USERNAME:
#             raise HTTPException(status_code=401, detail="Unauthorized")
#     except JWTError:
#         raise HTTPException(status_code=401, detail="Invalid token")

#     # 🔴 Manually paste your batch here
#     BATCH_LOGINS = [
#         1001472, 1001473, 1001474, 1001475, 1001476,
#         1001479, 1001484, 1001486, 1001487, 1001488,
#         1001489, 1001490, 1001491, 1001492, 1001493,
#         # ... up to 95 logins
#     ]

#     delete_result = await mt5_credentials_collection.delete_many({
#         "login": { "$in": BATCH_LOGINS }
#     })

#     return {
#         "deleted_count": delete_result.deleted_count,
#         "status": f"Deleted {len(BATCH_LOGINS)} accounts by login list"
#     }






@router.post("/disable-breached-trading")
async def disable_breached_trading(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") != ADMIN_USERNAME:
            raise HTTPException(status_code=401, detail="Unauthorized")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Connect to MT5 manager
    manager = await return_manager()
    if not manager:
        raise HTTPException(status_code=500, detail="MT5 manager not available")

    query = {
        # "group_type": "Breached",
        # "off_trading_rigts": True
        "login": {"$in": [1001621,1001620]}
    }

    updated = []
    failed = []

    async for doc in mt5_credentials_collection.find(query):
        login = doc.get("login")
        try:
            await disable_mt5_trading(login, manager)
            # await enable_mt5_trading(login, manager)
            updated.append(login)
        except Exception as e:
            logging.error(f"Failed to disable trading for login {login}: {e}")
            failed.append({"login": login, "error": str(e)})

    return {
        "disabled_trading_for": updated,
        "failed": failed,
        "total_processed": len(updated) + len(failed)
    }



# db-logins-not-in-mt5

@router.get("/db-logins-not-in-mt5")
async def db_logins_not_in_mt5():
    try:
        # 1. Fetch all MT5 users
        mt5_users = manager.UserGetByGroup("*")
        if not mt5_users:
            error = MT5Manager.LastError()
            print("❌ Failed to fetch MT5 users:", error)
            return {"error": f"MT5 fetch failed: {error}"}

        # 2. Make a set of MT5 logins
        mt5_logins = {user.Login for user in mt5_users}

        # 3. Fetch all logins from the DB
        db_logins = set()
        async for doc in mt5_credentials_collection.find({}, {"login": 1}):
            db_logins.add(doc["login"])

        # 4. Identify logins:
        missing_in_mt5 = db_logins - mt5_logins
        available_in_both = db_logins & mt5_logins

        print(f"✅ Total in DB: {len(db_logins)} | Missing in MT5: {len(missing_in_mt5)} | Available in MT5: {len(available_in_both)}")

        return {
            "total_in_db": len(db_logins),
            "count_missing": len(missing_in_mt5),
            "count_available": len(available_in_both),
            "missing_in_mt5": list(missing_in_mt5),
            "available_in_mt5": list(available_in_both),
        }

    except Exception as e:
        return {"error": str(e)}

