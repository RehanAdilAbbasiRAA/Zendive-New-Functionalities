#db-logins-not-in-mt5

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