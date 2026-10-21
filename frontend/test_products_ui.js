const { chromium } = require('playwright');

(async () => {
    let browser;
    try {
        console.log("Starting Phase 5.13 Products UI end-to-end audit test with Playwright...");
        browser = await chromium.launch();
        const context = await browser.newContext();
        const page = await context.newPage();
        await page.setViewportSize({ width: 1280, height: 900 });

        // Intercept login route for safe hermetic UI test
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

        // Intercept initial dashboard calls
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

        // 1. Log in as admin
        console.log("1. Logging in as admin...");
        await page.goto('http://localhost:3000/login');
        await page.fill('input[name="login-username"]', 'admin');
        await page.fill('input[name="login-password"]', 'Admin@123');
        await page.click('button[type="submit"]');
        await page.waitForURL('**/dashboard');
        console.log("PASS: Landed on /dashboard");

        // 2. Verify Sidebar contains Products link and navigate
        console.log("2. Navigating to /inventory/products via sidebar...");
        const productsNavLink = await page.waitForSelector('nav a[href="/inventory/products"]');
        const linkText = await productsNavLink.textContent();
        if (!linkText.includes("Products")) {
            throw new Error(`Expected 'Products' in sidebar link text, got: ${linkText}`);
        }
        await productsNavLink.click();
        await page.waitForURL('**/inventory/products');
        console.log("PASS: Reached /inventory/products");

        // 3. Test Error State handling (Check 8: API and database errors are handled safely by UI)
        console.log("3. Testing UI error handling when /api/products/ returns 500...");
        let simulateError = true;
        await page.route('**/products/', route => {
            if (simulateError) {
                route.fulfill({
                    status: 500,
                    contentType: 'application/json',
                    body: JSON.stringify({ detail: "Database connection failed" })
                });
            } else {
                route.continue();
            }
        });

        await page.route('**/dashboard/inventory', route => {
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify([])
            });
        });

        await page.reload();
        await page.waitForTimeout(600);
        const errorBanner = await page.locator('.bg-red-50');
        const errorText = await errorBanner.textContent();
        if (!errorText || !errorText.includes("Failed to fetch products")) {
            throw new Error(`UI did not display expected error banner on 500 failure! Found text: ${errorText}`);
        }
        console.log("PASS: UI safely displays 'Failed to fetch products' banner on backend 500 error");

        // 4. Test Empty State handling
        console.log("4. Testing empty state when no products exist...");
        simulateError = false;
        await page.unroute('**/products/');

        await page.route('**/products/', route => {
            if (route.request().method() === 'GET') {
                route.fulfill({
                    status: 200,
                    contentType: 'application/json',
                    body: JSON.stringify([])
                });
            } else {
                route.continue();
            }
        });
        await page.route('**/dashboard/inventory', route => {
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify([])
            });
        });

        await page.reload();
        await page.waitForTimeout(500);
        const emptyStateText = await page.locator('text=No products registered');
        if (!await emptyStateText.isVisible()) {
            throw new Error("Expected 'No products registered' empty state not visible!");
        }
        console.log("PASS: UI safely renders empty state when zero products are registered");

        // 5. Test Populated Products Table with Active and Inactive items
        console.log("5. Testing populated products table with mocked products and inventory...");
        await page.unroute('**/products/');
        await page.unroute('**/dashboard/inventory');

        const mockProducts = [
            {
                sku: "SNS-001",
                name: "Industrial Vibration Sensor",
                description: "Triaxial 24V vibration sensor",
                is_active: true,
                qr_code: "INV|SNS-001"
            },
            {
                sku: "DIS-002",
                name: "Legacy Relay Module",
                description: "Deprecated relay module",
                is_active: false,
                qr_code: "INV|DIS-002"
            }
        ];

        const mockInventory = [
            { sku: "SNS-001", quantity: 42, product_name: "Industrial Vibration Sensor", is_active: true },
            { sku: "DIS-002", quantity: 0, product_name: "Legacy Relay Module", is_active: false }
        ];

        await page.route('**/products/', route => {
            if (route.request().method() === 'GET') {
                route.fulfill({
                    status: 200,
                    contentType: 'application/json',
                    body: JSON.stringify(mockProducts)
                });
            } else {
                route.continue();
            }
        });
        await page.route('**/dashboard/inventory', route => {
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify(mockInventory)
            });
        });

        await page.reload();
        await page.waitForTimeout(500);

        // Verify table rendered rows
        const activeRow = page.locator('tr:has-text("SNS-001")');
        const inactiveRow = page.locator('tr:has-text("DIS-002")');
        if (!await activeRow.isVisible() || !await inactiveRow.isVisible()) {
            throw new Error("Product rows for SNS-001 or DIS-002 not visible in table!");
        }

        // Verify quantity merged from inventory
        const qtyText = await activeRow.locator('td:has-text("42")').isVisible();
        if (!qtyText) {
            throw new Error("Quantity 42 for SNS-001 not rendered!");
        }

        // Verify status badges
        const activeBadge = await activeRow.locator('span:has-text("Active")').isVisible();
        const inactiveBadge = await inactiveRow.locator('span:has-text("Inactive")').isVisible();
        if (!activeBadge || !inactiveBadge) {
            throw new Error("Active/Inactive badges not rendered correctly!");
        }
        console.log("PASS: Products table correctly renders rows, merged inventory quantities, and Active/Inactive badges");

        // 6. Test Search filter
        console.log("6. Testing search filter by SKU and Product Name...");
        const searchInput = page.locator('input[placeholder*="Search by Product Name"]');
        await searchInput.fill("Legacy");
        await page.waitForTimeout(200);
        if (await activeRow.isVisible()) {
            throw new Error("SNS-001 should have been filtered out by search 'Legacy'!");
        }
        if (!await inactiveRow.isVisible()) {
            throw new Error("DIS-002 should be visible for search 'Legacy'!");
        }
        await searchInput.fill("");
        await page.waitForTimeout(200);
        console.log("PASS: Search bar correctly filters table rows in real-time");

        // 7. Test Add Product Modal & Duplicate SKU error handling
        console.log("7. Testing Add Product Modal error handling on duplicate SKU...");
        const addBtn = page.locator('button:has-text("Add Product")');
        await addBtn.click();
        await page.waitForSelector('text=Register Product');

        // Setup route to simulate 400 Duplicate SKU
        await page.route('**/products/', route => {
            if (route.request().method() === 'POST') {
                route.fulfill({
                    status: 400,
                    contentType: 'application/json',
                    body: JSON.stringify({ detail: "Product with this SKU already exists" })
                });
            } else if (route.request().method() === 'GET') {
                route.fulfill({
                    status: 200,
                    contentType: 'application/json',
                    body: JSON.stringify(mockProducts)
                });
            }
        });

        await page.fill('input[placeholder="e.g. Type-C Adapter"]', "Duplicate Test");
        await page.fill('input[placeholder="e.g. ADP-001"]', "SNS-001");
        await page.click('button:has-text("Save Product")');
        await page.waitForTimeout(400);

        const dupErrorMsg = page.locator('text=Product with this SKU already exists');
        if (!await dupErrorMsg.isVisible()) {
            throw new Error("Add Product modal did not display duplicate SKU error message!");
        }
        console.log("PASS: Add Product modal displays backend 400 duplicate SKU rejection safely");

        // Close modal
        await page.click('button:has-text("Cancel")');
        await page.waitForTimeout(200);

        // 8. Test View Label Modal
        console.log("8. Testing View QR Label Modal...");
        // Mock 1x1 transparent png
        const mockPngBase64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";
        const mockPngBuffer = Buffer.from(mockPngBase64, 'base64');

        let labelRequestedUrl = null;
        let labelRequestAuthHeader = null;
        await page.route('**/products/*/label', route => {
            labelRequestedUrl = route.request().url();
            labelRequestAuthHeader = route.request().headers()['authorization'];
            route.fulfill({
                status: 200,
                contentType: 'image/png',
                body: mockPngBuffer
            });
        });

        const viewLabelBtn = activeRow.locator('button:has-text("View")');
        await viewLabelBtn.click();
        await page.waitForSelector('text=Product Label');

        if (!labelRequestedUrl || !labelRequestedUrl.endsWith('/products/SNS-001/label')) {
            throw new Error(`Label requested with incorrect URL: ${labelRequestedUrl}`);
        }
        if (!labelRequestAuthHeader || !labelRequestAuthHeader.includes('Bearer mock_admin_jwt_token')) {
            throw new Error(`Label requested without proper Bearer token: ${labelRequestAuthHeader}`);
        }
        console.log(`PASS: Verified QR label request uses established fetchWithAuth client with Bearer auth: ${labelRequestedUrl}`);

        const downloadLink = page.locator('a:has-text("Download QR Label")');
        if (!await downloadLink.isVisible()) {
            throw new Error("Download QR Label button not visible in label modal!");
        }
        console.log("PASS: View Label modal displays label and Download QR Label button");

        await page.click('button:has-text("Close")');
        await page.waitForTimeout(200);

        // 9. Phase 5.15B: Test Edit Product Modal, Validation, False Checkbox, and Save
        console.log("9. Testing Phase 5.15B Edit Product Modal and PATCH behavior...");
        const editBtn = activeRow.locator('button[title="Edit Product"]');
        if (!await editBtn.isVisible()) {
            throw new Error("Edit Product button not found on active row!");
        }
        await editBtn.click();
        await page.waitForSelector('text=Edit Product');

        // 9a. Verify pre-populated values and read-only SKU
        const editModal = page.locator('div.fixed:has-text("Edit Product")');
        const skuInput = editModal.locator('input[disabled]');
        const skuVal = await skuInput.inputValue();
        if (skuVal !== "SNS-001") {
            throw new Error(`Expected disabled SKU input to have 'SNS-001', got: '${skuVal}'`);
        }
        const isSkuDisabled = await skuInput.isDisabled();
        if (!isSkuDisabled) {
            throw new Error("SKU input is not disabled!");
        }

        const nameInput = editModal.locator('input[placeholder="e.g. Type-C Adapter"]');
        const nameVal = await nameInput.inputValue();
        if (nameVal !== "Industrial Vibration Sensor") {
            throw new Error(`Expected Name input to have 'Industrial Vibration Sensor', got: '${nameVal}'`);
        }

        const activeCheckbox = editModal.locator('input#editIsActive');
        const isChecked = await activeCheckbox.isChecked();
        if (!isChecked) {
            throw new Error("Expected active status checkbox to be checked for SNS-001!");
        }
        console.log("PASS: Edit modal correctly displays read-only SKU and pre-populated values");

        // 9b. Test client-side blank name validation
        await nameInput.fill("    ");
        await editModal.locator('button:has-text("Save Changes")').click();
        await page.waitForTimeout(200);

        const blankError = editModal.locator('div[role="alert"]:has-text("Product name cannot be empty")');
        if (!await blankError.isVisible()) {
            throw new Error("Expected client-side validation error 'Product name cannot be empty' not visible!");
        }
        // Modal must remain open
        if (!await editModal.isVisible()) {
            throw new Error("Edit modal closed prematurely on blank name validation failure!");
        }
        console.log("PASS: Client-side blank name rejection keeps modal open and displays error");

        // 9c. Test backend failure handling (keeps modal open, displays server error)
        let patchRequestPayload = null;
        let patchRequestHeaders = null;
        let patchRequestUrl = null;
        let simulatePatchFailure = true;

        await page.route('**/products/SNS-001', route => {
            if (route.request().method() === 'PATCH') {
                patchRequestUrl = route.request().url();
                patchRequestHeaders = route.request().headers();
                patchRequestPayload = JSON.parse(route.request().postData());

                if (simulatePatchFailure) {
                    route.fulfill({
                        status: 400,
                        contentType: 'application/json',
                        body: JSON.stringify({ detail: "Database constraint failure on edit" })
                    });
                } else {
                    route.fulfill({
                        status: 200,
                        contentType: 'application/json',
                        body: JSON.stringify({
                            sku: "SNS-001",
                            name: patchRequestPayload.name,
                            description: patchRequestPayload.description,
                            is_active: patchRequestPayload.is_active,
                            qr_code: "INV|SNS-001"
                        })
                    });
                }
            } else {
                route.continue();
            }
        });

        await nameInput.fill("Updated Vibration Sensor");
        await editModal.locator('button:has-text("Save Changes")').click();
        await page.waitForTimeout(300);

        const serverError = editModal.locator('div[role="alert"]:has-text("Database constraint failure on edit")');
        if (!await serverError.isVisible()) {
            throw new Error("Expected backend failure banner not displayed in edit modal!");
        }
        if (!await editModal.isVisible()) {
            throw new Error("Edit modal closed prematurely on backend failure!");
        }
        console.log("PASS: Backend failure keeps edit modal open and displays server error message");

        // 9d. Test successful PATCH with unchecked active status (submits false)
        simulatePatchFailure = false;
        await activeCheckbox.uncheck();
        const descInput = editModal.locator('textarea[placeholder="Optional details..."]');
        await descInput.fill("Updated sensor description 2026");

        // Update mock GET products for the post-save refresh
        const updatedMockProducts = [
            {
                sku: "SNS-001",
                name: "Updated Vibration Sensor",
                description: "Updated sensor description 2026",
                is_active: false,
                qr_code: "INV|SNS-001"
            },
            mockProducts[1]
        ];
        await page.route('**/products/', route => {
            if (route.request().method() === 'GET') {
                route.fulfill({
                    status: 200,
                    contentType: 'application/json',
                    body: JSON.stringify(updatedMockProducts)
                });
            } else {
                route.continue();
            }
        });

        await editModal.locator('button:has-text("Save Changes")').click();
        await page.waitForTimeout(500);

        // Verify edit modal is closed on success
        if (await editModal.isVisible()) {
            throw new Error("Edit modal did not close after successful update!");
        }

        // Verify PATCH request payload
        if (!patchRequestPayload) {
            throw new Error("No PATCH request was intercepted!");
        }
        if (patchRequestPayload.sku !== undefined || patchRequestPayload.qr_code !== undefined) {
            throw new Error(`PATCH payload included immutable fields! ${JSON.stringify(patchRequestPayload)}`);
        }
        if (patchRequestPayload.name !== "Updated Vibration Sensor") {
            throw new Error(`Expected name 'Updated Vibration Sensor', got '${patchRequestPayload.name}'`);
        }
        if (patchRequestPayload.description !== "Updated sensor description 2026") {
            throw new Error(`Expected description 'Updated sensor description 2026', got '${patchRequestPayload.description}'`);
        }
        if (patchRequestPayload.is_active !== false) {
            throw new Error(`Expected is_active to be explicitly false, got: ${patchRequestPayload.is_active}`);
        }
        if (!patchRequestHeaders['authorization'] || !patchRequestHeaders['authorization'].includes('Bearer mock_admin_jwt_token')) {
            throw new Error(`PATCH request missing Bearer auth: ${JSON.stringify(patchRequestHeaders)}`);
        }
        console.log("PASS: Verified PATCH request submits only editable fields, explicit false for is_active, and Bearer token");

        // Verify table refreshed with updated product
        const updatedRow = page.locator('tr:has-text("Updated Vibration Sensor")');
        if (!await updatedRow.isVisible()) {
            throw new Error("Updated product name not visible in table after refresh!");
        }
        const updatedInactiveBadge = updatedRow.locator('span:has-text("Inactive")');
        if (!await updatedInactiveBadge.isVisible()) {
            throw new Error("Product SNS-001 does not show Inactive badge in table after update!");
        }
        console.log("PASS: Table refreshed with updated product name and Inactive status");

        console.log("ALL PLAYWRIGHT FRONTEND PRODUCTS AUDIT TESTS PASSED SUCCESSFULLY!");
    } catch (err) {
        console.error("TEST FAILED:", err);
        process.exitCode = 1;
    } finally {
        if (browser) await browser.close();
    }
})();
