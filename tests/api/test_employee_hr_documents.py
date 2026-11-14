import io
from types import SimpleNamespace

import fitz
import pytest
from test_employee_hr import BASE, PROFILE, identity


@pytest.fixture
def private_store(monkeypatch):
    from app.features.employee import hr_documents as documents
    objects={}
    class S3:
        def head_object(self,*,Bucket,Key):return {"ContentLength":len(objects[Key])}
        def get_object(self,*,Bucket,Key):return {"Body":io.BytesIO(objects[Key])}
        def put_object(self,*,Bucket,Key,Body,ContentType):objects[Key]=Body
    monkeypatch.setattr(documents,"get_s3_client",lambda:S3())
    monkeypatch.setattr(documents,"get_storage_config",lambda:SimpleNamespace(bucket_name="private-test-bucket"))
    monkeypatch.setattr(documents,"generate_presigned_upload_url",lambda key,**kwargs:"https://storage.invalid/put/"+key)
    monkeypatch.setattr(documents,"generate_presigned_download_url",lambda key,**kwargs:"https://storage.invalid/get/"+key)
    return objects


def pdf(password=None):
    with fitz.open() as document:
        document.new_page()
        return document.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256,owner_pw="Owner-test-secret",user_pw=password) if password else document.tobytes()


async def upload(client,headers,db,objects,category="aadhaar",password=None,version=0):
    data=pdf(password)
    intent=await client.post(BASE+"me/documents/upload",headers=headers,json={"category":category,"file_name":"private.pdf","content_type":"application/pdf","size":len(data)})
    assert intent.status_code==200,intent.text
    ticket=intent.json()["data"]["ticket"]
    row=await db.employee_upload_intents.find_one({"_id":ticket})
    objects[row["key"]]=data
    result=await client.post(BASE+"me/documents/confirm",headers=headers,json={"category":category,"version":version,"tickets":[ticket],"pdf_password":password})
    return result,row


async def test_private_pdf_password_not_retained_rejection_and_version_history(client,mock_db,owner_headers,master_data,private_store):
    employee,headers=await identity(client,owner_headers,master_data)
    await client.put(BASE+"me/profile",headers=headers,json=PROFILE|{"version":0})
    response,intent=await upload(client,headers,mock_db,private_store,password="Employee-private-pass")
    assert response.status_code==200,response.text
    assert response.json()["data"]["aadhaar"]["status"]=="pending_verification"
    assert "s3_key" not in response.text and "Employee-private-pass" not in response.text
    all_metadata=str(await mock_db.employee_upload_intents.find().to_list(None))+str(await mock_db.employee_documents.find().to_list(None))+str(await mock_db.audit_logs.find().to_list(None))
    assert "Employee-private-pass" not in all_metadata
    final=next(key for key in private_store if key.startswith("employee-documents/"))
    with fitz.open(stream=private_store[final],filetype="pdf") as decrypted:assert not decrypted.needs_pass
    private_store[intent["key"]]=b"Changed staging object" # Cannot modify the final version.
    with fitz.open(stream=private_store[final],filetype="pdf") as decrypted:assert decrypted.page_count==1
    review=BASE+employee["id"]+"/documents/aadhaar/review"
    assert (await client.post(review,headers=headers,json={"version":1,"decision":"approved"})).status_code==403
    assert (await client.post(review,headers=owner_headers,json={"version":1,"decision":"rejected","reason":"PDF needs correction"})).status_code==200
    replacement,_=await upload(client,headers,mock_db,private_store,version=1)
    assert replacement.status_code==200,replacement.text
    history=replacement.json()["data"]["aadhaar"]["versions"]
    assert history[0]["version"]==1 and history[0]["history"][0]["reason"]=="PDF needs correction"
    old=await client.get(BASE+employee["id"]+"/documents/aadhaar/1/file/download",headers=owner_headers)
    assert old.status_code==200 and "/get/employee-documents/" in old.json()["data"]["url"]


async def test_bad_file_shape_size_and_cross_employee_access(client,mock_db,owner_headers,master_data,employee_headers,private_store):
    employee,headers=await identity(client,owner_headers,master_data)
    url=BASE+"me/documents/upload"
    assert (await client.post(url,headers=headers,json={"category":"pan","file_name":"bad.exe","content_type":"application/octet-stream","size":100})).status_code==422
    assert (await client.post(url,headers=headers,json={"category":"pan","file_name":"too-big.pdf","content_type":"application/pdf","size":11*1024*1024})).status_code==422
    assert (await client.get(BASE+employee["id"]+"/documents",headers=employee_headers)).status_code==403
    assert (await client.post(url,headers=headers,json={"category":"aadhaar","part":"front","file_name":"front.pdf","content_type":"application/pdf","size":100})).status_code==422


async def test_legacy_uploads_use_private_intents_and_cannot_overwrite_versions(client,mock_db,owner_headers,master_data,private_store):
    employee,_=await identity(client,owner_headers,master_data)
    url=f"/api/v1/employees/{employee['id']}/documents"
    data={"document_type":"pan","file_name":"pan.pdf","content_type":"application/pdf"}
    first=(await client.post(url+"/upload-url",headers=owner_headers,json=data)).json()["data"]
    second=(await client.post(url+"/upload-url",headers=owner_headers,json=data)).json()["data"]
    assert first["s3_key"]!=second["s3_key"]
    private_store[first["s3_key"]]=pdf()
    confirmed=await client.post(url,headers=owner_headers,json=data|{"s3_key":first["s3_key"]})
    assert confirmed.status_code==200,confirmed.text
    assert confirmed.json()["data"]["s3_key"]!=first["s3_key"]
    final=confirmed.json()["data"]["s3_key"]
    assert (await client.post(url,headers=owner_headers,json=data|{"s3_key":final})).status_code==422
    assert (await client.post(url,headers=owner_headers,json=data|{"s3_key":first["s3_key"]})).status_code==422
