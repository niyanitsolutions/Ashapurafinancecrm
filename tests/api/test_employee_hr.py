from bson import ObjectId
from test_employee import _create_employee

BASE="/api/v1/employees/hr/"
PROFILE={"first_name":"Updated","last_name":"Employee","email":"jane.doe@example.com","emergency_contact":{"name":"Emergency","relationship":"Family","mobile":"9222222222"},"current_address":{"line1":"One street","city":"Pune","state":"Maharashtra","pincode":"411001"},"permanent_same_as_current":True,"fresher":True}


async def identity(client,owner_headers,master_data,mode="account_only"):
    employee=await _create_employee(client,owner_headers,master_data,onboarding_mode=mode)
    if mode=="account_only":
        login=await client.post("/api/v1/auth/login",json={"mobile":employee["mobile"],"password":"InitialPass1!"})
        assert login.status_code==200,login.text
        return employee,{"Authorization":"Bearer "+login.json()["data"]["access_token"]}
    return employee,None


async def test_account_only_profile_review_does_not_block_access(client,mock_db,owner_headers,master_data):
    employee,headers=await identity(client,owner_headers,master_data)
    saved=await client.put(BASE+"me/profile",headers=headers,json=PROFILE|{"version":0})
    assert saved.status_code==200,saved.text
    row=saved.json()["data"]
    assert row["onboarding"]["profile"]["permanent_address"]==PROFILE["current_address"]|{"line2":None,"country":"India"}
    assert row["current_profile"]["first_name"]=="Jane" # Draft is not official.
    assert (await client.post(BASE+"me/profile/submit",headers=headers,json={"version":1})).status_code==200
    assert (await client.get("/api/v1/auth/profile",headers=headers)).status_code==200
    assert (await client.post(BASE+employee["id"]+"/profile/review",headers=headers,json={"version":2,"decision":"approve"})).status_code==403
    assert (await client.post(BASE+employee["id"]+"/profile/review",headers=owner_headers,json={"version":2,"decision":"approve"})).status_code==422
    from app.features.employee.hr_documents import REQUIRED
    await mock_db.employees.update_one({"_id":ObjectId(employee["id"])},{"$set":{"hr_documents":{name:{"status":"approved"} for name in REQUIRED}}})
    approved=await client.post(BASE+employee["id"]+"/profile/review",headers=owner_headers,json={"version":2,"decision":"approve"})
    assert approved.status_code==200,approved.text
    assert approved.json()["data"]["onboarding"]["status"]=="verified"
    assert approved.json()["data"]["current_profile"]["first_name"]=="Updated"
    direct=await client.patch("/api/v1/employees/me",headers=headers,json={"first_name":"Unauthorized overwrite"})
    assert direct.status_code==409


async def test_owner_complete_stays_inactive_until_verified_and_mode_survives_save(client,owner_headers,master_data):
    employee,_=await identity(client,owner_headers,master_data,"owner_complete")
    assert employee["status"]=="inactive"
    assert (await client.post("/api/v1/auth/login",json={"mobile":employee["mobile"],"password":"InitialPass1!"})).status_code==401
    saved=await client.put(BASE+employee["id"]+"/profile",headers=owner_headers,json=PROFILE|{"version":0})
    assert saved.status_code==200,saved.text
    assert saved.json()["data"]["onboarding"]["mode"]=="owner_complete"


async def test_fresher_rules_stale_updates_and_cross_employee_denial(client,owner_headers,master_data,employee_headers):
    employee,headers=await identity(client,owner_headers,master_data)
    assert (await client.get(BASE+employee["id"]+"/profile",headers=employee_headers)).status_code==403
    bad=PROFILE|{"version":0,"fresher":False,"previous_company":"","experience_years":0,"experience_months":12}
    assert (await client.put(BASE+"me/profile",headers=headers,json=bad)).status_code==422
    assert (await client.put(BASE+"me/profile",headers=headers,json=PROFILE|{"version":0})).status_code==200
    assert (await client.put(BASE+"me/profile",headers=headers,json=PROFILE|{"version":0})).status_code==409


async def test_initial_activation_guard_and_verified_marker_survive_revisions(client,mock_db,owner_headers,master_data):
    employee,_=await identity(client,owner_headers,master_data,"owner_complete")
    activate="/api/v1/employees/"+employee["id"]+"/activate"
    assert (await client.patch(activate,headers=owner_headers)).status_code==422
    raw=await mock_db.employees.find_one({"_id":ObjectId(employee["id"])})
    from app.features.employee.hr_documents import REQUIRED
    org={key:raw[key] for key in ("department_id","designation_id","branch_id")}
    await mock_db.employees.update_one({"_id":raw["_id"]},{"$set":{
        "onboarding.status":"verified","onboarding.ever_verified":True,
        "hr_documents":{name:{"status":"approved"} for name in REQUIRED},
    }})
    assert (await client.patch(activate,headers=owner_headers)).status_code==422
    ack=await client.post(BASE+employee["id"]+"/access-review",headers=owner_headers,json={"version":0,"organization":org,"role_ids":[]})
    assert ack.status_code==200,ack.text
    activated=await client.patch(activate,headers=owner_headers)
    assert activated.status_code==200,activated.text
    await mock_db.employees.update_one({"_id":raw["_id"]},{"$set":{"onboarding.status":"changes_required"}})
    saved=await client.put(BASE+employee["id"]+"/profile",headers=owner_headers,json=PROFILE|{"version":1})
    assert saved.status_code==200,saved.text
    onboarding=(await mock_db.employees.find_one({"_id":raw["_id"]}))["onboarding"]
    assert onboarding["ever_verified"] is True and onboarding["account_created_at"]
    assert onboarding["access_review"]["organization"]==org


async def test_committed_hr_event_outbox_recovers_notifications_once(client,mock_db,owner_headers,master_data):
    employee,headers=await identity(client,owner_headers,master_data)
    from app.features.employee.hr_notifications import queue_event,retry_delivery
    mutation=queue_event({"$set":{"onboarding.status":"pending_verification"}},"employee_onboarding_submitted",employee["id"],{"employee_id":employee["id"]})
    await mock_db.employees.update_one({"_id":ObjectId(employee["id"])},mutation)
    before=await mock_db.notifications.count_documents({})
    await retry_delivery(mock_db)
    after=await mock_db.notifications.count_documents({})
    assert after>before
    await retry_delivery(mock_db)
    assert await mock_db.notifications.count_documents({})==after
    raw=await mock_db.employees.find_one({"_id":ObjectId(employee["id"])})
    assert raw["hr_event_outbox"]==[]
