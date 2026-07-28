import os, requests, pathlib
API=(os.environ.get('REACT_APP_BACKEND_URL') or 'https://club-express-lite.preview.emergentagent.com').rstrip()+'/api'
login=requests.post(API+'/auth/login',json={'email':'admin@clubhaven.app','password':'Admin123!'},timeout=15)
login.raise_for_status()
h={'Authorization':'Bearer '+login.json()['access_token']}
# 1x1 transparent png
png=bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6360000002000100ffff03000006000557bfab540000000049454e44ae426082')
files={'file':('qa.png',png,'image/png')}
r=requests.post(API+'/email/upload-image',headers=h,files=files,timeout=30)
print('upload status',r.status_code,r.text[:500])
r.raise_for_status()
url=r.json()['url']
print('uploaded url',url)
# public image endpoint should load without auth
img=requests.get(API.rsplit('/api',1)[0]+url,timeout=30)
print('public current image fetch',img.status_code,img.headers.get('content-type'),len(img.content))
# preview with current image URL should keep /email/image/email and absolutize
payload={'subject':'Image current URL preview','body_html':f'<p>Image below</p><img src="{url}" />','segment':'custom','custom_user_ids':[],'external_emails':['preview@example.com']}
p=requests.post(API+'/email/preview',headers=h,json=payload,timeout=20)
print('preview current status',p.status_code)
html=p.json().get('html','') if p.ok else p.text
print('contains /api/email/image/email/', '/api/email/image/email/' in html)
# preview with legacy /api/files/email/... URL equivalent
legacy=url.replace('/api/email/image/','/api/files/')
print('legacy url',legacy)
p2=requests.post(API+'/email/preview',headers=h,json={**payload,'body_html':f'<p>Legacy</p><img src="{legacy}" />'},timeout=20)
print('preview legacy status',p2.status_code)
html2=p2.json().get('html','') if p2.ok else p2.text
print('legacy html contains /api/email/image/email/', '/api/email/image/email/' in html2)
print('legacy html contains /api/email/image/', '/api/email/image/' in html2)
import re
srcs=re.findall(r'src="([^"]+)"',html2)
print('legacy srcs',srcs[:5])
if srcs:
    fetch=requests.get(srcs[0],timeout=30)
    print('legacy rewritten src public fetch',fetch.status_code,fetch.text[:120] if fetch.status_code!=200 else len(fetch.content))
