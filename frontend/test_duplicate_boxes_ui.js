const { chromium } = require('playwright');

(async () => {
    let browser;
    try {
        console.log("Starting Phase 5.10 Dedicated Duplicate Boxes UI regression tests with Playwright...");
        browser = await chromium.launch();
        const context = await browser.newContext();
        const page = await context.newPage();
        await page.setViewportSize({ width: 1280, height: 800 });

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

        // 1. Log in as admin
        console.log("1. Logging in as admin...");
        await page.goto('http://localhost:3000/login');
        await page.fill('input[name="login-username"]', 'admin');
        await page.fill('input[name="login-password"]', 'Admin@123');
        await page.click('button[type="submit"]');
        await page.waitForURL('**/dashboard');
        console.log("PASS: Landed on /dashboard");

        // 2. Verify Dashboard NO LONGER renders the detailed Duplicate Boxes section
        console.log("2. Checking Dashboard removed Duplicate Boxes section while preserving summary & exceptions...");
        const dupHeadingOnDashboard = await page.$('text=Duplicate Boxes & SKU Groups');
        if (dupHeadingOnDashboard) {
            throw new Error("Dashboard still renders Duplicate Boxes & SKU Groups section!");
        }
        console.log("PASS: Detailed Duplicate Boxes section is cleanly removed from Dashboard");

        // 3. Verify Dashboard STILL renders summary cards and Exception Breakdown
        const overallBoxes = await page.textContent('text=Overall Boxes');
        const validQr = await page.textContent('text=Valid QR');
        const qrExceptions = await page.textContent('text=QR Exceptions');
        const inventoryAdded = await page.textContent('text=Inventory Added');
        const exceptionBreakdown = await page.textContent('text=Exception Breakdown');

        if (!overallBoxes || !validQr || !qrExceptions || !inventoryAdded || !exceptionBreakdown) {
            throw new Error("Dashboard summary cards or Exception Breakdown are missing!");
        }
        console.log("PASS: Dashboard preserves Overall Boxes, Valid QR, QR Exceptions, Inventory Added, and Exception Breakdown");

        // 4. Verify Sidebar contains the Duplicate Boxes link
        console.log("3. Verifying sidebar navigation contains Duplicate Boxes item...");
        const sidebarLink = await page.waitForSelector('nav a[href="/duplicate-boxes"]');
        const linkText = await sidebarLink.textContent();
        if (!linkText.includes("Duplicate Boxes")) {
            throw new Error(`Sidebar link text expected 'Duplicate Boxes', got: ${linkText}`);
        }
        console.log("PASS: Sidebar contains Duplicate Boxes navigation link");

        // 5. Intercept route for Error State before navigating to /duplicate-boxes
        console.log("4. Setting up route interception for Error State test...");
        let shouldFail = true;
        await page.route('**/dashboard/duplicate-boxes', route => {
            if (shouldFail) {
                route.fulfill({
                    status: 500,
                    contentType: 'application/json',
                    body: JSON.stringify({ detail: "Simulated backend failure" })
                });
            } else {
                route.fulfill({
                    status: 200,
                    contentType: 'application/json',
                    body: JSON.stringify({
                        summary: {
                            repeated_scans_count: 0,
                            id_conflicts_count: 0,
                            same_sku_groups_count: 0,
                            has_serialized_box_ids: false,
                            schema_notice: "Mocked schema contract notice for testing"
                        },
                        repeated_scans_and_conflicts: [],
                        same_sku_groups: []
                    })
                });
            }
        });

        // 6. Navigate to /duplicate-boxes by clicking the sidebar link
        console.log("5. Clicking Duplicate Boxes in sidebar to navigate to /duplicate-boxes...");
        await sidebarLink.click();
        await page.waitForURL('**/duplicate-boxes');
        console.log("PASS: Successfully navigated to /duplicate-boxes");

        // Verify active route highlighting on sidebar
        const activeLinkClass = await sidebarLink.getAttribute('class');
        if (!activeLinkClass.includes("bg-blue-600")) {
            throw new Error(`Sidebar item not highlighted as active! Class: ${activeLinkClass}`);
        }
        console.log("PASS: Sidebar navigation highlights Duplicate Boxes as active route");

        // 7. Verify Error State & Retry Action
        console.log("6. Verifying Error State and Retry button on /duplicate-boxes...");
        await page.waitForSelector('text=Failed to load duplicate boxes data');
        const retryBtn = await page.waitForSelector('button:has-text("Retry")');
        console.log("PASS: Error state rendered with retry action");

        // 8. Recover and click Retry -> Verify Empty State
        console.log("7. Clicking Retry to verify Empty State...");
        shouldFail = false;
        await retryBtn.click();
        await page.waitForTimeout(600);

        const noConflicts = await page.textContent('text=No repeated scans or ID conflicts detected');
        if (!noConflicts) throw new Error("Expected empty state for Category 1 not visible!");
        const noGroups = await page.textContent('text=No multi-box groups found for any SKU');
        if (!noGroups) throw new Error("Expected empty state for Category 2 not visible!");
        const schemaNotice = await page.textContent('text=Mocked schema contract notice for testing');
        if (!schemaNotice) throw new Error("Schema notice banner not visible!");
        console.log("PASS: Empty state rendered cleanly with schema notice on dedicated page");

        // 9. Populated State verification
        console.log("8. Testing Populated State on /duplicate-boxes...");
        await page.unroute('**/dashboard/duplicate-boxes');
        await page.route('**/dashboard/duplicate-boxes', route => {
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    summary: {
                        repeated_scans_count: 2,
                        id_conflicts_count: 1,
                        same_sku_groups_count: 1,
                        has_serialized_box_ids: true,
                        schema_notice: "Active Schema Contract: distinct events with same SKU are separate boxes."
                    },
                    repeated_scans_and_conflicts: [
                        {
                            box_id: "BOX-TEST-001",
                            sku: "SKU-TEST-A, SKU-TEST-B",
                            product_name: "Widget Combo",
                            category: "ID_CONFLICT",
                            reason: "Box ID 'BOX-TEST-001' associated with conflicting SKUs",
                            first_seen: "2026-10-21T02:00:00Z",
                            last_seen: "2026-10-21T02:05:00Z",
                            review_status: "NEEDS_REVIEW"
                        },
                        {
                            box_id: "BOX-TEST-002",
                            sku: "SKU-TEST-C",
                            product_name: "Widget Regular",
                            category: "REPEATED_SCAN",
                            reason: "Box ID 'BOX-TEST-002' observed 2 times with identical SKU",
                            first_seen: "2026-10-21T02:10:00Z",
                            last_seen: "2026-10-21T02:12:00Z",
                            review_status: "REVIEW_CANDIDATE"
                        }
                    ],
                    same_sku_groups: [
                        {
                            sku: "SKU-MULTI-99",
                            product_name: "Multi-Box Item",
                            box_count: 5,
                            sample_event_ids: ["evt-11111111", "evt-22222222"],
                            box_ids: null,
                            has_distinct_box_ids: false,
                            first_seen: "2026-10-21T01:00:00Z",
                            last_seen: "2026-10-21T02:00:00Z",
                            review_status: "VALID_INVENTORY_GROUP",
                            reason: "Multiple distinct physical box observations sharing the same product SKU."
                        }
                    ]
                })
            });
        });

        const refreshBtn = await page.waitForSelector('button[title="Refresh duplicate analysis"]');
        await refreshBtn.click();
        await page.waitForTimeout(600);

        // Verify summary KPI cards
        const kpiRepeated = await page.textContent('span.text-3xl:has-text("2")');
        if (!kpiRepeated) throw new Error("Repeated scans KPI count 2 not found!");

        // Verify Category 1 table rows
        const conflictCell = await page.textContent('td:has-text("BOX-TEST-001")');
        if (!conflictCell) throw new Error("Category 1 row BOX-TEST-001 not found!");
        const needsReviewBadge = await page.textContent('text=NEEDS_REVIEW');
        if (!needsReviewBadge) throw new Error("NEEDS_REVIEW badge not found!");
        const reviewCandidateBadge = await page.textContent('text=REVIEW_CANDIDATE');
        if (!reviewCandidateBadge) throw new Error("REVIEW_CANDIDATE badge not found!");

        // Verify Category 2 table rows
        const groupSkuCell = await page.textContent('td:has-text("SKU-MULTI-99")');
        if (!groupSkuCell) throw new Error("Category 2 row SKU-MULTI-99 not found!");
        const boxCountBadge = await page.textContent('text=5 boxes counted');
        if (!boxCountBadge) throw new Error("5 boxes counted badge not found!");
        const validGroupBadge = await page.textContent('text=Valid Inventory Group');
        if (!validGroupBadge) throw new Error("Valid Inventory Group badge not found!");

        console.log("PASS: Populated state displays KPI cards, Category 1 conflicts, Category 2 groups, and accurate badges");

        await browser.close();
        console.log("ALL PHASE 5.10 DEDICATED DUPLICATE BOXES UI TESTS PASSED SUCCESSFULLY!");
    } catch (err) {
        console.error("Test failed:", err);
        process.exitCode = 1;
    } finally {
        if (browser) {
            await browser.close();
        }
    }
})();
