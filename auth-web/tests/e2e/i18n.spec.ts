import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const LANGUAGES = ['th', 'vi', 'en', 'ko'];

const TARGET_PAGES = [
    { name: '01_landing', url: '/' },
    { name: '02_signup', url: '/?mode=signup' },
    { name: '03_login', url: '/?mode=signin' },
    { name: '04_dashboard', url: '/dashboard' }
];

test.describe('AIR-0156E Browser-based Thai & Vietnamese UX Validation', () => {
    for (const lang of LANGUAGES) {
        test.describe(`Language: ${lang}`, () => {
            for (const target of TARGET_PAGES) {
                test(`Check overflow and screenshot for ${target.name}`, async ({ page, isMobile }) => {
                    const viewportType = isMobile ? 'mobile' : 'desktop';
                    
                    // Attempt to load the page with the language parameter
                    const fullUrl = `${target.url}${target.url.includes('?') ? '&' : '?'}lang=${lang}`;
                    await page.goto(fullUrl, { waitUntil: 'networkidle' });

                    // Check for overflows
                    const overflowNodes = await page.evaluate(() => {
                        const overflows: string[] = [];
                        const elements = document.querySelectorAll('button, input, label, .modal, .toast, .card, table, nav, aside, header, p, span, div');
                        elements.forEach(el => {
                            if (el.scrollWidth > el.clientWidth) {
                                const text = (el.textContent || '').trim().substring(0, 30);
                                overflows.push(`Tag: ${el.tagName}, Class: ${el.className}, Text: ${text}`);
                            }
                        });
                        return overflows;
                    });

                    if (overflowNodes.length > 0) {
                        console.log(`[OVERFLOW WARNING] [${lang}] [${viewportType}] [${target.name}]:`, overflowNodes);
                    }

                    // Save screenshots
                    const dirPath = path.resolve(`docs/screenshots/i18n_e2e/${lang}`);
                    if (!fs.existsSync(dirPath)) {
                        fs.mkdirSync(dirPath, { recursive: true });
                    }
                    
                    await page.screenshot({ path: `${dirPath}/${viewportType}_${target.name}.png`, fullPage: true });
                });
            }
        });
    }
});
