const { chromium } = require('playwright');

(async () => {
    let browser;
    try {
        console.log("Starting Phase 5.17 Reports UI & Export Regression Tests with Playwright...");
        browser = await chromium.launch();
        const context = await browser.newContext({ acceptDownloads: true });
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
                    overall_boxes: 10,
                    valid_qr: 8,
                    no_qr: 1,
                    unreadable_qr: 1,
                    invalid_qr: 0,
                    qr_exceptions: 2,
                    inventory_added: 8
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

        // Mock report data for /dashboard/reports
        const mockReportData = {
            summary: {
                overall_boxes: 25,
                valid_qr: 20,
                no_qr: 2,
                unreadable_qr: 2,
                invalid_qr: 1,
                qr_exceptions: 5,
                inventory_added: 20
            },
            events: [
                {
                    event_id: "evt-001",
                    timestamp: "2026-10-21T10:00:00Z",
                    track_id: 101,
                    qr_status: "VALID_QR",
                    qr_payload: "BOX-A1-SKU-100",
                    count_direction: "IN",
                    sku: "SKU-TEST-100",
                    status: "PROCESSED"
                },
                {
                    event_id: "evt-002",
                    timestamp: "2026-10-21T10:05:00Z",
                    track_id: 102,
                    qr_status: "UNREADABLE_QR",
                    qr_payload: null,
                    count_direction: "IN",
                    sku: null,
                    status: "EXCEPTION"
                }
            ]
        };

        let lastReportQuery = "";
        await page.route(/\/dashboard\/reports(\?.*)?$/, route => {
            const url = new URL(route.request().url());
            lastReportQuery = url.search;
            // Verify Authorization header
            const authHeader = route.request().headers()['authorization'];
            if (!authHeader || !authHeader.startsWith('Bearer ')) {
                route.fulfill({ status: 401, body: JSON.stringify({ detail: "Missing or invalid token" }) });
                return;
            }
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify(mockReportData)
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

        // 2. Navigate to /reports via sidebar
        console.log("2. Navigating to /reports via sidebar...");
        const reportsLink = await page.waitForSelector('nav a[href="/reports"]');
        await reportsLink.click();
        await page.waitForURL('**/reports');
        console.log("PASS: Reached /reports");

        // 3. Verify initial reports data rendered
        console.log("3. Verifying reports page renders summary KPI cards and events table...");
        await page.waitForSelector('text=Inventory processing and QR validation history.');
        const overallText = await page.textContent('span.text-3xl:has-text("25")');
        if (!overallText) throw new Error("Expected summary KPI count 25 not rendered!");

        const eventRow = await page.textContent('td:has-text("SKU-TEST-100")');
        if (!eventRow) throw new Error("Expected event row SKU-TEST-100 not rendered!");
        console.log("PASS: Initial reports data successfully rendered");

        // 4. Test filter interaction
        console.log("4. Testing filter parameter passing with fetchWithAuth...");
        await page.fill('input[placeholder="e.g. ADP-001"]', 'SKU-FILTER-99');
        await page.selectOption('select', 'VALID_QR');
        await page.click('button:has-text("Apply Filters")');
        await page.waitForTimeout(500);

        if (!lastReportQuery.includes("sku=SKU-FILTER-99") || !lastReportQuery.includes("qr_status=VALID_QR")) {
            throw new Error(`Filters were not passed in report query! Got: ${lastReportQuery}`);
        }
        console.log("PASS: Filters passed to backend via fetchWithAuth with Bearer token");

        // 5. Test Successful CSV Export via fetchWithAuth
        console.log("5. Testing CSV export download and Bearer token transmission...");
        let csvAuthReceived = null;
        let csvQueryParams = null;
        await page.route('**/dashboard/reports/export.csv*', route => {
            const req = route.request();
            csvAuthReceived = req.headers()['authorization'];
            csvQueryParams = new URL(req.url()).search;
            route.fulfill({
                status: 200,
                contentType: 'text/csv',
                headers: {
                    'content-disposition': 'attachment; filename="smart-inventory-export-custom.csv"',
                    'access-control-expose-headers': 'content-disposition',
                    'access-control-allow-origin': '*'
                },
                body: "event_id,timestamp,qr_status,sku\nevt-001,2026-10-21T10:00:00Z,VALID_QR,SKU-TEST-100\n"
            });
        });

        const [csvDownload] = await Promise.all([
            page.waitForEvent('download'),
            page.click('button:has-text("Export CSV")')
        ]);
        const csvFilename = csvDownload.suggestedFilename();
        if (csvFilename !== "smart-inventory-export-custom.csv") {
            throw new Error(`Expected downloaded filename 'smart-inventory-export-custom.csv', got: '${csvFilename}'`);
        }
        if (csvAuthReceived !== "Bearer mock_admin_jwt_token") {
            throw new Error(`CSV export did not transmit Bearer token! Received: ${csvAuthReceived}`);
        }
        if (!csvQueryParams.includes("sku=SKU-FILTER-99") || !csvQueryParams.includes("qr_status=VALID_QR")) {
            throw new Error(`CSV export did not preserve active filter query parameters! Got: ${csvQueryParams}`);
        }
        console.log("PASS: CSV export successfully downloaded with Bearer auth and preserved active query params");

        // 6. Test Successful PDF Export via fetchWithAuth
        console.log("6. Testing PDF export download and Bearer token transmission...");
        let pdfAuthReceived = null;
        let pdfQueryParams = null;
        await page.route('**/dashboard/reports/export.pdf*', route => {
            const req = route.request();
            pdfAuthReceived = req.headers()['authorization'];
            pdfQueryParams = new URL(req.url()).search;
            route.fulfill({
                status: 200,
                contentType: 'application/pdf',
                headers: {
                    'content-disposition': 'attachment; filename="smart-inventory-export-custom.pdf"',
                    'access-control-expose-headers': 'content-disposition',
                    'access-control-allow-origin': '*'
                },
                body: Buffer.from("%PDF-1.4 Mock PDF Content %%EOF")
            });
        });

        const [pdfDownload] = await Promise.all([
            page.waitForEvent('download'),
            page.click('button:has-text("Export PDF")')
        ]);
        const pdfFilename = pdfDownload.suggestedFilename();
        if (pdfFilename !== "smart-inventory-export-custom.pdf") {
            throw new Error(`Expected downloaded filename 'smart-inventory-export-custom.pdf', got: '${pdfFilename}'`);
        }
        if (pdfAuthReceived !== "Bearer mock_admin_jwt_token") {
            throw new Error(`PDF export did not transmit Bearer token! Received: ${pdfAuthReceived}`);
        }
        if (!pdfQueryParams.includes("sku=SKU-FILTER-99") || !pdfQueryParams.includes("qr_status=VALID_QR")) {
            throw new Error(`PDF export did not preserve active filter query parameters! Got: ${pdfQueryParams}`);
        }
        console.log("PASS: PDF export successfully downloaded binary blob with Bearer auth and preserved query params");

        // 7. Test Export Failure (HTTP 500) Error Handling
        console.log("7. Testing HTTP 500 error display without creating broken downloads...");
        await page.unroute('**/dashboard/reports/export.csv*');
        await page.route('**/dashboard/reports/export.csv*', route => {
            route.fulfill({
                status: 500,
                contentType: 'application/json',
                headers: {
                    'access-control-allow-origin': '*'
                },
                body: JSON.stringify({ detail: "Database connection failed during export generation" })
            });
        });

        await page.click('button:has-text("Export CSV")');
        await page.waitForTimeout(600);

        const errorBanner = await page.waitForSelector('text=Database connection failed during export generation');
        if (!errorBanner) {
            throw new Error("Export failure error message not displayed in UI!");
        }
        console.log("PASS: Server error displayed clearly in UI banner on export failure");

        // 8. Test HTTP 401 Session Expiration and Centralized Redirect
        console.log("8. Testing HTTP 401 session expiration handling and redirect to /login...");
        await page.unroute('**/dashboard/reports/export.csv*');
        await page.route('**/dashboard/reports/export.csv*', route => {
            route.fulfill({
                status: 401,
                contentType: 'application/json',
                headers: {
                    'access-control-allow-origin': '*'
                },
                body: JSON.stringify({ detail: "Token expired" })
            });
        });

        await page.click('button:has-text("Export CSV")');
        await page.waitForURL('**/login');
        console.log("PASS: HTTP 401 on export correctly cleared session and redirected to /login");

        // Verify token removed from sessionStorage
        const tokenAfter401 = await page.evaluate(() => sessionStorage.getItem('access_token'));
        if (tokenAfter401 !== null) {
            throw new Error(`Expected token to be cleared from sessionStorage, got: ${tokenAfter401}`);
        }
        console.log("PASS: Session token was removed from sessionStorage upon 401");

        await browser.close();
        console.log("\nALL PHASE 5.17 REPORTS UI & EXPORT REGRESSION TESTS PASSED SUCCESSFULLY!");
    } catch (err) {
        console.error("TEST FAILED:", err);
        process.exitCode = 1;
    } finally {
        if (browser) {
            await browser.close();
        }
    }
})();
