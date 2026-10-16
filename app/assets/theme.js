/* Hell/Dunkel-Einstellung vor dem ersten Zeichnen anwenden (ohne Inline-Skript, wegen Content-Security-Policy) */
try { var t = localStorage.getItem('wochenangebot.theme'); if (t) { t = JSON.parse(t); if (t === 'dark' || t === 'light') document.documentElement.setAttribute('data-theme', t); } } catch (e) { /* ignorieren */ }
