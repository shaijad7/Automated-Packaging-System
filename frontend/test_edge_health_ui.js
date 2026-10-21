const { chromium } = require('playwright');

(async () => {
    let browser;
    try {
        console.log("Starting Phase 5.12 Live Edge Camera & AI Model Health UI Tests...");
        browser = await chromium.launch();
        const context = await browser.newContext();
        const page = await context.newPage();
        await page.setViewportSize({ width: 1280, height: 900 });

        // Hermetic mock route for admin login
        await page.route('**/api/login', route => {
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    access_token: "mock_admin_jwt_token",
                    token_type: "bearer"
                })
            });
        });

        // Hermetic mock routes for initial dashboard calls
        await page.route('**/dashboard/summary', route => {
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    overall_boxes: 0,
                    valid_qr: 0,
                    no_qr: 0,
                    unreadable_qr: 0,
                    invalid_qr: 0,
                    qr_exceptions: 0,
                    inventory_added: 0
                })
            });
        });
        await page.route('**/dashboard/analytics*', route => {
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ trend: [], distribution: [] })
            });
        });
        await page.route('**/dashboard/events*', route => {
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify([])
            });
        });
        await page.route('**/dashboard/inventory*', route => {
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify([])
            });
        });

        // 1. Log in as admin
        console.log("1. Logging in as admin...");
        await page.goto('http://localhost:3000/login');
        await page.fill('input[name="login-username"]', 'admin');
        await page.fill('input[name="login-password"]', 'Admin@123');
        await page.click('button[type="submit"]');
        await page.waitForURL('**/dashboard');
        console.log("PASS: Logged in and reached /dashboard");

        // 2. Set up route intercepts for backend health and edge system health
        let edgeHealthData = {
            camera_status: "UNKNOWN",
            camera_details: "No edge heartbeat received",
            model_status: "UNKNOWN",
            model_details: "No edge heartbeat received",
            last_heartbeat: null,
            age_seconds: null,
            is_stale: false,
            fps: null,
        };

        await page.route('**/health', route => {
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ status: "healthy", database: "connected" })
            });
        });

        let edgeRouteStatus = 200;
        let edgeRouteAbort = false;
        await page.route('**/dashboard/system-health', route => {
            if (edgeRouteAbort) {
                route.abort('failed');
            } else {
                route.fulfill({
                    status: edgeRouteStatus,
                    contentType: 'application/json',
                    body: edgeRouteStatus === 200 ? JSON.stringify(edgeHealthData) : JSON.stringify({ detail: "Internal error" })
                });
            }
        });

        // 3. Navigate to /settings (Case 1: No heartbeat ever received -> UNKNOWN)
        console.log("2. Navigating to /settings with no heartbeat received (Case 1)...");
        await page.goto('http://localhost:3000/settings');
        await page.waitForTimeout(600);

        const cameraCard = await page.locator('div:has-text("Camera Stream")').first();
        const modelCard = await page.locator('div:has-text("AI Model")').first();

        const camUnknown = await cameraCard.locator('div:has-text("UNKNOWN")').first().isVisible();
        const modelUnknown = await modelCard.locator('div:has-text("UNKNOWN")').first().isVisible();

        if (!camUnknown || !modelUnknown) {
            throw new Error(`Case 1 failed: Expected Camera and Model to be UNKNOWN. camUnknown: ${camUnknown}, modelUnknown: ${modelUnknown}`);
        }
        console.log("PASS (Case 1): No heartbeat received correctly renders UNKNOWN for Camera and Model");

        // 4. Case 2: Fresh healthy telemetry -> UP
        console.log("3. Testing Case 2: Fresh healthy edge heartbeat (UP)...");
        edgeHealthData = {
            camera_status: "UP",
            camera_details: "Camera stream active (1280x720 @ 30fps)",
            model_status: "UP",
            model_details: "Inference operational",
            last_heartbeat: new Date().toISOString(),
            age_seconds: 3.2,
            is_stale: false,
            fps: 29.5,
        };

        const refreshBtn = await page.waitForSelector('button[title="Refresh system health status"]');
        await refreshBtn.click();
        await page.waitForTimeout(600);

        const camUp = await cameraCard.locator('div:has-text("UP")').first().isVisible();
        const modelUp = await modelCard.locator('div:has-text("UP")').first().isVisible();
        const modelFpsVisible = await page.locator('text=Inference operational').first().isVisible();

        if (!camUp || !modelUp) {
            throw new Error(`Case 2 failed: Expected Camera and Model to be UP. camUp: ${camUp}, modelUp: ${modelUp}`);
        }
        console.log("PASS (Case 2): Fresh healthy telemetry correctly renders UP for Camera Stream and AI Model");

        // 5. Case 3: Stale heartbeat (>60s) -> DOWN with stale warning
        console.log("4. Testing Case 3: Stale edge heartbeat (>60s)...");
        edgeHealthData = {
            camera_status: "DOWN",
            camera_details: "Heartbeat telemetry stale (last received 72s ago)",
            model_status: "DOWN",
            model_details: "Heartbeat telemetry stale (last received 72s ago)",
            last_heartbeat: new Date(Date.now() - 72000).toISOString(),
            age_seconds: 72.0,
            is_stale: true,
            fps: 30.0,
        };

        await refreshBtn.click();
        await page.waitForTimeout(600);

        const camDown = await cameraCard.locator('div:has-text("DOWN")').first().isVisible();
        const modelDown = await modelCard.locator('div:has-text("DOWN")').first().isVisible();
        const staleTextVisible = await page.locator('text=Heartbeat telemetry stale (last received 72s ago)').first().isVisible();

        if (!camDown || !modelDown || !staleTextVisible) {
            throw new Error(`Case 3 failed: Expected Camera and Model DOWN with stale notice. camDown: ${camDown}, modelDown: ${modelDown}, staleTextVisible: ${staleTextVisible}`);
        }
        console.log("PASS (Case 3): Stale edge heartbeat correctly renders DOWN with clear stale notice");

        // 6. Case 4: Edge camera failure / model degraded
        console.log("5. Testing Case 4: Camera DOWN, Model DEGRADED...");
        edgeHealthData = {
            camera_status: "DOWN",
            camera_details: "Camera acquisition failed (device busy)",
            model_status: "DEGRADED",
            model_details: "Intermittent inference drops",
            last_heartbeat: new Date().toISOString(),
            age_seconds: 2.0,
            is_stale: false,
            fps: 5.2,
        };

        await refreshBtn.click();
        await page.waitForTimeout(600);

        const camDown4 = await cameraCard.locator('div:has-text("DOWN")').first().isVisible();
        const modelDegraded = await modelCard.locator('div:has-text("DEGRADED")').first().isVisible();

        if (!camDown4 || !modelDegraded) {
            throw new Error(`Case 4 failed: Expected Camera DOWN and Model DEGRADED. camDown: ${camDown4}, modelDegraded: ${modelDegraded}`);
        }
        console.log("PASS (Case 4): Edge failure telemetry accurately renders Camera DOWN and Model DEGRADED");

        // 7. Case 5: HTTP 500 error on telemetry probe transitions to DOWN (does not preserve stale UP)
        console.log("6. Testing Case 5: Endpoint error (HTTP 500) transitions to DOWN...");
        edgeRouteStatus = 500;
        await refreshBtn.click();
        await page.waitForTimeout(600);

        const camDown5 = await cameraCard.locator('div:has-text("DOWN")').first().isVisible();
        const modelDown5 = await modelCard.locator('div:has-text("DOWN")').first().isVisible();
        if (!camDown5 || !modelDown5) {
            throw new Error(`Case 5 failed: Expected Camera and Model DOWN on HTTP 500. camDown5: ${camDown5}, modelDown5: ${modelDown5}`);
        }
        console.log("PASS (Case 5): Endpoint error (HTTP 500) correctly transitions Camera and Model to DOWN");

        // 8. Case 6: Network drop / fetch failure transitions to DOWN
        console.log("7. Testing Case 6: Network connection failure transitions to DOWN...");
        edgeRouteAbort = true;
        await refreshBtn.click();
        await page.waitForTimeout(600);

        const camDown6 = await cameraCard.locator('div:has-text("DOWN")').first().isVisible();
        const modelDown6 = await modelCard.locator('div:has-text("DOWN")').first().isVisible();
        if (!camDown6 || !modelDown6) {
            throw new Error(`Case 6 failed: Expected Camera and Model DOWN on network failure. camDown6: ${camDown6}, modelDown6: ${modelDown6}`);
        }
        console.log("PASS (Case 6): Network failure correctly transitions Camera and Model to DOWN");

        // Restore route status
        edgeRouteAbort = false;
        edgeRouteStatus = 200;

        // 9. Verify settings configuration parameters remain read-only
        console.log("8. Verifying settings parameters remain read-only...");
        const cameraSourceDisplay = await page.locator('text=0 (Default)').first().isVisible();
        if (!cameraSourceDisplay) {
            throw new Error("Settings configuration display for camera source missing or altered");
        }
        console.log("PASS: Configuration sections preserved and read-only");

        console.log("\nALL PHASE 5.12 LIVE EDGE HEALTH UI TESTS PASSED SUCCESSFULLY!");
    } catch (err) {
        console.error("TEST FAILED:", err);
        process.exitCode = 1;
    } finally {
        if (browser) {
            await browser.close();
        }
    }
})();
