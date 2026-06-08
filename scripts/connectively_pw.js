
const { chromium } = require('playwright');
(async () => {
    const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
    const ctx = await browser.newContext();
    const page = await ctx.newPage();

    // Go to login
    await page.goto('https://www.connectively.us/login', { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(3000);

    // Fill login form
    await page.locator('input[autocomplete="email"]').fill('support@ct-designs.co.za');
    await page.locator('input[autocomplete="current-password"]').fill('xIl6l8JEDc9ACB');
    await page.locator('button[type="submit"]:has-text("Submit")').click();
    await page.waitForTimeout(5000);

    const afterLoginUrl = page.url();
    log('After login: ' + afterLoginUrl);

    // Go to HARO questions
    await page.goto('https://www.connectively.us/expert-questions', { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(5000);

    // Save auth state
    const cookies = await ctx.cookies();
    const sessionToken = cookies.find(c => c.name.includes('session'));
    const token = sessionToken ? sessionToken.value : '';

    // Scrape table rows
    const queries = await page.evaluate(() => {
        const results = [];
        const table = document.querySelector('table');
        if (!table) return results;
        const tbody = table.querySelector('tbody');
        if (!tbody) return results;
        const rows = tbody.querySelectorAll('tr');
        rows.forEach(row => {
            const cells = row.querySelectorAll('td');
            if (cells.length >= 4) {
                const links = cells[cells.length - 1].querySelectorAll('a');
                const answerLink = Array.from(links).find(a => a.textContent.trim() === 'Answer');
                // Extract question from first cell
                const qCell = cells[0];
                // Publication from second cell
                const pubCell = cells[1];
                // Deadline from third cell
                const dlCell = cells[2];

                let qText = '';
                // Walk through cell children - text nodes are question text
                const walker = document.createTreeWalker(qCell, NodeFilter.SHOW_TEXT);
                let node;
                while (node = walker.nextNode()) {
                    const t = node.textContent.trim();
                    if (t && t !== 'Questions' && t !== 'Publication' && t !== 'Deadline' && t !== 'Actions') {
                        qText += t + ' ';
                    }
                }
                qText = qText.trim();

                results.push({
                    question: qText.substring(0, 500),
                    publication: pubCell ? pubCell.textContent.trim().replace(/\s+/g, ' ') : '',
                    deadline: dlCell ? dlCell.textContent.trim().replace(/\s+/g, ' ') : '',
                    answerUrl: answerLink ? answerLink.href : ''
                });
            }
        });
        return results;
    });

    console.log(JSON.stringify({ queries, token, url: page.url() }));
    await browser.close();
})().catch(e => { console.error('ERROR:' + e.message); process.exit(1); });
