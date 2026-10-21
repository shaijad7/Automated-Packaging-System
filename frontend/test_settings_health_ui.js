const { chromium } = require('playwright');

(async () => {
    let browser;
    try {
        console.log("Starting Phase 5.11 Settings Live Health UI regression tests with Playwright...");
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

        // Hermetic mock for edge telemetry on settings page (default UNKNOWN for camera/model)
        await page.route('**/dashboard/system-health', route => {
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    camera_status: "UNKNOWN",
                    camera_details: "No edge heartbeat received",
                    model_status: "UNKNOWN",
                    model_details: "No edge heartbeat received",
                    last_heartbeat: null,
                    age_seconds: null,
                    is_stale: false,
                    fps: null
                })
            });
        });

        // 1. Log in as admin
        console.log("1. Logging in as admin...");
        await page.goto('http://localhost:3000/login');
        await page.fill('input[name="login-username"]', 'admin');
        await page.fill('input[name="login-password"]', 'Admin@123');
        await page.click('button[type="submit"]');
        await page.waitForURL('**/dashboard');
        console.log("PASS: Landed on /dashboard");

        // 2. Set up initial healthy route for /health before opening /settings
        console.log("2. Navigating to /settings with healthy route (Case 1)...");
        let healthResponse = {
            status: 200,
            body: { status: "healthy", database: "connected" }
        };

        await page.route('**/health', route => {
            if (healthResponse.networkError) {
                route.abort('failed');
            } else {
                route.fulfill({
                    status: healthResponse.status,
                    contentType: 'application/json',
                    body: JSON.stringify(healthResponse.body)
                });
            }
        });

        await page.goto('http://localhost:3000/settings');
        await page.waitForTimeout(600);

        // Case 1: Healthy backend & MongoDB
        const backendCard = await page.locator('div:has-text("Backend API")').first();
        const mongoCard = await page.locator('div:has-text("MongoDB")').first();
        const cameraCard = await page.locator('div:has-text("Camera Stream")').first();
        const modelCard = await page.locator('div:has-text("AI Model")').first();

        const backendUp = await backendCard.locator('div:has-text("UP")').first().isVisible();
        const mongoUp = await mongoCard.locator('div:has-text("UP")').first().isVisible();
        const cameraUnknown = await cameraCard.locator('div:has-text("UNKNOWN")').first().isVisible();
        const modelUnknown = await modelCard.locator('div:has-text("UNKNOWN")').first().isVisible();

        if (!backendUp || !mongoUp) {
            throw new Error(`Expected Backend and Mongo UP in Case 1. backendUp: ${backendUp}, mongoUp: ${mongoUp}`);
        }
        if (!cameraUnknown || !modelUnknown) {
            throw new Error(`Expected Camera and Model UNKNOWN in Case 1. cameraUnknown: ${cameraUnknown}, modelUnknown: ${modelUnknown}`);
        }
        console.log("PASS (Case 1): Healthy backend reports Backend API UP, MongoDB UP, Camera UNKNOWN, and Model UNKNOWN");

        // Case 2: Database disconnected while backend API returns 503
        console.log("3. Testing Case 2: Database disconnected (503)...");
        healthResponse = {
            status: 503,
            body: { status: "unhealthy", database: "disconnected", detail: "Database connection failed" }
        };

        const refreshBtn = await page.waitForSelector('button[title="Refresh system health status"]');
        await refreshBtn.click();
        await page.waitForTimeout(600);

        const backendUp503 = await backendCard.locator('div:has-text("UP")').first().isVisible();
        const mongoDown = await mongoCard.locator('div:has-text("DOWN")').first().isVisible();
        if (!backendUp503 || !mongoDown) {
            throw new Error(`Case 2 failed: Expected Backend UP (responding 503) and Mongo DOWN. backendUp: ${backendUp503}, mongoDown: ${mongoDown}`);
        }
        console.log("PASS (Case 2): When database is disconnected, Backend API is UP (responding 503) and MongoDB is DOWN");

        // Case 3: Backend API unreachable (Network failure)
        console.log("4. Testing Case 3: Backend unreachable / network failure...");
        healthResponse = { networkError: true };

        await refreshBtn.click();
        await page.waitForTimeout(600);

        const backendDown = await backendCard.locator('div:has-text("DOWN")').first().isVisible();
        const mongoUnknown = await mongoCard.locator('div:has-text("UNKNOWN")').first().isVisible();
        if (!backendDown || !mongoUnknown) {
            throw new Error(`Case 3 failed: Expected Backend DOWN and Mongo UNKNOWN. backendDown: ${backendDown}, mongoUnknown: ${mongoUnknown}`);
        }
        console.log("PASS (Case 3): When backend is unreachable, Backend API is DOWN and MongoDB is safely UNKNOWN");

        // Case 4: Degraded status (HTTP 500)
        console.log("5. Testing Case 4: Unexpected response status (HTTP 500)...");
        healthResponse = {
            status: 500,
            networkError: false,
            body: { detail: "Internal error" }
        };

        await refreshBtn.click();
        await page.waitForTimeout(600);

        const backendDegraded = await backendCard.locator('div:has-text("DEGRADED")').first().isVisible();
        if (!backendDegraded) {
            throw new Error("Case 4 failed: Expected Backend DEGRADED on HTTP 500");
        }
        console.log("PASS (Case 4): Unexpected HTTP 500 status displays Backend API as DEGRADED");

        // Case 5: Recovery back to healthy
        console.log("6. Testing Case 5: Recovery back to healthy...");
        healthResponse = {
            status: 200,
            networkError: false,
            body: { status: "healthy", database: "connected" }
        };

        await refreshBtn.click();
        await page.waitForTimeout(600);

        const backendRecovered = await backendCard.locator('div:has-text("UP")').first().isVisible();
        const mongoRecovered = await mongoCard.locator('div:has-text("UP")').first().isVisible();
        if (!backendRecovered || !mongoRecovered) {
            throw new Error("Case 5 failed: Expected recovery back to UP for Backend and Mongo");
        }
        console.log("PASS (Case 5): System successfully recovers back to UP states");

        // Case 6: Verify all read-only configuration sections remain intact
        console.log("7. Verifying all read-only configuration sections remain rendered...");
        const cameraSection = await page.textContent('text=Camera & Video');
        const aiSection = await page.textContent('div.font-medium:has-text("AI Model")');
        const countingSection = await page.textContent('text=Counting Logic');
        const qrSection = await page.textContent('text=QR Scanning');
        const alertsSection = await page.textContent('text=Alerts Configuration');

        if (!cameraSection || !aiSection || !countingSection || !qrSection || !alertsSection) {
            throw new Error("One or more configuration sections were not found!");
        }
        console.log("PASS (Case 6): All read-only configuration sections preserved");

        await browser.close();
        console.log("ALL PHASE 5.11 SETTINGS HEALTH UI TESTS PASSED SUCCESSFULLY!");
    } catch (err) {
        console.error("Test failed:", err);
        process.exitCode = 1;
    } finally {
        if (browser) {
            await browser.close();
        }
    }
})();
