@router.get("/order_send")
async def order_send(login):
    positions = await asyncio.get_running_loop().run_in_executor(None , manager.PositionGetByLogins , [login])
    failed_orders = []
    for pos in positions:
        symbol = pos.Symbol
        volume = pos.Volume
        position_type = pos.Action
        positionId = pos.Position
        tick_info = await asyncio.get_running_loop().run_in_executor(None , manager.TickStat , symbol)
        if tick_info is None:
            failed_orders.append({
                "ticket": positionId,
                "error": "No tick info",
                "message": f"Could not get tick info for {symbol}"
            })
            continue
        deal = MT5Manager.MTDeal(manager)
        price = tick_info.bid_low if position_type == mt5.POSITION_TYPE_BUY else tick_info.ask_low
        order_type = mt5.ORDER_TYPE_SELL if position_type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        deal.Login = login
        deal.Symbol = symbol
        deal.Action = order_type
        deal.Volume = volume
        deal.Price = price
        deal.PositionID = positionId
        deal.Comment = "Closed by API"
        deal_perform = manager.DealPerform(deal=deal)
        if not deal_perform:
            error = MT5Manager.LastError()
            raise HTTPException(status_code=500, detail=f"Failed to perform a deal: {error}")