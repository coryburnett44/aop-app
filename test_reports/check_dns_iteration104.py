import os, json, requests
API=(os.environ.get('REACT_APP_BACKEND_URL') or 'https://club-express-lite.preview.emergentagent.com').rstrip()+'/api'
r=requests.post(API+'/auth/login',json={'email':'admin@clubhaven.app','password':'Admin123!'},timeout=15); r.raise_for_status()
h={'Authorization':'Bearer '+r.json()['access_token']}
d=requests.get(API+'/email/deliverability/check-dns',headers=h,timeout=20)
print(d.status_code)
print(json.dumps(d.json(), indent=2)[:5000])
