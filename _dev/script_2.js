
        // Global Language Switcher
        async function changeGlobalLanguage(lang) {
            try {
                const res = await fetch('/api/settings/language', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ lang: lang })
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    // Show animation or toast
                    Utils.showToast('Language changing...', 'success');
                    setTimeout(() => window.location.reload(), 500);
                }
            } catch (e) {
                console.error("Language switch failed:", e);
                Utils.showToast('Failed to switch language', 'error');
            }
        }

        // Highlight current lang
        document.addEventListener('DOMContentLoaded', () => {
            // current_lang is injected by Jinja2, but we can't access it easily in JS variable unless we distinct it.
            // But we can check the html lang attribute if set, or just use server logic.
            // Ideally visual feedback is good.
            // Let's assume re-render handles it, but for active state:
            // We can check cookies? Or just reliance on reload.
        });
    