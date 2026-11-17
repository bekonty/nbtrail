"""End-to-end smoke test: drive a real JupyterLab and let nbtrail record it."""
import asyncio

from playwright.async_api import async_playwright

import sys
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8899/lab/tree/hw/demo.ipynb?token=tok"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-proxy-server"])
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        logs = []
        page.on("console", lambda m: logs.append(m.text))
        await page.goto(URL)
        editor = page.locator(".jp-Notebook .jp-Cell .cm-content").first
        await editor.wait_for(timeout=60000)
        await page.wait_for_timeout(3000)
        dlg = page.locator(".jp-Dialog .jp-mod-accept")
        if await dlg.count():
            print("dialog:", (await page.locator(".jp-Dialog-header").inner_text()).strip())
            await dlg.first.click()
            await page.wait_for_timeout(3000)

        await editor.click()
        await page.keyboard.type("print(x)")
        await page.keyboard.press("Shift+Enter")  # NameError, and a new cell appears
        await page.wait_for_timeout(2500)

        await editor.click()
        await page.keyboard.press("Control+Home")
        await page.keyboard.type("x = 1\n")
        await page.keyboard.press("Shift+Enter")  # now it works
        await page.wait_for_timeout(2500)

        # Simulate pasting a chunk of code into the first cell.
        await editor.click()
        await page.keyboard.press("Control+End")
        await page.evaluate(
            """() => {
                const dt = new DataTransfer();
                dt.setData('text/plain', '\\n# pasted: ' + 'z'.repeat(40));
                const ev = new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true});
                document.querySelector('.jp-Notebook .jp-Cell .cm-content').dispatchEvent(ev);
            }"""
        )
        await page.wait_for_timeout(4000)  # let the recorder flush
        await page.screenshot(path="smoke.png")
        print("\n".join(l for l in logs if "nbtrail" in l))
        await browser.close()


asyncio.run(main())
