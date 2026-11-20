"""Self-contained browser handoff for desktop Google sign-in.

Keep the page in the server package so cloud archives need no static assets.
"""
from __future__ import annotations

from html import escape
import secrets
from string import Template
from typing import Literal

from fastapi.responses import HTMLResponse


CallbackStatus = Literal['success', 'cancelled', 'failed', 'inactive']

COPY = {
    'uk': {
        'provider': 'Вхід через Google',
        'close': 'Закрити вкладку',
        'manual': 'Цю вкладку можна закрити вручну.',
        'blocked': 'Браузер залишив вкладку відкритою. Закрийте її вручну й поверніться до Backalor.',
        'next': 'Поверніться до застосунку',
        'retry': 'У вікні Backalor натисніть «Продовжити з Google», щоб спробувати ще раз.',
        'success': ('Ви увійшли в Backalor', 'Ваш обліковий запис Google підтверджено. Усе готово, щоб продовжити роботу з проєктами.'),
        'continue': 'Відкрийте вікно Backalor. Застосунок продовжить вхід автоматично.',
        'cancelled': ('Вхід скасовано', 'Ви не завершили вхід через Google. Коли будете готові, можна спробувати знову.'),
        'failed': ('Не вдалося увійти', 'Не вдалося підтвердити обліковий запис Google. Розпочніть вхід ще раз у застосунку.'),
        'inactive': ('Цей запит уже неактивний', 'Час очікування минув або це посилання вже використано. Розпочніть новий вхід у Backalor.'),
        'footer': 'Можна закрити браузер і повернутися до роботи.',
    },
    'sk': {
        'provider': 'Prihlásenie cez Google',
        'close': 'Zavrieť kartu',
        'manual': 'Túto kartu môžete zavrieť ručne.',
        'blocked': 'Prehliadač nechal kartu otvorenú. Zavrite ju ručne a vráťte sa do aplikácie Backalor.',
        'next': 'Vráťte sa do aplikácie',
        'retry': 'V aplikácii Backalor kliknite na „Pokračovať cez Google“ a skúste to znova.',
        'success': ('Ste prihlásení do Backalor', 'Váš účet Google bol overený. Všetko je pripravené na pokračovanie v práci s projektmi.'),
        'continue': 'Otvorte okno aplikácie Backalor. Aplikácia automaticky dokončí prihlásenie.',
        'cancelled': ('Prihlásenie bolo zrušené', 'Prihlásenie cez Google ste nedokončili. Keď budete pripravení, môžete to skúsiť znova.'),
        'failed': ('Prihlásenie sa nepodarilo', 'Účet Google sa nepodarilo overiť. Spustite prihlásenie znova v aplikácii.'),
        'inactive': ('Táto požiadavka už nie je aktívna', 'Čas na prihlásenie vypršal alebo bol odkaz už použitý. Spustite nové prihlásenie v aplikácii Backalor.'),
        'footer': 'Môžete zavrieť prehliadač a vrátiť sa k práci.',
    },
    'en': {
        'provider': 'Sign in with Google',
        'close': 'Close this tab',
        'manual': 'You can close this tab manually.',
        'blocked': 'Your browser kept this tab open. Close it manually and return to Backalor.',
        'next': 'Return to the app',
        'retry': 'In Backalor, choose “Continue with Google” to try again.',
        'success': ('You’re signed in to Backalor', 'Your Google account is verified. You’re ready to continue working with your projects.'),
        'continue': 'Open your Backalor window. The app will finish signing you in automatically.',
        'cancelled': ('Sign-in cancelled', 'You haven’t finished signing in with Google. You can try again whenever you’re ready.'),
        'failed': ('We couldn’t sign you in', 'We couldn’t verify your Google account. Start sign-in again in the app.'),
        'inactive': ('This request is no longer active', 'This sign-in link has expired or has already been used. Start a new sign-in in Backalor.'),
        'footer': 'You can close your browser and return to your work.',
    },
}

PAGE = Template('''<!doctype html>
<html lang="$language">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta name="theme-color" content="#182820">
  <title>$title · Backalor</title>
  <style nonce="$nonce">
    :root {
      color-scheme: light;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
      color: #202e26;
      background: #f7f8f5;
      font-synthesis: none;
      -webkit-font-smoothing: antialiased;
      --accent: #206b49;
      --muted: #56665c;
      --line: #d8e0d8;
    }
    * { box-sizing: border-box; }
    [hidden] { display: none !important; }
    body { margin: 0; min-height: 100vh; min-height: 100svh; display: flex; flex-direction: column; }
    ::selection { color: #163f2b; background: #deeee2; }
    .masthead { background: #182820; color: #f1f5ef; }
    .masthead-inner {
      max-width: 72rem; min-height: 5.5rem; margin: 0 auto; padding: 1.25rem 2rem;
      display: flex; align-items: center; justify-content: space-between; gap: 1rem;
    }
    .wordmark { font-size: 1.125rem; font-weight: 600; letter-spacing: .125em; }
    .provider { display: flex; align-items: center; gap: .625rem; color: #b9cfc0; font-size: .875rem; }
    .provider svg { width: 1.125rem; height: 1.125rem; flex: none; }
    main { flex: 1; display: grid; place-items: center; padding: 3.5rem 1.5rem; }
    .confirmation { width: 100%; max-width: 37.5rem; padding: 3rem; background: #fff; border: 1px solid var(--line); border-radius: .875rem; }
    .status-mark {
      display: grid; place-items: center; width: 4.5rem; height: 4.5rem;
      margin-bottom: 2rem; border-radius: 50%; background: #deeee2; color: var(--accent);
    }
    .status-mark svg { width: 2.25rem; height: 2.25rem; }
    .attention .status-mark { background: #f4eae2; color: #8a4b2f; }
    h1 { margin: 0 0 1rem; color: #20392b; font-size: clamp(1.875rem, 4vw, 2.5rem); line-height: 1.16; letter-spacing: -.025em; font-weight: 600; text-wrap: balance; }
    p { margin: 0; font-size: 1rem; line-height: 1.65; }
    .description { color: var(--muted); }
    .handoff { margin-top: 2rem; padding-top: 1.75rem; border-top: 1px solid var(--line); }
    h2 { margin: 0 0 .5rem; font-size: 1rem; line-height: 1.5; font-weight: 600; }
    .instruction { color: var(--muted); }
    button {
      display: inline-flex; align-items: center; justify-content: center; gap: .625rem;
      margin-top: 1.5rem; min-height: 3rem; padding: .75rem 1.25rem;
      border: 1px solid transparent; border-radius: .375rem; background: var(--accent); color: #fff;
      font: inherit; font-size: 1rem; font-weight: 600; line-height: 1.5; cursor: pointer;
      transition: background-color 150ms ease-out;
    }
    button svg { width: 1.125rem; height: 1.125rem; flex: none; }
    button:hover { background: #185639; }
    button:active { background: #163f2b; }
    button:focus-visible { outline: 3px solid #347e55; outline-offset: 4px; }
    .close-help { margin-top: .875rem; font-size: .875rem; color: var(--muted); }
    footer { padding: 0 1.5rem 1.75rem; color: var(--muted); font-size: .875rem; line-height: 1.6; text-align: center; }
    @media (max-width: 40rem) {
      .masthead-inner { min-height: 4.5rem; padding: 1.25rem 1.5rem; flex-wrap: wrap; }
      .provider { font-size: .8125rem; }
      main { padding: 2rem 1rem; }
      .confirmation { padding: 2rem 1.5rem; }
      .status-mark { width: 4rem; height: 4rem; margin-bottom: 1.5rem; }
      button { width: 100%; }
      footer { padding-bottom: 1.25rem; }
    }
    @media (prefers-reduced-motion: reduce) { button { transition: none; } }
    @media (forced-colors: active) { .status-mark { border: 1px solid; } button { border-color: ButtonText; } }
  </style>
</head>
<body>
  <!-- THESIS: A clear browser-to-desktop handoff, extending Backalor's existing sign-in.
       OWN-WORLD: Forest masthead, paper ground, white surface, native system type and green actions.
       STORY: Read the actual sign-in result, return to Backalor, close this browser tab.
       FIRST VIEWPORT: Quiet wordmark above a centered, left-aligned confirmation; result, next step, close action.
       FORM: Narrow extension of the established authentication surface; no new-world seed.
       FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md -->
  <header class="masthead">
    <div class="masthead-inner">
      <span class="wordmark">BACKALOR</span>
      <span class="provider">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path fill="#4285f4" d="M21.6 12.23c0-.71-.06-1.39-.18-2.05H12v3.88h5.38a4.6 4.6 0 0 1-2 3.02v2.51h3.24c1.9-1.75 2.98-4.33 2.98-7.36Z"/>
          <path fill="#34a853" d="M12 22c2.7 0 4.96-.9 6.62-2.41l-3.24-2.51c-.9.6-2.06.97-3.38.97-2.6 0-4.8-1.76-5.59-4.12H3.07v2.59A10 10 0 0 0 12 22Z"/>
          <path fill="#fbbc05" d="M6.41 13.93a6 6 0 0 1 0-3.86V7.48H3.07a10 10 0 0 0 0 9.04l3.34-2.59Z"/>
          <path fill="#ea4335" d="M12 5.95c1.47 0 2.79.5 3.83 1.5l2.87-2.87A9.6 9.6 0 0 0 12 2a10 10 0 0 0-8.93 5.48l3.34 2.59A5.98 5.98 0 0 1 12 5.95Z"/>
        </svg>
        $provider
      </span>
    </div>
  </header>
  <main>
    <section class="confirmation $status_class" aria-labelledby="result-title">
      <div class="status-mark" aria-hidden="true">
        <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">$status_icon</svg>
      </div>
      <h1 id="result-title">$title</h1>
      <p class="description">$description</p>
      <div class="handoff">
        <h2>$next</h2>
        <p class="instruction">$instruction</p>
        <button id="close-tab" type="button" hidden>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17"/></svg>
          $close
        </button>
        <p class="close-help" id="close-help" role="status">$manual</p>
        <template id="close-blocked">$blocked</template>
      </div>
    </section>
  </main>
  <footer>$footer</footer>
  <script nonce="$nonce">
    // OAuth parameters are no longer needed once the server has handled them.
    try { window.history.replaceState(null, '', window.location.pathname); } catch (_) {}
    const closeButton = document.getElementById('close-tab');
    closeButton.hidden = false;
    closeButton.addEventListener('click', () => {
      try { window.close(); } catch (_) {}
      document.getElementById('close-help').textContent = document.getElementById('close-blocked').content.textContent;
    });
  </script>
</body>
</html>''')


def browser_language(accept_language: str) -> str:
    preferences = []
    for item in accept_language.lower().split(','):
        tag, *parameters = item.strip().split(';')
        quality = 1.0
        for parameter in parameters:
            if parameter.strip().startswith('q='):
                try:
                    quality = float(parameter.strip()[2:])
                except ValueError:
                    quality = 0
        language = tag.split('-')[0]
        if language in COPY and 0 < quality <= 1:
            preferences.append((quality, language))
    return max(preferences, key=lambda preference: preference[0])[1] if preferences else 'uk'


def google_callback_page(status: CallbackStatus, accept_language: str = '') -> HTMLResponse:
    language = browser_language(accept_language)
    copy = COPY[language]
    title, description = copy[status]
    nonce = secrets.token_urlsafe(24)
    content = {key: escape(copy[key]) for key in ('provider', 'next', 'close', 'manual', 'blocked', 'footer')}
    content.update(
        language=language, nonce=nonce, title=escape(title), description=escape(description),
        instruction=escape(copy['continue' if status == 'success' else 'retry']),
        status_class='success' if status == 'success' else 'attention',
        status_icon='<path d="m8 16 5 5L24 10"/>' if status == 'success' else '<path d="M16 8v10m0 6h.01"/>',
    )
    return HTMLResponse(PAGE.substitute(content), status_code=200 if status == 'success' else 400, headers={
        'Content-Security-Policy': (
            f"default-src 'none'; style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        ),
        'Content-Language': language,
        'Vary': 'Accept-Language',
    })
