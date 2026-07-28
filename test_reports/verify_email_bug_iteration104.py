"""Focused verification for email deliverability/attachments/wrapper regression.

Runs offline/unit checks plus live API checks where safe. Does not modify product code.
"""
import base64
import json
import os
import re
import sys
from pathlib import Path

import requests

ROOT = Path('/app')
BACKEND = ROOT / 'backend'
FRONTEND = ROOT / 'frontend'
sys.path.insert(0, str(BACKEND))

API_BASE = os.environ.get('REACT_APP_BACKEND_URL') or 'https://club-express-lite.preview.emergentagent.com'
API = API_BASE.rstrip('/') + '/api'
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@clubhaven.app')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Admin123!')


def check(condition, message, failures):
    if not condition:
        failures.append(message)
    status = 'PASS' if condition else 'FAIL'
    print(f'{status}: {message}')


def login():
    r = requests.post(f'{API}/auth/login', json={'email': ADMIN_EMAIL, 'password': ADMIN_PASSWORD}, timeout=15)
    r.raise_for_status()
    token = r.json().get('access_token')
    if not token:
        raise RuntimeError('No access_token returned from login')
    return {'Authorization': f'Bearer {token}'}


def main():
    failures = []

    # 1) Source/UI copy checks: deliverability panel and test-send toast/result copy.
    admin_src = (FRONTEND / 'src/pages/Admin.jsx').read_text()
    m = re.search(r'function EmailDeliverability\(\).*?\n}\n\nfunction EmailTestSend', admin_src, re.S)
    deliverability_src = m.group(0) if m else ''
    check(bool(deliverability_src), 'Located EmailDeliverability component source', failures)
    check('Resend' not in deliverability_src, 'Deliverability panel source contains no user-facing Resend string', failures)
    check('Remove any conflicting records from previous email providers to avoid authentication failures.' in deliverability_src,
          'Deliverability panel has provider-agnostic previous-provider wording', failures)
    m2 = re.search(r'function EmailTestSend\(\).*?\n}\n\nfunction ComposeBlast', admin_src, re.S)
    test_send_src = m2.group(0) if m2 else ''
    check(bool(test_send_src), 'Located EmailTestSend component source', failures)
    check('Resend' not in test_send_src, 'Test-send toast/result source contains no Resend string', failures)
    check('Brevo accepted the test' in test_send_src and 'Test email accepted by Brevo' in test_send_src,
          'Test-send UI uses Brevo success wording', failures)

    # 2) Brevo translation: singular attachment key with base64 content.
    from brevo_sdk import _translate
    translated = _translate({
        'from': 'Alpha Omega Phi <info@aop-app.org>',
        'to': ['member@example.com'],
        'subject': 'Attachment test',
        'html': '<p>Hello</p>',
        'attachments': [{'filename': 'picture.png', 'content': b'PNGDATA', 'content_type': 'image/png'}],
    })
    check('attachment' in translated, 'Brevo translated payload includes singular attachment key', failures)
    check('attachments' not in translated, 'Brevo translated payload does not include plural attachments key', failures)
    check(translated.get('attachment', [{}])[0].get('name') == 'picture.png', 'Attachment filename translated to Brevo name field', failures)
    check(base64.b64decode(translated.get('attachment', [{}])[0].get('content', '')) == b'PNGDATA', 'Raw attachment bytes are base64 encoded', failures)

    # 3) Wrapper/preheader/bulk params by monkeypatching the email sender.
    import server
    wrapped = server._wrap_email_document('<p>Hello <strong>member</strong></p>', subject='QA <Subject>', preheader='Preview text')
    checks = [
        (wrapped.startswith('<!DOCTYPE'), 'Wrapper starts with doctype'),
        ('<html xmlns="http://www.w3.org/1999/xhtml" lang="en"' in wrapped, 'Wrapper includes full html tag/lang'),
        ('<meta http-equiv="Content-Type" content="text/html; charset=UTF-8"' in wrapped, 'Wrapper includes charset meta'),
        ('<!--[if mso]>' in wrapped, 'Wrapper includes MSO conditional comment'),
        ('role="presentation"' in wrapped and '<table' in wrapped, 'Wrapper includes table presentation container'),
        ('Preview text' in wrapped and 'display:none' in wrapped, 'Wrapper includes hidden preheader'),
    ]
    for ok, msg in checks:
        check(ok, msg, failures)

    captured = {}
    old_send = server.resend_sdk.Emails.send
    old_key = server.RESEND_API_KEY
    try:
        server.RESEND_API_KEY = server.RESEND_API_KEY or 'test-key'
        def fake_send(params):
            captured.update(params)
            return {'id': 'fake-id'}
        server.resend_sdk.Emails.send = fake_send
        import asyncio
        asyncio.run(server.send_bulk_email(
            to_email='member@example.com',
            subject='Bulk wrapper test',
            html_body='<p>Body with <img src="/api/files/email/u/f/p.png" /></p>',
            recipient_id='recipient-1',
            attachments=[{'filename': 'doc.pdf', 'content': base64.b64encode(b'pdf').decode('ascii'), 'content_type': 'application/pdf'}],
        ))
    finally:
        server.resend_sdk.Emails.send = old_send
        server.RESEND_API_KEY = old_key
    check(captured.get('attachments'), 'send_bulk_email forwards attachments to shim', failures)
    check(captured.get('html', '').startswith('<!DOCTYPE'), 'send_bulk_email sends wrapped full HTML document', failures)
    check('/api/email/image/email/' in captured.get('html', ''), 'send_bulk_email rewrites embedded image URLs to public email-image endpoint', failures)
    check(captured.get('text'), 'send_bulk_email sends plain-text fallback', failures)
    check('List-Unsubscribe' in captured.get('headers', {}), 'send_bulk_email includes List-Unsubscribe header', failures)

    # 4) Live API regression checks.
    headers = login()
    deliverability = requests.get(f'{API}/email/deliverability', headers=headers, timeout=15)
    check(deliverability.status_code == 200, '/api/email/deliverability succeeds', failures)
    if deliverability.ok:
        dj = deliverability.json()
        text = json.dumps(dj)
        check(dj.get('provider_label') == 'Brevo', 'Deliverability API reports Brevo provider label', failures)
        check('spf.brevo.com' in text, 'Deliverability API contains Brevo SPF checklist', failures)
        check('previous email providers' not in text or 'Resend' not in text, 'Deliverability API does not force Resend in Brevo checklist', failures)

    preview_payload = {
        'subject': 'QA wrapped preview',
        'body_html': '<p>Hello {{first_name}}</p><img src="/api/files/email/u/f/p.png" />',
        'segment': 'custom',
        'custom_user_ids': [],
        'external_emails': ['preview-recipient@example.com'],
        'test_only': False,
    }
    preview = requests.post(f'{API}/email/preview', headers=headers, json=preview_payload, timeout=20)
    check(preview.status_code == 200, '/api/email/preview succeeds', failures)
    if preview.ok:
        pj = preview.json()
        html = pj.get('html', '')
        check(html.startswith('<!DOCTYPE'), 'Preview response returns wrapped HTML', failures)
        check('role="presentation"' in html and '<!--[if mso]>' in html, 'Preview wrapped HTML includes table and MSO structures', failures)
        check('/api/email/image/email/' in html, 'Preview rewrites embedded image URL for mailbox display', failures)

    test_send = requests.post(
        f'{API}/email/test-send', headers=headers,
        json={'to_email': 'delivery-check@example.com', 'subject': 'QA API test-send iteration 104', 'body_html': '<p>Wrapped API send</p>'}, timeout=25,
    )
    check(test_send.status_code == 200, '/api/email/test-send returns HTTP 200', failures)
    if test_send.ok:
        tj = test_send.json()
        check(tj.get('ok') is True, '/api/email/test-send accepted by provider', failures)
        check('Brevo' in tj.get('detail', ''), '/api/email/test-send response uses Brevo wording', failures)
        check('mailin.fr' in tj.get('message_id', ''), '/api/email/test-send message id is from Brevo relay', failures)

    blast_payload = {
        'subject': 'QA wrapped blast test',
        'body_html': '<p>Hello {{first_name}}, QA blast wrapper test.</p><img src="/api/files/email/u/f/p.png" />',
        'segment': 'custom',
        'custom_user_ids': [],
        'external_emails': ['blast-check@example.com'],
        'test_only': True,
        'attachment_ids': [],
    }
    blast = requests.post(f'{API}/email/blast', headers=headers, json=blast_payload, timeout=30)
    check(blast.status_code == 200, '/api/email/blast test_only succeeds', failures)
    if blast.ok:
        bj = blast.json()
        check(bj.get('sent', 0) >= 1 and bj.get('failed', 99) == 0, '/api/email/blast reports sent with zero failed in test_only mode', failures)

    if failures:
        print('\nFailures:')
        for f in failures:
            print('-', f)
        raise SystemExit(1)
    print('\nAll focused email bug checks passed.')


if __name__ == '__main__':
    main()
