import asyncio

from bson import ObjectId
from test_employee_hr import BASE, PROFILE, identity


async def verified(client,db,owner_headers,master_data):
    employee,headers=await identity(client,owner_headers,master_data)
    assert (await client.put(BASE+"me/profile",headers=headers,json=PROFILE|{"version":0})).status_code==200
    assert (await client.post(BASE+"me/profile/submit",headers=headers,json={"version":1})).status_code==200
    from app.features.employee.hr_documents import REQUIRED
    await db.employees.update_one({"_id":ObjectId(employee["id"])},{"$set":{"hr_documents":{name:{"status":"approved"} for name in REQUIRED}}})
    assert (await client.post(BASE+employee["id"]+"/profile/review",headers=owner_headers,json={"version":2,"decision":"approve"})).status_code==200
    snapshot=(await client.get(BASE+"me/profile",headers=headers)).json()["data"]
    return employee,headers,snapshot


async def test_employee_edit_request_approval_rejection_and_no_delete(client,mock_db,owner_headers,master_data):
    employee,headers,snapshot=await verified(client,mock_db,owner_headers,master_data)
    proposal=snapshot["onboarding"]["profile"]|{"first_name":"Proposed","version":snapshot["employee_version"]}
    created=await client.post(BASE+"me/edit-requests",headers=headers,json=proposal)
    assert created.status_code==200,created.text
    request=created.json()["data"]
    assert request["previous_values"]["first_name"]=="Updated"
    raw=await mock_db.employees.find_one({"_id":ObjectId(employee["id"])})
    assert raw["first_name"]=="Updated"
    url=BASE+employee["id"]+"/edit-requests/"+request["id"]+"/review"
    assert (await client.post(url,headers=headers,json={"decision":"approved"})).status_code==403
    assert (await client.post(url,headers=owner_headers,json={"decision":"rejected"})).status_code==422
    assert (await client.post(url,headers=owner_headers,json={"decision":"rejected","reason":"Incorrect information"})).status_code==200
    assert (await mock_db.employees.find_one({"_id":ObjectId(employee["id"])}))["first_name"]=="Updated"
    created=await client.post(BASE+"me/edit-requests",headers=headers,json=proposal)
    assert created.status_code==200
    url=BASE+employee["id"]+"/edit-requests/"+created.json()["data"]["id"]+"/review"
    assert (await client.post(url,headers=owner_headers,json={"decision":"approved"})).status_code==200
    assert (await mock_db.employees.find_one({"_id":ObjectId(employee["id"])}))["first_name"]=="Proposed"
    assert (await client.post(url,headers=owner_headers,json={"decision":"approved"})).status_code==409
    assert (await client.delete("/api/v1/employees/"+employee["id"],headers=headers)).status_code==405


async def test_concurrent_edit_requests_and_stale_approval(client,mock_db,owner_headers,master_data):
    employee,headers,snapshot=await verified(client,mock_db,owner_headers,master_data)
    proposal=snapshot["onboarding"]["profile"]|{"first_name":"Proposed","version":snapshot["employee_version"]}
    results=await asyncio.gather(*(client.post(BASE+"me/edit-requests",headers=headers,json=proposal) for _ in range(2)))
    assert sorted(result.status_code for result in results)==[200,409]
    request=next(result.json()["data"] for result in results if result.status_code==200)
    await mock_db.employees.update_one({"_id":ObjectId(employee["id"])},{"$set":{"first_name":"Owner changed"},"$inc":{"version":1}})
    assert (await client.post(BASE+employee["id"]+"/edit-requests/"+request["id"]+"/review",headers=owner_headers,json={"decision":"approved"})).status_code==409
    assert (await mock_db.employees.find_one({"_id":ObjectId(employee["id"])}))["first_name"]=="Owner changed"
