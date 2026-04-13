/**
 * Brand Style Extractor
 *
 * Run this in browser DevTools console on any website to extract brand styles.
 * Copy the output and update brand-config.json + brand-guidelines.md
 *
 * Usage:
 * 1. Go to your website (e.g. https://yourcompany.com)
 * 2. Open DevTools (F12)
 * 3. Go to Console tab
 * 4. Paste this entire script and press Enter
 * 5. Copy the JSON output → update brand-config.json
 */

(function extractBrandStyles() {
  const results = {
    timestamp: new Date().toISOString(),
    url: window.location.href,
    colors: {},
    fonts: {},
    cssVariables: {},
    buttons: [],
    headings: [],
  };

  // ── 1. Extract CSS Variables from :root ────────────────────────────

  try {
    for (const sheet of document.styleSheets) {
      try {
        for (const rule of sheet.cssRules) {
          if (rule.selectorText === ':root' || rule.selectorText === 'html') {
            const style = rule.style;
            for (let i = 0; i < style.length; i++) {
              const prop = style[i];
              if (prop.startsWith('--')) {
                results.cssVariables[prop] = style.getPropertyValue(prop).trim();
              }
            }
          }
        }
      } catch (e) {
        // Cross-origin stylesheet, skip
      }
    }
  } catch (e) {
    console.log('Could not access all stylesheets');
  }

  // ── 2. Extract colors from key elements ────────────────────────────

  const colorElements = {
    'body': document.body,
    'header': document.querySelector('header'),
    'nav': document.querySelector('nav'),
    'main': document.querySelector('main'),
    'footer': document.querySelector('footer'),
    'h1': document.querySelector('h1'),
    'h2': document.querySelector('h2'),
    'p': document.querySelector('p'),
    'a': document.querySelector('a'),
    'button': document.querySelector('button'),
    'primaryButton': document.querySelector('.btn-primary, .button-primary, [class*="primary"]'),
    'logo': document.querySelector('[class*="logo"], .logo, #logo'),
  };

  Object.entries(colorElements).forEach(([name, el]) => {
    if (el) {
      const style = getComputedStyle(el);
      results.colors[name] = {
        color: style.color,
        backgroundColor: style.backgroundColor,
        borderColor: style.borderColor,
      };
    }
  });

  // ── 3. Extract font families ───────────────────────────────────────

  const fontElements = ['body', 'h1', 'h2', 'h3', 'p', 'button'];
  fontElements.forEach(selector => {
    const el = document.querySelector(selector);
    if (el) {
      const style = getComputedStyle(el);
      results.fonts[selector] = {
        fontFamily: style.fontFamily,
        fontSize: style.fontSize,
        fontWeight: style.fontWeight,
        lineHeight: style.lineHeight,
      };
    }
  });

  // ── 4. Collect unique colors ───────────────────────────────────────

  const allColors = new Set();
  document.querySelectorAll('*').forEach(el => {
    const style = getComputedStyle(el);
    ['color', 'backgroundColor', 'borderColor'].forEach(prop => {
      const value = style[prop];
      if (value && value !== 'rgba(0, 0, 0, 0)' && value !== 'transparent') {
        allColors.add(value);
      }
    });
  });
  results.uniqueColors = Array.from(allColors).slice(0, 30);

  // ── 5. Extract button styles ───────────────────────────────────────

  document.querySelectorAll('button, .btn, [class*="button"]').forEach((btn, i) => {
    if (i < 5) {
      const style = getComputedStyle(btn);
      results.buttons.push({
        text: btn.textContent.trim().substring(0, 30),
        className: btn.className,
        backgroundColor: style.backgroundColor,
        color: style.color,
        borderRadius: style.borderRadius,
        padding: style.padding,
      });
    }
  });

  // ── 6. Extract heading styles ──────────────────────────────────────

  ['h1', 'h2', 'h3'].forEach(tag => {
    const el = document.querySelector(tag);
    if (el) {
      const style = getComputedStyle(el);
      results.headings.push({
        tag,
        fontFamily: style.fontFamily,
        fontSize: style.fontSize,
        fontWeight: style.fontWeight,
        color: style.color,
        lineHeight: style.lineHeight,
      });
    }
  });

  // ── 7. RGB to HEX helper ──────────────────────────────────────────

  function rgbToHex(rgb) {
    if (!rgb || rgb === 'transparent') return null;
    const match = rgb.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    if (match) {
      const r = parseInt(match[1]).toString(16).padStart(2, '0');
      const g = parseInt(match[2]).toString(16).padStart(2, '0');
      const b = parseInt(match[3]).toString(16).padStart(2, '0');
      return `#${r}${g}${b}`.toUpperCase();
    }
    return rgb;
  }

  // ── 8. Generate brand-config.json template ─────────────────────────

  const primaryBg = rgbToHex(results.colors.primaryButton?.backgroundColor)
    || rgbToHex(results.colors.button?.backgroundColor)
    || '#3B82F6';
  const bodyBg = rgbToHex(results.colors.body?.backgroundColor) || '#FFFFFF';
  const bodyText = rgbToHex(results.colors.body?.color) || '#1E293B';
  const headingText = rgbToHex(results.colors.h1?.color) || bodyText;
  const fontFamily = results.fonts.body?.fontFamily.split(',')[0].replace(/['"]/g, '').trim() || 'Inter';

  const brandConfig = {
    company: {
      name: document.title.split(/[|\-–]/)[0].trim(),
      url: window.location.origin,
      tagline: document.querySelector('meta[name="description"]')?.content || '',
    },
    logo: {
      light: 'assets/branding/logo-light.svg',
      dark: 'assets/branding/logo-dark.svg',
      fallback_text: true,
    },
    colors: {
      primary: primaryBg,
      primary_light: primaryBg,
      secondary: rgbToHex(results.colors.a?.color) || '#10B981',
      background: bodyBg,
      background_dark: '#0F172A',
      background_card: '#F8FAFC',
      text_primary: headingText,
      text_secondary: bodyText,
      text_muted: '#94A3B8',
      border: '#E2E8F0',
      success: '#22C55E',
      warning: '#F59E0B',
      error: '#EF4444',
    },
    typography: {
      font_family: `${fontFamily}, system-ui, -apple-system, sans-serif`,
      font_family_mono: 'JetBrains Mono, monospace',
      heading_weight: results.fonts.h1?.fontWeight || '700',
      body_weight: results.fonts.body?.fontWeight || '400',
    },
    report: {
      show_logo: true,
      show_footer: true,
      footer_text: `Generated with Nodeshub SEO Skills`,
      date_format: 'YYYY-MM-DD',
    },
  };

  // ── Output ─────────────────────────────────────────────────────────

  console.log('\n========== BRAND STYLES EXTRACTED ==========\n');
  console.log('Raw data:');
  console.log(JSON.stringify(results, null, 2));
  console.log('\n========== brand-config.json ==========\n');
  console.log(JSON.stringify(brandConfig, null, 2));
  console.log('\n========== Copy the above into assets/branding/brand-config.json ==========\n');

  return { raw: results, brandConfig };
})();
