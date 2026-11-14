import asyncio
from datetime import timedelta

from bson import ObjectId
from test_employee_hr import BASE, identity


async def leave_type(client,owner_headers,limit=None):
    result=await client.post("/api/v1/employees/hr/leave-types",headers=owner_headers,json={"name":"Configured Leave","annual_calendar_day_limit":limit,"counting_method":"calendar_days"})
    assert result.status_code==200,result.text
    return result.json()["data"]


async def test_leave_policy_explicit_balance_overlap_approval_and_notifications(client,mock_db,owner_headers,master_data):
    from app.utils.datetime import to_ist,utc_now
    employee,headers=await identity(client,owner_headers,master_data)
    assert (await client.post("/api/v1/employees/hr/leave-types",headers=headers,json={"name":"Unauthorized","counting_method":"calendar_days"})).status_code==403
    policy=await leave_type(client,owner_headers,3)
    day=to_ist(utc_now()).date()
    payload={"leave_type_id":policy["id"],"start_date":day.isoformat(),"end_date":(day+timedelta(days=1)).isoformat(),"reason":"Personal request"}
    requests=await asyncio.gather(*(client.post(BASE+"me/leaves",headers=headers,json=payload) for _ in range(2)))
    assert sorted(row.status_code for row in requests)==[200,409]
    request=next(row.json()["data"] for row in requests if row.status_code==200)
    assert (await client.get(BASE+"me/leaves",headers=headers)).json()["data"]["balances"][0]["available_days"]==1
    exceed=payload|{"start_date":(day+timedelta(days=3)).isoformat(),"end_date":(day+timedelta(days=4)).isoformat()}
    assert (await client.post(BASE+"me/leaves",headers=headers,json=exceed)).status_code==422
    url=BASE+employee["id"]+"/leaves/"+request["id"]+"/review"
    assert (await client.post(url,headers=headers,json={"decision":"approved"})).status_code==403
    assert (await client.post(url,headers=owner_headers,json={"decision":"approved"})).status_code==200
    # A committed approval can rebuild its attendance projection after an interruption.
    from app.features.employee.hr_leave import project_approved_leave
    raw = await mock_db.employees.find_one({"_id": ObjectId(employee["id"])})
    await mock_db.attendance_days.update_many({}, {"$unset": {"approved_leave_request_ids": ""}})
    await mock_db.employees.update_one({"_id": raw["_id"], "hr_leave_requests.id": request["id"]}, {"$set": {"hr_leave_requests.$.attendance_projection_pending": True}})
    raw = await mock_db.employees.find_one({"_id": raw["_id"]})
    await project_approved_leave(mock_db, raw)
    await project_approved_leave(mock_db, raw)
    projected = await mock_db.attendance_days.find({"approved_leave_request_ids": request["id"]}).to_list(None)
    assert len(projected) == 2
    assert all(row["approved_leave_request_ids"] == [request["id"]] for row in projected)
    assert (await client.post(BASE+"me/leaves/"+request["id"]+"/cancel",headers=headers)).status_code==409
    report=await client.get("/api/v1/employees/hr/reports/attendance",headers=owner_headers,params={"month":day.strftime("%Y-%m"),"employee":employee["id"]})
    assert report.status_code==200,report.text
    assert any(row["approved_leave"] for row in report.json()["data"]["items"])
    inbox=await mock_db.notifications.find({"recipient_user_id":(await mock_db.employees.find_one({"_id":ObjectId(employee["id"])}))["user_id"]}).to_list(None)
    assert any("leave approved" in row["message"].lower() for row in inbox)
    from app.features.employee.hr_notifications import retry_delivery
    count=await mock_db.notifications.count_documents({})
    await retry_delivery(mock_db)
    assert await mock_db.notifications.count_documents({})==count


async def test_leave_cancel_and_reject_release_reserved_days_no_invented_entitlement(client,mock_db,owner_headers,master_data):
    employee,headers=await identity(client,owner_headers,master_data)
    policy=await leave_type(client,owner_headers)
    payload={"leave_type_id":policy["id"],"start_date":"2026-12-01","end_date":"2026-12-02","reason":"Personal request"}
    created=await client.post(BASE+"me/leaves",headers=headers,json=payload)
    request=created.json()["data"]
    assert (await client.get(BASE+"me/leaves?year=2026",headers=headers)).json()["data"]["balances"][0]["available_days"] is None
    assert (await client.post(BASE+"me/leaves/"+request["id"]+"/cancel",headers=headers)).status_code==200
    created=await client.post(BASE+"me/leaves",headers=headers,json=payload)
    assert created.status_code==200
    url=BASE+employee["id"]+"/leaves/"+created.json()["data"]["id"]+"/review"
    assert (await client.post(url,headers=owner_headers,json={"decision":"rejected"})).status_code==422
    assert (await client.post(url,headers=owner_headers,json={"decision":"rejected","reason":"Required coverage"})).status_code==200
    assert (await client.post(BASE+"me/leaves",headers=headers,json=payload)).status_code==200


async def test_attendance_reuses_refresh_families_and_flags_unobserved_out(client,mock_db,owner_headers,master_data):
    from app.utils.datetime import to_ist,utc_now
    from app.features.auth.session_lifecycle import expire_sessions
    employee,headers=await identity(client,owner_headers,master_data)
    raw=await mock_db.employees.find_one({"_id":ObjectId(employee["id"])})
    first=await mock_db.sessions.find_one({"user_id":raw["user_id"]})
    now=utc_now()
    await mock_db.sessions.update_one({"_id":first["_id"]},{"$set":{"login_at":now-timedelta(hours=1),"last_activity_at":now-timedelta(minutes=20)}})
    await expire_sessions(mock_db)
    login=(await client.post("/api/v1/auth/login",json={"mobile":employee["mobile"],"password":"InitialPass1!"})).json()["data"]
    refresh=await client.post("/api/v1/auth/refresh",json={"refresh_token":login["refresh_token"]})
    assert refresh.status_code==200
    assert (await client.post("/api/v1/auth/logout",headers={"Authorization":"Bearer "+login["access_token"]},json={"refresh_token":refresh.json()["data"]["refresh_token"]})).status_code==200
    response=await client.get("/api/v1/employees/hr/reports/attendance",headers=owner_headers,params={"month":to_ist(now).strftime("%Y-%m"),"employee":employee["id"]})
    assert response.status_code==200,response.text
    rows=response.json()["data"]["items"]
    events=[event for row in rows for event in row["events"]]
    assert len({event["id"] for event in events})==len(events)
    assert sum(event["type"]=="IN" for event in events)==2
    assert sum(event["type"]=="OUT" for event in events)==1
    assert any(row["needs_reconciliation"] for row in rows)
    timed_out=next(session for row in rows for session in row["sessions"] if session["end_reason"]=="inactivity_timeout")
    assert timed_out["observed_logout_at"] is None and timed_out["needs_reconciliation"]
    assert (await client.get("/api/v1/daily-operations/sessions",headers=owner_headers,params={"month":to_ist(now).strftime("%Y-%m")})).status_code==200


async def test_report_scope_and_export_permission(client,owner_headers,master_data):
    _,headers=await identity(client,owner_headers,master_data)
    assert (await client.get("/api/v1/employees/hr/reports/directory",headers=headers)).status_code==403
    assert (await client.get("/api/v1/employees/hr/reports/leaves/export",headers=headers)).status_code==403
    exported=await client.get("/api/v1/employees/hr/reports/directory/export",headers=owner_headers)
    assert exported.status_code==200 and "employee_name" in exported.text
