// CVtoMatch Autofill — Self-Contained Extension Popup Controller
// Runs open-tab token sync, Google Sign-In, and API fallback directly so it works immediately.

document.addEventListener("DOMContentLoaded", () => {
  const loginView = document.getElementById("loginView");
  const mainView = document.getElementById("mainView");
  const authBadge = document.getElementById("authBadge");
  const statusMsg = document.getElementById("statusMsg");

  const googleLoginBtn = document.getElementById("googleLoginBtn");
  const emailInput = document.getElementById("emailInput");
  const passwordInput = document.getElementById("passwordInput");
  const apiBaseInput = document.getElementById("apiBaseInput");
  const loginBtn = document.getElementById("loginBtn");
  const logoutBtn = document.getElementById("logoutBtn");

  const personaSelect = document.getElementById("personaSelect");
  const cvFileLabel = document.getElementById("cvFileLabel");
  const skillsCountLabel = document.getElementById("skillsCountLabel");
  const tailorCheck = document.getElementById("tailorCheck");
  const autofillNowBtn = document.getElementById("autofillNowBtn");
  const saveTrackerBtn = document.getElementById("saveTrackerBtn");
  const copyPills = document.getElementById("copyPills");
  const openDashboardLink = document.getElementById("openDashboardLink");

  function showStatus(text, isError = false) {
    statusMsg.textContent = text;
    statusMsg.className = `status ${isError ? "error" : "info"}`;
  }

  function getStorage() {
    return new Promise((resolve) => {
      chrome.storage.local.get(
        ["cvtomatch_token", "cvtomatch_api_base", "cvtomatch_user"],
        (res) => {
          resolve({
            token: res.cvtomatch_token || "",
            apiBase: (res.cvtomatch_api_base || "https://cvtomatch.com").replace(/\/+$/, ""),
            user: res.cvtomatch_user || null
          });
        }
      );
    });
  }

  // Directly inspect any open CVtoMatch tab for a logged-in JWT token
  async function syncFromOpenTabs() {
    try {
      if (!chrome.tabs || !chrome.scripting) return null;
      const tabs = await chrome.tabs.query({});
      for (const tab of tabs) {
        const url = (tab.url || "").toLowerCase();
        if (
          url.includes("cvtomatch.com") ||
          url.includes("job-searcher-api") ||
          url.includes("localhost:5173") ||
          url.includes("localhost:8000") ||
          url.includes("127.0.0.1:5173") ||
          url.includes("127.0.0.1:8000")
        ) {
          try {
            const results = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: () => {
                const token = localStorage.getItem("token");
                let user = null;
                try {
                  user = JSON.parse(localStorage.getItem("user") || "null");
                } catch (_) {}
                const origin =
                  window.location.port === "5173"
                    ? "http://localhost:8000"
                    : window.location.origin;
                document.documentElement.setAttribute("data-cvtomatch-extension", "installed");
                return { token, user, origin };
              }
            });
            const data = results && results[0] && results[0].result;
            if (data && data.token) {
              const apiBase = (data.origin || "https://cvtomatch.com").replace(/\/+$/, "");
              await chrome.storage.local.set({
                cvtomatch_token: data.token,
                cvtomatch_user: data.user || null,
                cvtomatch_api_base: apiBase
              });
              return { token: data.token, user: data.user, apiBase };
            }
          } catch (_) {}
        }
      }
    } catch (_) {}
    return null;
  }

  async function directApiFetch(path, options = {}) {
    const { token, apiBase } = await getStorage();
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {})
    };
    if (token && !options.skipAuth) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const resp = await fetch(`${apiBase}${path}`, {
      method: options.method || "GET",
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined
    });
    const contentType = (resp.headers.get("content-type") || "").toLowerCase();
    if (resp.status === 404 || resp.status === 405 || contentType.includes("text/html")) {
      const e = new Error("HTTP_404");
      e.status = resp.status;
      throw e;
    }
    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}));
      if (errData.detail === "Method Not Allowed") {
        throw new Error("HTTP_404");
      }
      throw new Error(errData.detail || `HTTP ${resp.status}`);
    }
    return await resp.json();
  }

  const KNOWN_COUNTRIES = new Set([
    "romania", "roumanie", "tunisia", "tunisie", "france", "germany",
    "united kingdom", "uk", "united states", "usa", "canada", "spain",
    "italy", "netherlands", "belgium", "switzerland", "morocco",
    "united arab emirates", "uae"
  ]);

  async function fetchProfileDirect() {
    // Prefer background service worker's unified profile builder (includes educations, experiences, and strict location rules)
    try {
      const bgResp = await new Promise((resolve) => {
        chrome.runtime.sendMessage({ type: "GET_PROFILE" }, (r) => {
          if (chrome.runtime.lastError || !r || !r.ok || !r.profile) {
            resolve(null);
          } else {
            resolve(r.profile);
          }
        });
      });
      if (bgResp) return bgResp;
    } catch (_) {}

    try {
      return await directApiFetch("/api/extension/profile");
    } catch (err) {
      if (err.message !== "HTTP_404") throw err;
      // Seamless fallback to existing production routes on https://cvtomatch.com
      const { user, cachedProfile } = await new Promise((resolve) => {
        chrome.storage.local.get(["cvtomatch_user", "cvtomatch_cached_profile"], (res) =>
          resolve({ user: res.cvtomatch_user || null, cachedProfile: res.cvtomatch_cached_profile || null })
        );
      });
      const [personasRes, parsedRes, analyzeRes] = await Promise.all([
        directApiFetch("/api/cv/personas").catch(() => ({ personas: [] })),
        directApiFetch("/api/cv/parsed").catch(() => ({ cv: {} })),
        directApiFetch("/api/cv/analyze").catch(() => ({}))
      ]);
      const structured = (parsedRes && parsedRes.cv) || {};
      const contact = structured.contact || {};
      const links = structured.links || {};
      const personas = (personasRes && personasRes.personas) || [];
      const activePersona = personas.find((p) => p.is_active) || personas[0] || null;
      const skills =
        structured.skills ||
        analyzeRes.skills ||
        (activePersona && activePersona.top_skills) ||
        [];

      const normalizeUrl = (u) => {
        if (!u) return "";
        const s = String(u).trim();
        return s.startsWith("http") ? s : `https://${s}`;
      };

      const rawLoc = (
        contact.location ||
        (analyzeRes.locations_found && analyzeRes.locations_found[0]) ||
        ""
      ).trim();
      const locParts = rawLoc.split(",").map((s) => s.trim()).filter(Boolean);
      let city = "";
      let country = "";
      if (locParts.length >= 2) {
        city = locParts[0];
        country = locParts[locParts.length - 1];
      } else if (locParts.length === 1) {
        if (KNOWN_COUNTRIES.has(locParts[0].toLowerCase())) {
          country = locParts[0];
          city = "";
        } else {
          city = locParts[0];
        }
      }

      return {
        ...(cachedProfile || {}),
        full_name: (structured.name || (user && user.name) || "").trim(),
        email: contact.email || (user && user.email) || "",
        phone: contact.phone || "",
        location: rawLoc,
        city,
        state: city,
        street: city,
        postal_code: "",
        country,
        linkedin_url: normalizeUrl(links.linkedin || ""),
        github_url: normalizeUrl(links.github || ""),
        portfolio_url: normalizeUrl(links.portfolio || links.website || ""),
        skills: skills.slice(0, 25),
        resume_filename:
          (parsedRes && parsedRes.filename) ||
          (activePersona && activePersona.filename) ||
          "Resume.pdf",
        personas
      };
    }
  }

  function renderProfile(profile) {
    authBadge.textContent = "Synced";
    statusMsg.className = "status";

    personaSelect.innerHTML = "";
    const personas = profile.personas || [];
    if (personas.length === 0) {
      const opt = document.createElement("option");
      opt.textContent = "No CV uploaded yet — Upload on CVtoMatch";
      personaSelect.appendChild(opt);
    } else {
      personas.forEach((p) => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = `${p.persona_name} (${p.filename})`;
        if (p.is_active) opt.selected = true;
        personaSelect.appendChild(opt);
      });
    }

    cvFileLabel.textContent = profile.resume_filename
      ? `📄 ${profile.resume_filename}`
      : "No PDF uploaded";
    skillsCountLabel.textContent = `${(profile.skills || []).length} skills ready`;

    const fields = [
      { k: "Full Name", v: profile.full_name },
      { k: "Email", v: profile.email },
      { k: "Phone", v: profile.phone },
      { k: "Location", v: profile.location },
      { k: "LinkedIn", v: profile.linkedin_url },
      { k: "GitHub / Site", v: profile.github_url || profile.portfolio_url }
    ];
    copyPills.innerHTML = "";
    fields.forEach(({ k, v }) => {
      const btn = document.createElement("button");
      btn.className = "copy-pill";
      btn.innerHTML = `<div class="k">${k}</div><div class="v">${v || "—"}</div>`;
      btn.addEventListener("click", () => {
        if (!v) return;
        navigator.clipboard.writeText(v);
        showStatus(`Copied ${k} to clipboard!`);
      });
      copyPills.appendChild(btn);
    });
  }

  async function loadProfile() {
    try {
      const profile = await fetchProfileDirect();
      await chrome.storage.local.set({ cvtomatch_cached_profile: profile });
      loginView.classList.add("hidden");
      mainView.classList.remove("hidden");
      renderProfile(profile);
    } catch (err) {
      // Try re-syncing from an open tab once if token expired
      const synced = await syncFromOpenTabs();
      if (synced && synced.token) {
        try {
          const profile = await fetchProfileDirect();
          loginView.classList.add("hidden");
          mainView.classList.remove("hidden");
          renderProfile(profile);
          return;
        } catch (_) {}
      }
      authBadge.textContent = "Sign In";
      mainView.classList.add("hidden");
      loginView.classList.remove("hidden");
    }
  }

  // Initialize on Popup Open
  (async () => {
    let state = await getStorage();
    if (!state.token) {
      const synced = await syncFromOpenTabs();
      if (synced && synced.token) {
        state = synced;
      }
    }
    if (state.apiBase) {
      apiBaseInput.value = state.apiBase;
      openDashboardLink.href = state.apiBase;
    }
    if (state.token) {
      await loadProfile();
    } else {
      authBadge.textContent = "Sign In";
      loginView.classList.remove("hidden");
    }
  })();

  // Sign in with Google button (self-contained in popup.js!)
  googleLoginBtn.addEventListener("click", async () => {
    const apiBase = (apiBaseInput.value.trim() || "https://cvtomatch.com").replace(/\/+$/, "");
    await chrome.storage.local.set({ cvtomatch_api_base: apiBase });
    googleLoginBtn.disabled = true;
    showStatus("Checking active CVtoMatch session...");

    // 1. Check if already logged in on any open CVtoMatch tab
    const synced = await syncFromOpenTabs();
    if (synced && synced.token) {
      googleLoginBtn.disabled = false;
      await loadProfile();
      return;
    }

    // 2. Otherwise open CVtoMatch Google Sign-In popup window and watch for token
    const authUrl = `${apiBase}/?ext_google_auth=1`;
    showStatus("Complete Google Sign-In in the opened window...");

    if (chrome.windows && chrome.windows.create) {
      chrome.windows.create(
        { url: authUrl, type: "popup", width: 520, height: 680, focused: true },
        (win) => {
          if (!win || !win.tabs || !win.tabs[0]) {
            chrome.tabs.create({ url: authUrl });
            googleLoginBtn.disabled = false;
            return;
          }
          const tabId = win.tabs[0].id;
          const winId = win.id;
          let checks = 0;
          const timer = setInterval(async () => {
            checks++;
            if (checks > 150) {
              clearInterval(timer);
              googleLoginBtn.disabled = false;
              return;
            }
            try {
              const results = await chrome.scripting.executeScript({
                target: { tabId },
                func: () => {
                  const token = localStorage.getItem("token");
                  let user = null;
                  try {
                    user = JSON.parse(localStorage.getItem("user") || "null");
                  } catch (_) {}
                  return { token, user };
                }
              });
              const res = results && results[0] && results[0].result;
              if (res && res.token) {
                clearInterval(timer);
                await chrome.storage.local.set({
                  cvtomatch_token: res.token,
                  cvtomatch_user: res.user || null,
                  cvtomatch_api_base: apiBase
                });
                try { chrome.windows.remove(winId); } catch (_) {}
                googleLoginBtn.disabled = false;
                await loadProfile();
              }
            } catch (_) {}
          }, 800);
        }
      );
    } else {
      chrome.tabs.create({ url: authUrl });
      googleLoginBtn.disabled = false;
    }
  });

  // Email + Password Sign In button
  loginBtn.addEventListener("click", async () => {
    const email = emailInput.value.trim();
    const password = passwordInput.value;
    const apiBase = (apiBaseInput.value.trim() || "https://cvtomatch.com").replace(/\/+$/, "");
    if (!email || !password) {
      showStatus("Enter your email & password, or click 'Sign in with Google' above.", true);
      return;
    }
    await chrome.storage.local.set({ cvtomatch_api_base: apiBase });
    loginBtn.disabled = true;
    loginBtn.textContent = "Signing in...";
    try {
      const data = await directApiFetch("/api/auth/login", {
        method: "POST",
        skipAuth: true,
        body: { email, password }
      });
      await chrome.storage.local.set({
        cvtomatch_token: data.access_token,
        cvtomatch_user: data.user || { email },
        cvtomatch_api_base: apiBase
      });
      await loadProfile();
    } catch (err) {
      const msg = String(err.message || "");
      if (msg.includes("Invalid") || msg.includes("401")) {
        showStatus("Invalid password — if you use Google, click 'Sign in with Google' above!", true);
      } else {
        showStatus(msg || "Login failed", true);
      }
    } finally {
      loginBtn.disabled = false;
      loginBtn.textContent = "Sign In & Sync CV";
    }
  });

  logoutBtn.addEventListener("click", async () => {
    await chrome.storage.local.remove([
      "cvtomatch_token",
      "cvtomatch_user",
      "cvtomatch_cached_profile"
    ]);
    authBadge.textContent = "Sign In";
    mainView.classList.add("hidden");
    loginView.classList.remove("hidden");
  });

  personaSelect.addEventListener("change", async () => {
    const personaId = personaSelect.value;
    if (!personaId) return;
    showStatus("Switching active CV persona...");
    try {
      await directApiFetch(`/api/cv/personas/${personaId}/activate`, { method: "POST" });
      await loadProfile();
      showStatus("Switched active CV persona!");
    } catch (e) {
      showStatus(e.message || "Could not switch persona", true);
    }
  });

  autofillNowBtn.addEventListener("click", async () => {
    autofillNowBtn.disabled = true;
    autofillNowBtn.textContent = "⏳ Autofilling Tab...";
    showStatus("Scanning page & generating tailored answers...");

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) {
      autofillNowBtn.disabled = false;
      autofillNowBtn.textContent = "⚡ Autofill This Page Now";
      showStatus("No active tab found.", true);
      return;
    }

    chrome.tabs.sendMessage(
      tab.id,
      { type: "TRIGGER_PAGE_AUTOFILL", tailorCv: tailorCheck.checked },
      (resp) => {
        autofillNowBtn.disabled = false;
        autofillNowBtn.textContent = "⚡ Autofill This Page Now";
        if (chrome.runtime.lastError || !resp || !resp.ok) {
          showStatus("Refresh the job page once and click Autofill again.", true);
          return;
        }
        const r = resp.result;
        showStatus(
          `✓ Filled ${r.filledCount} fields${r.attachedResume ? ` + attached ${r.resumeFilename}` : ""}!`
        );
      }
    );
  });

  saveTrackerBtn.addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) return;

    chrome.tabs.sendMessage(tab.id, { type: "GET_PAGE_JOB_CONTEXT" }, async (ctxResp) => {
      const jobCtx = (ctxResp && ctxResp.jobCtx) || {
        job_title: tab.title || "Job Application",
        company: new URL(tab.url || "https://company.com").hostname.replace(/^www\./, ""),
        job_url: tab.url || ""
      };
      try {
        try {
          await directApiFetch("/api/extension/track", {
            method: "POST",
            body: {
              title: jobCtx.job_title,
              company: jobCtx.company,
              location: "Remote",
              url: jobCtx.job_url
            }
          });
        } catch (err) {
          if (err.message === "HTTP_404") {
            await directApiFetch("/api/tracker", {
              method: "POST",
              body: {
                title: jobCtx.job_title,
                company: jobCtx.company,
                location: "Remote",
                url: jobCtx.job_url,
                status: "applied",
                notes: "Applied via CVtoMatch Chrome Extension Autofill"
              }
            });
          } else {
            throw err;
          }
        }
        showStatus("✓ Saved to your CVtoMatch Application Tracker!");
      } catch (e) {
        showStatus(e.message || "Could not save to Tracker", true);
      }
    });
  });
});
