"""Focused Playwright UI check for Iter 160 photo page rendering.

Run by the testing agent through mcp_browser_automation. Uses the QA album
created by iter160_downscale_api_test.py and verifies the album grid, photo
grid, and PhotoSwipe viewer still render after the new photo metadata fields.
"""

# This file documents the exact script submitted to mcp_browser_automation.
# It is intentionally not standalone because the MCP tool injects `page` into
# an async Playwright context.

SCRIPT = r'''
try:
    await page.set_viewport_size({"width": 1920, "height": 1080})
    base = "https://club-express-lite.preview.emergentagent.com"
    album = "Iter160 QA WebP 20260806010337"
    first_photo_id = "4921bb68-c309-4734-869b-9bfd8b2a308d"

    print("Opening login page")
    await page.goto(f"{base}/login", wait_until="domcontentloaded")
    await page.get_by_test_id("login-email-input").fill("admin@clubhaven.app")
    await page.get_by_test_id("login-password-input").fill("Admin123!")
    await page.get_by_test_id("login-submit-btn").click()
    await page.wait_for_timeout(1500)
    print(f"After login URL: {page.url}")

    print("Opening Photos page")
    await page.goto(f"{base}/photos", wait_until="domcontentloaded")
    await page.wait_for_selector('[data-testid="album-grid"]', timeout=20000)
    await page.get_by_test_id(f"album-card-{album}").scroll_into_view_if_needed()
    visible = await page.get_by_test_id(f"album-card-{album}").is_visible()
    print(f"QA album visible: {visible}")
    if not visible:
        raise Exception("QA album card was not visible")

    await page.get_by_test_id(f"album-card-{album}").click()
    await page.wait_for_selector('[data-testid="photo-grid"]', timeout=20000)
    open_button = page.get_by_test_id(f"photo-open-{first_photo_id}")
    await open_button.wait_for(state="visible", timeout=20000)
    await open_button.scroll_into_view_if_needed()
    await page.wait_for_function("""(pid) => {
        const img = document.querySelector(`[data-testid='photo-open-${pid}'] img`);
        return img && img.complete && img.naturalWidth > 0;
    }""", arg=first_photo_id, timeout=30000)
    thumb_info = await page.evaluate("""() => {
        const img = document.querySelector(`[data-testid='photo-open-4921bb68-c309-4734-869b-9bfd8b2a308d'] img`);
        return img ? {src: img.currentSrc || img.src, complete: img.complete, naturalWidth: img.naturalWidth, naturalHeight: img.naturalHeight} : null;
    }""")
    print(f"Thumbnail loaded: {thumb_info}")

    await open_button.click()
    await page.wait_for_selector('.pswp', state="visible", timeout=20000)
    await page.wait_for_timeout(1000)
    pswp_img_count = await page.locator('.pswp__img').count()
    pswp_visible = await page.locator('.pswp').first.is_visible()
    current_srcs = await page.evaluate("""() => Array.from(document.querySelectorAll('.pswp__img')).map(img => ({src: img.currentSrc || img.src, complete: img.complete, naturalWidth: img.naturalWidth}))""")
    print(f"PhotoSwipe visible: {pswp_visible}; image elements: {pswp_img_count}; srcs={current_srcs}")
    if not pswp_visible or pswp_img_count == 0:
        raise Exception("PhotoSwipe viewer did not render an image")

    # Get error messages using specific selectors
    error_text = await page.evaluate("""() => {
    const errorElements = Array.from(document.querySelectorAll('.error, [class*="error"], [id*="error"]'));
    return errorElements.map(el => el.textContent).join(", ");
    }""")
    if error_text:
        print(f"Found error message: {error_text}")
        raise Exception(f"Unexpected visible error text: {error_text}")
    else:
        print("No error messages found on the page")

    await page.locator('.pswp__button--close').click(force=True)
    await page.wait_for_timeout(300)
    print("SUCCESS: /photos grid and PhotoSwipe viewer render with Iter160 WebP metadata")
except Exception as e:
    print(f"FAILURE: {e}")
    await page.screenshot(path="/app/test_reports/iter160_photos_ui_failure.jpg", quality=40, full_page=False)
    raise
'''