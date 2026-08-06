"""Playwright UI checklist for Iteration 159 photo download fix.

This file mirrors the script executed through the browser automation tool.
"""

async def run(page, base_url="https://club-express-lite.preview.emergentagent.com"):
    try:
        print("Step 1: login as admin")
        await page.set_viewport_size({"width": 1920, "height": 1080})
        await page.goto(f"{base_url}/login", wait_until="networkidle")
        await page.get_by_test_id("login-email-input").fill("admin@clubhaven.app")
        await page.get_by_test_id("login-password-input").fill("Admin123!")
        await page.get_by_test_id("login-submit-btn").click()
        await page.wait_for_timeout(1200)
        if "/login" in page.url:
            raise AssertionError(f"Still on login after submit: {page.url}")
        print("PASS: admin login completed")

        print("Step 2: open Photos and 5-Year Anniversary album")
        await page.goto(f"{base_url}/photos", wait_until="networkidle")
        await page.wait_for_selector('[data-testid="album-grid"]', timeout=20000)
        await page.locator('[data-testid="album-card-5-Year Anniversary"]').click()
        await page.wait_for_selector('[data-testid="photo-grid"]', timeout=20000)
        first_photo = page.locator('[data-testid^="photo-open-"]').first
        await first_photo.click()
        print("PASS: opened album and first photo")

        print("Step 3: verify PhotoSwipe uses mid-size preview URL")
        await page.wait_for_selector('.pswp__img', timeout=20000)
        await page.wait_for_timeout(1000)
        srcs = await page.evaluate("""() => Array.from(document.querySelectorAll('.pswp__img')).map(img => img.currentSrc || img.src || '')""")
        print(f"PhotoSwipe image srcs: {srcs}")
        if not any('/photos/preview/' in src for src in srcs):
            raise AssertionError(f"No PhotoSwipe image used /photos/preview/: {srcs}")
        print("PASS: viewer is using /photos/preview/ WebP preview")

        print("Step 4: click custom PhotoSwipe Download toolbar button and wait for browser download")
        download_button = page.locator('button[title="Download original"]').first
        await download_button.wait_for(state="visible", timeout=10000)
        async with page.expect_download(timeout=60000) as download_info:
            await download_button.click(force=True)
        download = await download_info.value
        path = await download.path()
        suggested = download.suggested_filename
        if not path:
            raise AssertionError("Download event fired but no downloaded temp path was available")
        print(f"PASS: browser download triggered; suggested filename={suggested}, path={path}")

        print("Step 5: refresh after download and verify session remains active")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        await page.reload(wait_until="networkidle")
        await page.wait_for_timeout(1200)
        if "/login" in page.url:
            raise AssertionError(f"Refresh after download redirected to login: {page.url}")
        await page.wait_for_selector('[data-testid="photo-grid"], [data-testid="album-grid"]', timeout=20000)
        print(f"PASS: refresh after download did not kick user out; current URL={page.url}")

        print("Step 6: UI selected-photo ZIP flow with four photos")
        await page.goto(f"{base_url}/photos", wait_until="networkidle")
        await page.wait_for_selector('[data-testid="album-grid"]', timeout=20000)
        await page.locator('[data-testid="album-card-Bug Fix Test"]').click()
        await page.wait_for_selector('[data-testid="photo-grid"]', timeout=20000)
        await page.get_by_test_id("select-photos-btn").click()
        await page.wait_for_selector('[data-testid^="photo-select-"]', timeout=10000)
        select_buttons = page.locator('[data-testid^="photo-select-"]')
        count = await select_buttons.count()
        if count < 4:
            raise AssertionError(f"Bug Fix Test album has fewer than 4 selectable photos in UI: {count}")
        for i in range(4):
            await select_buttons.nth(i).click()
        async with page.expect_download(timeout=60000) as zip_download_info:
            await page.get_by_test_id("download-selected-btn").click()
        zip_download = await zip_download_info.value
        zip_path = await zip_download.path()
        if not zip_path:
            raise AssertionError("Selected ZIP download event fired but no temp file path was available")
        print(f"PASS: selected-photo ZIP download triggered; filename={zip_download.suggested_filename}")

        await page.reload(wait_until="networkidle")
        await page.wait_for_timeout(1200)
        if "/login" in page.url:
            raise AssertionError(f"Refresh after selected ZIP redirected to login: {page.url}")
        print(f"PASS: refresh after selected ZIP did not kick user out; current URL={page.url}")

        error_text = await page.evaluate("""() => {
            const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
            return errorElements.map(el => el.textContent).join(", ");
        }""")
        if error_text:
            print(f"Found error message: {error_text}")
        else:
            print("No error messages found on the page")
        print("UI TEST PASSED")
    except Exception as e:
        print(f"UI TEST FAILED: {e}")
        raise