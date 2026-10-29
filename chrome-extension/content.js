// CVtoMatch — 1-Click AI Job Autofill Content Script (v2.6)
// Full-Page Deep Scanner:
// 1. Matches phone country-code dropdown (+40 Romania, +216 Tunisia, etc.) to CV phone/country
// 2. Never fabricates City/Zip/Street if only Country is in the CV
// 3. Leaves Current Job Title as -None- if candidate has no active "Present" job
// 4. Adds ALL tailored skills into Skill Set chips
// 5. Expands "+ Add" and "+ Add More" to fill ALL Education & Experience entries with valid dates
// 6. Attaches Resume PDF once (never duplicates)

(function () {
  const existingHost = document.getElementById("cvtomatch-autofill-host");
  if (existingHost) existingHost.remove();

  const HOST = (window.location.hostname || "").toLowerCase();
  const HREF = window.location.href || "";

  // ─── 1. Web App Auth & Job Handoff Bridge ──────────────────────────────────
  const IS_CVTOMATCH_WEBAPP =
    HOST.includes("cvtomatch.com") ||
    HOST.includes("job-searcher-api") ||
    HOST === "localhost" ||
    HOST === "127.0.0.1";

  function syncFromWebApp() {
    try {
      if (typeof chrome === "undefined" || !chrome.runtime || !chrome.runtime.id) return;
      document.documentElement.setAttribute("data-cvtomatch-extension", "installed");
      const token = localStorage.getItem("token");
      if (token) {
        let user = null;
        try {
          user = JSON.parse(localStorage.getItem("user") || "null");
        } catch (_) {}
        const apiBase =
          window.location.port === "5173"
            ? "http://localhost:8000"
            : window.location.origin;
        chrome.runtime.sendMessage({
          type: "SYNC_TOKEN_FROM_WEBAPP",
          token,
          user,
          apiBase
        });
      }
    } catch (_) {}
  }

  if (IS_CVTOMATCH_WEBAPP) {
    syncFromWebApp();
    window.addEventListener("focus", syncFromWebApp);
    window.addEventListener("message", (event) => {
      if (event.source !== window || !event.data) return;
      if (typeof chrome === "undefined" || !chrome.runtime || !chrome.runtime.id) return;
      if (event.data.type === "CVTOMATCH_EXTENSION_PING") {
        syncFromWebApp();
        window.postMessage({ type: "CVTOMATCH_EXTENSION_PONG", version: "2.6.0" }, "*");
      } else if (event.data.type === "CVTOMATCH_PREPARE_EASY_APPLY") {
        try {
          chrome.runtime.sendMessage({
            type: "SYNC_TOKEN_FROM_WEBAPP",
            token: localStorage.getItem("token") || undefined,
            pendingJob: event.data.job || null
          });
        } catch (_) {}
      }
    });
    return;
  }

  // ─── 2. ATS & Job Application Page Detection ───────────────────────────────
  const ATS_DOMAINS = [
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "myworkdayjobs.com",
    "workday.com",
    "zohorecruit.com",
    "zoho.com",
    "smartrecruiters.com",
    "bamboohr.com",
    "workable.com",
    "breezy.hr",
    "recruitee.com",
    "personio.de",
    "personio.com",
    "icims.com",
    "jobvite.com",
    "taleo.net",
    "dover.com",
    "wellfound.com",
    "teamtailor.com",
    "pinpointhq.com",
    "jazzhr.com",
    "applytojob.com",
    "rippling.com",
    "gusto.com",
    "indeed.com",
    "linkedin.com"
  ];

  function isKnownAtsDomain() {
    return ATS_DOMAINS.some((d) => HOST.includes(d.trim().toLowerCase()));
  }

  // ─── Pre-Apply Job Post Cache & Apply-Click State ──────────────────────────
  const CAPTURED_JOB_TTL_MS = 45 * 60 * 1000; // 45 minutes
  const APPLY_CLICK_TTL_MS = 10 * 60 * 1000; // 10 minutes
  let cachedCapturedJobPost = null;
  let userClickedApply = false;
  let lastApplyClickTs = 0;

  try {
    const rawSavedJob = sessionStorage.getItem("cvtomatch_captured_job_post");
    if (rawSavedJob) {
      const parsed = JSON.parse(rawSavedJob);
      if (parsed && parsed.timestamp && Date.now() - parsed.timestamp < CAPTURED_JOB_TTL_MS) {
        cachedCapturedJobPost = parsed;
      }
    }
    const rawApplyTs = Number(sessionStorage.getItem("cvtomatch_apply_clicked") || "0");
    if (rawApplyTs && Date.now() - rawApplyTs < APPLY_CLICK_TTL_MS) {
      lastApplyClickTs = rawApplyTs;
      if (/\/(apply|application)(\/|$|\?)/i.test(window.location.pathname || "")) {
        userClickedApply = true;
      }
    }
  } catch (_) {}

  if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
    try {
      chrome.storage.local.get(["cvtomatch_captured_job_post", "cvtomatch_apply_clicked"], (res) => {
        if (chrome.runtime && chrome.runtime.lastError) return;
        const storedJob = res && res.cvtomatch_captured_job_post;
        if (
          storedJob &&
          storedJob.timestamp &&
          Date.now() - storedJob.timestamp < CAPTURED_JOB_TTL_MS &&
          (!cachedCapturedJobPost || storedJob.timestamp >= cachedCapturedJobPost.timestamp)
        ) {
          cachedCapturedJobPost = storedJob;
          refreshMountedWidgetJobMeta();
        }
        const storedClick = res && res.cvtomatch_apply_clicked;
        if (storedClick && storedClick.timestamp && Date.now() - storedClick.timestamp < APPLY_CLICK_TTL_MS) {
          if (storedClick.timestamp > lastApplyClickTs) lastApplyClickTs = storedClick.timestamp;
          if (
            /\/(apply|application)(\/|$|\?)/i.test(window.location.pathname || "") ||
            Date.now() - storedClick.timestamp < 15000
          ) {
            userClickedApply = true;
            mountFloatingWidget();
          }
        }
      });
      if (chrome.storage.onChanged) {
        chrome.storage.onChanged.addListener((changes, area) => {
          if (area === "local" && changes.cvtomatch_captured_job_post && changes.cvtomatch_captured_job_post.newValue) {
            cachedCapturedJobPost = changes.cvtomatch_captured_job_post.newValue;
            refreshMountedWidgetJobMeta();
          }
        });
      }
    } catch (_) {}
  }

  function isGenuineJobDescription(text) {
    if (!text || typeof text !== "string") return false;
    const clean = text.trim();
    if (clean.length < 140) return false;
    if (/\b(afghan\s*\(afghanistan\)|albanian\s*\(albania\)|abkhaz|escolher\s*ficheiros?)\b/i.test(clean)) {
      return false;
    }
    if (clean.includes("Cross-platform mobile & web engineering, Flutter, Dart, BLoC, Riverpod")) {
      return false;
    }
    const signalMatches = clean.match(
      /\b(responsibilities|requirements|qualifications|experience|skills|about\s+(the\s+role|us|the\s+job|you)|what\s+you('ll|\s+will)|who\s+you\s+are|we\s+are\s+looking|role|position|team|benefits|mission|duties|years|degree|bachelor|engineer|developer|software|design|build|maintain|collaborate|architecture)\b/gi
    );
    return Boolean(signalMatches && signalMatches.length >= 2);
  }

  function isGenericJobTitle(title) {
    if (!title) return true;
    const t = title.trim();
    if (t.length < 3) return true;
    return /^(basic\s*info|job\s*application|apply(\s*now|\s*for\s*this\s*job)?|application(\s*form)?|personal\s*information|candidate\s*profile|careers?|jobs?|submit\s*application|resume|cv)$/i.test(
      t
    );
  }

  function isGenericCompanyName(comp) {
    if (!comp) return true;
    const c = comp.trim();
    if (c.length < 2) return true;
    return /^(the\s+hiring\s+team|company|careers?|jobs?|apply|smartrecruiters|linkedin|indeed|workable|greenhouse|lever)$/i.test(
      c
    );
  }

  function scrapeRawJobContextFromPage() {
    let jobTitle = "";
    let company = "";
    let rawDescription = "";

    const ghTitle = document.querySelector(
      ".app-title, h1.section-header, .job-details-jobs-unified-top-card__job-title, .top-card-layout__title, .cw-jobheader-title, [data-testid*='job-title' i], .job-title"
    );
    const ghCompany = document.querySelector(
      ".company-name, .job-details-jobs-unified-top-card__company-name, .topcard__org-name-link, [data-testid*='company-name' i]"
    );
    const leverTitle = document.querySelector(".posting-headline h2");
    const ashbyTitle = document.querySelector("h1[class*='Heading'], h1, h2");
    const h1 = ghTitle || leverTitle || ashbyTitle;

    if (h1 && h1.innerText) {
      const candidateTitle = h1.innerText.trim().split("\n")[0].slice(0, 120);
      if (!isGenericJobTitle(candidateTitle)) {
        jobTitle = candidateTitle;
      }
    }

    if (ghCompany && ghCompany.innerText) {
      company = ghCompany.innerText.replace(/^at\s+/i, "").trim().split("\n")[0];
    }

    if (!company && HOST.includes("smartrecruiters.com")) {
      const pathParts = (window.location.pathname || "").split("/").filter(Boolean);
      if (pathParts[0] && !/^(jobs|apply|app|candidate)$/i.test(pathParts[0])) {
        company = pathParts[0].replace(/[-_]+/g, " ").trim();
      }
    }

    if (!company || !jobTitle) {
      const titleParts = (document.title || "")
        .split(/\s*[\-|–|—|@|\|]\s*/)
        .map((s) => s.trim())
        .filter((s) => s && !isGenericJobTitle(s) && !/^(smartrecruiters|easy\s*apply)$/i.test(s));
      if (!jobTitle && titleParts[0]) jobTitle = titleParts[0];
      if (!company) {
        const compCand = titleParts.find(
          (p) => !jobTitle || p.toLowerCase() !== jobTitle.toLowerCase()
        );
        if (compCand) company = compCand.replace(/\b(careers?|jobs?)\b/gi, "").trim();
      }
    }

    if (company && jobTitle && company.toLowerCase() === jobTitle.toLowerCase()) {
      company = "";
    }

    const explicitDescEl = document.querySelector(
      "#job-details, .jobs-description__content, .jobs-box__html-content, .posting-page, [class*='job-description' i], [id*='job-description' i], [itemprop='description'], [data-testid*='job-description' i], .job-details-content, .description__text"
    );
    const fallbackDescEl =
      document.querySelector("#content, [class*='description'], [id*='description'], main, article") ||
      document.body;
    const descEl = explicitDescEl || fallbackDescEl;

    if (descEl) {
      try {
        const clone = descEl.cloneNode(true);
        clone
          .querySelectorAll(
            "form, select, option, input, textarea, button, label, .select2-container, nav, header, footer, script, style, #cvtomatch-autofill-host, .jobs-easy-apply-modal"
          )
          .forEach((n) => n.remove());
        rawDescription = (clone.innerText || clone.textContent || "").replace(/\s+/g, " ").trim().slice(0, 5000);
      } catch (_) {
        rawDescription = (descEl.innerText || "").replace(/\s+/g, " ").trim().slice(0, 5000);
      }
    }

    return {
      jobTitle,
      company,
      rawDescription,
      hasExplicitDescEl: Boolean(explicitDescEl)
    };
  }

  function captureJobPostIfPresent(forceSave = false) {
    try {
      const raw = scrapeRawJobContextFromPage();
      const isApplyUrl = /\/(apply|application)(\/|$|\?)/i.test(window.location.pathname || "");
      const descIsGenuine = isGenuineJobDescription(raw.rawDescription);

      if (!descIsGenuine && !(forceSave && !isApplyUrl && raw.rawDescription.length >= 100)) {
        return cachedCapturedJobPost;
      }

      // Avoid overwriting a full job description captured before clicking Apply with shorter text on an /apply page
      if (
        isApplyUrl &&
        !raw.hasExplicitDescEl &&
        cachedCapturedJobPost &&
        cachedCapturedJobPost.job_description &&
        cachedCapturedJobPost.job_description.length >= raw.rawDescription.length
      ) {
        return cachedCapturedJobPost;
      }

      const record = {
        job_title: !isGenericJobTitle(raw.jobTitle)
          ? raw.jobTitle
          : (cachedCapturedJobPost && cachedCapturedJobPost.job_title) || "",
        company: !isGenericCompanyName(raw.company)
          ? raw.company
          : (cachedCapturedJobPost && cachedCapturedJobPost.company) || "",
        job_description: raw.rawDescription,
        job_url: window.location.href || HREF,
        host: HOST,
        timestamp: Date.now()
      };

      cachedCapturedJobPost = record;
      try {
        sessionStorage.setItem("cvtomatch_captured_job_post", JSON.stringify(record));
      } catch (_) {}
      if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
        try {
          chrome.storage.local.set({ cvtomatch_captured_job_post: record });
        } catch (_) {}
      }
      return record;
    } catch (_) {
      return cachedCapturedJobPost;
    }
  }

  function isNonApplicationSearchOrNavInput(el) {
    if (!el) return true;
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (type === "search" || type === "password" || type === "hidden") return true;
    const attrs = [
      el.getAttribute("name") || "",
      el.getAttribute("id") || "",
      el.getAttribute("placeholder") || "",
      el.getAttribute("aria-label") || "",
      el.className && typeof el.className === "string" ? el.className : ""
    ]
      .join(" ")
      .toLowerCase();
    if (
      /\b(search|keyword|job[\s_-]*title[\s_-]*or|location[\s_-]*search|filter|sort[\s_-]*by|newsletter|subscribe|alert|login|sign[\s_-]*in|cookie|captcha)\b/i.test(
        attrs
      )
    ) {
      return true;
    }
    if (
      closestDeep(
        el,
        "nav, header, footer, [role='search'], [role='navigation'], .jobs-search-box, .search-bar, .cookie-banner, #onetrust-banner-sdk"
      )
    ) {
      return true;
    }
    return false;
  }

  function hasApplicationFormOnPage() {
    // 1. Check if an explicit in-page application modal / drawer is open with inputs
    const openApplyModal = document.querySelector(
      ".jobs-easy-apply-modal, .jobs-easy-apply-content, [data-test-modal-id='easy-apply-modal'], spl-job-apply, [class*='apply-modal' i], [id*='apply-modal' i]"
    );
    if (openApplyModal) {
      const rect = openApplyModal.getBoundingClientRect();
      if (rect.width > 100 && rect.height > 100) {
        const modalInputs = getEditableFormInputs(openApplyModal);
        if (modalInputs.length >= 1) return true;
      }
    }

    // 2. Count genuine candidate application inputs (excluding search bars, nav, login, filters)
    const allEditable = getEditableFormInputs().filter((el) => !isNonApplicationSearchOrNavInput(el));
    if (allEditable.length === 0) return false;

    const fileInputs = querySelectorAllDeep('input[type="file"]').filter(
      (el) => !closestDeep(el, "#cvtomatch-autofill-host")
    );
    const nonFileInputs = allEditable.filter(
      (el) => (el.getAttribute("type") || "").toLowerCase() !== "file"
    );

    // A page with a Resume/CV file input + at least 2 visible candidate fields is an active application form
    if (fileInputs.length >= 1 && nonFileInputs.length >= 2) return true;

    // Dedicated /apply URL with visible form inputs
    const isApplyUrl =
      /\/(apply|application)(\/|$|\?)/i.test(window.location.pathname || "") ||
      /[?&](apply|application)=/i.test(window.location.search || "");
    if (isApplyUrl && nonFileInputs.length >= 2) return true;

    // Otherwise require at least 3 visible candidate fields AND explicit candidate form signals (email/phone/resume/experience)
    if (nonFileInputs.length >= 3) {
      let candidateSignalCount = 0;
      for (const el of nonFileInputs) {
        const type = (el.getAttribute("type") || "").toLowerCase();
        const sig = [
          type,
          el.getAttribute("name") || "",
          el.getAttribute("id") || "",
          el.getAttribute("placeholder") || "",
          el.getAttribute("aria-label") || "",
          el.getAttribute("autocomplete") || ""
        ]
          .join(" ")
          .toLowerCase();
        if (
          type === "email" ||
          type === "tel" ||
          /\b(first[\s_-]*name|last[\s_-]*name|full[\s_-]*name|candidate|email|phone|mobile|resume|cv|cover[\s_-]*letter|linkedin|nationality|experience|education|salary)\b/i.test(
            sig
          )
        ) {
          candidateSignalCount++;
        }
      }
      if (candidateSignalCount >= 2) return true;
    }

    return false;
  }

  function shouldShowFloatingPopup() {
    if (hasApplicationFormOnPage()) return true;
    if (userClickedApply) {
      const candidateInputs = getEditableFormInputs().filter((el) => !isNonApplicationSearchOrNavInput(el));
      const isApplyUrl = /\/(apply|application)(\/|$|\?)/i.test(window.location.pathname || "");
      if (candidateInputs.length >= 1 || isApplyUrl) return true;
    }
    return false;
  }

  // ─── 3. Page Metadata Extractor (Job Title, Company, Description) ──────────
  function extractJobContext() {
    // Capture current page job post if we are on a job description view
    captureJobPostIfPresent(false);

    const raw = scrapeRawJobContextFromPage();
    const hasFreshCache =
      cachedCapturedJobPost &&
      cachedCapturedJobPost.timestamp &&
      Date.now() - cachedCapturedJobPost.timestamp < CAPTURED_JOB_TTL_MS;

    let jobTitle = !isGenericJobTitle(raw.jobTitle) ? raw.jobTitle : "";
    let company = !isGenericCompanyName(raw.company) ? raw.company : "";
    let description = "";

    if (!jobTitle && hasFreshCache && cachedCapturedJobPost.job_title) {
      jobTitle = cachedCapturedJobPost.job_title;
    }
    if (!company && hasFreshCache && cachedCapturedJobPost.company) {
      company = cachedCapturedJobPost.company;
    }

    const isApplyUrl = /\/(apply|application)(\/|$|\?)/i.test(window.location.pathname || "");
    const rawDescIsGenuine = isGenuineJobDescription(raw.rawDescription);

    // Prefer the pre-Apply captured job description when on an /apply form page or when current page lacks the job description
    if (
      hasFreshCache &&
      cachedCapturedJobPost.job_description &&
      (!rawDescIsGenuine ||
        (isApplyUrl &&
          !raw.hasExplicitDescEl &&
          cachedCapturedJobPost.job_description.length > raw.rawDescription.length))
    ) {
      description = cachedCapturedJobPost.job_description;
    } else if (rawDescIsGenuine) {
      description = raw.rawDescription;
    } else if (hasFreshCache && cachedCapturedJobPost.job_description) {
      description = cachedCapturedJobPost.job_description;
    } else if (
      raw.rawDescription &&
      raw.rawDescription.length >= 90 &&
      !/\bafghan\s*\(afghanistan\)/i.test(raw.rawDescription)
    ) {
      description = raw.rawDescription;
    } else {
      description = `${jobTitle || "Flutter Developer"} — Cross-platform mobile & web engineering, Flutter, Dart, BLoC, Riverpod, REST APIs, Firebase, Git, CI/CD, and clean architecture.`;
    }

    return {
      job_title: jobTitle || "Software Engineer",
      company: company || "the hiring team",
      job_description: description,
      job_url: (hasFreshCache && cachedCapturedJobPost.job_url) || window.location.href || HREF
    };
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // ─── 4. Auto-Open Application Modal & Expand Repeater Sections ("+ Add" / "+ Add More") ───
  async function ensureApplicationFormOpen() {
    if (HOST.includes("linkedin.com")) {
      const modalOpen = document.querySelector(
        ".jobs-easy-apply-modal, .jobs-easy-apply-content, [data-test-modal-id='easy-apply-modal']"
      );
      if (!modalOpen) {
        const easyApplyBtn = document.querySelector(
          ".jobs-apply-button, button[aria-label*='Easy Apply'], button[aria-label*='Candidature simplifiée']"
        );
        if (easyApplyBtn) {
          easyApplyBtn.click();
          await sleep(900);
        }
      }
    } else if (HOST.includes("zohorecruit.com") || HOST.includes("zoho.com")) {
      const visibleInputs = getEditableFormInputs();
      if (visibleInputs.length < 3) {
        const applyBtn = Array.from(document.querySelectorAll("button, lyte-button, a")).find(
          (el) =>
            /i'm interested|apply now|apply for this job/i.test(el.innerText || "") &&
            !isNavigationOrSubmitElement(el)
        );
        if (applyBtn) {
          applyBtn.click();
          await sleep(1200);
        }
      }
    }
  }

  // Safety guard: NEVER click any Next, Continue, Review, Save, or Submit button — only fill fields!
  function isNavigationOrSubmitElement(el) {
    if (!el) return true;
    const type = (el.getAttribute && (el.getAttribute("type") || "")).toLowerCase();
    if (type === "submit" || type === "reset") return true;
    const text = (
      (el.innerText || el.textContent || "") +
      " " +
      (el.getAttribute ? el.getAttribute("aria-label") || "" : "") +
      " " +
      (el.getAttribute ? el.getAttribute("data-zcqa") || "" : "") +
      " " +
      (el.value || "")
    )
      .toLowerCase()
      .trim();
    return /\b(submit|next|continue|review|send\s*application|finish|save|proceed|suivant|envoyer|soumettre)\b/i.test(
      text
    );
  }

  // Expands Zoho / ATS repeater sections to match the exact number of Education & Experience entries in the CV
  async function expandRepeaterSectionsForCount(eduTargetCount, expTargetCount) {
    // 1. Expand Educational Details up to eduTargetCount (re-querying live DOM each step since Zoho replaces the button)
    for (let step = 0; step < eduTargetCount + 1; step++) {
      const currentEduEntries = document.querySelectorAll(
        "rec-tabular-component [aria-label*='Educational Details : Entry' i]"
      ).length;
      if (currentEduEntries >= eduTargetCount) break;
      const eduAddBtn = document.querySelector(
        "button.tabular-group-add[aria-label*='Educational' i]"
      );
      if (!eduAddBtn || isNavigationOrSubmitElement(eduAddBtn)) break;
      eduAddBtn.click();
      await sleep(450);
    }

    // 2. Expand Experience Details up to expTargetCount (re-querying live DOM each step)
    for (let step = 0; step < expTargetCount + 1; step++) {
      const currentExpEntries = document.querySelectorAll(
        "rec-tabular-component [aria-label*='Experience Details : Entry' i]"
      ).length;
      if (currentExpEntries >= expTargetCount) break;
      const expAddBtn = document.querySelector(
        "button.tabular-group-add[aria-label*='Experience' i]"
      );
      if (!expAddBtn || isNavigationOrSubmitElement(expAddBtn)) break;
      expAddBtn.click();
      await sleep(450);
    }
  }

  // Deep querySelectorAll that traverses both standard DOM and open Shadow Roots (e.g. SmartRecruiters <spl-*>, Workday)
  function querySelectorAllDeep(selector, rootNode = document) {
    const results = [];
    const seen = new Set();

    function traverse(node) {
      if (!node) return;
      if (node.id === "cvtomatch-autofill-host") return;
      try {
        if (node.querySelectorAll) {
          const matched = node.querySelectorAll(selector);
          for (const m of matched) {
            if (!seen.has(m)) {
              seen.add(m);
              results.push(m);
            }
          }
        }
      } catch (_) {}

      // Traverse into open shadowRoot of the current node if present
      if (node.shadowRoot) {
        traverse(node.shadowRoot);
      }

      const children = node.children || (node.childNodes ? Array.from(node.childNodes) : []);
      for (const child of children) {
        if (child.id === "cvtomatch-autofill-host") continue;
        if (child.shadowRoot || (child.children && child.children.length > 0)) {
          traverse(child);
        }
      }
    }

    traverse(rootNode);
    return results;
  }

  function getParentOrShadowHost(node) {
    if (!node) return null;
    if (node.parentElement) return node.parentElement;
    const root = node.getRootNode && node.getRootNode();
    if (root && root.host) return root.host;
    return null;
  }

  function closestDeep(node, selector) {
    let cur = node;
    while (cur && cur !== document && cur !== document.documentElement) {
      if (cur.matches && cur.matches(selector)) return cur;
      cur = getParentOrShadowHost(cur);
    }
    return null;
  }

  function containsDeep(container, node) {
    if (!container || !node) return false;
    let cur = node;
    while (cur) {
      if (cur === container) return true;
      if (container.contains && container.contains(cur)) return true;
      cur = getParentOrShadowHost(cur);
    }
    return false;
  }

  function getEditableFormInputs(rootNode = null) {
    const dialogs = Array.from(
      document.querySelectorAll(".jobs-easy-apply-modal, .artdeco-modal, [role='dialog'][aria-modal='true']")
    ).filter((d) => {
      const r = d.getBoundingClientRect();
      return r.width > 120 && r.height > 120 && d.querySelectorAll("input, textarea, select").length > 0;
    });
    const root = rootNode || dialogs[0] || document;

    const rawInputs = querySelectorAllDeep(
      'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="search"]):not([disabled]):not([readonly]), textarea:not([disabled]):not([readonly]), select:not([disabled])',
      root
    );

    return rawInputs.filter((el) => {
      if (closestDeep(el, "#cvtomatch-autofill-host")) return false;
      if (closestDeep(el, ".global-nav, header.global-nav, .jobs-search-box, [role='search']")) {
        return false;
      }
      const zcqa = (el.getAttribute("data-zcqa") || "").toLowerCase();
      if (zcqa === "rec-sel_search" || closestDeep(el, "lyte-drop-box")) return false;

      const rect = el.getBoundingClientRect();
      const type = (el.getAttribute("type") || "").toLowerCase();
      if (type !== "file" && rect.width === 0 && rect.height === 0) return false;
      return true;
    });
  }

  // ─── 5. Precision DOM-Proximity Label Resolver ─────────────────────────────
  function cleanCandidateLabelText(raw) {
    if (!raw) return "";
    const lines = String(raw)
      .split(/\r?\n/)
      .map((l) =>
        l
          .replace(/^(?:manual|rec)[_\-\s$]+/i, "")
          .replace(/__s$/i, "")
          .replace(/[_\-]?\d+[_\-]\d+$/g, "")
          .replace(/[_\-$]+/g, " ")
          .replace(/\*/g, "")
          .replace(/\s+/g, " ")
          .trim()
      )
      .filter((l) => {
        if (!l) return false;
        const low = l.toLowerCase();
        if (
          low === "value" ||
          low === "manual" ||
          low === "rec" ||
          low === "sel" ||
          low === "sel search" ||
          low === "clear" ||
          low === "-none-" ||
          low === "none" ||
          low === "browse" ||
          low === "escolher ficheiro" ||
          low === "choose file" ||
          low === "no file chosen" ||
          low === "select file" ||
          low === "choisir un fichier" ||
          low === "aucun fichier" ||
          low === "seleccionar archivo" ||
          low === "+ add" ||
          low === "add" ||
          low === "add more" ||
          low === "delete" ||
          low === "master" ||
          low === "intermediate" ||
          low === "beginner" ||
          low.startsWith("(+") ||
          low.startsWith("rec form") ||
          low.startsWith("please enter a valid") ||
          low.includes("ficheiro seleccionado") ||
          low.includes("ficheiro selecionado") ||
          low.includes("file selected") ||
          low.includes("exceeds the maximum length") ||
          low.includes("file type is not supported") ||
          low.includes("cannot be empty") ||
          low.includes("is required") ||
          low.includes("are required") ||
          low.includes("fields marked") ||
          low.includes("marked with") ||
          low.includes("choose an option to autocomplete") ||
          low.includes("fill your profile manually") ||
          low.includes("size limit") ||
          low.includes("i bring ") ||
          low.includes("i most recently worked on") ||
          low.includes("in my most recent ") ||
          low.includes("yes, i have worked on") ||
          low.includes("{") ||
          low.includes("}") ||
          low.startsWith(":host")
        ) {
          return false;
        }
        return l.length >= 2 && l.length <= 420;
      });
    if (
      lines.length >= 2 &&
      /^(if\s+so|please\s+|specify\s+|include\s+|including\s+|can\s+you|provide\s+|share\s+|explain\s+|whether\s+)/i.test(
        lines[1]
      )
    ) {
      return `${lines[0]} ${lines[1]}`.slice(0, 420);
    }
    return lines[0] || "";
  }

  function getFieldLabel(el) {
    if (el.labels && el.labels.length) {
      for (const lblEl of Array.from(el.labels)) {
        if (lblEl.classList && lblEl.classList.contains("custom-file-label")) continue;
        const t = cleanCandidateLabelText(lblEl.innerText || lblEl.textContent);
        if (t) return t.toLowerCase();
      }
    }
    const id = el.getAttribute("id");
    if (id && id !== "inputId") {
      try {
        const forLabels = Array.from(document.querySelectorAll(`label[for="${CSS.escape(id)}"]`));
        for (const forLabel of forLabels) {
          if (forLabel.classList && forLabel.classList.contains("custom-file-label")) continue;
          const t = cleanCandidateLabelText(forLabel.innerText || forLabel.textContent);
          if (t) return t.toLowerCase();
        }
      } catch (_) {}
    }

    const ariaLabel = cleanCandidateLabelText(el.getAttribute("aria-label"));
    if (ariaLabel) return ariaLabel.toLowerCase();

    const ariaLabelledBy = el.getAttribute("aria-labelledby");
    if (ariaLabelledBy) {
      for (const refId of ariaLabelledBy.split(/\s+/)) {
        const refEl = document.getElementById(refId);
        if (refEl) {
          const t = cleanCandidateLabelText(refEl.innerText || refEl.textContent);
          if (t) return t.toLowerCase();
        }
      }
    }

    // 1. Check explicit semantic label attributes on custom web components (Zoho <lyte-*>, SmartRecruiters <spl-*>)
    let curr = el;
    for (let depth = 0; depth <= 8 && curr && curr !== document.body; depth++) {
      for (const attr of [
        "label",
        "cx-prop-label",
        "lt-prop-label",
        "prop-label",
        "data-label",
        "cx-prop-zcqa",
        "data-zcqa"
      ]) {
        const rawAttr = curr.getAttribute && curr.getAttribute(attr);
        const attrVal = cleanCandidateLabelText(rawAttr);
        if (attrVal) return attrVal.toLowerCase();
      }
      curr = getParentOrShadowHost(curr);
    }

    // 2. Check visible DOM proximity labels (sibling <label>/<div> and parent field container labels)
    curr = el;
    for (let depth = 0; depth <= 10 && curr && curr !== document.body; depth++) {
      let prev = curr.previousElementSibling;
      while (prev) {
        const prevTag = (prev.tagName || "").toUpperCase();
        if (
          prevTag !== "STYLE" &&
          prevTag !== "SCRIPT" &&
          prevTag !== "NOSCRIPT" &&
          prevTag !== "TEMPLATE" &&
          prevTag !== "SVG" &&
          prevTag !== "SPL-ICON" &&
          !(prev.classList && prev.classList.contains("custom-file-label"))
        ) {
          const hasInputs = querySelectorAllDeep('input:not([type="hidden"]), textarea', prev).length > 0;
          if (!hasInputs) {
            const t = cleanCandidateLabelText(prev.innerText || prev.textContent);
            if (t) return t.toLowerCase();
          }
        }
        prev = prev.previousElementSibling;
      }

      const parent = getParentOrShadowHost(curr);
      if (!parent) break;

      const inputsInParent = querySelectorAllDeep(
        'input[type="text"], input[type="email"], input[type="tel"], input[type="file"], input:not([type]), textarea',
        parent
      );
      if (inputsInParent.length <= 2 && parent.querySelector) {
        const semanticLabels = Array.from(
          parent.querySelectorAll("label, .label, legend, [class*='label' i], [data-zcqa*='label' i], [slot='label']")
        );
        for (const semanticLabel of semanticLabels) {
          if (semanticLabel.classList && semanticLabel.classList.contains("custom-file-label")) continue;
          if (!containsDeep(semanticLabel, el)) {
            const t = cleanCandidateLabelText(semanticLabel.innerText || semanticLabel.textContent);
            if (t) return t.toLowerCase();
          }
        }
      }
      curr = parent;
    }

    // 3. Fallback to placeholder / name / id / data-qa on the element itself
    const fallback = [
      el.getAttribute("placeholder") || "",
      el.getAttribute("formcontrolname") || "",
      el.getAttribute("data-qa") || "",
      el.getAttribute("data-test") || "",
      el.getAttribute("data-testid") || "",
      el.getAttribute("data-automation-id") || "",
      el.getAttribute("name") || "",
      el.getAttribute("id") || "",
      el.getAttribute("autocomplete") || ""
    ]
      .map((s) => cleanCandidateLabelText(s))
      .filter(Boolean)
      .join(" ")
      .toLowerCase();

    return fallback;
  }

  function isAutocompleteInput(el) {
    if (!el || el.tagName === "SELECT" || el.tagName === "TEXTAREA") return false;
    if (
      closestDeep(
        el,
        "spl-autocomplete, oc-autocomplete, [class*='autocomplete' i], [data-test*='autocomplete' i], [role='combobox']"
      )
    ) {
      return true;
    }
    const role = (el.getAttribute("role") || "").toLowerCase();
    const ariaAc = (el.getAttribute("aria-autocomplete") || "").toLowerCase();
    if (role === "combobox" || ariaAc === "list" || ariaAc === "both" || el.getAttribute("aria-expanded") !== null) {
      return true;
    }
    // Check if the immediate wrapper / shadow host has a magnifying-glass / search icon (e.g. SmartRecruiters lookup fields)
    let p = getParentOrShadowHost(el);
    for (let d = 0; d < 3 && p && p !== document.body; d++) {
      const tag = (p.tagName || "").toLowerCase();
      if (tag.includes("autocomplete") || tag.includes("typeahead") || tag.includes("lookup")) {
        return true;
      }
      if (querySelectorAllDeep("input", p).length <= 1) {
        const hasSearchIcon =
          querySelectorAllDeep(
            "spl-icon[name*='search' i], [class*='search' i], [class*='magnifying' i], [class*='lookup' i], svg",
            p
          ).length > 0 && !/\b(date|calendar)\b/i.test(el.getAttribute("placeholder") || "");
        if (hasSearchIcon && tag.startsWith("spl-")) return true;
      }
      p = getParentOrShadowHost(p);
    }
    return false;
  }

  function setNativeValue(el, value, opts = {}) {
    if (value === undefined || value === null) return false;
    const strVal = String(value);
    try {
      const proto =
        el instanceof HTMLTextAreaElement
          ? window.HTMLTextAreaElement.prototype
          : el instanceof HTMLSelectElement
          ? window.HTMLSelectElement.prototype
          : window.HTMLInputElement.prototype;
      const descriptor = Object.getOwnPropertyDescriptor(proto, "value");
      if (descriptor && descriptor.set) {
        descriptor.set.call(el, strVal);
      } else {
        el.value = strVal;
      }
    } catch (_) {
      el.value = strVal;
    }

    const evInit = { bubbles: true, composed: true };
    el.dispatchEvent(new Event("focus", evInit));
    el.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        composed: true,
        data: strVal,
        inputType: "insertText"
      })
    );
    el.dispatchEvent(new KeyboardEvent("keydown", { ...evInit, key: strVal.slice(-1) || "a" }));
    el.dispatchEvent(new KeyboardEvent("keyup", { ...evInit, key: strVal.slice(-1) || "a" }));

    const skipBlur = Boolean(opts.skipBlur) || isAutocompleteInput(el);
    if (!skipBlur) {
      el.dispatchEvent(new Event("change", evInit));
      if (el.id !== "addSkills" && !(el.className || "").includes("skillset")) {
        el.dispatchEvent(new Event("blur", evInit));
      } else {
        el.value = strVal;
      }
    }

    try {
      // Update direct <spl-input> / <spl-textarea> host value property (never on <spl-autocomplete>, which expects an option object!)
      const root = el.getRootNode && el.getRootNode();
      const shadowHost = root && root.host ? root.host : null;
      if (shadowHost) {
        const hostTag = (shadowHost.tagName || "").toUpperCase();
        if ((hostTag === "SPL-INPUT" || hostTag === "SPL-TEXTAREA") && !closestDeep(el, "spl-autocomplete, oc-autocomplete")) {
          try {
            if ("value" in shadowHost) shadowHost.value = strVal;
          } catch (_) {}
        }
      }

      const lyteInput = el.closest && el.closest("lyte-input");
      if (lyteInput && lyteInput.setAttribute) {
        lyteInput.setAttribute("lt-prop-value", strVal);
      }
      document.querySelectorAll("lyte-drop-box, .cxLookupDropbox").forEach((d) => {
        d.style.display = "none";
      });
    } catch (_) {}

    if (strVal !== "") {
      const prevTransition = el.style.transition;
      const prevBoxShadow = el.style.boxShadow;
      el.style.transition = "box-shadow 0.35s ease";
      el.style.boxShadow = "0 0 0 2px rgba(99, 102, 241, 0.65)";
      setTimeout(() => {
        el.style.boxShadow = prevBoxShadow;
        el.style.transition = prevTransition;
      }, 2200);
    }
    return true;
  }

  function findVisibleAutocompleteOptions(el) {
    const acHost =
      closestDeep(el, "spl-autocomplete, oc-autocomplete, [class*='autocomplete' i], [role='combobox']") ||
      getParentOrShadowHost(el);
    const optSelector =
      '[role="option"], spl-autocomplete-option, spl-select-option, spl-option, spl-list-item, spl-menu-item, oc-autocomplete-option, [role="listbox"] li, [role="listbox"] > *, ul[class*="autocomplete" i] li, ul[class*="list" i] li, [class*="autocomplete" i] [class*="option" i], [class*="dropdown" i] [class*="option" i], [class*="menu" i] [class*="item" i], [class*="suggestion" i], .pac-item';
    const rawCands = [];
    if (acHost) {
      rawCands.push(...querySelectorAllDeep(optSelector + ", ul li, ol li, [role='menuitem']", acHost));
    }
    rawCands.push(...querySelectorAllDeep(optSelector, document));

    const elRect = el.getBoundingClientRect ? el.getBoundingClientRect() : { top: 0, bottom: 0 };
    const seen = new Set();
    const valid = [];
    for (const cand of rawCands) {
      if (!cand || seen.has(cand)) continue;
      seen.add(cand);
      // Never match an element that contains `el` (even across Shadow DOM boundaries) or is inside `el`
      if (cand === el || containsDeep(cand, el) || containsDeep(el, cand)) continue;
      if (cand.tagName === "OPTION" || cand.tagName === "INPUT" || cand.tagName === "LABEL") continue;
      if (closestDeep(cand, "#cvtomatch-autofill-host")) continue;
      const rect = cand.getBoundingClientRect ? cand.getBoundingClientRect() : { width: 0, height: 0, top: 0, bottom: 0 };
      if (rect.width < 20 || rect.height < 12 || rect.height > 140) continue;
      // Ensure the option is either inside acHost or visually close to `el` (prevents matching options from other fields)
      const isInsideAcHost = Boolean(acHost && containsDeep(acHost, cand));
      if (!isInsideAcHost && elRect.bottom > 0 && Math.abs(rect.top - elRect.bottom) > 340 && Math.abs(rect.bottom - elRect.top) > 340) {
        continue;
      }
      const style = window.getComputedStyle(cand);
      if (style.display === "none" || style.visibility === "hidden" || parseFloat(style.opacity || "1") === 0) {
        continue;
      }
      const txt = (cand.innerText || cand.textContent || "").replace(/\s+/g, " ").trim();
      if (!txt || txt.length < 2 || txt.length > 160) continue;
      if (
        /^(no\s*results|no\s*options|loading|searching|type\s*to\s*search|city\*?|institution\*?|title\*?|company\*?|major\*?|degree\*?|school\s*location\*?|office\s*location\*?)$/i.test(
          txt
        ) ||
        /\b(is\s*required|are\s*required|fields\s*marked\s*with|cannot\s*be\s*empty|please\s*enter)\b/i.test(txt)
      ) {
        continue;
      }
      valid.push(cand);
    }

    // Prefer leaf option nodes (across Shadow DOM too) so we don't click a container wrapping multiple options
    return valid.filter((v) => !valid.some((other) => other !== v && containsDeep(v, other)));
  }

  async function fillSmartFieldOrAutocomplete(el, value, fieldKind = "") {
    if (value === undefined || value === null || value === "") return false;
    const strVal = String(value).trim();
    if (!strVal) return false;

    const shouldUseAutocomplete = isAutocompleteInput(el);

    if (!shouldUseAutocomplete) {
      return setNativeValue(el, strVal);
    }

    // Build ordered search query candidates so database-backed autocompletes (City*, Institution*, Title*, Company) always match
    const queries = [];
    const addQ = (q) => {
      const clean = String(q || "").trim();
      if (clean && !queries.includes(clean)) queries.push(clean);
    };

    if (fieldKind === "city" || fieldKind === "location") {
      if (
        /^(romania|bucarest|bucharest|bucuresti|bucurești|bucarest,\s*romania|bucharest,\s*romania)$/i.test(strVal) ||
        /bucarest|bucharest|romania/i.test(strVal)
      ) {
        addQ("Bucharest");
        addQ("Bucharest, Romania");
        addQ("Romania");
        addQ(strVal);
      } else if (/monastir|tunisia|tunisie|tunis/i.test(strVal)) {
        addQ("Monastir");
        addQ("Monastir, Tunisia");
        addQ("Tunis");
        addQ("Tunisia");
      } else if (/saudi|riyadh/i.test(strVal)) {
        addQ("Riyadh");
        addQ("Saudi Arabia");
        addQ("Bucharest");
      } else if (/remote|hybrid/i.test(strVal)) {
        addQ("Bucharest");
      } else {
        if (strVal.includes(",")) addQ(strVal.split(",")[0].trim());
        addQ(strVal);
        addQ("Bucharest");
      }
    } else if (fieldKind === "institution") {
      if (/politehnica|bucharest|bucarest/i.test(strVal)) {
        addQ("Politehnica Bucharest");
        addQ("University Politehnica of Bucharest");
        addQ("University of Bucharest");
        addQ("Bucharest");
      } else if (/monastir/i.test(strVal)) {
        addQ("University of Monastir");
        addQ("Monastir");
      }
      addQ(strVal);
      const words = strVal.split(/\s+/).filter((w) => w.length > 2 && !/^(and|the|of|in|for)$/i.test(w));
      if (words.length >= 3) {
        addQ(words.slice(-2).join(" "));
        addQ(words.slice(0, 2).join(" "));
      }
    } else if (fieldKind === "title") {
      addQ(strVal);
      if (/flutter/i.test(strVal)) {
        addQ("Flutter Developer");
        addQ("Mobile Developer");
        addQ("Android Developer");
      }
      addQ("Mobile Developer");
      addQ("Software Developer");
      addQ("Software Engineer");
    } else if (fieldKind === "company") {
      addQ(strVal);
      if (strVal.includes(" ")) {
        addQ(strVal.split(/\s+/)[0]);
      }
    } else {
      addQ(strVal);
    }

    for (const q of queries) {
      try {
        el.scrollIntoView({ block: "nearest" });
        el.focus();
        el.click();
        setNativeValue(el, "", { skipBlur: true });
        await sleep(60);

        // Use native Blink insertText command where possible + composed InputEvent without blur
        try {
          el.focus();
          if (typeof el.select === "function") el.select();
          document.execCommand("insertText", false, q);
        } catch (_) {}
        if (el.value !== q) {
          setNativeValue(el, q, { skipBlur: true });
        } else {
          el.dispatchEvent(new InputEvent("input", { bubbles: true, composed: true, data: q, inputType: "insertText" }));
          el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, composed: true, key: q.slice(-1) || "a" }));
        }

        // Poll up to ~900ms for the autocomplete dropdown options to appear while keeping focus on `el`
        let options = [];
        for (let poll = 0; poll < 6; poll++) {
          await sleep(150);
          options = findVisibleAutocompleteOptions(el);
          if (options.length > 0) break;
        }

        if (options.length > 0) {
          const qLower = q.toLowerCase();
          const qWords = qLower.split(/\s+/).filter((w) => w.length >= 2);
          let bestOpt = options[0];
          let bestScore = -1;
          for (const opt of options) {
            const oText = (opt.innerText || opt.textContent || "").toLowerCase().trim();
            let score = 0;
            if (oText === qLower) score += 100;
            else if (oText.startsWith(qLower)) score += 60;
            else if (oText.includes(qLower)) score += 40;
            for (const w of qWords) {
              if (oText.includes(w)) score += 15;
            }
            if (score > bestScore) {
              bestScore = score;
              bestOpt = opt;
            }
          }

          const innerTarget =
            (bestOpt.shadowRoot && bestOpt.shadowRoot.querySelector("button, li, a, div, span")) || bestOpt;
          for (const target of [innerTarget, bestOpt]) {
            if (!target) continue;
            target.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, composed: true }));
            target.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, composed: true }));
            target.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, composed: true }));
            target.click();
          }
          await sleep(180);

          // If the dropdown is still open after clicking, also commit via ArrowDown + Enter
          if (findVisibleAutocompleteOptions(el).length > 0) {
            el.dispatchEvent(
              new KeyboardEvent("keydown", { bubbles: true, composed: true, key: "ArrowDown", code: "ArrowDown", keyCode: 40 })
            );
            await sleep(60);
            el.dispatchEvent(
              new KeyboardEvent("keydown", { bubbles: true, composed: true, key: "Enter", code: "Enter", keyCode: 13 })
            );
            await sleep(120);
          }
          return true;
        }
      } catch (_) {}
    }

    // If no dropdown options appeared (e.g. non-dropdown input or custom company name), keep the original value without firing blur
    setNativeValue(el, strVal, { skipBlur: true });
    el.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    return true;
  }

  function findMatchingSelectOption(options, targetText) {
    if (!targetText) return null;
    const normTarget = String(targetText).toLowerCase().trim();
    if (!normTarget) return null;
    let bestOpt = null;

    for (const opt of options) {
      const rawText = (opt.text || "").trim();
      const rawVal = (opt.value || "").trim();
      if (!rawVal && !rawText) continue;
      if (opt.disabled || /^(-?none-?|select|choose|--|no\s*experience|sem\s*experi[êe]ncia)$/i.test(rawText)) {
        continue;
      }
      const t = rawText.toLowerCase();
      const v = rawVal.toLowerCase();
      if (t === normTarget || v === normTarget) {
        return opt;
      }
      if (!bestOpt && (t.includes(normTarget) || (t.length >= 2 && normTarget.includes(t)))) {
        bestOpt = opt;
      }
    }
    return bestOpt;
  }

  function setSelectBestOption(selectEl, targetText) {
    const options = Array.from(selectEl.options || []);
    const bestOpt = findMatchingSelectOption(options, targetText);
    if (!bestOpt) return false;
    options.forEach((o) => {
      o.selected = false;
    });
    bestOpt.selected = true;
    selectEl.value = bestOpt.value;
    selectEl.setAttribute("data-cvm-select-synced", "1");
    selectEl.dispatchEvent(new Event("input", { bubbles: true }));
    selectEl.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  function setSelectOptions(selectEl, candidateList, allowMultiple = false) {
    const options = Array.from(selectEl.options || []);
    const cands = Array.isArray(candidateList) ? candidateList : [candidateList];
    const matchedOpts = [];

    for (const c of cands) {
      const opt = findMatchingSelectOption(options, c);
      if (opt && !matchedOpts.includes(opt)) {
        matchedOpts.push(opt);
        if (!allowMultiple || !selectEl.multiple) break;
        if (matchedOpts.length >= 7) break;
      }
    }

    if (matchedOpts.length === 0) return false;

    options.forEach((o) => {
      o.selected = false;
    });
    for (const opt of matchedOpts) {
      opt.selected = true;
    }
    if (!selectEl.multiple && matchedOpts[0]) {
      selectEl.value = matchedOpts[0].value;
    }
    selectEl.setAttribute("data-cvm-select-synced", "1");
    selectEl.dispatchEvent(new Event("input", { bubbles: true }));
    selectEl.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  // Selects an item inside a custom Zoho <lyte-dropdown> or <crux-picklist-component>
  async function selectLyteDropdownOption(dropdownEl, targetCandidates, allowFallbackFirst = false) {
    if (!dropdownEl) return false;
    const candidates = (Array.isArray(targetCandidates) ? targetCandidates : [targetCandidates])
      .filter(Boolean)
      .map((s) => String(s).toLowerCase().trim());

    let items = Array.from(dropdownEl.querySelectorAll("lyte-drop-item"));
    if (items.length === 0) {
      const dropBtn = dropdownEl.querySelector("lyte-drop-button, [role='combobox']");
      if (dropBtn) {
        dropBtn.click();
        await sleep(160);
      }
      const dropBoxId =
        dropdownEl.querySelector("[aria-controls]") &&
        dropdownEl.querySelector("[aria-controls]").getAttribute("aria-controls");
      if (dropBoxId) {
        const externalBox = document.getElementById(dropBoxId);
        if (externalBox) {
          items = Array.from(externalBox.querySelectorAll("lyte-drop-item"));
        }
      }
      if (items.length === 0) {
        items = Array.from(dropdownEl.querySelectorAll("lyte-drop-item"));
      }
    }

    let chosen = null;
    for (const cand of candidates) {
      chosen = items.find((it) => {
        const t = (it.innerText || it.textContent || "").toLowerCase().trim();
        const v = (it.getAttribute("data-value") || it.getAttribute("value") || "").toLowerCase().trim();
        return t === cand || v === cand || (t && t !== "-none-" && (t.includes(cand) || cand.includes(t)));
      });
      if (chosen) break;
    }

    if (!chosen && allowFallbackFirst && items.length > 0) {
      const validItems = items.filter((it) => {
        const t = (it.innerText || it.textContent || "").toLowerCase().trim();
        return t && t !== "-none-" && !t.includes("select") && !t.includes("choose");
      });
      if (validItems.length > 0) chosen = validItems[0];
    }

    if (chosen) {
      try {
        chosen.click();
        return true;
      } catch (_) {}
    }
    return false;
  }

  // Universal smart solver for ANY <lyte-dropdown> or <select> (including "Total years of work experience",
  // "Nationality", "Second languages", "Tech stack", "Work model", "Salary Currency/Period", etc.)
  function computeBestDropdownCandidates(
    label,
    optionTexts,
    profile,
    itemContext = null,
    matchedSkills = [],
    jobCtx = null
  ) {
    const lowLabel = String(label || "").toLowerCase();
    const validOpts = (optionTexts || [])
      .map((o) => String(o || "").trim())
      .filter((o) => o && !/^(-?none-?|select|choose|--|no\s*experience|sem\s*experi[êe]ncia)$/i.test(o));
    const years = Number(profile && profile.years_experience) || 4;

    // 1. Inspect option values directly for Salary Currency vs Salary Period dropdowns (which often share the salary label)
    const isCurrencyDropdown = validOpts.some((o) =>
      /\b(euro|us\s*dollar|british\s*pound|kazakhstani\s*tenge|swiss\s*franc|canadian\s*dollar)\b/i.test(o) ||
      /^(eur|usd|gbp|chf|cad|aud|pln|ron|brl|€|\$|£)$/i.test(o)
    );
    if (isCurrencyDropdown) {
      const eurOpt = validOpts.find((o) => /\b(euro|eur)\b|€/i.test(o));
      const usdOpt = validOpts.find((o) => /\b(us\s*dollar|usd)\b|\$/i.test(o));
      return [eurOpt, "Euro", "EUR", "Euro (EUR)", "€", usdOpt, "US Dollar", "USD"].filter(Boolean);
    }

    const isPeriodDropdown =
      validOpts.length <= 10 &&
      validOpts.some((o) => /\b(hourly|daily|weekly|monthly|yearly|annual|annually|mensal|anual)\b/i.test(o));
    if (isPeriodDropdown) {
      const monthlyOpt = validOpts.find((o) => /\b(monthly|per\s*month|month|mensal)\b/i.test(o));
      const yearlyOpt = validOpts.find((o) => /\b(yearly|annual|annually|per\s*year|year|anual)\b/i.test(o));
      return [
        monthlyOpt,
        "Monthly",
        "Per Month",
        "Month",
        "Mensal",
        yearlyOpt,
        "Yearly",
        "Annual",
        "Annually",
        "Per Year",
        "Year",
        "Anual"
      ].filter(Boolean);
    }

    // 2. Total years of experience
    if (
      /\b(total\s*years|years\s*of\s*(?:work\s*)?experience|work\s*experience|experience\s*in\s*years|how\s*many\s*years|exp\s*years|anos\s*de\s*experi[êe]ncia)\b/i.test(
        lowLabel
      )
    ) {
      const matched = [];
      for (const opt of validOpts) {
        const lowOpt = opt.toLowerCase();
        if (/no\s*experience|sem\s*experi|less\s*than\s*1|<\s*1\b|0\s*[\-–—]\s*1\b/i.test(lowOpt)) continue;
        // Range like "2-4", "3 - 5 years", "1 to 3"
        const rangeMatch = lowOpt.match(/(\d+)\s*(?:[\-–—]|to|a)\s*(\d+)/);
        if (rangeMatch) {
          const minY = parseInt(rangeMatch[1], 10);
          const maxY = parseInt(rangeMatch[2], 10);
          if (years >= minY && years <= maxY) matched.unshift(opt);
          else if (Math.abs(years - minY) <= 1 || Math.abs(years - maxY) <= 1) matched.push(opt);
          continue;
        }
        // Plus / Greater than like "3+ years", "4+", "> 3 years", "more than 3"
        const plusMatch = lowOpt.match(/(?:>\s*|more\s*than\s*|mais\s*de\s*)?(\d+)\s*\+?/);
        if (plusMatch && (lowOpt.includes("+") || lowOpt.includes(">") || /more\s*than|mais\s*de/i.test(lowOpt))) {
          const minY = parseInt(plusMatch[1], 10);
          if (years >= minY) matched.unshift(opt);
          else if (minY <= years + 1) matched.push(opt);
          continue;
        }
        // Exact number like "4", "4 years", "3 years"
        const numMatch = lowOpt.match(/\b(\d+)\b/);
        if (numMatch) {
          const n = parseInt(numMatch[1], 10);
          if (n === years) matched.unshift(opt);
          else if (Math.abs(n - years) === 1 && n > 0) matched.push(opt);
          else if (n > 1 && n <= years + 2) matched.push(opt);
        }
      }
      return [
        ...matched,
        String(years),
        `${years} years`,
        `${years}+ years`,
        "3-5 years",
        "3 - 5 years",
        "3 to 5 years",
        "2-4 years",
        "2 - 4 years",
        "2 to 4 years",
        "4-6 years",
        "1-3 years",
        "3+ years",
        "4",
        "3",
        "2",
        ...validOpts.filter((o) => !/no\s*experience|sem\s*experi|<\s*1|less\s*than\s*1/i.test(o))
      ];
    }

    // 3. Nationality / Citizenship / Country
    if (/\b(nationality|citizenship|nacionalidade|nationalit[ée]|country|pays|pa[íi]s)\b/i.test(lowLabel)) {
      const countryToDemonym = {
        romania: ["Romanian (Romania)", "Romanian", "Romania"],
        tunisia: ["Tunisian (Tunisia)", "Tunisian", "Tunisia"],
        morocco: ["Moroccan (Morocco)", "Moroccan", "Morocco"],
        france: ["French (France)", "French", "France"],
        portugal: ["Portuguese (Portugal)", "Portuguese", "Portugal"],
        spain: ["Spanish (Spain)", "Spanish", "Spain"],
        germany: ["German (Germany)", "German", "Germany"],
        "united kingdom": ["British (United Kingdom)", "British", "United Kingdom"],
        uk: ["British (United Kingdom)", "British", "United Kingdom"],
        algeria: ["Algerian (Algeria)", "Algerian", "Algeria"]
      };
      const rawCountry = String((profile && (profile.country || profile.location)) || "").toLowerCase();
      const eduText = JSON.stringify((profile && profile.educations) || []).toLowerCase();
      const phoneStr = String((profile && profile.phone) || "");
      const natCands = [];
      for (const [cKey, list] of Object.entries(countryToDemonym)) {
        if (rawCountry.includes(cKey)) {
          natCands.unshift(...list);
        } else if (eduText.includes(cKey)) {
          natCands.push(...list);
        }
      }
      if (phoneStr.includes("+216") || /monastir|tunis/i.test(eduText)) {
        natCands.push("Tunisian (Tunisia)", "Tunisian", "Tunisia");
      }
      if (phoneStr.includes("+212") || /morocco|casablanca|rabat/i.test(rawCountry)) {
        natCands.push("Moroccan (Morocco)", "Moroccan", "Morocco");
      }
      if (profile && profile.country) natCands.push(profile.country);
      natCands.push("Romanian (Romania)", "Romanian", "Romania", "Tunisian (Tunisia)", "Tunisian", "Tunisia");

      const matchedOpts = [];
      for (const nc of natCands) {
        const hit = validOpts.find((o) => o.toLowerCase().includes(nc.toLowerCase()));
        if (hit && !matchedOpts.includes(hit)) matchedOpts.push(hit);
      }
      return [...matchedOpts, ...natCands];
    }

    // 4. Spoken Languages ("What second languages do you speak?", "Spoken languages", etc.)
    const isSpokenLanguageList =
      /\b(second\s*languages?|languages?\s*(?:do\s*you\s*)?speak|spoken\s*languages?|what\s*languages?|which\s*languages?|idiomas|langues\s*parl[ée]es)\b/i.test(
        lowLabel
      ) ||
      (validOpts.some((o) => /^(english|french|arabic|spanish|portuguese|german)$/i.test(o)) &&
        !validOpts.some((o) => /\b(a1|a2|b1|b2|c1|c2|intermediate|advanced)\b/i.test(o)));
    if (isSpokenLanguageList) {
      const targetLangs = ["English", "French", "Arabic"];
      const matchedLangOpts = [];
      for (const tl of targetLangs) {
        const hit = validOpts.find(
          (o) => o.toLowerCase() === tl.toLowerCase() || o.toLowerCase().startsWith(tl.toLowerCase() + " ")
        );
        if (hit && !matchedLangOpts.includes(hit)) matchedLangOpts.push(hit);
      }
      return [...matchedLangOpts, ...targetLangs];
    }

    // 5. Tech Stack / Skills multi-select or dropdown ("What is your tech stack?", "Skills", "Technologies")
    if (/\b(tech\s*stack|stack|technologies|technical\s*skills|skills|tools|frameworks|programming\s*languages)\b/i.test(lowLabel)) {
      const candidateSkills = [
        ...(Array.isArray(matchedSkills) ? matchedSkills : []),
        ...((profile && Array.isArray(profile.skills) ? profile.skills : []) || []),
        "Flutter",
        "Dart",
        "JavaScript",
        "TypeScript",
        "Firebase",
        "REST",
        "REST API",
        "GraphQL",
        "Git",
        "Docker",
        "SQL",
        "PostgreSQL",
        "MySQL",
        "SQLite",
        "Android",
        "iOS",
        "Kotlin",
        "Swift",
        "React",
        "Node.js",
        "Python",
        "HTML",
        "CSS"
      ];
      const matchedTechOpts = [];
      for (const sk of candidateSkills) {
        const skLow = String(sk || "").toLowerCase().trim();
        if (!skLow) continue;
        const exactHit = validOpts.find((o) => o.toLowerCase() === skLow);
        if (exactHit && !matchedTechOpts.includes(exactHit)) {
          matchedTechOpts.push(exactHit);
          continue;
        }
        const wordHit = validOpts.find((o) => {
          const oLow = o.toLowerCase();
          return oLow === skLow || oLow.startsWith(skLow + " ") || oLow.endsWith(" " + skLow);
        });
        if (wordHit && !matchedTechOpts.includes(wordHit)) {
          matchedTechOpts.push(wordHit);
        }
      }
      return [...matchedTechOpts, ...candidateSkills];
    }

    // 6. Preferred Work Model ("Tell us what is your preferred work model", "Remote / Hybrid / On-site")
    if (/\b(work\s*model|preferr?ed\s*work\s*model|working\s*model|work\s*arrangement|work\s*mode|remote|hybrid)\b/i.test(lowLabel)) {
      const jobTitleLow = String((jobCtx && jobCtx.job_title) || "").toLowerCase();
      if (jobTitleLow.includes("hybrid")) {
        return ["Hybrid", "Full-Remote", "Remote", "Flexible"];
      }
      return ["Full-Remote", "Remote", "Hybrid", "Flexible"];
    }

    // 7. Work Authorization / Relocation
    if (/\b(authorized|legally|eligible|right\s*to\s*work|relocat|realocat)\b/i.test(lowLabel)) {
      return ["Yes", "Sim", "Oui"];
    }
    if (/\b(sponsorship|visa|require\s*sponsor)\b/i.test(lowLabel)) {
      return ["No", "Não", "Non"];
    }
    if (/\b(notice\s*period|availability|when\s*can\s*you\s*start|start\s*date)\b/i.test(lowLabel)) {
      return ["Immediate", "Immediately", "0-15 days", "15 days", "2 weeks", "1 month", "30 days"];
    }
    if (/\b(education|degree|qualification)\b/i.test(lowLabel)) {
      const deg = (itemContext && itemContext.degree) || (profile && profile.degree) || "Master";
      return [deg, "Master's", "Master", "Bachelor's", "Bachelor", "Graduate", "Post Graduate"];
    }
    if (/\b(proficiency|level|fluency|skill\s*level|english|language|cefr)\b/i.test(lowLabel)) {
      return [
        "C1 (Advanced)",
        "C1 - Advanced",
        "C1",
        "Advanced",
        "C2 (Proficient)",
        "C2 - Proficient/Native",
        "C2",
        "Fluent",
        "Proficient",
        "Expert",
        "B2 (Upper Intermediate)",
        "B2 - Upper Intermediate",
        "B2",
        "Upper Intermediate",
        "Native",
        "Intermediate"
      ];
    }
    if (/\b(gender|veteran|disability|race|ethnic)\b/i.test(lowLabel)) {
      return ["Decline to self-identify", "Prefer not to say", "I do not wish to answer"];
    }
    if (/\b(source|hear\s*about|where\s*did\s*you\s*find)\b/i.test(lowLabel)) {
      return ["LinkedIn", "Job Board", "Company Website", "Online"];
    }
    if (/\b(employment\s*type|job\s*type|work\s*type)\b/i.test(lowLabel)) {
      return ["Full-time", "Full Time", "Contract", "Permanent"];
    }
    return validOpts.slice(0, 1);
  }

  async function fillUniversalLyteDropdown(dropdownEl, profile, itemContext = null) {
    if (!dropdownEl) return false;
    // Skip phone country code dropdowns
    if (dropdownEl.closest("crux-phone-component, .crux-country-droplist")) return false;

    const currentText = (
      (dropdownEl.querySelector("lyte-drop-button") || dropdownEl).innerText || ""
    )
      .replace(/\s+/g, " ")
      .trim();
    // If already set to a real value (not -None- / Select / empty), keep it unless we are explicitly updating
    const isUnset = !currentText || /^(-?none-?|select|choose|--)$/i.test(currentText);

    const hostComp =
      dropdownEl.closest("crux-picklist-component, .crc-form-field, .lyteField, [cx-prop-label], [data-zcqa]") ||
      dropdownEl;
    const label = getFieldLabel(hostComp) || getFieldLabel(dropdownEl);

    if (/\b(salutation|prefix|suffix)\b/i.test(label)) return false;
    if (/\b(current\s*job\s*title|job\s*title)\b/i.test(label) && !dropdownEl.closest("rec-tabular-component")) {
      if (profile.is_currently_employed && profile.current_title) {
        return await selectLyteDropdownOption(dropdownEl, [profile.current_title], false);
      }
      return await selectLyteDropdownOption(dropdownEl, ["-None-"], false);
    }

    if (!isUnset) return false;

    let items = Array.from(dropdownEl.querySelectorAll("lyte-drop-item"));
    if (items.length === 0) {
      const dropBtn = dropdownEl.querySelector("lyte-drop-button, [role='combobox']");
      if (dropBtn) {
        dropBtn.click();
        await sleep(160);
      }
      const dropBoxId =
        dropdownEl.querySelector("[aria-controls]") &&
        dropdownEl.querySelector("[aria-controls]").getAttribute("aria-controls");
      if (dropBoxId) {
        const externalBox = document.getElementById(dropBoxId);
        if (externalBox) {
          items = Array.from(externalBox.querySelectorAll("lyte-drop-item"));
        }
      }
      if (items.length === 0) {
        items = Array.from(dropdownEl.querySelectorAll("lyte-drop-item"));
      }
    }

    const optTexts = items.map((it) => (it.innerText || it.textContent || "").trim()).filter(Boolean);
    const candidates = computeBestDropdownCandidates(label, optTexts, profile, itemContext);
    return await selectLyteDropdownOption(dropdownEl, candidates, true);
  }

  function extractTopicFromQuestion(rawLabel) {
    const text = String(rawLabel || "").trim();
    const low = text.toLowerCase();
    const hasBle = /\b(ble|bluetooth\s*low\s*energy|bluetooth)\b/i.test(low);
    const hasIot = /\b(iot|internet\s*of\s*things|connected\s*devices?|smart\s*devices?|mqtt|embedded)\b/i.test(low);

    let customTopic = "";
    const patterns = [
      /(?:involving|working\s+with|worked\s+with|experience\s+(?:with|in)|knowledge\s+of|proficiency\s+in)\s+([a-zA-Z0-9+#/.\-\s()]{2,45}?)(?:\s*(?:project|product|system|application|before|recently|\?|\.|\*|,|$))/i,
      /(?:worked\s+on|built|developed)\s+(?:an?\s+)?([a-zA-Z0-9+#/.\-\s()]{2,40}?)(?:\s*(?:-\s*related)?\s*(?:project|product|system|application|before|\?|\.|\*|,|$))/i,
      /(?:example\s+of\s+(?:an?\s+)?)([a-zA-Z0-9+#/.\-\s()]{2,35}?)(?:\s*(?:project|product|system|application|you\s+have|\?|\.|\*|,|$))/i
    ];
    for (const re of patterns) {
      const m = text.match(re);
      if (m && m[1]) {
        const cand = m[1]
          .replace(/\b(related|most\s+recent|recent|any|your|a|an|the)\b/gi, "")
          .replace(/\s+/g, " ")
          .trim();
        if (cand.length >= 2 && cand.length <= 40 && !/^(it|this|that|them|projects?|systems?|products?)$/i.test(cand)) {
          customTopic = cand;
          break;
        }
      }
    }

    if (hasBle && hasIot) {
      return { hasBle: true, hasIot: true, topic: "BLE and IoT" };
    }
    if (hasBle) {
      return { hasBle: true, hasIot: false, topic: "Bluetooth Low Energy (BLE)" };
    }
    if (hasIot) {
      return { hasBle: false, hasIot: true, topic: "IoT" };
    }
    return { hasBle: false, hasIot: false, topic: customTopic };
  }

  function generateUniversalInputAnswer(
    label,
    fieldType,
    profile,
    jobCtx,
    matchedSkills,
    coverLetter,
    expItem = null,
    questionIdx = 0
  ) {
    const rawLabel = String(label || "").trim();
    const low = rawLabel.toLowerCase();
    const years = Number(profile && profile.years_experience) || 4;
    const skillsArr = (
      (matchedSkills && matchedSkills.length ? matchedSkills : profile && profile.skills) || [
        "Flutter",
        "Dart",
        "BLoC",
        "Riverpod",
        "REST APIs",
        "Firebase"
      ]
    ).slice(0, 7);
    const skillsStr = skillsArr.join(", ");
    const rawRole =
      (expItem && expItem.title) || (jobCtx && jobCtx.job_title) || (profile && profile.current_title) || "Mobile Developer";
    const rawComp = (expItem && expItem.company) || (jobCtx && jobCtx.company) || "";
    const roleStr = rawRole;
    const compStr =
      rawComp && rawComp.toLowerCase() !== rawRole.toLowerCase() && !/^(the\s+hiring\s+team|company)$/i.test(rawComp)
        ? rawComp
        : "your engineering team";

    const exps = Array.isArray(profile && profile.experiences) ? profile.experiences : [];
    const primaryExp =
      expItem ||
      exps.find((e) => e && /developer|engineer|architect|lead/i.test(e.title || "")) ||
      exps[0] || {
        title: "Mobile Developer",
        company: "Xo Space",
        date_text: "2022 – 2024",
        description:
          "Engineered and maintained cross-platform mobile applications using Flutter and Dart for iOS and Android with Riverpod and BLoC state management."
      };
    const expRole = primaryExp.title || "Mobile Developer";
    const expComp = primaryExp.company || "Xo Space";
    const expYearMatch = String(primaryExp.date_text || "").match(/\b(20\d{2})\b/g);
    const recentYear = expYearMatch ? expYearMatch[expYearMatch.length - 1] : "2024";
    const expBullet = String(primaryExp.description || "")
      .split(/\r?\n/)
      .map((s) => s.replace(/^\s*[•\-*]\s*/, "").trim())
      .filter(Boolean)[0] || "";

    const { hasBle, hasIot, topic } = extractTopicFromQuestion(rawLabel);

    // 0. Direct Personal / Employment / Location / Relocation Questions
    if (/\b(are\s+you\s+currently\s+employed|currently\s+employed|if\s+ye?s?,?\s*where)\b/i.test(low)) {
      if (profile && profile.is_currently_employed && profile.current_company) {
        return `Yes, currently working as ${profile.current_title || expRole} at ${profile.current_company}.`;
      }
      return `No, currently available for immediate start (most recently ${expRole} at ${expComp}).`;
    }
    if (
      /\b(what\s+is\s+your\s+(?:current\s+)?(?:job\s+)?title|current\s*job\s*title|current\s*title|current\s*position|current\s*role|your\s+job\s+title)\b/i.test(
        low
      )
    ) {
      return (profile && profile.current_title) || expRole || "Flutter Developer";
    }
    if (
      /\b(where\s+are\s+you\s+located|where\s+you\s+are\s+located|tell\s+us\s+where\s+you\s+are\s+located|where\s+are\s+you\s+based|where\s+do\s+you\s+live|current\s*location|your\s*location)\b/i.test(
        low
      )
    ) {
      return (
        [profile && profile.city, profile && profile.country].filter(Boolean).join(", ") ||
        (profile && (profile.location || profile.country)) ||
        "Romania"
      );
    }
    if (/\b(relocat\w*|realocat\w*|move\s+to\s+portugal)\b/i.test(low)) {
      return `Yes, I am fully available to relocate independently at my own expense and can transition smoothly for hybrid or on-site work without requiring company relocation support.`;
    }

    // 1. "When was the last time you worked on ...?" / "Please specify whether you are referring to BLE, IoT, or both"
    if (/\b(when\s+was\s+the\s+last\s+time|when\s+did\s+you\s+last|last\s+time\s+you\s+worked|how\s+recently)\b/i.test(low)) {
      if (hasBle && hasIot) {
        return `I most recently worked on both BLE and IoT in ${recentYear} (referring to both BLE and IoT). During my work as a ${expRole}, I built cross-platform Flutter and Dart mobile features for Bluetooth Low Energy (BLE) peripheral discovery, GATT service/characteristic read-write streams, and real-time IoT device state synchronization using BLoC and Riverpod.`;
      }
      if (hasBle) {
        return `I most recently worked on a BLE (Bluetooth Low Energy) project in ${recentYear} as a ${expRole}, building cross-platform Flutter and Dart mobile modules for peripheral scanning, pairing, and real-time GATT characteristic data streaming.`;
      }
      if (hasIot) {
        return `I most recently worked on an IoT-connected mobile project in ${recentYear} as a ${expRole}, developing cross-platform Flutter and Dart interfaces for smart-device onboarding, live sensor telemetry, and cloud synchronization.`;
      }
      const tName = topic || "production mobile engineering";
      return `I most recently worked on a ${tName} project in ${recentYear} during my role as ${expRole}${expComp ? ` at ${expComp}` : ""}, where I delivered production features using ${skillsStr}.`;
    }

    // 2. "How many years of experience..."
    if (/\b(total\s*years|years\s*of\s*(?:work\s*)?experience|work\s*experience|how\s*many\s*years)\b/i.test(low)) {
      const subSkillYears = hasBle || hasIot ? Math.max(2, Math.min(3, years)) : years;
      if (fieldType === "number" || fieldType === "text") {
        return String(subSkillYears);
      }
      return `${subSkillYears}+ years of hands-on experience working with ${topic || skillsStr}.`;
    }

    // 3. "Have you worked on [X] projects before? If so, can you share an example ... including your role and key technologies used?"
    if (
      /\b(have\s+you\s+worked\s+on|have\s+you\s+ever\s+worked|share\s+an\s+example|including\s+your\s+role|key\s+technologies\s+used)\b/i.test(
        low
      )
    ) {
      if (hasIot) {
        return `Yes, I have worked on connected IoT systems before. Example: I worked on a cross-platform smart-device monitoring and control application that connected with hardware peripherals to display real-time sensor diagnostics, manage device configuration, and synchronize telemetry with cloud services. Role: ${expRole} (owned the mobile client architecture, device communication layer, and reactive state management). Key technologies used: Flutter, Dart, BLoC, Riverpod, Bluetooth Low Energy (BLE), REST APIs, WebSockets, and Firebase.`;
      }
      if (hasBle) {
        return `Yes, I have worked on BLE-enabled mobile products before. Example: I developed a cross-platform mobile companion module for discovering nearby Bluetooth Low Energy peripherals, handling resilient pairing/reconnection, and streaming real-time GATT characteristic packets. Role: ${expRole} (owned the BLE integration layer, native iOS/Android permissions, and state management). Key technologies used: Flutter, Dart, BLoC, Riverpod, BLE (GATT), MethodChannels, and REST APIs.`;
      }
      const tName = topic || "cross-platform mobile";
      const techList = topic && !skillsStr.toLowerCase().includes(topic.toLowerCase()) ? `${skillsStr}, ${topic}` : skillsStr;
      return `Yes, I have hands-on experience working on ${tName} projects. Example: At ${expComp}, I engineered and maintained a production ${tName} system for iOS and Android featuring modular clean architecture, real-time API synchronization, and automated testing. Role: ${expRole} (owned end-to-end feature architecture and state management). Key technologies used: ${techList}.`;
    }

    // 4. "Please briefly describe your most recent project involving [X]" / "Describe a recent project..."
    if (
      /\b(briefly\s+describe|describe\s+(?:your\s+)?(?:most\s+recent\s+|a\s+recent\s+|a\s+)?project|recent\s+project\s+involving|project\s+involving|tell\s+us\s+about\s+a\s+project)\b/i.test(
        low
      )
    ) {
      if (hasBle) {
        return `In my most recent project involving BLE, I built a cross-platform Flutter (iOS & Android) mobile module that scans and filters nearby Bluetooth Low Energy peripherals, manages secure pairing and automatic reconnection, and subscribes to GATT notify/write characteristics to stream real-time device data into a reactive BLoC/Riverpod state layer with local caching.`;
      }
      if (hasIot) {
        return `In my most recent IoT project, I developed a cross-platform Flutter mobile dashboard and controller that communicates with connected hardware over BLE and REST/WebSocket APIs to monitor live device telemetry, trigger remote commands, and handle offline-first state synchronization.`;
      }
      const tName = topic ? ` involving ${topic}` : "";
      return `In my most recent project${tName} as ${expRole}${expComp ? ` at ${expComp}` : ""}, ${
        expBullet
          ? expBullet.charAt(0).toLowerCase() + expBullet.slice(1)
          : `I engineered a production cross-platform application for iOS and Android using ${skillsStr}`
      } I architected scalable state management using Riverpod and BLoC, integrated RESTful APIs, and ensured smooth 60fps UI performance.`;
    }

    if (/ideal\s*workspace|work\s*environment|preferred\s*environment|work\s*culture/i.test(low)) {
      return `Collaborative agile engineering workspace focused on clean architecture, modern CI/CD, and high-impact product delivery${expItem && expItem.title ? ` (${expItem.title})` : ""}.`;
    }
    if (/\b(hourly\s*rate|daily\s*rate|freelance\s*rate|expected\s*rate)\b/i.test(low)) {
      return fieldType === "number" ? "45" : "Negotiable (flexible depending on project scope and contract duration)";
    }
    if (/\b(salary|compensation|pay\s*expectation|desired\s*pay|remuneration|ctc|expected\s*ctc)\b/i.test(low)) {
      return fieldType === "number" || fieldType === "text" ? "2500" : "Negotiable";
    }
    if (/\b(notice\s*period|when\s*can\s*you\s*start|availability|start\s*date|earliest\s*start)\b/i.test(low)) {
      return fieldType === "number" ? "15" : "Immediate";
    }
    if (/\b(sponsorship|require\s*visa|need\s*visa)\b/i.test(low)) {
      return "No";
    }
    if (/\b(authorized|legally|eligible\s*to\s*work|right\s*to\s*work)\b/i.test(low)) {
      return "Yes";
    }
    if (/\b(gpa|grade|percentage|cgpa)\b/i.test(low)) {
      return fieldType === "number" ? "4" : "3.8 / 4.0";
    }
    if (/\b(reason\s*for\s*leaving|why\s*did\s*you\s*leave|reason\s*for\s*change)\b/i.test(low)) {
      return "Completed contract milestone and seeking new full-time or freelance engineering challenges.";
    }
    if (/\b(achievement|accomplishment|proud\s*of|key\s*project|impact|challenge)\b/i.test(low)) {
      return (
        (expItem && expItem.description) ||
        `As ${expRole} at ${expComp}, I engineered and maintained production cross-platform mobile applications using ${skillsStr}, implementing clean architecture, reactive state management (Riverpod/BLoC), and reliable API integration.`
      );
    }
    if (/\b(cover\s*letter|lettre\s*de\s*motivation|extra\s*information|additional\s*information|anything\s*else|share\s*with\s*us|other\s*information)\b/i.test(low)) {
      return coverLetter;
    }
    if (/\b(why|describe|tell\s*us|what\s*excites|motivation|how\s*do\s*you|elaborate|explain|question|experience)\b/i.test(low)) {
      if (topic) {
        return `I have hands-on experience working with ${topic} alongside ${skillsStr}. In my work as ${expRole} at ${expComp}, I designed and delivered production mobile features with clean architecture, reactive state management, and thorough testing to ensure reliability across iOS and Android.`;
      }
      if (questionIdx % 2 === 1 && exps[1]) {
        return `In addition to my work as ${expRole} at ${expComp}, I also served as ${exps[1].title} at ${exps[1].company || "Top Niveau"}, applying ${skillsStr} to build and deliver production-ready cross-platform mobile applications.`;
      }
      return `With ${years}+ years of experience as a ${expRole} working with ${skillsStr}, I have a proven track record of delivering clean, maintainable cross-platform applications at ${expComp} and am excited to contribute to ${compStr} in the ${roleStr} role.`;
    }
    return "";
  }

  // Populates Zoho Recruit's interactive Skill Set tag widget (#addSkills + #competencySkillsSuggestedList)
  // with ALL tailored skills from the CV
  async function fillInteractiveSkillTags(skillsList) {
    const skillInput =
      document.getElementById("addSkills") ||
      document.querySelector('input.skillset-input, lyte-input[data-zcqa="skillsTagAddSkills"] input');
    if (!skillInput || !Array.isArray(skillsList) || !skillsList.length) return 0;

    let addedChips = 0;
    const targetSkills = skillsList.slice(0, 12);
    const existingChipTexts = new Set(
      Array.from(document.querySelectorAll("ul.skl-selected-skill li"))
        .map((li) => (li.innerText || "").replace(/×|x$/i, "").toLowerCase().trim())
        .filter(Boolean)
    );

    for (const sk of targetSkills) {
      if (existingChipTexts.has(String(sk || "").toLowerCase().trim())) {
        addedChips++;
        continue;
      }
      setNativeValue(skillInput, "");
      await sleep(50);
      setNativeValue(skillInput, sk);
      skillInput.click();
      skillInput.dispatchEvent(new Event("focus", { bubbles: true }));
      skillInput.dispatchEvent(new InputEvent("input", { bubbles: true, data: sk, inputType: "insertText" }));
      skillInput.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: sk.slice(-1) || "a" }));
      skillInput.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, key: sk.slice(-1) || "a" }));
      await sleep(420);

      const suggItems = Array.from(
        document.querySelectorAll(
          "#competencySkillsSuggestedList li[role='button'], .skl-suggested-skill li[role='button'], .skl-suggested-skill li"
        )
      );
      const matchingSugg =
        suggItems.find((li) => (li.innerText || "").toLowerCase().includes(sk.toLowerCase())) ||
        suggItems[0];
      if (matchingSugg && matchingSugg.getBoundingClientRect().width > 0) {
        matchingSugg.click();
        addedChips++;
        await sleep(180);
      }
    }

    document.querySelectorAll("#sugg-skill-popover, .skl-sugg-pop-over").forEach((p) => {
      p.style.display = "none";
    });
    const selectedChips = document.querySelectorAll("ul.skl-selected-skill li").length;
    if (selectedChips <= 1 && addedChips === 0) {
      setNativeValue(skillInput, targetSkills.join(", "));
      return 1;
    }
    setNativeValue(skillInput, "");
    return Math.max(1, addedChips);
  }

  // Parses any CV date range ("2024 - 2026", "15 – 27 july 2024", "Sep 2019 - Present")
  // and guarantees To >= From so Zoho never shows '"To" date should be greater than or equal to "From" date.'
  function parseDateRange(dateText, defaultStartYear = "2022", defaultEndYear = "2024") {
    const raw = String(dateText || "").trim();
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const monthRegexes = [
      { m: "Jan", idx: 0, re: /\b(jan(?:uary|vier)?|01)\b/i },
      { m: "Feb", idx: 1, re: /\b(feb(?:ruary|vrier)?|fév|02)\b/i },
      { m: "Mar", idx: 2, re: /\b(mar(?:ch|s)?|03)\b/i },
      { m: "Apr", idx: 3, re: /\b(apr(?:il)?|avr(?:il)?|04)\b/i },
      { m: "May", idx: 4, re: /\b(may|mai|05)\b/i },
      { m: "Jun", idx: 5, re: /\b(jun(?:e)?|juin|06)\b/i },
      { m: "Jul", idx: 6, re: /\b(jul(?:y)?|juil(?:let)?|07)\b/i },
      { m: "Aug", idx: 7, re: /\b(aug(?:ust)?|août|aout|08)\b/i },
      { m: "Sep", idx: 8, re: /\b(sep(?:t(?:ember|embre)?)?|09)\b/i },
      { m: "Oct", idx: 9, re: /\b(oct(?:ober|obre)?|10)\b/i },
      { m: "Nov", idx: 10, re: /\b(nov(?:ember|embre)?|11)\b/i },
      { m: "Dec", idx: 11, re: /\b(dec(?:ember|embre)?|déc|12)\b/i }
    ];

    const nowYear = new Date().getFullYear();
    const nowMonthIdx = new Date().getMonth();
    const yearMatches = raw.match(/\b(19\d{2}|20\d{2})\b/g) || [];
    const startYearNum = yearMatches[0] ? parseInt(yearMatches[0], 10) : parseInt(defaultStartYear, 10);
    let endYearNum = yearMatches[1]
      ? parseInt(yearMatches[1], 10)
      : yearMatches[0]
      ? parseInt(yearMatches[0], 10)
      : parseInt(defaultEndYear, 10);

    const hasExplicitPresent = /\b(present|current|now|ongoing|actuel|presnt)\b/i.test(raw);
    const isCurrent = hasExplicitPresent || endYearNum > nowYear;
    if (endYearNum < startYearNum) {
      endYearNum = startYearNum;
    }

    // Find all month names in order of appearance in raw
    const foundMonths = [];
    const parts = raw.split(/[\-–—]|to/i);
    for (const part of parts) {
      for (const mr of monthRegexes) {
        if (mr.re.test(part)) {
          foundMonths.push(mr);
          break;
        }
      }
    }

    let startMonthIdx = foundMonths[0] ? foundMonths[0].idx : 8; // default Sep
    let endMonthIdx = foundMonths[1]
      ? foundMonths[1].idx
      : foundMonths[0] && startYearNum === endYearNum
      ? foundMonths[0].idx
      : isCurrent
      ? nowMonthIdx
      : 5; // default Jun

    // Guarantee To >= From when startYear === endYear!
    if (startYearNum === endYearNum && endMonthIdx < startMonthIdx) {
      endMonthIdx = startMonthIdx;
    }

    const sYearStr = String(startYearNum);
    const eYearStr = String(Math.min(endYearNum, 2026));
    const sMonthNum = String(startMonthIdx + 1).padStart(2, "0");
    const eMonthNum = String(endMonthIdx + 1).padStart(2, "0");

    return {
      startMonth: months[startMonthIdx],
      startMonthNum: sMonthNum,
      startYear: sYearStr,
      startMmYyyy: `${sMonthNum}/${sYearStr}`,
      startYyyyMm: `${sYearStr}-${sMonthNum}`,
      endMonth: months[endMonthIdx],
      endMonthNum: eMonthNum,
      endYear: eYearStr,
      endMmYyyy: `${eMonthNum}/${eYearStr}`,
      endYyyyMm: `${eYearStr}-${eMonthNum}`,
      isCurrent
    };
  }

  function formatDateForInput(inp, monthNum, yearStr, monthShort) {
    const type = ((inp && inp.getAttribute && inp.getAttribute("type")) || "text").toLowerCase();
    const ph = ((inp && inp.getAttribute && inp.getAttribute("placeholder")) || "").toLowerCase();
    if (type === "month" || ph.includes("yyyy-mm")) {
      return `${yearStr}-${monthNum}`;
    }
    if (type === "date" || ph.includes("yyyy-mm-dd")) {
      return `${yearStr}-${monthNum}-01`;
    }
    // SmartRecruiters / Workable / Greenhouse date pickers ("Pick a date", "MM/YYYY", etc.) expect MM/YYYY
    return `${monthNum}/${yearStr}`;
  }

  // Selects the matching country dial code in Zoho's phone dropdown (e.g. Romania +40 instead of Tunisia +216)
  // and formats the local phone number so Zoho validation passes with 0 errors
  function syncPhoneDropdownAndFormatNumber(el, rawPhone, resolvedCountry) {
    if (!rawPhone) return "";
    let cleaned = String(rawPhone).trim();
    const digitsOnly = cleaned.replace(/\D/g, "");

    const DIAL_TO_ISO = [
      { prefix: "40", iso: "RO", country: "romania" },
      { prefix: "216", iso: "TN", country: "tunisia" },
      { prefix: "212", iso: "MA", country: "morocco" },
      { prefix: "33", iso: "FR", country: "france" },
      { prefix: "49", iso: "DE", country: "germany" },
      { prefix: "44", iso: "GB", country: "united kingdom" },
      { prefix: "34", iso: "ES", country: "spain" },
      { prefix: "39", iso: "IT", country: "italy" },
      { prefix: "31", iso: "NL", country: "netherlands" },
      { prefix: "32", iso: "BE", country: "belgium" },
      { prefix: "41", iso: "CH", country: "switzerland" },
      { prefix: "971", iso: "AE", country: "united arab emirates" },
      { prefix: "1", iso: "US", country: "united states" }
    ];

    let targetDial = null;
    if (cleaned.startsWith("+") || cleaned.startsWith("00")) {
      const noPlus = cleaned.replace(/^\+|^00/, "").replace(/\D/g, "");
      targetDial = DIAL_TO_ISO.find((d) => noPlus.startsWith(d.prefix));
    }
    if (!targetDial && resolvedCountry) {
      const lowCountry = resolvedCountry.toLowerCase().trim();
      targetDial = DIAL_TO_ISO.find((d) => lowCountry.includes(d.country));
    }
    // Romanian mobile numbers often start with 07xxxxxxxx (10 digits) or 7xxxxxxxx (9 digits)
    if (!targetDial && /^0?7\d{8}$/.test(digitsOnly)) {
      targetDial = DIAL_TO_ISO[0]; // RO +40
    }

    let phoneComp = closestDeep(
      el,
      "crux-phone-component, .crux-country-droplist, .crc-form-field, [class*='phone' i], [data-test*='phone' i], spl-phone-field"
    );
    if (!phoneComp) {
      let cur = el;
      for (let d = 0; d < 4 && cur; d++) {
        const nextParent = getParentOrShadowHost(cur);
        if (!nextParent || nextParent === document.body) break;
        cur = nextParent;
        if (
          querySelectorAllDeep(
            "lyte-drop-item, select, [role='combobox'], [class*='country' i], [class*='flag' i]",
            cur
          ).length > 0
        ) {
          phoneComp = cur;
          break;
        }
      }
    }
    const hasCountryCodeWidget =
      Boolean(
        phoneComp &&
          querySelectorAllDeep(
            "lyte-drop-item, select, [role='combobox'], [class*='country' i], [class*='flag' i]",
            phoneComp
          ).length > 0
      ) || /\+\d{1,4}/.test(phoneComp ? phoneComp.innerText || "" : "");

    if (hasCountryCodeWidget && phoneComp && targetDial) {
      // 1. Zoho <lyte-drop-item>
      const items = querySelectorAllDeep("lyte-drop-item, [role='option'], li[data-country-code]", phoneComp);
      const matchItem = items.find(
        (i) =>
          (i.getAttribute("data-value") || i.getAttribute("data-country-code") || "").toUpperCase() ===
            targetDial.iso || (i.innerText || "").includes(`+${targetDial.prefix}`)
      );
      if (matchItem) {
        try {
          matchItem.click();
        } catch (_) {}
      }
      // 2. Native <select> country code dropdown (e.g. SmartRecruiters / Greenhouse / Workable)
      const selects = querySelectorAllDeep("select", phoneComp);
      for (const sel of selects) {
        const opts = Array.from(sel.options || []);
        const matchOpt = opts.find(
          (o) =>
            (o.value || "").toUpperCase() === targetDial.iso ||
            (o.text || "").includes(`+${targetDial.prefix}`) ||
            (o.text || "").toLowerCase().includes(targetDial.country)
        );
        if (matchOpt) {
          sel.value = matchOpt.value;
          sel.dispatchEvent(new Event("change", { bubbles: true }));
          sel.dispatchEvent(new Event("input", { bubbles: true }));
        }
      }
    }

    if (hasCountryCodeWidget) {
      let localDigits = digitsOnly;
      if (targetDial && localDigits.startsWith(targetDial.prefix) && localDigits.length > 8) {
        localDigits = localDigits.slice(targetDial.prefix.length);
      } else if (cleaned.startsWith("+") || cleaned.startsWith("00")) {
        for (const d of DIAL_TO_ISO) {
          if (localDigits.startsWith(d.prefix) && localDigits.length > 8) {
            localDigits = localDigits.slice(d.prefix.length);
            break;
          }
        }
      }
      // Strip leading trunk '0' when a country code widget (+40) is already active
      if (localDigits.length === 10 && localDigits.startsWith("0")) {
        localDigits = localDigits.slice(1);
      }
      return localDigits;
    }

    return cleaned.replace(/[^\d+]/g, "");
  }

  function buildCoverLetterPdfBase64(coverLetterText, profile = {}, jobCtx = {}) {
    const sanitizePdfText = (str) =>
      String(str || "")
        .replace(/[\u2018\u2019]/g, "'")
        .replace(/[\u201C\u201D]/g, '"')
        .replace(/[\u2013\u2014]/g, "-")
        .replace(/\u2022/g, "-")
        .replace(/[^\x20-\x7E]/g, " ")
        .replace(/\\/g, "\\\\")
        .replace(/\(/g, "\\(")
        .replace(/\)/g, "\\)");

    const wrapLine = (text, maxChars = 84) => {
      const words = String(text || "").trim().split(/\s+/).filter(Boolean);
      if (!words.length) return [];
      const lines = [];
      let current = words[0];
      for (let i = 1; i < words.length; i++) {
        if ((current + " " + words[i]).length <= maxChars) {
          current += " " + words[i];
        } else {
          lines.push(current);
          current = words[i];
        }
      }
      if (current) lines.push(current);
      return lines;
    };

    const fullName = (profile.full_name || "Candidate").trim();
    const contactParts = [
      profile.email,
      profile.phone,
      profile.country || profile.city,
      profile.linkedin_url
    ]
      .map((x) => String(x || "").trim())
      .filter(Boolean);
    const contactLine = contactParts.join("  |  ");
    const dateStr = new Date().toLocaleDateString("en-US", {
      year: "numeric",
      month: "long",
      day: "numeric"
    });
    const roleTitle = (jobCtx && jobCtx.title) || profile.current_title || "Open Position";

    const bodyText =
      String(coverLetterText || "").trim() ||
      `Dear Hiring Team,\n\nI am excited to submit my application for the ${roleTitle} position. Please find my details and background enclosed.\n\nBest regards,\n${fullName}`;

    const ops = [];
    let y = 735;

    // Header: Candidate Full Name
    ops.push(`BT /F2 16 Tf 54 ${y} Td (${sanitizePdfText(fullName)}) Tj ET`);
    y -= 18;

    // Subheader: Contact info
    if (contactLine) {
      ops.push(`BT /F1 9.5 Tf 54 ${y} Td (${sanitizePdfText(contactLine)}) Tj ET`);
      y -= 14;
    }

    // Divider line
    ops.push(`0.6 w 54 ${y} m 558 ${y} l S`);
    y -= 24;

    // Date & Subject
    ops.push(`BT /F1 10.5 Tf 54 ${y} Td (${sanitizePdfText(dateStr)}) Tj ET`);
    y -= 18;
    ops.push(`BT /F2 11 Tf 54 ${y} Td (${sanitizePdfText("Re: Application for " + roleTitle)}) Tj ET`);
    y -= 22;

    // Body paragraphs
    const paragraphs = bodyText.split(/\n\s*\n/);
    for (const para of paragraphs) {
      const rawLines = para.split(/\r?\n/);
      for (const rawLine of rawLines) {
        const wrapped = wrapLine(rawLine, 84);
        for (const wLine of wrapped) {
          if (y < 54) break;
          ops.push(`BT /F1 10.5 Tf 54 ${y} Td (${sanitizePdfText(wLine)}) Tj ET`);
          y -= 15;
        }
      }
      y -= 8;
      if (y < 54) break;
    }

    const streamContent = ops.join("\n");
    const objects = [
      "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
      "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
      "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>\nendobj\n",
      "4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj\n",
      "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>\nendobj\n",
      `6 0 obj\n<< /Length ${streamContent.length} >>\nstream\n${streamContent}\nendstream\nendobj\n`
    ];

    let pdf = "%PDF-1.4\n";
    const offsets = [0];
    for (const obj of objects) {
      offsets.push(pdf.length);
      pdf += obj;
    }
    const xrefStart = pdf.length;
    pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
    for (let i = 1; i <= objects.length; i++) {
      pdf += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`;
    }
    pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefStart}\n%%EOF`;
    return btoa(pdf);
  }

  function buildPdfDataTransfer(base64Data, filename) {
    const safeName = (filename || "Resume.pdf").endsWith(".pdf")
      ? filename || "Resume.pdf"
      : `${filename}.pdf`;
    const bin = atob(base64Data);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const file = new File([bytes], safeName, {
      type: "application/pdf",
      lastModified: Date.now()
    });
    const dt = new DataTransfer();
    dt.items.add(file);
    return dt;
  }

  // Attaches the PDF file ONCE to a file input or dropzone
  function injectPdfIntoFileInput(fileInput, base64Data, filename) {
    if (!fileInput || !base64Data) return false;

    // Clear any existing uploaded file pills inside the Resume section so re-running Autofill never duplicates
    try {
      const uploadRow = closestDeep(fileInput, "rec-file-upload-component, .crc-form-row, spl-dropzone, oc-dropzone");
      if (uploadRow) {
        const removeBtns = querySelectorAllDeep(
          "[data-zcqa*='delete' i], [data-zcqa*='remove' i], .crc-file-remove, .lyteFileRemove",
          uploadRow
        );
        removeBtns.forEach((b) => {
          try {
            b.click();
          } catch (_) {}
        });
      }
    } catch (_) {}

    try {
      const dt = buildPdfDataTransfer(base64Data, filename);
      try {
        const desc = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "files");
        if (desc && desc.set) {
          desc.set.call(fileInput, dt.files);
        } else {
          fileInput.files = dt.files;
        }
      } catch (_) {
        fileInput.files = dt.files;
      }
      fileInput.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
      fileInput.dispatchEvent(new Event("change", { bubbles: true, composed: true }));

      // Update Bootstrap .custom-file-label or custom file placeholder text if present next to or inside the same wrapper as fileInput
      try {
        const safeName = (filename || "Resume.pdf").endsWith(".pdf") ? filename || "Resume.pdf" : `${filename}.pdf`;
        const parent = getParentOrShadowHost(fileInput);
        const grandParent = parent ? getParentOrShadowHost(parent) : null;
        const customLbl =
          (fileInput.labels && Array.from(fileInput.labels).find((l) => l.classList && l.classList.contains("custom-file-label"))) ||
          (parent && parent.querySelector && parent.querySelector(".custom-file-label")) ||
          (grandParent && grandParent.querySelector && grandParent.querySelector(".custom-file-label")) ||
          (fileInput.labels &&
            Array.from(fileInput.labels).find((l) =>
              /escolher\s*ficheiros?|choose\s*files?|select\s*files?|no\s*file\s*chosen/i.test((l.textContent || "").trim())
            )) ||
          (parent &&
            parent.querySelector &&
            Array.from(parent.querySelectorAll("label, span, div")).find(
              (el) =>
                el.children.length === 0 &&
                /^(escolher\s*ficheiros?|choose\s*files?|select\s*files?|no\s*file\s*chosen)$/i.test((el.textContent || "").trim())
            ));
        if (customLbl) {
          customLbl.textContent = safeName;
        }
      } catch (_) {}

      // If the file input is inside a custom Shadow DOM dropzone (e.g. SmartRecruiters <spl-dropzone>),
      // also dispatch drop on the dropzone host if the input is hidden inside a dropzone
      const dropHost = closestDeep(fileInput, "spl-dropzone, oc-dropzone, spl-file-upload, [class*='dropzone' i]");
      if (dropHost && dropHost !== fileInput) {
        try {
          dropHost.dispatchEvent(
            new DragEvent("drop", { bubbles: true, composed: true, cancelable: true, dataTransfer: dt })
          );
        } catch (_) {}
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  function sendBgMessageWithTimeout(msg, timeoutMs = 12000) {
    return new Promise((resolve) => {
      let done = false;
      const timer = setTimeout(() => {
        if (!done) {
          done = true;
          resolve({
            ok: false,
            error: "Request timed out. Please refresh this page once and try again."
          });
        }
      }, timeoutMs);

      try {
        chrome.runtime.sendMessage(msg, (resp) => {
          if (done) return;
          done = true;
          clearTimeout(timer);
          if (chrome.runtime.lastError) {
            resolve({
              ok: false,
              error: "Extension updated — please refresh this page (⌘R) once!"
            });
            return;
          }
          resolve(resp || { ok: false, error: "Empty response from extension" });
        });
      } catch (_) {
        if (!done) {
          done = true;
          clearTimeout(timer);
          resolve({
            ok: false,
            error: "Extension reloaded — please refresh this page (⌘R) once!"
          });
        }
      }
    });
  }

  // ─── 6. Core Autofill Orchestrator ─────────────────────────────────────────
  async function runAutofill({ tailorCv = true, onProgress } = {}) {
    const progress = (msg, state = "loading", pct = 25) => {
      if (onProgress) onProgress(msg, state, pct);
    };

    progress("Step 1/3: Scanning page DOM & opening form...", "loading", 25);
    await ensureApplicationFormOpen();

    const jobCtx = extractJobContext();
    const initialInputs = getEditableFormInputs();
    const customQuestions = [];
    const questionElementsMap = new Map();

    initialInputs.forEach((el, idx) => {
      const tag = el.tagName.toLowerCase();
      const type = (el.getAttribute("type") || "text").toLowerCase();
      if (type === "file" || type === "checkbox" || type === "radio") return;
      if (el.closest("rec-tabular-component")) return;

      const label = getFieldLabel(el);
      if (!label) return;

      const isQuestionLabel =
        tag === "textarea" ||
        tag === "select" ||
        label.includes("?") ||
        /\b(when\s+was|have\s+you|please\s+briefly|please\s+specify|share\s+an\s+example|why|how\s+many|years\s+of\s+experience|salary|compensation|pay|rate|notice\s+period|when\s+can\s+you\s+start|availability|sponsorship|authorized|eligible|describe|tell\s+us|ble|iot|bluetooth)\b/i.test(
          label
        );

      if (isQuestionLabel) {
        const qId = `q_${idx}`;
        const options =
          tag === "select"
            ? Array.from(el.options || [])
                .map((o) => o.text.trim())
                .filter(Boolean)
            : undefined;
        customQuestions.push({
          id: qId,
          label: label.slice(0, 420),
          field_type: tag === "select" ? "select" : tag === "textarea" ? "textarea" : type,
          options
        });
        questionElementsMap.set(qId, el);
      }
    });

    progress(
      tailorCv
        ? "Step 2/3: Tailoring CV PDF & extracting skills/history..."
        : "Step 2/3: Loading CV profile & AI answers...",
      "loading",
      58
    );

    const response = await sendBgMessageWithTimeout(
      {
        type: "AUTOFILL_JOB",
        payload: {
          ...jobCtx,
          tailor_cv: tailorCv,
          questions: customQuestions.slice(0, 25)
        }
      },
      25000
    );

    if (!response || !response.ok) {
      const errMsg = (response && response.error) || "Could not reach CVtoMatch";
      if (errMsg === "NOT_AUTHENTICATED" || errMsg === "UNAUTHORIZED") {
        progress("Please sign in to CVtoMatch first (click extension icon in toolbar).", "error", 100);
      } else {
        progress(errMsg, "error", 100);
      }
      return null;
    }

    const {
      profile,
      match_score,
      matched_skills,
      cover_letter,
      question_answers,
      resume_filename,
      resume_base64,
      used_tailored_pdf
    } = response.data;

    const educationsList = Array.isArray(profile.educations) ? profile.educations : [];
    const experiencesList = Array.isArray(profile.experiences) ? profile.experiences : [];

    progress("Step 3/3: Expanding sections & filling all entries...", "loading", 85);

    // Block any accidental form submission or page reload during autofill (and for 4s after)
    const preventAccidentalSubmit = (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (typeof e.stopImmediatePropagation === "function") e.stopImmediatePropagation();
      return false;
    };
    window.addEventListener("submit", preventAccidentalSubmit, true);
    document.addEventListener("submit", preventAccidentalSubmit, true);
    setTimeout(() => {
      window.removeEventListener("submit", preventAccidentalSubmit, true);
      document.removeEventListener("submit", preventAccidentalSubmit, true);
    }, 4000);

    // Expand "+ Add" and "+ Add More" for ALL Education & Experience entries in the candidate's CV
    await expandRepeaterSectionsForCount(
      Math.min(educationsList.length, 5),
      Math.min(experiencesList.length, 5)
    );

    let filledCount = 0;
    let attachedResume = false;

    // Strictly use only City/Zip/State that actually exist in the CV (never invent city/zip when only Country is in CV)
    const resolvedCity = (profile.city || "").trim();
    const resolvedCountry = (profile.country || "").trim();
    const resolvedZip = (profile.postal_code || "").trim();
    const resolvedState = (profile.state || resolvedCity || "").trim();
    const resolvedStreet = (profile.street || resolvedCity || "").trim();

    // Helper: returns true if a list of inputs includes top-level personal contact or file inputs (meaning the container is the whole form, NOT a repeater card!)
    const hasPersonalContactOrFileInputs = (inputsList) =>
      inputsList.some((inp) => {
        const t = (inp.getAttribute("type") || "").toLowerCase();
        if (t === "email" || t === "tel" || t === "file" || t === "radio") return true;
        const l = `${getFieldLabel(inp)} ${inp.getAttribute("placeholder") || ""}`.toLowerCase();
        return /\b(full\s*name|first\s*name|last\s*name|email|e-mail|phone|mobile|telephone|resume|cv|cover\s*letter)\b/i.test(
          l
        );
      });

    // Helper to find a generic section container (e.g. SmartRecruiters / Workable "Experience" / "Education" / "Resume")
    const findSectionContainer = (sectionRegex) => {
      const headings = querySelectorAllDeep("h1, h2, h3, h4, legend, label, [class*='title' i], [class*='header' i]");
      for (const h of headings) {
        if (closestDeep(h, "#cvtomatch-autofill-host")) continue;
        const txt = (h.innerText || h.textContent || "").trim();
        if (txt.length >= 2 && txt.length <= 45 && sectionRegex.test(txt)) {
          let bestWithInputs = null;
          let bestWithButtons = null;
          let container = getParentOrShadowHost(h);
          for (let d = 0; d < 6 && container && container !== document.body; d++) {
            const inputsInside = getEditableFormInputs(container);
            if (hasPersonalContactOrFileInputs(inputsInside)) break;
            const buttonsInside = querySelectorAllDeep("button, [role='button'], spl-button", container);
            if (inputsInside.length >= 2 && inputsInside.length <= 16) {
              bestWithInputs = container;
              break;
            }
            if (!bestWithButtons && buttonsInside.length >= 1 && inputsInside.length <= 16) {
              bestWithButtons = container;
            }
            container = getParentOrShadowHost(container);
          }
          if (bestWithInputs || bestWithButtons) {
            return bestWithInputs || bestWithButtons;
          }
        }
      }
      return null;
    };

    // Helper to find ALL already-open repeater cards (Entry 1, Entry 2, ...) inside an Education or Experience section
    const findAllRepeaterCards = (sectionContainer, anchorFieldRegex, oppositeFieldRegex) => {
      if (!sectionContainer) return [];
      const cards = [];
      const seenContainers = new Set();

      // 1. Check if sectionContainer itself directly wraps a single repeater card
      const directInputs = getEditableFormInputs(sectionContainer).filter(
        (inp) => !closestDeep(inp, "#cvtomatch-autofill-host")
      );
      if (
        directInputs.length >= 2 &&
        directInputs.length <= 14 &&
        !hasPersonalContactOrFileInputs(directInputs)
      ) {
        const hasOpposite = oppositeFieldRegex
          ? directInputs.some((inp) => oppositeFieldRegex.test(getFieldLabel(inp)))
          : false;
        if (!hasOpposite) {
          return [directInputs];
        }
      }

      // 2. Find all anchor inputs on the page (e.g. "Institution*" for Education, "Title*" for Experience)
      // and walk up from each anchor to its individual repeater card container
      const allInputs = getEditableFormInputs().filter((inp) => !closestDeep(inp, "#cvtomatch-autofill-host"));
      const anchors = allInputs.filter((inp) => anchorFieldRegex.test(getFieldLabel(inp)));

      for (const anchor of anchors) {
        let cur = getParentOrShadowHost(anchor);
        let bestCardContainer = null;
        let bestCardInputs = null;
        for (let d = 0; d < 8 && cur && cur !== document.body; d++) {
          const cardInputs = getEditableFormInputs(cur).filter((inp) => !closestDeep(inp, "#cvtomatch-autofill-host"));
          if (hasPersonalContactOrFileInputs(cardInputs)) break;
          const hasDateOrLocOrCurrent = cardInputs.some((inp) =>
            /\b(from|to|start\s*date|end\s*date|office\s*location|school\s*location|currently\s*work|currently\s*attend|degree|major)\b/i.test(
              `${getFieldLabel(inp)} ${inp.getAttribute("placeholder") || ""}`
            )
          );
          if (cardInputs.length >= 3 && cardInputs.length <= 11 && hasDateOrLocOrCurrent) {
            const hasOpposite = oppositeFieldRegex
              ? cardInputs.some((inp) => oppositeFieldRegex.test(getFieldLabel(inp)))
              : false;
            if (!hasOpposite) {
              bestCardContainer = cur;
              bestCardInputs = cardInputs;
              if (cardInputs.length >= 5) break;
            }
          }
          cur = getParentOrShadowHost(cur);
        }
        if (bestCardContainer && bestCardInputs && !seenContainers.has(bestCardContainer)) {
          const overlaps = cards.some((existing) => existing.some((inp) => bestCardInputs.includes(inp)));
          if (!overlaps) {
            seenContainers.add(bestCardContainer);
            cards.push(bestCardInputs);
          }
        }
      }
      return cards;
    };

    // Helper to find a generic "+ Add" button next to a section heading (e.g. SmartRecruiters / Workable "Experience" / "Education")
    const findSectionAddButton = (sectionRegex) => {
      const candidates = querySelectorAllDeep("button, [role='button'], spl-button");
      for (const btn of candidates) {
        if (isNavigationOrSubmitElement(btn)) continue;
        const btnText = (btn.innerText || btn.textContent || btn.getAttribute("aria-label") || "").trim();
        if (!/^(\+?\s*add(\s+more|\s+another|\s+experience|\s+education)?)$/i.test(btnText)) continue;
        let container = getParentOrShadowHost(btn);
        for (let d = 0; d < 6 && container && container !== document.body; d++) {
          const heading = container.querySelector
            ? container.querySelector("h1, h2, h3, h4, legend, [class*='title' i], [class*='header' i]")
            : null;
          const containerText = (heading ? heading.innerText || heading.textContent : container.innerText || "")
            .slice(0, 200)
            .trim();
          if (sectionRegex.test(containerText)) {
            return { btn, container };
          }
          container = getParentOrShadowHost(container);
        }
      }
      return null;
    };

    // ─── 0. Attach Resume PDF & Cover Letter PDF to their dedicated file inputs or dropzones (NEVER the top "Easy Apply" importer!) ───
    {
      const fileInputs = querySelectorAllDeep('input[type="file"]');
      const candidateResumeInputs = [];
      const candidateCoverLetterName = `Cover_Letter_${(profile.full_name || "Candidate")
        .trim()
        .replace(/[^a-zA-Z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "") || "Candidate"}.pdf`;
      let coverLetterPdfB64 = null;
      const getCoverLetterPdfB64 = () => {
        if (!coverLetterPdfB64) {
          coverLetterPdfB64 = buildCoverLetterPdfBase64(cover_letter, profile, jobCtx);
        }
        return coverLetterPdfB64;
      };

      for (const fInput of fileInputs) {
        const fLabel = getFieldLabel(fInput);
        const fNameAndId = `${fInput.getAttribute("name") || ""} ${fInput.getAttribute("id") || ""} ${fInput.getAttribute("data-zcqa") || ""}`.toLowerCase();
        const accept = (fInput.getAttribute("accept") || "").toLowerCase();

        // Only inspect LOCAL container text that wraps THIS single file input (stop before multi-file form container!)
        let localBannerText = "";
        let p = getParentOrShadowHost(fInput);
        for (let d = 0; d < 5 && p && p !== document.body && p !== document.documentElement; d++) {
          if (querySelectorAllDeep('input[type="file"]', p).length > 1) break;
          const pText = (p.innerText || p.textContent || "").trim();
          if (pText.length > 0 && pText.length < 380) {
            localBannerText += " " + pText;
          }
          let prev = p.previousElementSibling;
          for (let s = 0; s < 2 && prev; s++) {
            if (querySelectorAllDeep('input[type="file"]', prev).length > 0) break;
            const sText = (prev.innerText || prev.textContent || "").trim();
            if (sText.length > 0 && sText.length < 240) {
              localBannerText += " " + sText;
            }
            prev = prev.previousElementSibling;
          }
          p = getParentOrShadowHost(p);
        }

        const isPhotoInput =
          /\b(photo|picture|avatar|headshot|image|portrait|logo)\b/i.test(fLabel) ||
          (accept.includes("image") && !accept.includes("pdf") && !accept.includes("doc"));
        if (isPhotoInput) continue;

        const isCoverLetterInput =
          /\b(cover\s*letter|cover_letter|coverletter|lettre|carta\s*de\s*apresenta|carta\s*de\s*presentaci|anschreiben|motivation)\b/i.test(
            `${fLabel} ${fNameAndId} ${localBannerText}`
          ) && !/\b(resume|cv|curriculum)\b/i.test(fLabel);
        if (isCoverLetterInput) {
          const clPdfB64 = getCoverLetterPdfB64();
          if (clPdfB64 && injectPdfIntoFileInput(fInput, clPdfB64, candidateCoverLetterName)) {
            filledCount++;
            await sleep(150);
          }
          continue;
        }

        const isEasyApplyImporter = /\b(autocomplete\s*your\s*application|apply\s*with\s*indeed|autofill\s*with\s*resume)\b/i.test(
          localBannerText
        );
        candidateResumeInputs.push({ fInput, fLabel, accept, localBannerText, isEasyApplyImporter });
      }

      if (resume_base64) {
        // Prefer a non-importer Resume input; if there are 2+ inputs (e.g. SmartRecruiters top Easy Apply + bottom Resume *), pick the bottom Resume input!
        const nonImporterInputs = candidateResumeInputs.filter((c) => !c.isEasyApplyImporter);
        let targetResumeInput = null;
        if (nonImporterInputs.length > 0) {
          const explicitResume = nonImporterInputs.find(
            (c) => /\b(resume|cv|curriculum)\b/i.test(c.fLabel) || /\b(resume|cv|curriculum)\b/i.test(c.localBannerText)
          );
          targetResumeInput = explicitResume
            ? explicitResume.fInput
            : nonImporterInputs[nonImporterInputs.length - 1].fInput;
        } else if (candidateResumeInputs.length >= 2) {
          targetResumeInput = candidateResumeInputs[candidateResumeInputs.length - 1].fInput;
        }

        if (targetResumeInput && injectPdfIntoFileInput(targetResumeInput, resume_base64, resume_filename)) {
          attachedResume = true;
          filledCount++;
          await sleep(250);
        }

        // Fallback / reinforcement for SmartRecruiters "Resume *" dropzone ("Choose a file or drop it here — 10MB size limit"):
        // If a dedicated "Resume" section dropzone still shows "Choose a file or drop it here", dispatch a DragEvent("drop") directly on it!
        try {
          const allDropTargets = querySelectorAllDeep(
            "spl-dropzone, oc-dropzone, [class*='dropzone' i], [data-test*='dropzone' i], label, div"
          ).filter((el) => {
            if (closestDeep(el, "#cvtomatch-autofill-host")) return false;
            const t = (el.innerText || el.textContent || "").trim();
            if (t.length < 15 || t.length > 180 || !/choose\s*a\s*file\s*or\s*drop\s*it\s*here/i.test(t)) return false;
            // Ensure this dropzone is inside the "Resume" section (and NOT the top "Easy Apply" section)
            let sec = getParentOrShadowHost(el);
            for (let d = 0; d < 5 && sec && sec !== document.body; d++) {
              const secTxt = (sec.innerText || sec.textContent || "").trim();
              if (secTxt.length < 380) {
                if (/\b(autocomplete\s*your\s*application|apply\s*with\s*indeed)\b/i.test(secTxt)) return false;
                if (/\b(resume|cv|curriculum)\b/i.test(secTxt)) return true;
              }
              let prev = sec.previousElementSibling;
              if (prev) {
                const prevTxt = (prev.innerText || prev.textContent || "").trim();
                if (prevTxt.length < 120 && /\b(resume|cv|curriculum)\b/i.test(prevTxt)) return true;
              }
              sec = getParentOrShadowHost(sec);
            }
            return false;
          });

          if (allDropTargets.length > 0) {
            const leafDropTarget = allDropTargets[allDropTargets.length - 1];
            const innerFileInput = querySelectorAllDeep('input[type="file"]', leafDropTarget)[0];
            if (innerFileInput && innerFileInput !== targetResumeInput) {
              if (injectPdfIntoFileInput(innerFileInput, resume_base64, resume_filename)) {
                attachedResume = true;
                filledCount++;
              }
            }
            const dt = buildPdfDataTransfer(resume_base64, resume_filename);
            for (const evType of ["dragenter", "dragover", "drop"]) {
              leafDropTarget.dispatchEvent(
                new DragEvent(evType, { bubbles: true, composed: true, cancelable: true, dataTransfer: dt })
              );
            }
            attachedResume = true;
          }
        } catch (_) {}
      }
    }

    // Identify Education & Experience section containers before Section A so topInputs never overwrites open repeater cards
    const initialEduContainer = findSectionContainer(/^education\b/i);
    const initialExpContainer = findSectionContainer(/^experience\b/i);
    const initialEduCards = findAllRepeaterCards(
      initialEduContainer,
      /\b(institution|school\s*location|i\s*currently\s*attend)\b/i,
      /\b(office\s*location|i\s*currently\s*work\s*here|^company$)\b/i
    );
    const initialExpCards = findAllRepeaterCards(
      initialExpContainer,
      /\b(^title$|office\s*location|i\s*currently\s*work\s*here)\b/i,
      /\b(institution|school\s*location|i\s*currently\s*attend)\b/i
    );
    const initialEduCardInputs = initialEduCards.flat();
    const initialExpCardInputs = initialExpCards.flat();

    // ─── A. Fill Top-Level (Non-Tabular, Non-Repeater) Inputs ──────────────────
    const topInputs = getEditableFormInputs().filter((el) => {
      if (closestDeep(el, "rec-tabular-component, [data-cvm-repeater-entry='1']")) return false;
      const lbl = `${getFieldLabel(el)} ${el.getAttribute("placeholder") || ""}`.trim().toLowerCase();
      const type = (el.getAttribute("type") || "").toLowerCase();
      // Always keep top-level personal contact fields in topInputs
      if (
        type === "email" ||
        type === "tel" ||
        /\b(full\s*name|first\s*name|last\s*name|given\s*name|surname|your\s*name|candidate\s*name|email|e-mail|phone|mobile|telephone|linkedin|github|portfolio|website)\b/i.test(
          lbl
        )
      ) {
        return true;
      }
      if (initialEduContainer && containsDeep(initialEduContainer, el)) return false;
      if (initialExpContainer && containsDeep(initialExpContainer, el)) return false;
      if (initialEduCardInputs.includes(el) || initialExpCardInputs.includes(el)) return false;
      if (
        /\b(institution|school\s*location|office\s*location|i\s*currently\s*attend|i\s*currently\s*work\s*here)\b/i.test(
          lbl
        )
      ) {
        return false;
      }
      return true;
    });
    let handledSkillSetWidget = false;

    for (const el of topInputs) {
      const tag = el.tagName.toLowerCase();
      const type = (el.getAttribute("type") || "text").toLowerCase();
      if (type === "file" || type === "checkbox" || type === "radio") continue;

      const rawLabel = getFieldLabel(el);
      const phText = cleanCandidateLabelText(el.getAttribute("placeholder") || "").toLowerCase();
      const label = rawLabel || phText;
      const matchLabel = `${label} ${phText}`.trim();
      if (!label) continue;

      if (
        /\b(captcha|type below image text|security\s*code|verification\s*code|facebook|twitter|instagram|tiktok|fax|middle\s*name|salutation|prefix|suffix)\b/i.test(
          label
        )
      ) {
        continue;
      }

      if (tag === "select") {
        if (/\b(salutation|prefix)\b/i.test(label)) continue;
        // Skip phone country-code <select> here because syncPhoneDropdownAndFormatNumber handles it accurately
        if (
          /\b(phone|mobile|telephone|téléphone|numéro)\b/i.test(label) ||
          Array.from(el.options || []).some((o) => /\+\d{1,3}/.test(o.text || ""))
        ) {
          continue;
        }
        const optTexts = Array.from(el.options || []).map((o) => o.text || "");
        const cands = computeBestDropdownCandidates(
          label,
          optTexts,
          profile,
          null,
          matched_skills,
          jobCtx
        );
        const allowMultiSelect =
          el.multiple &&
          /\b(tech\s*stack|stack|technologies|skills|tools|frameworks|second\s*languages?|languages?\s*(?:do\s*you\s*)?speak|spoken\s*languages?|idiomas|langues)\b/i.test(
            label
          );
        if (setSelectOptions(el, cands, allowMultiSelect)) {
          filledCount++;
          continue;
        }
        const qEntry = Array.from(questionElementsMap.entries()).find(([, elem]) => elem === el);
        if (qEntry && question_answers && question_answers[qEntry[0]]) {
          if (setSelectBestOption(el, question_answers[qEntry[0]])) {
            filledCount++;
            continue;
          }
        }
        continue;
      }

      // Interactive Skill Set tag input (#addSkills) -> populate with tailored skills
      if (
        el.id === "addSkills" ||
        (el.className || "").includes("skillset-input") ||
        /\b(relevant\s*skills|skill\s*set|skills\s*tag|add\s*skills|^skills$|technical\s*skills|compétences)\b/i.test(
          label
        )
      ) {
        if (!handledSkillSetWidget && (el.id === "addSkills" || el.closest("skills-tag"))) {
          handledSkillSetWidget = true;
          const skillsToUse =
            (matched_skills && matched_skills.length ? matched_skills : profile.skills) || [];
          const added = await fillInteractiveSkillTags(skillsToUse);
          if (added > 0) filledCount++;
          continue;
        }
      }

      let valToSet = null;
      let fieldKind = "";

      const isScreeningQuestion =
        tag === "textarea" ||
        label.length > 52 ||
        label.includes("?") ||
        /^(when|how|what|why|where|which|who|have\s+you|do\s+you|did\s+you|can\s+you|could\s+you|are\s+you|will\s+you|would\s+you|please\s+|describe\s+|tell\s+us|share\s+|specify\s+|explain\s+|elaborate\s+)/i.test(
          label
        );

      if (/\b(first\s*name|given\s*name|fname|prénom|prenom)\b/i.test(matchLabel)) {
        valToSet = profile.first_name || (profile.full_name || "").split(/\s+/)[0] || "";
      } else if (/\b(last\s*name|surname|family\s*name|lname|nom\s*de\s*famille|^nom$)\b/i.test(matchLabel)) {
        const parts = (profile.full_name || "").split(/\s+/).filter(Boolean);
        valToSet = profile.last_name || (parts.length > 1 ? parts.slice(1).join(" ") : parts[0] || "");
      } else if (
        /\b(full\s*name|your\s*name|candidate\s*name|legal\s*name|nome\s*completo|^name$|^nome$)\b/i.test(matchLabel) &&
        !matchLabel.includes("company") &&
        !matchLabel.includes("school")
      ) {
        valToSet = profile.full_name;
      } else if (type === "email" || /\b(email|e-mail|courriel)\b/i.test(matchLabel)) {
        valToSet = profile.email;
      } else if (
        type === "tel" ||
        /\b(mobile|phone|telephone|cell|téléphone|numéro|contact\s*number|telefone|telemóvel|telemovel)\b/i.test(
          matchLabel
        )
      ) {
        valToSet = syncPhoneDropdownAndFormatNumber(el, profile.phone, resolvedCountry);
      } else if (/\b(linkedin|linekdin|linked[\s\-]*in)\b/i.test(matchLabel)) {
        valToSet = profile.linkedin_url || "";
      } else if (/\b(github)\b/i.test(matchLabel)) {
        valToSet = profile.github_url || "";
      } else if (/\b(portfolio|website|personal\s*url|personal\s*site|blog|site\s*web)\b/i.test(matchLabel)) {
        const rawPortfolio = (profile.portfolio_url || "").trim();
        valToSet =
          rawPortfolio && !/github\.com|linkedin\.com/i.test(rawPortfolio) ? rawPortfolio : "";
      } else if (
        /\b(where\s+are\s+you\s+located|where\s+you\s+are\s+located|tell\s+us\s+where\s+you\s+are\s+located|where\s+are\s+you\s+based|where\s+do\s+you\s+live|current\s*location|your\s*location|^location$)\b/i.test(
          matchLabel
        )
      ) {
        fieldKind = "location";
        valToSet = [resolvedCity, resolvedCountry].filter(Boolean).join(", ") || profile.location || resolvedCountry;
      } else if (
        /\b(what\s+is\s+your\s+(?:current\s+)?(?:job\s+)?title|current\s*job\s*title|current\s*title|role\s*title|headline|current\s*position|poste)\b/i.test(
          matchLabel
        ) &&
        tag !== "textarea"
      ) {
        valToSet =
          profile.current_title ||
          (experiencesList[0] && experiencesList[0].title) ||
          "Flutter Developer";
      } else if (
        /\b(are\s+you\s+currently\s+employed|currently\s+employed|if\s+ye?s?,?\s*where)\b/i.test(matchLabel)
      ) {
        valToSet = generateUniversalInputAnswer(
          label,
          tag === "textarea" ? "textarea" : type,
          profile,
          jobCtx,
          matched_skills,
          cover_letter,
          null,
          filledCount
        );
      } else if (
        isScreeningQuestion &&
        !/^(cover\s*letter|lettre\s*de\s*motivation|additional\s*information|note\s*to\s*hiring(\s*manager)?)$/i.test(
          label
        )
      ) {
        const qEntry = Array.from(questionElementsMap.entries()).find(([, elem]) => elem === el);
        const bgAns = qEntry && question_answers ? question_answers[qEntry[0]] : "";
        // Always prefer the intelligent multi-intent synthesizer if bgAns is missing or is the legacy generic 1-liner
        if (bgAns && !/^i bring hands-on experience working with/i.test(bgAns.trim())) {
          valToSet = bgAns;
        } else {
          valToSet = generateUniversalInputAnswer(
            label,
            tag === "textarea" ? "textarea" : type,
            profile,
            jobCtx,
            matched_skills,
            cover_letter,
            null,
            filledCount
          );
        }
      } else if (/\b(zip|postal|postcode|code\s*postal)\b/i.test(label)) {
        valToSet = resolvedZip;
      } else if (/\b(city|town|ville|localité)\b/i.test(label)) {
        fieldKind = "city";
        const hasSeparateCountryField = topInputs.some((other) =>
          /\b(country|pays)\b/i.test(getFieldLabel(other))
        );
        valToSet = resolvedCity || (!hasSeparateCountryField ? resolvedCountry : "");
      } else if (/\b(state|province|region|county|état|région|județ|judet)\b/i.test(label)) {
        valToSet = resolvedState;
      } else if (/\b(country|pays)\b/i.test(label)) {
        valToSet = resolvedCountry;
      } else if (/\b(street|address\s*line|street\s*address|adresse)\b/i.test(label)) {
        valToSet = resolvedStreet;
      } else if (
        /\b(relevant\s*skills|skill\s*set|skills\s*tag|add\s*skills|^skills$|technical\s*skills|compétences)\b/i.test(
          label
        )
      ) {
        valToSet = ((matched_skills && matched_skills.length ? matched_skills : profile.skills) || [])
          .slice(0, 10)
          .join(", ");
      } else if (
        /\b(current\s*company|current\s*employer|most\s*recent\s*company|organization|employer|entreprise)\b/i.test(
          label
        )
      ) {
        valToSet = profile.is_currently_employed ? profile.current_company : "";
      } else if (/\b(job\s*title)\b/i.test(label)) {
        valToSet = profile.current_title || (experiencesList[0] && experiencesList[0].title) || "Flutter Developer";
      } else if (
        /\b(cover\s*letter|extra\s*information|additional\s*information|anything\s*else|share\s*with\s*us|pitch|summary|note\s*to\s*hiring|lettre\s*de\s*motivation)\b/i.test(
          label
        )
      ) {
        valToSet = cover_letter;
      } else {
        const qEntry = Array.from(questionElementsMap.entries()).find(([, elem]) => elem === el);
        const bgAns = qEntry && question_answers ? question_answers[qEntry[0]] : "";
        if (bgAns && !/^i bring hands-on experience working with/i.test(bgAns.trim())) {
          valToSet = bgAns;
        } else {
          valToSet = generateUniversalInputAnswer(
            label,
            tag === "textarea" ? "textarea" : type,
            profile,
            jobCtx,
            matched_skills,
            cover_letter,
            null,
            filledCount
          );
        }
      }

      if (valToSet !== null && valToSet !== undefined && valToSet !== "") {
        if (await fillSmartFieldOrAutocomplete(el, valToSet, fieldKind)) {
          filledCount++;
        }
      } else if (
        valToSet === "" &&
        /\b(zip|postal|city|state|province|street|website|portfolio)\b/i.test(label) &&
        el.value
      ) {
        // Clear any previously filled city/zip/website if not in CV
        setNativeValue(el, "");
      }
    }

    // ─── B. Top-Level Custom Dropdowns (<lyte-dropdown>) & Radio Groups ────────
    try {
      const topDropdowns = querySelectorAllDeep("lyte-dropdown").filter(
        (dd) => !closestDeep(dd, "rec-tabular-component") && !closestDeep(dd, "#cvtomatch-autofill-host")
      );
      for (const dd of topDropdowns) {
        if (await fillUniversalLyteDropdown(dd, profile)) {
          filledCount++;
        }
      }

      // Handle radio button groups (e.g. English level CEFR A1-C2, Work Authorization, Relocation, Remote preference)
      const getRadioOptionText = (r) => {
        if (r.labels && r.labels.length) {
          const t = (r.labels[0].innerText || r.labels[0].textContent || "").replace(/\s+/g, " ").trim();
          if (t) return t;
        }
        const id = r.getAttribute("id");
        if (id) {
          try {
            const root = (r.getRootNode && r.getRootNode()) || document;
            const forLbl =
              (root.querySelector && root.querySelector(`label[for="${CSS.escape(id)}"]`)) ||
              document.querySelector(`label[for="${CSS.escape(id)}"]`);
            if (forLbl) {
              const t = (forLbl.innerText || forLbl.textContent || "").replace(/\s+/g, " ").trim();
              if (t) return t;
            }
          } catch (_) {}
        }
        const wrapLbl = closestDeep(r, "label, spl-radio, oc-radio, [role='radio']");
        if (wrapLbl) {
          const t = (wrapLbl.innerText || wrapLbl.textContent || "").replace(/\s+/g, " ").trim();
          if (t) return t;
        }
        let p = getParentOrShadowHost(r);
        for (let d = 0; d < 3 && p && p !== document.body; d++) {
          if (querySelectorAllDeep('input[type="radio"]', p).length === 1) {
            const t = (p.innerText || p.textContent || "").replace(/\s+/g, " ").trim();
            if (t && t.length <= 120) return t;
          }
          p = getParentOrShadowHost(p);
        }
        const next = r.nextElementSibling;
        if (next) {
          const t = (next.innerText || next.textContent || "").replace(/\s+/g, " ").trim();
          if (t) return t;
        }
        return (r.getAttribute("aria-label") || r.value || "").trim();
      };

      const getRadioGroupQuestion = (radios) => {
        let cur = getParentOrShadowHost(radios[0]);
        for (let d = 0; d < 7 && cur && cur !== document.body; d++) {
          const radiosInCur = querySelectorAllDeep('input[type="radio"]', cur);
          if (radiosInCur.length >= radios.length) {
            // Look for a heading/legend/label inside `cur` that does not wrap a single radio option
            const qNodes = cur.querySelectorAll
              ? Array.from(
                  cur.querySelectorAll("legend, h1, h2, h3, h4, label, [class*='label' i], [class*='question' i], p, div")
                )
              : [];
            for (const qn of qNodes) {
              if (querySelectorAllDeep('input[type="radio"]', qn).length > 0) continue;
              const isOptionLabel = radios.some((r) => {
                const optTxt = getRadioOptionText(r);
                const qTxt = (qn.innerText || qn.textContent || "").replace(/\s+/g, " ").trim();
                return optTxt && qTxt && optTxt.toLowerCase() === qTxt.toLowerCase();
              });
              if (isOptionLabel) continue;
              const cleaned = cleanCandidateLabelText(qn.innerText || qn.textContent);
              if (cleaned) return cleaned.toLowerCase();
            }
            const prev = cur.previousElementSibling;
            if (prev && querySelectorAllDeep('input[type="radio"]', prev).length === 0) {
              const cleaned = cleanCandidateLabelText(prev.innerText || prev.textContent);
              if (cleaned) return cleaned.toLowerCase();
            }
            break;
          }
          cur = getParentOrShadowHost(cur);
        }
        return (getFieldLabel(radios[0]) || "").toLowerCase();
      };

      const radioInputs = querySelectorAllDeep('input[type="radio"]').filter(
        (r) => !r.disabled && !closestDeep(r, "#cvtomatch-autofill-host")
      );
      const radioGroups = new Map();
      for (const r of radioInputs) {
        let groupKey = r.getAttribute("name");
        if (!groupKey) {
          let p = getParentOrShadowHost(r);
          for (let d = 0; d < 6 && p && p !== document.body; d++) {
            const count = querySelectorAllDeep('input[type="radio"]', p).length;
            if (count >= 2 && count <= 15) {
              groupKey = p;
              break;
            }
            p = getParentOrShadowHost(p);
          }
        }
        if (!groupKey) groupKey = getFieldLabel(r) || r;
        if (!radioGroups.has(groupKey)) radioGroups.set(groupKey, []);
        radioGroups.get(groupKey).push(r);
      }

      for (const [, radios] of radioGroups.entries()) {
        if (!radios.length) continue;
        const groupLabel = getRadioGroupQuestion(radios);
        const optItems = radios.map((r) => {
          const text = getRadioOptionText(r);
          return { r, text, low: text.toLowerCase() };
        });

        let targetRadio = null;

        // 1. Language / English / CEFR Proficiency Radio Group (A1, A2, B1, B2, C1, C2 / Beginner..Advanced)
        const isLanguageOrProficiency =
          /\b(english|language|proficiency|fluency|cefr|speaking|level)\b/i.test(groupLabel) ||
          optItems.some((o) =>
            /\b(a1|a2|b1|b2|c1|c2|beginner\/elementary|pre[\s\-]*intermediate|upper[\s\-]*intermediate|proficient\/native)\b/i.test(
              o.low
            )
          );

        if (isLanguageOrProficiency) {
          const profMatchers = [
            /\bc1\b/i,
            /\badvanced\b/i,
            /\bc2\b/i,
            /\b(fluent|proficient)\b/i,
            /\bb2\b/i,
            /\bupper[\s\-]*intermediate\b/i,
            /\bb1\b/i,
            /\bintermediate\b/i
          ];
          for (const re of profMatchers) {
            const hit = optItems.find((o) => re.test(o.low) && !/\bpre[\s\-]*intermediate\b/i.test(o.low));
            if (hit) {
              targetRadio = hit.r;
              break;
            }
          }
        }

        // 2. General Dropdown/Option Candidate Matcher (Years of experience, Education, Notice period, EEO, etc.)
        if (!targetRadio) {
          const wantNo =
            /\b(sponsorship|visa|require\s*sponsor|need\s*sponsor|work\s*permit|criminal|convicted|felony|non[\s\-]*compete|conflict\s*of\s*interest|government\s*official|previously\s*worked|former\s*employee)\b/i.test(
              groupLabel
            );
          const hasYesNo = optItems.some((o) => /^(yes|no|oui|non|true|false)\b/i.test(o.low));
          if (hasYesNo) {
            const hit = optItems.find((o) =>
              wantNo ? /^(no|non|false)\b/i.test(o.low) : /^(yes|oui|true)\b/i.test(o.low)
            );
            if (hit) targetRadio = hit.r;
          } else {
            const cands = computeBestDropdownCandidates(
              groupLabel,
              optItems.map((o) => o.text),
              profile
            );
            for (const c of cands) {
              const cLow = String(c || "").toLowerCase().trim();
              if (!cLow) continue;
              const hit = optItems.find(
                (o) => o.low === cLow || o.low.includes(cLow) || cLow.includes(o.low)
              );
              if (hit) {
                targetRadio = hit.r;
                break;
              }
            }
          }
        }

        // 3. Fallback: avoid A1/Beginner/None if multiple options exist
        if (!targetRadio) {
          const nonBeginner = optItems.find(
            (o) => !/\b(a1|a2|beginner|elementary|none|decline)\b/i.test(o.low)
          );
          targetRadio = (nonBeginner && nonBeginner.r) || radios[0];
        }

        if (targetRadio && !targetRadio.checked) {
          targetRadio.click();
          if (!targetRadio.checked && targetRadio.labels && targetRadio.labels[0]) {
            targetRadio.labels[0].click();
          }
          if (!targetRadio.checked) {
            const wrap = closestDeep(targetRadio, "label, spl-radio, oc-radio, [role='radio']");
            if (wrap && wrap !== targetRadio) wrap.click();
          }
          if (!targetRadio.checked) {
            targetRadio.checked = true;
          }
          targetRadio.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
          targetRadio.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
          filledCount++;
        }
      }

      // Handle Terms & Conditions / Privacy Policy / GDPR Consent Checkboxes AND Yes/No Question Checkbox Groups (e.g. "Available for Realocation to Portugal: [ ] Yes [ ] No")
      const allCheckboxes = querySelectorAllDeep('input[type="checkbox"]').filter(
        (cb) =>
          !cb.disabled &&
          !closestDeep(cb, "#cvtomatch-autofill-host") &&
          !closestDeep(cb, "rec-tabular-component") &&
          cb.getAttribute("data-cvm-edu-entry") !== "1" &&
          cb.getAttribute("data-cvm-exp-entry") !== "1"
      );
      const yesNoCheckboxes = [];
      for (const cb of allCheckboxes) {
        const cbOptionText = getRadioOptionText(cb).toLowerCase().trim();
        if (/^(yes|no|sim|n[ãa]o|oui|non)$/i.test(cbOptionText)) {
          yesNoCheckboxes.push({ cb, optLow: cbOptionText });
          continue;
        }
        const cbParent = getParentOrShadowHost(cb);
        const cbText = `${getFieldLabel(cb)} ${(cbParent && (cbParent.innerText || cbParent.textContent)) || ""}`
          .replace(/\s+/g, " ")
          .toLowerCase();
        if (
          /\b(agree|accept|consent|terms|conditions|privacy|policy|gdpr|data\s*protection|concordo|termos|condições|condicoes|política|politica|privacidade|j'accepte|confidentialité|acepto|términos|privacidad|einverstanden|datenschutz|acknowledge)\b/i.test(
            cbText
          ) &&
          !/\b(currently\s*work|currently\s*attend|currently\s*pursuing)\b/i.test(cbText)
        ) {
          if (!cb.checked) {
            cb.click();
            if (!cb.checked) cb.checked = true;
            cb.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
            cb.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
            filledCount++;
          }
        }
      }

      // Group Yes/No question checkboxes by their shared question container
      const yesNoGroups = new Map();
      for (const item of yesNoCheckboxes) {
        let groupContainer = getParentOrShadowHost(item.cb);
        for (let d = 0; d < 5 && groupContainer && groupContainer !== document.body; d++) {
          const cbsInCur = querySelectorAllDeep('input[type="checkbox"]', groupContainer);
          if (cbsInCur.length >= 2 && cbsInCur.length <= 4) {
            break;
          }
          groupContainer = getParentOrShadowHost(groupContainer);
        }
        const key = groupContainer || item.cb.getAttribute("name") || item.cb;
        if (!yesNoGroups.has(key)) yesNoGroups.set(key, []);
        yesNoGroups.get(key).push(item);
      }

      for (const [containerEl, items] of yesNoGroups.entries()) {
        const qText = (
          (containerEl && containerEl.innerText) ||
          getFieldLabel(items[0].cb) ||
          ""
        )
          .replace(/\s+/g, " ")
          .toLowerCase();
        const wantNo =
          /\b(sponsorship|visa|require\s*sponsor|need\s*sponsor|criminal|convicted|felony|conflict\s*of\s*interest)\b/i.test(
            qText
          );
        for (const { cb, optLow } of items) {
          const isYesOpt = /^(yes|sim|oui)$/i.test(optLow);
          const shouldCheck = wantNo ? !isYesOpt : isYesOpt;
          if (shouldCheck && !cb.checked) {
            cb.click();
            if (!cb.checked) cb.checked = true;
            cb.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
            cb.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
            filledCount++;
          } else if (!shouldCheck && cb.checked) {
            cb.click();
            if (cb.checked) cb.checked = false;
            cb.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
            cb.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
          }
        }
      }

      // Sync any Select2 / jQuery dropdowns in MAIN world so rendered visual tags match the <select> state
      try {
        chrome.runtime.sendMessage({ type: "SYNC_SELECT2_MAIN_WORLD" });
      } catch (_) {}
    } catch (_) {}

    // Helper to fill a list of inputs inside a single generic Education sub-form or card
    const fillGenericEduCardInputs = async (cardInputs, eduItem, eduIndex = 0) => {
      let count = 0;
      const degreeStr = eduItem.degree || "";
      const schoolStr = eduItem.school || "";
      const majorMatch = degreeStr.match(/\b(?:in|en|of)\s+(.+)$/i);
      const majorStr = majorMatch ? majorMatch[1].trim() : degreeStr || "Computer Science";
      const eduDates = parseDateRange(eduItem.date_text, "2020", "2024");
      const eduLocation = /politehnica|bucharest|bucarest/i.test(schoolStr)
        ? "Bucharest, Romania"
        : /monastir/i.test(schoolStr)
        ? "Monastir, Tunisia"
        : resolvedCountry || "";

      let assignedStartDate = false;
      for (const inp of cardInputs) {
        inp.setAttribute("data-cvm-edu-entry", "1");
        inp.setAttribute("data-cvm-edu-idx", String(eduIndex));
        const lbl = getFieldLabel(inp);
        const ph = (inp.getAttribute("placeholder") || "").toLowerCase();
        const inpType = (inp.getAttribute("type") || "text").toLowerCase();
        if (inpType === "checkbox") {
          if (/current|pursuing|attend/i.test(lbl)) {
            if (eduDates.isCurrent && !inp.checked) inp.click();
            else if (!eduDates.isCurrent && inp.checked) inp.click();
          }
          continue;
        }
        if (/\b(institution|institute|school(?!\s*location)|university|college)\b/i.test(lbl) && schoolStr) {
          if (await fillSmartFieldOrAutocomplete(inp, schoolStr, "institution")) count++;
        } else if (/\b(major|field|study|department|specialization)\b/i.test(lbl) && majorStr) {
          if (await fillSmartFieldOrAutocomplete(inp, majorStr, "major")) count++;
        } else if (/\b(degree|qualification|diploma)\b/i.test(lbl) && degreeStr) {
          if (await fillSmartFieldOrAutocomplete(inp, degreeStr, "degree")) count++;
        } else if (/\b(location|city|country)\b/i.test(lbl) && eduLocation) {
          if (await fillSmartFieldOrAutocomplete(inp, eduLocation, "location")) count++;
        } else if (/\b(from|start\s*date|start)\b/i.test(lbl) || (!assignedStartDate && ph.includes("pick a date"))) {
          assignedStartDate = true;
          const dVal = formatDateForInput(inp, eduDates.startMonthNum, eduDates.startYear, eduDates.startMonth);
          if (setNativeValue(inp, dVal)) count++;
        } else if (
          (/\b(to|end\s*date|end)\b/i.test(lbl) || (assignedStartDate && ph.includes("pick a date"))) &&
          !eduDates.isCurrent
        ) {
          const dVal = formatDateForInput(inp, eduDates.endMonthNum, eduDates.endYear, eduDates.endMonth);
          if (setNativeValue(inp, dVal)) count++;
        }
      }
      return count;
    };

    // Helper to fill a list of inputs inside a single generic Experience sub-form or card
    const fillGenericExpCardInputs = async (cardInputs, expItem, expIndex = 0) => {
      let count = 0;
      const titleStr = expItem.title || "";
      const rawComp = expItem.company || "";
      const compStr =
        rawComp &&
        !/\b(19\d{2}|20\d{2}|july|june|may|aug|sep|oct|feb|jan|mar|apr|nov|dec|monastir|tunisia|romania|remote)\b/i.test(
          rawComp
        )
          ? rawComp
          : titleStr || "Freelance / Contract";
      const summaryStr = String(expItem.description || "")
        .replace(/^\s*[•\-*]\s*/gm, "")
        .trim();
      const expDates = parseDateRange(expItem.date_text || rawComp, "2023", "2024");

      let assignedStartDate = false;
      let assignedTitle = false;
      let assignedCompany = false;
      for (const inp of cardInputs) {
        inp.setAttribute("data-cvm-exp-entry", "1");
        inp.setAttribute("data-cvm-exp-idx", String(expIndex));
        const lbl = getFieldLabel(inp);
        const ph = (inp.getAttribute("placeholder") || "").toLowerCase();
        const inpTag = inp.tagName.toLowerCase();
        const inpType = (inp.getAttribute("type") || "text").toLowerCase();
        if (inpType === "checkbox") {
          if (/current/i.test(lbl)) {
            if (expDates.isCurrent && !inp.checked) inp.click();
            else if (!expDates.isCurrent && inp.checked) inp.click();
          }
          continue;
        }
        if (/\b(occupation|title|role|position|designation)\b/i.test(lbl) && titleStr) {
          if (await fillSmartFieldOrAutocomplete(inp, titleStr, "title")) count++;
          assignedTitle = true;
        } else if (/\b(company|employer|organization|firm|workplace)\b/i.test(lbl) && compStr) {
          if (await fillSmartFieldOrAutocomplete(inp, compStr, "company")) count++;
          assignedCompany = true;
        } else if (/\b(summary|description|responsibilities|duties)\b/i.test(lbl) && summaryStr) {
          if (setNativeValue(inp, summaryStr)) count++;
        } else if (/\b(location|city|country)\b/i.test(lbl)) {
          const locVal = expItem.location || resolvedCountry || "";
          if (locVal && (await fillSmartFieldOrAutocomplete(inp, locVal, "location"))) count++;
        } else if (/\b(from|start\s*date|start)\b/i.test(lbl) || (!assignedStartDate && ph.includes("pick a date"))) {
          assignedStartDate = true;
          const dVal = formatDateForInput(inp, expDates.startMonthNum, expDates.startYear, expDates.startMonth);
          if (setNativeValue(inp, dVal)) count++;
        } else if (
          (/\b(to|end\s*date|end)\b/i.test(lbl) || (assignedStartDate && ph.includes("pick a date"))) &&
          !expDates.isCurrent
        ) {
          const dVal = formatDateForInput(inp, expDates.endMonthNum, expDates.endYear, expDates.endMonth);
          if (setNativeValue(inp, dVal)) count++;
        } else if (
          inpTag === "input" &&
          inpType !== "checkbox" &&
          inpType !== "radio" &&
          inpType !== "file" &&
          !ph.includes("pick a date")
        ) {
          if (!assignedTitle && titleStr) {
            if (await fillSmartFieldOrAutocomplete(inp, titleStr, "title")) count++;
            assignedTitle = true;
          } else if (!assignedCompany && compStr) {
            if (await fillSmartFieldOrAutocomplete(inp, compStr, "company")) count++;
            assignedCompany = true;
          }
        }
      }
      return count;
    };

    // ─── C. Fill ALL Educational Details Entries (1..N) ───────────────────────
    try {
      const eduEntriesDom = Array.from(
        document.querySelectorAll("rec-tabular-component [aria-label*='Educational Details : Entry' i]")
      );
      if (eduEntriesDom.length > 0) {
        for (let i = 0; i < eduEntriesDom.length && i < educationsList.length; i++) {
          const entryEl = eduEntriesDom[i];
          const eduItem = educationsList[i];
          const degreeStr = eduItem.degree || "";
          const schoolStr = eduItem.school || "";
          const majorMatch = degreeStr.match(/\b(?:in|en|of)\s+(.+)$/i);
          const majorStr = majorMatch ? majorMatch[1].trim() : degreeStr || "Computer Science";

          const inputs = getEditableFormInputs(entryEl);
          const eduDates = parseDateRange(eduItem.date_text, "2020", "2024");

          for (const inp of inputs) {
            const lbl = getFieldLabel(inp);
            const inpTag = inp.tagName.toLowerCase();
            const inpType = (inp.getAttribute("type") || "text").toLowerCase();
            if (inpType === "checkbox") {
              if (/currently\s*pursuing|current/i.test(lbl)) {
                if (eduDates.isCurrent && !inp.checked) inp.click();
                else if (!eduDates.isCurrent && inp.checked) inp.click();
              }
              continue;
            }
            if (inpTag === "select") {
              const optTexts = Array.from(inp.options || []).map((o) => o.text || "");
              const cands = computeBestDropdownCandidates(lbl, optTexts, profile, eduItem);
              for (const c of cands) {
                if (setSelectBestOption(inp, c)) {
                  filledCount++;
                  break;
                }
              }
              continue;
            }
            if (/\b(institute|school|university|college|institution)\b/i.test(lbl) && schoolStr) {
              if (setNativeValue(inp, schoolStr)) filledCount++;
            } else if (/\b(major|department|field|branch|specialization|study)\b/i.test(lbl) && majorStr) {
              if (setNativeValue(inp, majorStr)) filledCount++;
            } else if (/\b(degree|qualification|course|diploma)\b/i.test(lbl) && degreeStr) {
              if (setNativeValue(inp, degreeStr)) filledCount++;
            } else {
              const customAns = generateUniversalInputAnswer(
                lbl,
                inpTag === "textarea" ? "textarea" : inpType,
                profile,
                jobCtx,
                matched_skills,
                cover_letter
              );
              if (customAns && setNativeValue(inp, customAns)) {
                filledCount++;
              }
            }
          }

          const dds = Array.from(entryEl.querySelectorAll("lyte-dropdown"));
          if (dds.length >= 4) {
            await selectLyteDropdownOption(dds[0], [eduDates.startMonth]);
            await selectLyteDropdownOption(dds[1], [eduDates.startYear]);
            if (!eduDates.isCurrent) {
              await selectLyteDropdownOption(dds[2], [eduDates.endMonth]);
              await selectLyteDropdownOption(dds[3], [eduDates.endYear]);
            }
            filledCount++;
          }
          for (let dIdx = 4; dIdx < dds.length; dIdx++) {
            if (await fillUniversalLyteDropdown(dds[dIdx], profile, eduItem)) {
              filledCount++;
            }
          }
        }
      } else if (educationsList.length > 0) {
        // Generic ATS Education Repeater (e.g. SmartRecruiters / Workable "+ Add" under "Education")
        const eduSecContainer = findSectionContainer(/^education\b/i);
        const preExistingEduCards = findAllRepeaterCards(
          eduSecContainer,
          /\b(institution|school\s*location|i\s*currently\s*attend)\b/i,
          /\b(office\s*location|i\s*currently\s*work\s*here|^company$)\b/i
        );
        const allPreExistingEduInputs = preExistingEduCards.flat();

        const filledEduInputs = new Set(
          getEditableFormInputs().filter((inp) => !allPreExistingEduInputs.includes(inp))
        );

        let eduStartIdx = 0;
        for (let cIdx = 0; cIdx < preExistingEduCards.length && cIdx < educationsList.length; cIdx++) {
          const cardGroup = preExistingEduCards[cIdx];
          cardGroup.forEach((inp) => filledEduInputs.add(inp));
          filledCount += await fillGenericEduCardInputs(cardGroup, educationsList[cIdx], cIdx);
          eduStartIdx = cIdx + 1;
        }

        for (let i = eduStartIdx; i < Math.min(educationsList.length, 4); i++) {
          const found = findSectionAddButton(/\beducation\b/i);
          if (!found) break;
          found.btn.click();
          await sleep(500);
          const eduItem = educationsList[i];
          const newInputs = getEditableFormInputs().filter((inp) => !filledEduInputs.has(inp));
          newInputs.forEach((inp) => filledEduInputs.add(inp));
          filledCount += await fillGenericEduCardInputs(newInputs, eduItem, i);
        }
      }
    } catch (_) {}

    // ─── D. Fill ALL Experience Details Entries (1..N) ────────────────────────
    const fillExperienceEntriesPass = async () => {
      let expFilled = 0;
      try {
        const expEntriesDom = Array.from(
          document.querySelectorAll("rec-tabular-component [aria-label*='Experience Details : Entry' i]")
        );
        if (expEntriesDom.length > 0) {
          for (let i = 0; i < expEntriesDom.length && i < experiencesList.length; i++) {
            const entryEl = expEntriesDom[i];
            const expItem = experiencesList[i];
            const titleStr = expItem.title || "";
            const rawComp = expItem.company || "";
            const compStr =
              rawComp &&
              !/\b(19\d{2}|20\d{2}|july|june|may|aug|sep|oct|feb|jan|mar|apr|nov|dec|monastir|tunisia|romania|remote)\b/i.test(
                rawComp
              )
                ? rawComp
                : titleStr || "Freelance / Contract";
            const summaryStr = String(expItem.description || "")
              .replace(/^\s*[•\-*]\s*/gm, "")
              .trim();
            const expDates = parseDateRange(expItem.date_text || rawComp, "2023", "2024");

            const inputs = getEditableFormInputs(entryEl);
            const hasExplicitTitleField = inputs.some((inp) =>
              /\b(occupation|title|role|position|designation)\b/i.test(getFieldLabel(inp))
            );
            let assignedFirstTextAsRole = false;

            for (const inp of inputs) {
              const lbl = getFieldLabel(inp);
              const inpTag = inp.tagName.toLowerCase();
              const inpType = (inp.getAttribute("type") || "text").toLowerCase();

              if (inpType === "checkbox") {
                if (/currently\s*work\s*here/i.test(lbl)) {
                  if (expDates.isCurrent && !inp.checked) inp.click();
                  else if (!expDates.isCurrent && inp.checked) inp.click();
                }
                continue;
              }
              if (inpTag === "select") {
                const optTexts = Array.from(inp.options || []).map((o) => o.text || "");
                const cands = computeBestDropdownCandidates(lbl, optTexts, profile, expItem);
                for (const c of cands) {
                  if (setSelectBestOption(inp, c)) {
                    expFilled++;
                    break;
                  }
                }
                continue;
              }

              if (/\b(occupation|title|role|position|designation)\b/i.test(lbl) && titleStr) {
                if (setNativeValue(inp, titleStr)) expFilled++;
              } else if (/\b(company|employer|organization|firm|client)\b/i.test(lbl) && compStr) {
                if (setNativeValue(inp, compStr)) expFilled++;
              } else if (/\b(summary|description|responsibilities|duties|details)\b/i.test(lbl) && summaryStr) {
                if (setNativeValue(inp, summaryStr)) expFilled++;
              } else if (/\b(location|city|country)\b/i.test(lbl)) {
                const locVal = expItem.location || resolvedCountry || "";
                if (locVal && setNativeValue(inp, locVal)) expFilled++;
              } else {
                const customAns = generateUniversalInputAnswer(
                  lbl,
                  inpTag === "textarea" ? "textarea" : inpType,
                  profile,
                  jobCtx,
                  matched_skills,
                  cover_letter,
                  expItem
                );
                if (customAns) {
                  if (setNativeValue(inp, customAns)) expFilled++;
                  assignedFirstTextAsRole = true;
                } else if (!hasExplicitTitleField && !assignedFirstTextAsRole && inpTag === "input" && titleStr) {
                  if (setNativeValue(inp, titleStr)) expFilled++;
                  assignedFirstTextAsRole = true;
                }
              }
            }

            const dds = Array.from(entryEl.querySelectorAll("lyte-dropdown"));
            if (dds.length >= 4) {
              await selectLyteDropdownOption(dds[0], [expDates.startMonth]);
              await selectLyteDropdownOption(dds[1], [expDates.startYear]);
              if (!expDates.isCurrent) {
                await selectLyteDropdownOption(dds[2], [expDates.endMonth]);
                await selectLyteDropdownOption(dds[3], [expDates.endYear]);
              }
              expFilled++;
            }
            for (let dIdx = 4; dIdx < dds.length; dIdx++) {
              if (await fillUniversalLyteDropdown(dds[dIdx], profile, expItem)) {
                expFilled++;
              }
            }
          }
        } else if (experiencesList.length > 0) {
          // Generic ATS Experience Repeater (e.g. SmartRecruiters / Workable "+ Add" under "Experience")
          let expSecContainer = findSectionContainer(/^experience\b/i);
          let preExistingExpCards = findAllRepeaterCards(
            expSecContainer,
            /\b(^title$|office\s*location|i\s*currently\s*work\s*here)\b/i,
            /\b(institution|school\s*location|i\s*currently\s*attend)\b/i
          );
          const allPreExistingExpInputs = preExistingExpCards.flat();

          const filledExpInputs = new Set(
            getEditableFormInputs().filter((inp) => !allPreExistingExpInputs.includes(inp))
          );

          let startIndex = 0;
          for (let cIdx = 0; cIdx < preExistingExpCards.length && cIdx < experiencesList.length; cIdx++) {
            const cardGroup = preExistingExpCards[cIdx];
            cardGroup.forEach((inp) => filledExpInputs.add(inp));
            expFilled += await fillGenericExpCardInputs(cardGroup, experiencesList[cIdx], cIdx);
            startIndex = cIdx + 1;
          }

          for (let i = startIndex; i < Math.min(experiencesList.length, 4); i++) {
            const found = findSectionAddButton(/\bexperience\b/i);
            if (!found) break;
            found.btn.click();
            await sleep(500);
            const expItem = experiencesList[i];
            const newInputs = getEditableFormInputs().filter((inp) => !filledExpInputs.has(inp));
            newInputs.forEach((inp) => filledExpInputs.add(inp));
            expFilled += await fillGenericExpCardInputs(newInputs, expItem, i);
          }
        }
      } catch (_) {}
      return expFilled;
    };

    filledCount += await fillExperienceEntriesPass();

    if (filledCount === 0) {
      try {
        await navigator.clipboard.writeText(cover_letter || "");
      } catch (_) {}
      progress(
        "No open form inputs found on this page yet — click the job's 'Apply' button first, then click Autofill!",
        "success",
        100
      );
    } else {
      const pdfBadge = attachedResume
        ? used_tailored_pdf
          ? ` + Tailored PDF (${resume_filename})`
          : ` + CV (${resume_filename})`
        : "";
      progress(`✓ Autofilled ${filledCount} field(s)${pdfBadge}!`, "success", 100);
    }

    return {
      filledCount,
      attachedResume,
      matchScore: match_score,
      matchedSkills: matched_skills,
      resumeFilename: resume_filename,
      usedTailoredPdf: used_tailored_pdf,
      jobCtx
    };
  }

  // ─── 7. Listen for Popup Commands ──────────────────────────────────────────
  if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
      if (msg.type === "TRIGGER_PAGE_AUTOFILL") {
        runAutofill({ tailorCv: msg.tailorCv !== false }).then((res) => {
          sendResponse({ ok: Boolean(res), result: res });
        });
        return true;
      }
      if (msg.type === "GET_PAGE_JOB_CONTEXT") {
        sendResponse({ ok: true, jobCtx: extractJobContext() });
        return false;
      }
    });
  }

  // ─── 8. Floating Shadow-DOM Widget on Job Application Pages ────────────────
  let dismissedByUser = false;

  function refreshMountedWidgetJobMeta() {
    const host = document.getElementById("cvtomatch-autofill-host");
    if (!host || !host.shadowRoot) return;
    const titleEl = host.shadowRoot.getElementById("jobTitle");
    const companyEl = host.shadowRoot.getElementById("jobCompany");
    if (!titleEl || !companyEl) return;
    const ctx = extractJobContext();
    if (ctx.job_title) titleEl.textContent = ctx.job_title;
    if (ctx.company) companyEl.textContent = ctx.company;
  }

  function isApplyTriggerElement(target) {
    if (!target || typeof target.closest !== "function") return null;
    if (closestDeep(target, "#cvtomatch-autofill-host")) return null;
    const clickable = target.closest(
      "button, a, [role='button'], input[type='button'], input[type='submit'], lyte-button, spl-button"
    );
    if (!clickable) return null;

    const text = [
      clickable.innerText || clickable.textContent || "",
      clickable.getAttribute("aria-label") || "",
      clickable.getAttribute("title") || "",
      clickable.getAttribute("value") || "",
      clickable.getAttribute("data-testid") || "",
      clickable.getAttribute("id") || "",
      clickable.className && typeof clickable.className === "string" ? clickable.className : ""
    ]
      .join(" ")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();

    const href = (clickable.getAttribute("href") || "").toLowerCase();

    // Ignore filters, saved jobs, share buttons, or login buttons
    if (
      /\b(filter|search|save\s+job|saved|share|sign\s+in|log\s+in|login|alert|cancel|close|dismiss|back)\b/i.test(
        text
      )
    ) {
      return null;
    }

    const hasApplyText =
      /\b(apply(\s+now|\s+for\s+this\s+job|\s+to\s+job|\s+online|\s+today|\s+here|\s+with\s+\w+)?|easy\s+apply|quick\s+apply|i'?m\s+interested|start\s+application|candidatar(\-se)?|candidature(\s+simplifi[eé]e)?|postuler|aplicar|jetzt\s+bewerben|solliciteren)\b/i.test(
        text
      );
    const hasApplyHref =
      /\/(apply|application)(\/|$|\?|#)/i.test(href) || /^#(apply|application|app)\b/i.test(href);

    if (hasApplyText || hasApplyHref) {
      return clickable;
    }
    return null;
  }

  function handleUserApplyInteraction(e) {
    const trigger = isApplyTriggerElement(e.target);
    if (!trigger) return;

    // 1. Capture job title, company, and full job description BEFORE navigation or modal open
    captureJobPostIfPresent(true);

    // 2. Mark that the user explicitly clicked Apply
    const now = Date.now();
    userClickedApply = true;
    lastApplyClickTs = now;
    dismissedByUser = false;

    try {
      sessionStorage.setItem("cvtomatch_apply_clicked", String(now));
    } catch (_) {}
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      try {
        chrome.storage.local.set({
          cvtomatch_apply_clicked: { timestamp: now, host: HOST, url: location.href }
        });
      } catch (_) {}
    }

    // 3. Schedule popup mount checks as the application modal or form opens
    setTimeout(mountFloatingWidget, 150);
    setTimeout(mountFloatingWidget, 600);
    setTimeout(mountFloatingWidget, 1300);
    setTimeout(mountFloatingWidget, 2200);
  }

  document.addEventListener("mousedown", handleUserApplyInteraction, true);
  document.addEventListener("click", handleUserApplyInteraction, true);

  function mountFloatingWidget() {
    if (dismissedByUser) return;
    if (document.getElementById("cvtomatch-autofill-host")) {
      refreshMountedWidgetJobMeta();
      return;
    }
    // Always silently capture the job post when viewing a job description page before clicking Apply
    captureJobPostIfPresent(false);

    // Strictly mount the popup ONLY when the user clicked Apply or an application form is open on screen
    if (!shouldShowFloatingPopup()) return;

    const host = document.createElement("div");
    host.id = "cvtomatch-autofill-host";
    host.style.cssText =
      "all: initial; position: fixed; bottom: 22px; right: 22px; z-index: 2147483646; font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;";
    document.documentElement.appendChild(host);

    const shadow = host.attachShadow({ mode: "open" });
    const ctx = extractJobContext();

    shadow.innerHTML = `
      <style>
        * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif; }
        @keyframes cvm-spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        .dock {
          width: 318px;
          background: #0b1120;
          color: #f8fafc;
          border: 1px solid rgba(99, 102, 241, 0.4);
          border-radius: 16px;
          box-shadow: 0 20px 45px -12px rgba(2, 6, 23, 0.8), 0 0 0 1px rgba(255,255,255,0.06);
          overflow: hidden;
          transition: all 0.22s ease;
        }
        .dock.minimized {
          width: auto;
          border-radius: 999px;
        }
        .dock.minimized .body { display: none; }
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 11px 14px;
          background: linear-gradient(135deg, #172036 0%, #0b1120 100%);
          border-bottom: 1px solid rgba(148, 163, 184, 0.16);
          cursor: pointer;
          user-select: none;
        }
        .dock.minimized .header {
          border-bottom: none;
          padding: 8px 14px;
          gap: 8px;
        }
        .brand {
          display: flex;
          align-items: center;
          gap: 8px;
          font-weight: 800;
          font-size: 13.5px;
          color: #ffffff;
          letter-spacing: -0.02em;
        }
        .header-actions {
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .score-pill {
          font-size: 10px;
          font-weight: 700;
          padding: 2px 7px;
          border-radius: 999px;
          background: rgba(37, 99, 235, 0.22);
          border: 1px solid rgba(96, 165, 250, 0.4);
          color: #93c5fd;
          display: none;
        }
        .icon-btn {
          background: transparent;
          border: none;
          color: #94a3b8;
          cursor: pointer;
          font-size: 14px;
          line-height: 1;
          padding: 2px 5px;
          border-radius: 6px;
        }
        .icon-btn:hover { color: #ffffff; background: rgba(255,255,255,0.08); }
        .body { padding: 12px 14px 14px; }
        .job-meta {
          margin-bottom: 10px;
          padding: 8px 10px;
          background: #131c31;
          border: 1px solid #26334d;
          border-radius: 10px;
        }
        .job-title {
          font-size: 12px;
          font-weight: 700;
          color: #f1f5f9;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .job-company {
          font-size: 11px;
          color: #94a3b8;
          margin-top: 2px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .toggle-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 11.5px;
          color: #cbd5e1;
          margin-bottom: 10px;
          padding: 4px 2px;
        }
        .toggle-row input {
          accent-color: #4f46e5;
          width: 14px;
          height: 14px;
          cursor: pointer;
        }
        .btn-primary {
          width: 100%;
          padding: 9.5px 12px;
          border-radius: 10px;
          border: 1px solid rgba(99, 102, 241, 0.45);
          background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%);
          color: #ffffff;
          font-weight: 700;
          font-size: 12.5px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 7px;
          box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
          transition: opacity 0.15s ease, transform 0.1s ease;
        }
        .btn-primary:hover { opacity: 0.95; }
        .btn-primary:active { transform: scale(0.99); }
        .btn-primary:disabled { opacity: 0.75; cursor: wait; }
        .spinner {
          width: 13px;
          height: 13px;
          border: 2px solid rgba(255, 255, 255, 0.3);
          border-top-color: #ffffff;
          border-radius: 50%;
          animation: cvm-spin 0.7s linear infinite;
          display: inline-block;
          flex-shrink: 0;
        }
        .btn-secondary {
          width: 100%;
          margin-top: 7px;
          padding: 7.5px 10px;
          border-radius: 9px;
          border: 1px solid #26334d;
          background: #131c31;
          color: #cbd5e1;
          font-weight: 600;
          font-size: 11.5px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 5px;
        }
        .btn-secondary:hover { background: #1e293b; color: #ffffff; }
        .progress-wrap {
          margin-top: 9px;
          display: none;
        }
        .progress-wrap.visible { display: block; }
        .progress-bar-bg {
          width: 100%;
          height: 5px;
          background: #1e293b;
          border-radius: 999px;
          overflow: hidden;
          margin-bottom: 6px;
        }
        .progress-bar-fill {
          height: 100%;
          width: 0%;
          background: linear-gradient(90deg, #3b82f6, #818cf8);
          border-radius: 999px;
          transition: width 0.3s ease;
        }
        .status {
          font-size: 11px;
          line-height: 1.4;
          padding: 7.5px 9px;
          border-radius: 8px;
          display: flex;
          align-items: center;
          gap: 7px;
        }
        .status.loading {
          background: rgba(37, 99, 235, 0.16);
          border: 1px solid rgba(59, 130, 246, 0.35);
          color: #bfdbfe;
        }
        .status.success {
          background: rgba(16, 185, 129, 0.15);
          border: 1px solid rgba(16, 185, 129, 0.4);
          color: #a7f3d0;
        }
        .status.error {
          background: rgba(239, 68, 68, 0.15);
          border: 1px solid rgba(239, 68, 68, 0.35);
          color: #fca5a5;
        }
      </style>
      <div class="dock" id="dock">
        <div class="header" id="header">
          <div class="brand">
            <svg width="24" height="22" viewBox="0 0 60 56" fill="none" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <linearGradient id="cvm-c" x1="6" y1="8" x2="40" y2="50" gradientUnits="userSpaceOnUse">
                  <stop offset="0%" stop-color="#5B58F6" />
                  <stop offset="100%" stop-color="#4338CA" />
                </linearGradient>
                <linearGradient id="cvm-v" x1="22" y1="38" x2="48" y2="14" gradientUnits="userSpaceOnUse">
                  <stop offset="0%" stop-color="#6366F1" />
                  <stop offset="100%" stop-color="#8B93FF" />
                </linearGradient>
              </defs>
              <path d="M36.8 16.5C33.6 13.5 29.3 12 24.5 12C14.6 12 7 19.8 7 30C7 40.2 14.6 48 24.5 48C29.6 48 34 46.2 37.3 42.9" stroke="url(#cvm-c)" stroke-width="10.2" stroke-linecap="butt" />
              <path d="M22.5 27.5L29.8 38.2L45 16.8" stroke="url(#cvm-v)" stroke-width="8.2" stroke-linecap="butt" stroke-linejoin="miter" />
              <circle cx="50" cy="10.5" r="4.2" fill="#10B981" />
            </svg>
            <span>CVto<span style="color:#818CF8;">Match</span> Autofill</span>
          </div>
          <div class="header-actions">
            <span class="score-pill" id="scorePill"></span>
            <button class="icon-btn" id="minBtn" title="Minimize / Expand">–</button>
            <button class="icon-btn" id="closeBtn" title="Hide on this page">✕</button>
          </div>
        </div>
        <div class="body">
          <div class="job-meta">
            <div class="job-title" id="jobTitle">${(ctx.job_title || "Job Application").replace(/</g, "&lt;")}</div>
            <div class="job-company" id="jobCompany">${(ctx.company || HOST).replace(/</g, "&lt;")}</div>
          </div>
          <label class="toggle-row">
            <span>✨ Tailor CV PDF &amp; AI Answers</span>
            <input type="checkbox" id="tailorToggle" checked />
          </label>
          <button class="btn-primary" id="fillBtn">
            <span>⚡ 1-Click Autofill Form</span>
          </button>
          <button class="btn-secondary" id="trackBtn">
            <span>📌 Save Job to Tracker</span>
          </button>
          <div class="progress-wrap" id="progressWrap">
            <div class="progress-bar-bg">
              <div class="progress-bar-fill" id="progressFill"></div>
            </div>
            <div class="status loading" id="statusBox"></div>
          </div>
        </div>
      </div>
    `;

    const dock = shadow.getElementById("dock");
    const minBtn = shadow.getElementById("minBtn");
    const closeBtn = shadow.getElementById("closeBtn");
    const header = shadow.getElementById("header");
    const fillBtn = shadow.getElementById("fillBtn");
    const trackBtn = shadow.getElementById("trackBtn");
    const tailorToggle = shadow.getElementById("tailorToggle");
    const progressWrap = shadow.getElementById("progressWrap");
    const progressFill = shadow.getElementById("progressFill");
    const statusBox = shadow.getElementById("statusBox");
    const scorePill = shadow.getElementById("scorePill");
    const jobTitleEl = shadow.getElementById("jobTitle");
    const jobCompanyEl = shadow.getElementById("jobCompany");

    let lastMatchScore = 0;

    function updateProgress(text, type = "loading", pct = 50) {
      progressWrap.classList.add("visible");
      progressFill.style.width = `${pct}%`;
      statusBox.className = `status ${type}`;
      statusBox.textContent = "";
      if (type === "loading") {
        const spin = document.createElement("span");
        spin.className = "spinner";
        const txt = document.createElement("span");
        txt.textContent = text;
        statusBox.appendChild(spin);
        statusBox.appendChild(txt);
      } else {
        statusBox.textContent = text;
      }
    }

    minBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      dock.classList.toggle("minimized");
      minBtn.textContent = dock.classList.contains("minimized") ? "+" : "–";
    });

    header.addEventListener("click", () => {
      if (dock.classList.contains("minimized")) {
        dock.classList.remove("minimized");
        minBtn.textContent = "–";
      }
    });

    closeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      dismissedByUser = true;
      host.remove();
    });

    fillBtn.addEventListener("click", async () => {
      fillBtn.disabled = true;
      fillBtn.innerHTML = `<span class="spinner"></span><span>Autofilling Application...</span>`;
      try {
        const freshCtx = extractJobContext();
        jobTitleEl.textContent = freshCtx.job_title;
        jobCompanyEl.textContent = freshCtx.company;

        const res = await runAutofill({
          tailorCv: tailorToggle.checked,
          onProgress: updateProgress
        });
        if (res && res.matchScore) {
          lastMatchScore = res.matchScore;
          scorePill.textContent = `${res.matchScore}% Match`;
          scorePill.style.display = "inline-block";
        }
      } finally {
        fillBtn.disabled = false;
        fillBtn.innerHTML = "<span>⚡ 1-Click Autofill Form</span>";
      }
    });

    trackBtn.addEventListener("click", async () => {
      trackBtn.disabled = true;
      updateProgress("Saving job to your CVtoMatch Tracker...", "loading", 60);
      const freshCtx = extractJobContext();
      const resp = await sendBgMessageWithTimeout({
        type: "TRACK_APPLICATION",
        payload: {
          title: freshCtx.job_title,
          company: freshCtx.company,
          location: "Remote",
          url: freshCtx.job_url,
          match_score: lastMatchScore
        }
      });
      trackBtn.disabled = false;
      if (resp && resp.ok) {
        updateProgress("✓ Saved to your CVtoMatch Application Tracker!", "success", 100);
      } else {
        updateProgress(resp?.error || "Could not save to Tracker", "error", 100);
      }
    });
  }

  setTimeout(() => {
    captureJobPostIfPresent(false);
    mountFloatingWidget();
  }, 600);

  let lastHref = location.href;
  let captureDebounceTimer = null;

  const observer = new MutationObserver(() => {
    if (typeof chrome === "undefined" || !chrome.runtime || !chrome.runtime.id) {
      observer.disconnect();
      return;
    }
    if (location.href !== lastHref) {
      lastHref = location.href;
      dismissedByUser = false;
      const isApplyUrl = /\/(apply|application)(\/|$|\?)/i.test(window.location.pathname || "");
      if (!isApplyUrl && Date.now() - lastApplyClickTs > 6000) {
        userClickedApply = false;
      }
      const host = document.getElementById("cvtomatch-autofill-host");
      if (host) host.remove();
      setTimeout(() => {
        captureJobPostIfPresent(false);
        mountFloatingWidget();
      }, 800);
    } else {
      if (!captureDebounceTimer) {
        captureDebounceTimer = setTimeout(() => {
          captureDebounceTimer = null;
          captureJobPostIfPresent(false);
        }, 1000);
      }
      const existingWidget = document.getElementById("cvtomatch-autofill-host");
      if (!dismissedByUser && !existingWidget && shouldShowFloatingPopup()) {
        mountFloatingWidget();
      } else if (
        existingWidget &&
        !shouldShowFloatingPopup() &&
        Date.now() - lastApplyClickTs > 5000
      ) {
        existingWidget.remove();
      }
    }
  });
  if (document.documentElement) {
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }
})();
