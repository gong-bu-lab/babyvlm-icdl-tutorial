/* ---------------------------------------------------------------------------
 * Private, cookie-free analytics — shared across the lab's four sites.
 *
 * Backend: GoatCounter (https://www.goatcounter.com) — no cookies, no
 * cross-site tracking, no persistent visitor IDs, no consent banner needed.
 *
 * All four sites report into ONE dashboard (babyvlm.goatcounter.com). To keep
 * them apart, every path and event is prefixed with SITE_KEY, so the dashboard
 * reads "challenge/", "workshop/alternate/speakers/", "tutorial/slides-main-deck"
 * and so on. Typing a site key into the dashboard's "Filter paths" box narrows
 * everything to that site.
 *
 * This file is identical across the four repos except for the CONFIG block
 * below. If you change the logic, copy it to all four.
 *
 * What is recorded
 *   <key>/<page>             one per page load
 *   <key>/slides-*, file-*   a PDF or other document was opened
 *   <key>/outbound-*         a click through to an allowlisted site (TRACK below)
 *   <key>/contact-email      a mailto: click
 *   <key>/data-open-*        a collapsible section was expanded
 *   <key>/engagement-scroll-50, -90   reached that % of page height
 *
 * These count link *opens*, not confirmed downloads: static hosting exposes no
 * server logs, and the browser's PDF viewer cannot be observed from the page.
 *
 * Each event fires at most once per page load. Only hosts in COUNT_ONLY_ON are
 * counted, so localhost and preview proxies never reach the dashboard. Add
 * #analytics-debug to any URL to log events to the console instead.
 * ------------------------------------------------------------------------- */
(function () {
  'use strict';

  /* === CONFIG — the only part that differs between sites ================== */
  var CONFIG = {
    SITE_CODE:     'babyvlm',            // GoatCounter account; same for all four
    SITE_KEY:      'tutorial',       // dashboard prefix for this site
    BASE_PATH:     '/babyvlm-icdl-tutorial',      // URL prefix to strip ('' if site is at domain root)
    COUNT_ONLY_ON: ['gong-bu-lab.github.io'],    // hostnames that are counted; everything else is a preview
    // Outbound links are an ALLOWLIST: only hosts listed here are recorded, so the
    // dashboard stays a short list of things worth acting on. Everything else -- speaker
    // homepages, citations, template credits -- is ignored. Add a host to track it.
    // Documents (.pdf and friends) are always tracked whether listed or not; an entry
    // here just gives the file a friendlier name than its filename.
    TRACK:         {
                     'ICDL Tutorial-2.pdf':                       'slides-main-deck',
                     'ICDL Tutorial.pdf':                         'slides-main-deck-v1',
                     '2026-09-14 ICDL BabyView Tutorial[52].pdf': 'slides-babyview-intro',
                     'shawnking98.github.io':                     'outbound-paper',
                     'github.com':                                'outbound-github'
                   },
    TRACK_EMAIL:    false,     // record mailto: clicks
    TRACK_SECTIONS: true,  // record <details> expansions
    RESPECT_DNT:   true,                 // honour Do Not Track / Global Privacy Control
    ALLOW_LOCAL:   false,                // true = count from anywhere, including previews
    SCROLL_DEPTH:  [90],                 // % milestones to record; [] disables
    DEBUG:         false                 // also switched on per-visit with #analytics-debug
  };
  /* ====================================================================== */

  var DEBUG = CONFIG.DEBUG || (location.hash || '').indexOf('analytics-debug') > -1;
  var log = function (msg) {
    if (DEBUG && window.console && console.log) console.log('[analytics] ' + msg);
  };

  if (CONFIG.SITE_CODE === 'YOUR-GOATCOUNTER-CODE' || CONFIG.SITE_KEY.indexOf('__') === 0) {
    if (window.console && console.warn) {
      console.warn('[analytics] Not enabled: CONFIG is still a template.');
    }
    return;
  }

  // Namespaced page path: /babyvlm-challenge/index.html -> challenge/index.html
  var pagePath = function () {
    var p = location.pathname;
    if (CONFIG.BASE_PATH && p.indexOf(CONFIG.BASE_PATH) === 0) p = p.slice(CONFIG.BASE_PATH.length);
    if (p.charAt(0) !== '/') p = '/' + p;
    return CONFIG.SITE_KEY + p;
  };

  // Namespaced event name: outbound-github -> challenge/outbound-github
  var evName = function (n) { return CONFIG.SITE_KEY + '/' + n; };

  // Preview environments must never reach the real dashboard: localhost, an
  // OnDemand proxy, a fork's Pages site, a local checkout. Detection stays live
  // so #analytics-debug still shows what *would* be recorded.
  var SENDING = true;

  if (!CONFIG.ALLOW_LOCAL && CONFIG.COUNT_ONLY_ON.length &&
      CONFIG.COUNT_ONLY_ON.indexOf(location.hostname) === -1) {
    SENDING = false;
    log('preview host "' + location.hostname + '" is not in COUNT_ONLY_ON, so nothing ' +
        'is sent. Events below show what would be recorded on the live site.');
  }

  if (SENDING && CONFIG.RESPECT_DNT &&
      (navigator.doNotTrack === '1' || window.doNotTrack === '1' ||
       navigator.msDoNotTrack === '1' || navigator.globalPrivacyControl === true)) {
    SENDING = false;
    log('disabled: this browser sends Do Not Track / Global Privacy Control');
  }

  var slug = function (s) {
    return s.toLowerCase()
            .replace(/\.[a-z0-9]+$/, '')      // drop extension
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '')
            .slice(0, 60);
  };

  // --- Transport -----------------------------------------------------------
  var queue = [], ready = false;

  var send = function (path, title, isEvent) {
    if (!path) return;
    log((isEvent === false ? 'page   ' : 'event  ') + path + '   (' + (title || '') + ')');
    if (!SENDING) return;
    if (ready && window.goatcounter && typeof window.goatcounter.count === 'function') {
      window.goatcounter.count({ path: path, title: title || path, event: isEvent !== false });
    } else if (queue.length < 50) {
      queue.push([path, title, isEvent]);
    }
  };

  // Fire an event at most once per page load, so a double-click or a repeated
  // scroll past a milestone doesn't inflate the counts.
  var seen = {};
  var sendOnce = function (name, title) {
    var path = evName(name);
    if (seen[path]) return;
    seen[path] = true;
    send(path, title, true);
  };

  window.goatcounter = {
    endpoint:    'https://' + CONFIG.SITE_CODE + '.goatcounter.com/count',
    allow_local: CONFIG.ALLOW_LOCAL,
    path:        pagePath          // namespaces the automatic pageview
  };

  // Record a pageview for a client-side route change (Next.js and friends).
  // Exposed so a framework component can call it; harmless everywhere else.
  window.__labAnalytics = {
    pageview: function () {
      seen = {};                   // new page => event dedup resets
      send(pagePath(), document.title, false);
    }
  };

  if (!SENDING) {
    log('ready (preview mode -- no pageview recorded, no network request made)');
    bindListeners();
    return;
  }

  var s = document.createElement('script');
  s.async = true;
  s.src = 'https://gc.zgo.at/count.js';
  s.onload = function () {
    ready = true;
    for (var i = 0; i < queue.length; i++) send(queue[i][0], queue[i][1], queue[i][2]);
    queue = [];
  };
  s.onerror = function () { queue = []; };
  document.head.appendChild(s);

  log('active for "' + CONFIG.SITE_CODE + '" on ' + location.hostname +
      '; this page load counts as ' + pagePath());

  bindListeners();

  function bindListeners() {
  // --- Click tracking ------------------------------------------------------
  // One delegated listener, capture phase so it still runs if something else
  // stops propagation. It never calls preventDefault, so navigation is
  // untouched. sendBeacon inside count.js survives the page unloading.
  document.addEventListener('click', function (ev) {
    var a = ev.target && ev.target.closest && ev.target.closest('a[href], [data-analytics-event]');
    if (!a) return;

    var override = a.getAttribute('data-analytics-event');
    if (override) {
      sendOnce(override, a.getAttribute('data-analytics-title') || a.textContent.trim());
      return;
    }

    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#') return;      // in-page anchors aren't navigation

    if (href.indexOf('mailto:') === 0) {
      if (CONFIG.TRACK_EMAIL) sendOnce('contact-email', 'Contact e-mail clicked');
      return;
    }

    var url;
    try { url = new URL(href, location.href); } catch (e) { return; }

    // Documents — slide decks, papers, datasets. Always tracked: "were the slides
    // opened" is the question this whole setup exists to answer, so a deck added
    // later is picked up with no code change.
    if (/\.(pdf|zip|csv|tsv|pptx?|docx?)$/i.test(url.pathname)) {
      var file = decodeURIComponent(url.pathname.split('/').pop());
      var name = CONFIG.TRACK[file] || ('file-' + slug(file));
      var where = a.closest('section[id], [id]');
      sendOnce(name, 'Opened: ' + file + (where && where.id ? ' (from #' + where.id + ')' : ''));
      return;
    }

    // Leaving the site — allowlist only, so the dashboard stays legible.
    if (url.origin !== location.origin && /^https?:$/.test(url.protocol)) {
      var host = url.hostname.replace(/^www\./, '');
      var tracked = CONFIG.TRACK[host];
      if (!tracked) return;            // not a key interaction — deliberately ignored
      sendOnce(tracked, 'Outbound: ' + url.hostname + url.pathname);
    }
  }, true);

  // --- Engagement: collapsible sections -------------------------------------
  var details = CONFIG.TRACK_SECTIONS ? document.querySelectorAll('details') : [];
  Array.prototype.forEach.call(details, function (d) {
    d.addEventListener('toggle', function () {
      if (!d.open) return;
      var h = d.querySelector('summary h3, summary h2, summary');
      var label = h ? h.textContent.trim() : 'section';
      sendOnce('data-open-' + slug(label), 'Opened section: ' + label);
    });
  });

  // --- Engagement: scroll depth -------------------------------------------
  if (CONFIG.SCROLL_DEPTH.length) {
    var ticking = false;
    var check = function () {
      ticking = false;
      var doc = document.documentElement;
      var scrollable = doc.scrollHeight - window.innerHeight;
      if (scrollable < 400) return;  // too short for depth to mean anything
      var pct = ((window.scrollY || doc.scrollTop) / scrollable) * 100;
      CONFIG.SCROLL_DEPTH.forEach(function (mark) {
        if (pct >= mark) sendOnce('engagement-scroll-' + mark, 'Scrolled ' + mark + '% of the page');
      });
    };
    window.addEventListener('scroll', function () {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(check);
    }, { passive: true });
  }
  }
})();
