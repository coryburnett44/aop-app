import os, requests, json
BASE=(os.environ.get('REACT_APP_BACKEND_URL') or 'https://club-express-lite.preview.emergentagent.com').rstrip()
API=BASE+'/api'
r=requests.post(API+'/auth/login',json={'email':'admin@clubhaven.app','password':'Admin123!'},timeout=15); r.raise_for_status()
h={'Authorization':'Bearer '+r.json()['access_token']}
files={'file':('qa-attachment.txt',b'QA attachment body','text/plain')}
u=requests.post(API+'/email/upload-attachment',headers=h,files=files,timeout=30)
print('upload',u.status_code,u.text[:500]); u.raise_for_status()
aid=u.json()['id']
payload={'subject':'QA live attachment blast iteration 104','body_html':'<p>Testing attached file.</p>','segment':'custom','custom_user_ids':[],'external_emails':['ignored-by-test-only@example.com'],'test_only':True,'attachment_ids':[aid]}
b=requests.post(API+'/email/blast',headers=h,json=payload,timeout=40)
print('blast',b.status_code,b.text[:500]); b.raise_for_status()
blasts=requests.get(API+'/email/blasts',headers=h,timeout=15)
print('history',blasts.status_code)
if blasts.ok:
    rows=blasts.json()
    hit=next((x for x in rows if x.get('subject')=='QA live attachment blast iteration 104'),None)
    print('history hit',json.dumps(hit,indent=2)[:1000] if hit else 'none')
