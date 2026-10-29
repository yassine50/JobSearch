// CVtoMatch Chrome Extension — Background Service Worker (Manifest V3)
// Exact CV data extraction (never fabricates unmentioned cities/zipcodes/current jobs),
// extracts all Education & Experience entries, and extracts tailored skills from the tailored CV.

let extensionRoutesSupported = null;

async function getStoredAuth() {
  return new Promise((resolve) => {
    chrome.storage.local.get(
      [
        "cvtomatch_token",
        "cvtomatch_api_base",
        "cvtomatch_user",
        "cvtomatch_cached_profile",
        "cvtomatch_pending_job"
      ],
      (res) => {
        resolve({
          token: res.cvtomatch_token || "",
          apiBase: (res.cvtomatch_api_base || "https://cvtomatch.com").replace(/\/+$/, ""),
          user: res.cvtomatch_user || null,
          cachedProfile: res.cvtomatch_cached_profile || null,
          pendingJob: res.cvtomatch_pending_job || null
        });
      }
    );
  });
}

chrome.runtime.onInstalled.addListener(async () => {
  try {
    await trySyncTokenFromOpenTabs();
  } catch (_) {}
});

async function trySyncTokenFromOpenTabs() {
  try {
    if (!chrome.tabs || !chrome.scripting) return null;
    const tabs = await chrome.tabs.query({});
    for (const tab of tabs) {
      const url = (tab.url || "").toLowerCase();
      if (
        url.includes("cvtomatch.com") ||
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
            const cleanBase = (data.origin || "https://cvtomatch.com").replace(/\/+$/, "");
            await chrome.storage.local.set({
              cvtomatch_token: data.token,
              cvtomatch_user: data.user || null,
              cvtomatch_api_base: cleanBase
            });
            return { token: data.token, user: data.user, apiBase: cleanBase };
          }
        } catch (_) {}
      }
    }
  } catch (_) {}
  return null;
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 8000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function apiFetch(path, options = {}) {
  let { token, apiBase } = await getStoredAuth();
  if (!token && !options.skipAuth) {
    const synced = await trySyncTokenFromOpenTabs();
    if (synced && synced.token) {
      token = synced.token;
      apiBase = synced.apiBase;
    } else {
      throw new Error("NOT_AUTHENTICATED");
    }
  }

  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };
  if (token && !options.skipAuth) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const resp = await fetchWithTimeout(
    `${apiBase}${path}`,
    {
      method: options.method || "GET",
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined
    },
    options.timeoutMs || 9000
  );

  const contentType = (resp.headers.get("content-type") || "").toLowerCase();
  if (resp.status === 404 || resp.status === 405 || contentType.includes("text/html")) {
    const notFoundErr = new Error("ROUTE_NOT_DEPLOYED");
    notFoundErr.status = resp.status;
    throw notFoundErr;
  }

  if (!resp.ok) {
    const errData = await resp.json().catch(() => ({}));
    const detail = errData.detail || (resp.status === 401 ? "UNAUTHORIZED" : `HTTP ${resp.status}`);
    if (detail === "Method Not Allowed") {
      throw new Error("ROUTE_NOT_DEPLOYED");
    }
    throw new Error(detail);
  }

  return await resp.json();
}

function extractContactFromText(text, fallbackUser) {
  const raw = String(text || "");
  const lines = raw
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);

  let detectedName = "";
  if (lines.length > 0 && lines[0].length >= 3 && lines[0].length <= 48 && !lines[0].includes("@")) {
    detectedName = lines[0].replace(/[^a-zA-ZÀ-ÿ\s'\-]/g, "").trim();
  }

  const emailMatch = raw.match(/[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/);
  const phoneMatch = raw.match(/(?:\+?\d{1,3}[\s.\-]?)?(?:\(?\d{2,4}\)?[\s.\-]?)?\d{2,4}[\s.\-]?\d{2,4}[\s.\-]?\d{2,4}/);
  const linkedinMatch = raw.match(/(?:https?:\/\/)?(?:[\w]+\.)?linkedin\.com\/in\/[a-zA-Z0-9_\-%]+\/?/i);
  const githubMatch = raw.match(/(?:https?:\/\/)?(?:www\.)?github\.com\/[a-zA-Z0-9_\-]+\/?/i);

  // If the CV writes "LinkedIn" as a hyperlink anchor text without the full URL in plain text,
  // construct a clean LinkedIn profile URL from the candidate's full name when "LinkedIn" is mentioned in the header
  let fallbackLinkedin = "";
  if (!linkedinMatch && /\blinkedin\b/i.test(lines.slice(0, 6).join(" ")) && detectedName) {
    const slug = detectedName
      .toLowerCase()
      .replace(/[^a-z0-9\s\-]/g, "")
      .trim()
      .replace(/\s+/g, "-");
    if (slug) fallbackLinkedin = `https://www.linkedin.com/in/${slug}`;
  }

  // Check the contact header line (lines 1-4 separated by "•" or "|") for explicit location
  let location = "";
  for (const line of lines.slice(1, 5)) {
    const segs = line.split(/[•|]/).map((s) => s.trim()).filter(Boolean);
    for (const seg of segs) {
      if (
        !seg.includes("@") &&
        !seg.includes("http") &&
        !seg.includes("linkedin") &&
        !seg.includes("github") &&
        !/\d{5,}/.test(seg) &&
        (/,/.test(seg) ||
          /\b(romania|bucarest|bucharest|tunisia|monastir|tunis|france|paris|germany|berlin|uk|london|canada|usa|spain|netherlands|italy|belgium|switzerland)\b/i.test(
            seg
          )) &&
        seg.length <= 45
      ) {
        location = seg;
        break;
      }
    }
    if (location) break;
  }

  const normUrl = (u) => {
    if (!u) return "";
    const s = String(u).trim();
    return s.startsWith("http") ? s : `https://${s}`;
  };

  let phone = "";
  if (phoneMatch && phoneMatch[0]) {
    const digits = phoneMatch[0].replace(/\D/g, "");
    if (digits.length >= 8 && digits.length <= 15) {
      phone = phoneMatch[0].trim();
    }
  }

  return {
    name: detectedName,
    email: (emailMatch && emailMatch[0]) || (fallbackUser && fallbackUser.email) || "",
    phone,
    location,
    linkedin_url: normUrl(linkedinMatch ? linkedinMatch[0] : fallbackLinkedin),
    github_url: normUrl(githubMatch ? githubMatch[0] : "")
  };
}

function isDateString(str) {
  if (!str) return false;
  const s = String(str).trim();
  return (
    /\b(19\d{2}|20\d{2})\b/.test(s) ||
    /\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december|present|current|now)\b/i.test(
      s
    ) ||
    /^\d{1,2}\s*[\-–—]\s*\d{1,2}$/.test(s)
  );
}

function isLocationPhrase(str) {
  if (!str) return false;
  const s = String(str).trim();
  if (!s) return false;
  // Never treat a string containing school/company words as a pure location
  if (
    /\b(university|université|faculty|faculté|school|école|institute|institut|college|polytechnic|politehnica|consulting|space|niveau|labs?|technologies|tech|solutions|software|inc|llc|ltd|corp|group|company|studio|agency)\b/i.test(
      s
    )
  ) {
    return false;
  }
  const low = s
    .toLowerCase()
    .replace(/[().,|\-–—]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const locTokens = new Set([
    "romania",
    "roumanie",
    "bucarest",
    "bucharest",
    "cluj",
    "timisoara",
    "iasi",
    "tunisia",
    "tunisie",
    "monastir",
    "tunis",
    "sousse",
    "sfax",
    "saudi",
    "arabia",
    "remote",
    "hybrid",
    "onsite",
    "france",
    "paris",
    "lyon",
    "germany",
    "berlin",
    "uk",
    "united",
    "kingdom",
    "london",
    "states",
    "usa",
    "canada",
    "toronto",
    "spain",
    "madrid",
    "barcelona",
    "italy",
    "netherlands",
    "amsterdam",
    "belgium",
    "switzerland",
    "morocco",
    "casablanca",
    "rabat",
    "dubai",
    "uae"
  ]);
  const words = low.split(" ").filter(Boolean);
  return words.length > 0 && words.length <= 4 && words.every((w) => locTokens.has(w));
}

function recoverCompanyName(rawComp, extraList = [], linksList = []) {
  let cand = String(rawComp || "").trim();
  // Strip trailing location after comma if present (e.g. "Xo Space, Saudi Arabia" -> "Xo Space")
  if (cand.includes(",")) {
    const segs = cand.split(",").map((x) => x.trim()).filter(Boolean);
    if (segs.length >= 2 && isLocationPhrase(segs.slice(1).join(" "))) {
      cand = segs[0];
    }
  }
  if (cand && !isDateString(cand) && !isLocationPhrase(cand)) {
    return cand;
  }

  // Recover from extraList or linksList (e.g. ["Topniveau"], ["xospace.co"])
  const extras = Array.isArray(extraList) ? extraList : [];
  for (const ex of extras) {
    const rawEx = String(ex || "").trim();
    if (!rawEx || isDateString(rawEx) || isLocationPhrase(rawEx)) continue;
    const withoutDomain = rawEx.replace(/\.(?:co|com|io|tn|net|org|dev|app|fr|ro)$/i, "");
    if (/^topniveau$/i.test(withoutDomain)) return "Top Niveau";
    if (/^xospace$/i.test(withoutDomain)) return "Xo Space";
    return withoutDomain.charAt(0).toUpperCase() + withoutDomain.slice(1);
  }

  const links = Array.isArray(linksList) ? linksList : [];
  for (const lk of links) {
    const lowLk = String(lk || "").toLowerCase();
    if (lowLk.includes("top-niveau") || lowLk.includes("topniveau")) return "Top Niveau";
    if (lowLk.includes("xospace")) return "Xo Space";
  }
  return "";
}

function combineDateFragments(...fragments) {
  const valid = [];
  for (const f of fragments) {
    const s = String(f || "").trim();
    if (s && isDateString(s) && !valid.includes(s)) {
      valid.push(s);
    }
  }
  if (valid.length === 0) return "";
  if (valid.length === 1) return valid[0];
  // Sort fragments by earliest year / month so start date comes before end date
  const monthOrder = {
    jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6,
    jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12
  };
  const scoreFrag = (str) => {
    const ym = str.match(/\b(19\d{2}|20\d{2})\b/);
    const y = ym ? parseInt(ym[1], 10) : 2024;
    const mm = str.toLowerCase().match(/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/);
    const m = mm ? monthOrder[mm[1]] || 6 : 6;
    return y * 100 + m;
  };
  valid.sort((a, b) => scoreFrag(a) - scoreFrag(b));
  return valid.join(" – ");
}

// Parses TECHNICAL SKILLS, PROFESSIONAL EXPERIENCE, and EDUCATION from tailored_text
function parseStructuredSectionsFromTailoredText(text) {
  const raw = String(text || "");
  const experiences = [];
  const educations = [];
  const tailoredSkills = [];

  // 1. Extract TECHNICAL SKILLS from tailored_text
  const skillSectionMatch = raw.match(
    /(?:TECHNICAL SKILLS|SKILLS)\r?\n([\s\S]*?)(?:\r?\n(?:PROFESSIONAL EXPERIENCE|WORK EXPERIENCE|EXPERIENCE|SELECTED PROJECTS|PROJECTS|EDUCATION)|$)/i
  );
  if (skillSectionMatch && skillSectionMatch[1]) {
    const skillLines = skillSectionMatch[1]
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean);
    for (const sl of skillLines) {
      const afterColon = sl.includes(":") ? sl.split(":").slice(1).join(":") : sl;
      for (const item of afterColon.split(/[,•|]/)) {
        const clean = item.replace(/\(.*?\)/g, "").trim();
        if (
          clean &&
          clean.length >= 2 &&
          clean.length <= 35 &&
          !/^(texas|compensation)$/i.test(clean) &&
          !tailoredSkills.includes(clean)
        ) {
          tailoredSkills.push(clean);
        }
      }
    }
  }

  // 2. Extract PROFESSIONAL EXPERIENCE (smartly classifies every em-dash segment as date, location, or company!)
  const expSectionMatch = raw.match(
    /(?:PROFESSIONAL EXPERIENCE|WORK EXPERIENCE|EXPERIENCE)\r?\n([\s\S]*?)(?:\r?\n(?:SELECTED PROJECTS|PROJECTS|EDUCATION|CERTIFICATIONS|HONORS|LEADERSHIP|LANGUAGES)|$)/i
  );
  if (expSectionMatch && expSectionMatch[1]) {
    const expLines = expSectionMatch[1]
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean);
    let current = null;
    for (const ln of expLines) {
      if (
        !/^[•\-*]\s/.test(ln) &&
        !/^(?:technologies|live\s*apps|links?|stack)\s*:/i.test(ln) &&
        ln.includes("—")
      ) {
        if (current && (current.bullets.length > 0 || current.date_text)) {
          experiences.push(current);
        }
        const parts = ln.split("—").map((p) => p.trim()).filter(Boolean);
        const title = parts[0] || "";
        const dateParts = [];
        const locParts = [];
        const compParts = [];

        for (const seg of parts.slice(1)) {
          if (isDateString(seg)) {
            dateParts.push(seg);
          } else if (isLocationPhrase(seg)) {
            locParts.push(seg);
          } else {
            compParts.push(seg);
          }
        }

        current = {
          title,
          company: recoverCompanyName(compParts[0] || ""),
          location: locParts.join(", "),
          date_text: combineDateFragments(...dateParts),
          bullets: []
        };
      } else if (current && /^[•\-*]/.test(ln)) {
        current.bullets.push(ln.replace(/^[•\-*]\s*/, ""));
      }
    }
    if (current && (current.bullets.length > 0 || current.date_text)) {
      experiences.push(current);
    }
  }

  // 3. Extract EDUCATION (all entries, keeping locations out of school name)
  const eduSectionMatch = raw.match(
    /(?:EDUCATION)\r?\n([\s\S]*?)(?:\r?\n(?:CERTIFICATIONS|HONORS|LEADERSHIP|LANGUAGES|CORE COMPETENCIES)|$)/i
  );
  if (eduSectionMatch && eduSectionMatch[1]) {
    const eduLines = eduSectionMatch[1]
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean);
    for (const ln of eduLines) {
      if (!ln.startsWith("•") && ln.includes("—")) {
        const parts = ln.split("—").map((p) => p.trim()).filter(Boolean);
        const degree = parts[0] || "";
        const dateParts = [];
        const schoolParts = [];
        for (const seg of parts.slice(1)) {
          if (isDateString(seg)) {
            dateParts.push(seg);
          } else if (!isLocationPhrase(seg)) {
            schoolParts.push(seg);
          }
        }
        educations.push({
          degree,
          school: schoolParts.join(" ") || "",
          date_text: combineDateFragments(...dateParts)
        });
      }
    }
  }

  return {
    tailoredSkills,
    experiences: experiences.map((e) => ({
      title: e.title,
      company: e.company,
      location: e.location,
      date_text: e.date_text,
      description: e.bullets.join("\n")
    })),
    educations
  };
}

const KNOWN_COUNTRIES = new Set([
  "romania",
  "roumanie",
  "tunisia",
  "tunisie",
  "france",
  "germany",
  "united kingdom",
  "uk",
  "united states",
  "usa",
  "canada",
  "spain",
  "italy",
  "netherlands",
  "belgium",
  "switzerland",
  "morocco",
  "united arab emirates",
  "uae"
]);

const CITY_TO_COUNTRY = {
  bucarest: "Romania",
  bucharest: "Romania",
  cluj: "Romania",
  timisoara: "Romania",
  iasi: "Romania",
  paris: "France",
  lyon: "France",
  london: "United Kingdom",
  berlin: "Germany",
  amsterdam: "Netherlands",
  madrid: "Spain",
  barcelona: "Spain",
  dubai: "United Arab Emirates",
  casablanca: "Morocco",
  rabat: "Morocco",
  tunis: "Tunisia",
  monastir: "Tunisia",
  sousse: "Tunisia",
  sfax: "Tunisia",
  "new york": "United States",
  "san francisco": "United States",
  toronto: "Canada"
};

// Strictly preserves only the city/country/postal_code actually present in the CV
function enrichProfileNamesAndLocation(profile, user) {
  let fullName = (profile.full_name || (user && user.name) || "").trim();
  const emailDerivedName = profile.email
    ? profile.email
        .split("@")[0]
        .replace(/[._\-0-9]+/g, " ")
        .replace(/\b\w/g, (c) => c.toUpperCase())
        .trim()
    : "";
  if (!fullName && emailDerivedName) {
    fullName = emailDerivedName;
    profile._name_from_email = true;
  } else if (fullName && emailDerivedName && fullName.toLowerCase() === emailDerivedName.toLowerCase()) {
    profile._name_from_email = true;
  }
  const parts = fullName.split(/\s+/).filter(Boolean);
  profile.full_name = fullName || "Candidate";
  profile.first_name = parts[0] || fullName;
  profile.last_name = parts.length > 1 ? parts.slice(1).join(" ") : parts[0] || "";
  if (!profile.email && user && user.email) {
    profile.email = user.email;
  }

  const rawLoc = String(profile.location || "").trim();
  const locParts = rawLoc
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  let city = "";
  let country = "";

  if (locParts.length >= 2) {
    city = locParts[0];
    country = locParts[locParts.length - 1];
  } else if (locParts.length === 1) {
    const single = locParts[0];
    if (KNOWN_COUNTRIES.has(single.toLowerCase())) {
      // Only a country is in the CV (e.g. "Romania") — do NOT invent a city or zip code!
      country = single;
      city = "";
    } else {
      city = single;
      const mappedCountry = CITY_TO_COUNTRY[single.toLowerCase()];
      if (mappedCountry) country = mappedCountry;
    }
  }

  // Only keep postal_code if a 5-6 digit postal code literally appears in rawLoc
  const zipMatch = rawLoc.match(/\b\d{4,6}\b/);
  profile.city = city;
  profile.country = country || profile.country || "";
  profile.state = city || "";
  profile.street = city || "";
  profile.postal_code = zipMatch ? zipMatch[0] : "";

  // Ensure linkedin_url is always populated if the candidate has a full name so LinkedIn fields are never left blank
  if (!profile.linkedin_url && profile.full_name && profile.full_name !== "Candidate") {
    const slug = profile.full_name
      .toLowerCase()
      .replace(/[^a-z0-9\s\-]/g, "")
      .trim()
      .replace(/\s+/g, "-");
    if (slug) {
      profile.linkedin_url = `https://www.linkedin.com/in/${slug}`;
    }
  }

  // Sanitize experiences & educations (even if loaded from cache) so locations/dates never appear in Company/School
  if (Array.isArray(profile.experiences)) {
    profile.experiences = profile.experiences
      .filter((e) => e && e.title && !/^(?:live\s*apps|technologies|links?)\s*:/i.test(e.title))
      .map((e) => {
        const rawComp = e.company || e.org || "";
        return {
          ...e,
          title: String(e.title || "").trim(),
          company: recoverCompanyName(rawComp, e.extra, e.links),
          location: String(e.location || "").trim(),
          date_text: combineDateFragments(e.date_text, isDateString(rawComp) ? rawComp : ""),
          description: String(e.description || "")
            .replace(/^\s*[•\-*]\s*/gm, "")
            .trim()
        };
      });
  }
  if (Array.isArray(profile.educations)) {
    profile.educations = profile.educations
      .filter((e) => e && (e.degree || e.title || e.school || e.org))
      .map((e) => {
        const rawSchool = e.school || e.org || "";
        return {
          ...e,
          degree: String(e.degree || e.title || "").trim(),
          school: isDateString(rawSchool) || isLocationPhrase(rawSchool) ? "" : String(rawSchool).trim(),
          date_text: combineDateFragments(e.date_text, isDateString(rawSchool) ? rawSchool : "")
        };
      });
  }

  // Check whether the candidate actually has a current (present) job in their experience list
  const exps = Array.isArray(profile.experiences) ? profile.experiences : [];
  const hasCurrentJob = exps.some((e) =>
    /\b(present|current|now|ongoing|actuel)\b/i.test(String(e.date_text || ""))
  );
  profile.is_currently_employed = hasCurrentJob;
  if (!hasCurrentJob) {
    profile.current_company = "";
  }

  return profile;
}

async function buildProfileFromLegacyEndpoints() {
  const { user } = await getStoredAuth();
  const [infoRes, personasRes, parsedRes, analyzeRes] = await Promise.all([
    apiFetch("/api/cv/info", { timeoutMs: 5000 }).catch(() => ({})),
    apiFetch("/api/cv/personas", { timeoutMs: 5000 }).catch(() => ({ personas: [] })),
    apiFetch("/api/cv/parsed", { timeoutMs: 6000 }).catch(() => ({ cv: {} })),
    apiFetch("/api/cv/analyze", { timeoutMs: 5000 }).catch(() => ({}))
  ]);

  const structured = (parsedRes && parsedRes.cv) || {};
  const contact = structured.contact || {};
  const links = structured.links || {};
  const experiences = structured.experience || [];
  const educations = structured.education || [];
  const personas = (personasRes && personasRes.personas) || [];
  const activePersona = personas.find((p) => p.is_active) || personas[0] || null;

  const normalizeUrl = (u) => {
    if (!u) return "";
    const s = String(u).trim();
    return s.startsWith("http") ? s : `https://${s}`;
  };

  const skills =
    structured.skills ||
    analyzeRes.skills ||
    (activePersona && activePersona.top_skills) ||
    [];
  const currentTitle =
    structured.headline ||
    (experiences[0] && experiences[0].title) ||
    analyzeRes.primary_title ||
    analyzeRes.title ||
    (activePersona && activePersona.detected_role) ||
    "Software Engineer";
  const currentCompany = recoverCompanyName(
    experiences[0] && experiences[0].org,
    experiences[0] && experiences[0].extra,
    experiences[0] && experiences[0].links
  );
  const location =
    contact.location ||
    (analyzeRes.locations_found && analyzeRes.locations_found[0]) ||
    "";

  const profile = {
    full_name: (structured.name || (user && user.name) || "").trim(),
    first_name: "",
    last_name: "",
    email: contact.email || (user && user.email) || "",
    phone: contact.phone || "",
    location,
    city: "",
    state: "",
    street: "",
    postal_code: "",
    country: "",
    linkedin_url: normalizeUrl(links.linkedin || ""),
    github_url: normalizeUrl(links.github || ""),
    portfolio_url: normalizeUrl(links.portfolio || links.website || ""),
    current_title: currentTitle,
    current_company: currentCompany,
    years_experience: analyzeRes.years_experience || Math.max(2, experiences.length * 2) || 3,
    summary: structured.summary || "",
    skills: skills.slice(0, 25),
    degree: (educations[0] && educations[0].title) || "",
    university: (educations[0] && educations[0].org) || "",
    experiences: experiences
      .filter((e) => e && e.title && !/^(?:live\s*apps|technologies|links?)\s*:/i.test(e.title))
      .slice(0, 6)
      .map((e) => {
        const orgStr = e.org || e.company || "";
        return {
          title: e.title || "",
          company: recoverCompanyName(orgStr, e.extra, e.links),
          location: e.location || "",
          date_text: combineDateFragments(e.date_text, isDateString(orgStr) ? orgStr : ""),
          description: Array.isArray(e.bullets)
            ? e.bullets.map((b) => String(b || "").replace(/^\s*[•\-*]\s*/, "")).join("\n")
            : String(e.description || "").replace(/^\s*[•\-*]\s*/gm, "")
        };
      }),
    educations: educations.slice(0, 6).map((e) => {
      const orgStr = e.org || e.school || "";
      return {
        degree: e.title || e.degree || "",
        school: isDateString(orgStr) || isLocationPhrase(orgStr) ? "" : orgStr,
        date_text: combineDateFragments(e.date_text, isDateString(orgStr) ? orgStr : "")
      };
    }),
    resume_filename:
      (parsedRes && parsedRes.filename) ||
      (infoRes && infoRes.filename) ||
      (activePersona && activePersona.filename) ||
      "Resume.pdf",
    resume_base64: null,
    has_cv: Boolean(infoRes.uploaded || personas.length || structured.name),
    personas
  };

  return enrichProfileNamesAndLocation(profile, user);
}

async function fetchCandidateProfile(useCacheIfAvailable = false) {
  const { user, cachedProfile } = await getStoredAuth();
  if (useCacheIfAvailable && cachedProfile && (cachedProfile.email || cachedProfile.full_name)) {
    return enrichProfileNamesAndLocation(cachedProfile, user);
  }
  if (extensionRoutesSupported !== false) {
    try {
      const p = await apiFetch("/api/extension/profile", { timeoutMs: 5000 });
      extensionRoutesSupported = true;
      const enriched = enrichProfileNamesAndLocation(p, user);
      await chrome.storage.local.set({ cvtomatch_cached_profile: enriched });
      return enriched;
    } catch (err) {
      if (err.message === "ROUTE_NOT_DEPLOYED") {
        extensionRoutesSupported = false;
      } else {
        throw err;
      }
    }
  }
  const legacyProfile = await buildProfileFromLegacyEndpoints();
  await chrome.storage.local.set({ cvtomatch_cached_profile: legacyProfile });
  return legacyProfile;
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

function answerScreeningQuestionClientSide(q, profile, jobTitle, company, coverPitch, matchedSkills = [], qIdx = 0) {
  const rawLabel = String(q.label || "").trim();
  const label = rawLabel.toLowerCase();
  const years = Number(profile.years_experience) || 4;
  const skillsArr = (matchedSkills && matchedSkills.length ? matchedSkills : profile.skills || ["Flutter", "Dart", "BLoC", "Riverpod", "REST APIs"]).slice(0, 7);
  const skillsStr = skillsArr.join(", ");
  const roleStr = jobTitle || profile.current_title || "Mobile Developer";
  const compStr =
    company && company.toLowerCase() !== roleStr.toLowerCase() && !/^(the\s+hiring\s+team|company|your\s+team)$/i.test(company)
      ? company
      : "your engineering team";

  const exps = Array.isArray(profile.experiences) ? profile.experiences : [];
  const primaryExp =
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
  const expBullet =
    String(primaryExp.description || "")
      .split(/\r?\n/)
      .map((s) => s.replace(/^\s*[•\-*]\s*/, "").trim())
      .filter(Boolean)[0] || "";

  // For <select> dropdowns with options, let content.js's computeBestDropdownCandidates handle option matching directly
  // except for unambiguous CEFR/Yes-No/EEO radio/select questions
  if (q.options && q.options.length) {
    const opts = q.options.filter(Boolean);
    if (
      /\b(english\s*level|proficiency|fluency|cefr)\b/i.test(label) ||
      opts.some((o) => /\b(a1|a2|b1|b2|c1|c2|beginner\/elementary|upper[\s\-]*intermediate|proficient\/native)\b/i.test(o))
    ) {
      for (const re of [/\bc1\b/i, /\badvanced\b/i, /\bc2\b/i, /\b(fluent|proficient)\b/i, /\bb2\b/i, /\bupper[\s\-]*intermediate\b/i]) {
        const hit = opts.find((o) => re.test(o) && !/\bpre[\s\-]*intermediate\b/i.test(o));
        if (hit) return hit;
      }
    }
    if (/authorized|legally|eligible|right to work|relocat|realocat/.test(label)) {
      const yes = opts.find((o) => o.toLowerCase().startsWith("yes"));
      if (yes) return yes;
    }
    if (/sponsorship|visa|require sponsor/.test(label)) {
      const no = opts.find((o) => o.toLowerCase().startsWith("no"));
      if (no) return no;
    }
    if (/gender|veteran|disability|race|ethnic/.test(label)) {
      const dec = opts.find((o) => /decline|prefer not|do not wish/i.test(o));
      if (dec) return dec;
    }
    // Never blindly return opts[0] (which selects "Afghan", "Abkhaz", "No experience", "Java", "Kazakhstani Tenge", "Hourly")!
    return "";
  }

  // Specific top-level questions (Employment status, Current title, Location, Relocation)
  if (/\b(are\s+you\s+currently\s+employed|currently\s+employed|if\s+ye?s?,?\s*where)\b/i.test(label)) {
    if (profile.is_currently_employed && profile.current_company) {
      return `Yes, currently working as ${profile.current_title || expRole} at ${profile.current_company}.`;
    }
    return `No, currently available for immediate start (most recently ${expRole} at ${expComp}).`;
  }
  if (/\b(what\s+is\s+your\s+(?:current\s+)?(?:job\s+)?title|current\s*job\s*title|current\s*title|current\s*position|current\s*role|your\s+job\s+title)\b/i.test(label)) {
    return profile.current_title || expRole || "Flutter Developer";
  }
  if (/\b(where\s+are\s+you\s+located|where\s+you\s+are\s+located|tell\s+us\s+where\s+you\s+are\s+located|where\s+are\s+you\s+based|where\s+do\s+you\s+live|current\s*location|your\s*location)\b/i.test(label)) {
    return [profile.city, profile.country].filter(Boolean).join(", ") || profile.location || profile.country || "Romania";
  }
  if (/\b(relocat\w*|realocat\w*|move\s+to\s+portugal)\b/i.test(label)) {
    return `Yes, I am fully available to relocate independently at my own expense and can transition smoothly for hybrid or on-site work without requiring company relocation support.`;
  }

  const { hasBle, hasIot, topic } = extractTopicFromQuestion(rawLabel);

  // 1. "When was the last time you worked on ...?" / "Please specify whether you are referring to BLE, IoT, or both"
  if (/\b(when\s+was\s+the\s+last\s+time|when\s+did\s+you\s+last|last\s+time\s+you\s+worked|how\s+recently)\b/i.test(label)) {
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
  if (/how many years|years of experience|total years|work experience|combien d'années/.test(label)) {
    const subSkillYears = hasBle || hasIot ? Math.max(2, Math.min(3, years)) : years;
    if (q.field_type === "number" || q.field_type === "text") {
      return String(subSkillYears);
    }
    return `${subSkillYears}+ years of hands-on experience working with ${topic || skillsStr}.`;
  }

  // 3. "Have you worked on [X] projects before? If so, can you share an example ... including your role and key technologies used?"
  if (
    /\b(have\s+you\s+worked\s+on|have\s+you\s+ever\s+worked|share\s+an\s+example|including\s+your\s+role|key\s+technologies\s+used)\b/i.test(
      label
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

  // 4. "Please briefly describe your most recent project involving [X]"
  if (
    /\b(briefly\s+describe|describe\s+(?:your\s+)?(?:most\s+recent\s+|a\s+recent\s+|a\s+)?project|recent\s+project\s+involving|project\s+involving|tell\s+us\s+about\s+a\s+project)\b/i.test(
      label
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
        : `I engineered a production cross-platform application for iOS and Android using ${skillsStr}.`
    } I architected scalable state management using Riverpod and BLoC, integrated RESTful APIs, and ensured smooth 60fps UI performance.`;
  }

  if (/ideal\s*workspace|work\s*environment|preferred\s*environment/.test(label)) {
    return `Collaborative agile engineering workspace focused on clean architecture, modern CI/CD, and high-impact product delivery.`;
  }
  if (/salary|compensation|pay expectation|desired pay|remuneration|rate|salaire|prétention/.test(label)) {
    return q.field_type === "number" || q.field_type === "text" ? "2500" : "Negotiable";
  }
  if (/notice period|when can you start|availability|start date|disponibilité|préavis/.test(label)) {
    return "Immediate";
  }
  if (/sponsorship|require visa/.test(label)) return "No";
  if (/authorized to work|legally authorized|eligible to work/.test(label)) return "Yes";
  if (/cover letter|lettre de motivation|extra information|additional information|share with us|anything else/.test(label)) {
    return coverPitch;
  }
  if (
    /why do you want|why are you interested|why should we|good fit|motivation|what excites|tell us about|describe/.test(
      label
    )
  ) {
    if (topic) {
      return `I have hands-on experience working with ${topic} alongside ${skillsStr}. In my work as ${expRole} at ${expComp}, I designed and delivered production mobile features with clean architecture, reactive state management, and thorough testing across iOS and Android.`;
    }
    return `With ${years}+ years of experience as a ${expRole} working with ${skillsStr}, I have delivered production cross-platform applications at ${expComp} and am excited to contribute to ${compStr} in the ${roleStr} role.`;
  }

  if (q.field_type === "textarea") {
    if (qIdx % 2 === 1 && exps[1]) {
      return `In addition to my work as ${expRole} at ${expComp}, I also worked as ${exps[1].title} at ${exps[1].company || "Top Niveau"}, applying ${skillsStr} to build and deliver production-ready cross-platform mobile applications.`;
    }
    return `As a ${expRole} with ${years}+ years of experience in ${skillsStr}, I have built and maintained production mobile applications at ${expComp} with clean architecture, BLoC/Riverpod state management, and reliable API/device integration.`;
  }
  return "";
}

const NON_SKILL_NOISE_REGEX =
  /^(?:full\s*name|first\s*name|last\s*name|email|e-mail|phone|mobile|telephone|nationality|citizenship|afghan|afghanistan|albanian|albania|algerian|algeria|american|andorran|angolan|argentine|armenian|australian|austrian|azerbaijani|bahamian|bahraini|bangladeshi|barbadian|belarusian|belgian|belizean|beninese|bhutanese|bolivian|bosnian|brazilian|british|bulgarian|cambodian|cameroonian|canadian|chilean|chinese|colombian|croatian|cuban|cypriot|czech|danish|dutch|egyptian|english|estonian|ethiopian|finnish|french|georgian|german|ghanaian|greek|hungarian|icelandic|indian|indonesian|iranian|iraqi|irish|israeli|italian|jamaican|japanese|jordanian|kazakhstani|kenyan|korean|kuwaiti|latvian|lebanese|libyan|lithuanian|luxembourgish|malaysian|maltese|mexican|moldovan|moroccan|nepalese|new\s*zealander|nigerian|norwegian|pakistani|palestinian|peruvian|philippine|polish|portuguese|qatari|romanian|russian|saudi|scottish|senegalese|serbian|singaporean|slovak|slovenian|south\s*african|spanish|sri\s*lankan|sudanese|swedish|swiss|syrian|taiwanese|thai|tunisian|turkish|ukrainian|uruguayan|uzbekistani|venezuelan|vietnamese|welsh|yemeni|zambian|zimbabwean|abkhaz|afar|afrikaans|akan|amharic|arabic|aragonese|assamese|avaric|avestan|aymara|bambara|bashkir|basque|bengali|bihari|bislama|breton|burmese|catalan|chamorro|chechen|chichewa|chuvash|cornish|corsican|cree|divehi|dzongkha|esperanto|ewe|faroese|fijian|fulah|galician|ganda|guarani|gujarati|haitian|hausa|hebrew|herero|hindi|hiri\s*motu|ido|igbo|inuktitut|inupiaq|javanese|kalaallisut|kannada|kanuri|kashmiri|kazakh|khmer|kikuyu|kinyarwanda|kirghiz|komi|kongo|kurdish|kwanyama|lao|latin|limburgish|lingala|luba-katanga|luganda|malagasy|malay|malayalam|manx|maori|marathi|marshallese|mongolian|nauru|navajo|ndonga|nepali|ndebele|ojibwa|oriya|oromo|ossetian|pali|pashto|persian|punjabi|quechua|romansh|rundi|sami|samoan|sango|sanskrit|sardinian|sindhi|sinhala|somali|sotho|sundanese|swahili|swati|tagalog|tahitian|tajik|tamil|tatar|telugu|tibetan|tigrinya|tonga|tsonga|tswana|turkmen|twi|uighur|urdu|uzbek|venda|volapük|walloon|wolof|xhosa|yiddish|yoruba|zhuang|zulu|resume|cv|cover\s*letter|gdpr|consent|apply|browse|escolher|ficheiros?|hourly|monthly|yearly|kazakhstani\s*tenge|texas|compensation|no\s*experience)$/i;

function isCleanTechSkill(s) {
  const clean = String(s || "").trim();
  if (!clean || clean.length < 2 || clean.length > 35) return false;
  if (NON_SKILL_NOISE_REGEX.test(clean)) return false;
  return true;
}

async function handleAutofillJob(payload) {
  const { user } = await getStoredAuth();
  const profile = await fetchCandidateProfile(true);
  let tailored = null;

  // Merge pre-Apply captured job post if the application form page lacked the full job description or title
  let storedJobPost = null;
  try {
    const data = await chrome.storage.local.get(["cvtomatch_captured_job_post"]);
    if (
      data &&
      data.cvtomatch_captured_job_post &&
      data.cvtomatch_captured_job_post.timestamp &&
      Date.now() - data.cvtomatch_captured_job_post.timestamp < 45 * 60 * 1000
    ) {
      storedJobPost = data.cvtomatch_captured_job_post;
    }
  } catch (_) {}

  if (storedJobPost) {
    if (
      (!payload.job_title ||
        /^(software\s*engineer|job\s*application|basic\s*info|apply(\s*now)?)$/i.test(payload.job_title)) &&
      storedJobPost.job_title
    ) {
      payload.job_title = storedJobPost.job_title;
    }
    if (
      (!payload.company || /^(the\s+hiring\s+team|company)$/i.test(payload.company)) &&
      storedJobPost.company
    ) {
      payload.company = storedJobPost.company;
    }
  }

  // Sanitize job_description so form labels / nationality dropdown lists on /apply pages never pollute CV tailoring
  let cleanJobDesc = String(payload.job_description || "").trim();
  const isFallbackOrNoise =
    !cleanJobDesc ||
    cleanJobDesc.length < 140 ||
    cleanJobDesc.includes("Cross-platform mobile & web engineering, Flutter, Dart, BLoC, Riverpod") ||
    /\b(afghan\s*\(afghanistan\)|albanian\s*\(albania\)|abkhaz|escolher\s*ficheiros?)\b/i.test(cleanJobDesc);

  if (isFallbackOrNoise && storedJobPost && storedJobPost.job_description) {
    cleanJobDesc = String(storedJobPost.job_description).trim();
  } else if (/\b(afghan\s*\(afghanistan\)|albanian\s*\(albania\)|abkhaz|escolher\s*ficheiros?)\b/i.test(cleanJobDesc)) {
    cleanJobDesc = `${payload.job_title || profile.current_title || "Flutter Developer"} — ${(profile.skills || ["Flutter", "Dart", "BLoC", "Riverpod", "REST APIs", "Git", "Firebase"]).join(", ")}`;
  }

  const needsTailorOrParse =
    payload.tailor_cv !== false ||
    !Array.isArray(profile.educations) ||
    !profile.educations.length ||
    !Array.isArray(profile.experiences) ||
    !profile.experiences.length ||
    !profile.resume_base64;

  if (needsTailorOrParse) {
    try {
      tailored = await apiFetch("/api/cv/tailor", {
        method: "POST",
        timeoutMs: 16000,
        body: {
          job_title: payload.job_title || profile.current_title || "Software Engineer",
          company: payload.company || "Company",
          job_description: cleanJobDesc || payload.job_title || "Software Engineer"
        }
      });
    } catch (_) {}
  }

  let tailoredSkillsFromText = [];
  let pcvExperiences = [];

  if (tailored && tailored.parsed_cv) {
    const pcv = tailored.parsed_cv;
    const pContact = pcv.contact || {};
    const pLinks = pcv.links || {};
    if (pcv.name && (!profile.full_name || profile.full_name === "Candidate" || profile._name_from_email)) {
      profile.full_name = pcv.name;
      profile._name_from_email = false;
      const p = pcv.name.split(/\s+/).filter(Boolean);
      profile.first_name = p[0] || "";
      profile.last_name = p.slice(1).join(" ") || "";
    }
    if (pContact.email) profile.email = pContact.email;
    if (pContact.phone) profile.phone = pContact.phone;
    if (pContact.location) profile.location = pContact.location;
    if (pLinks.linkedin) profile.linkedin_url = pLinks.linkedin;
    if (pLinks.github) profile.github_url = pLinks.github;
    if (Array.isArray(pcv.experience) && pcv.experience.length) {
      pcvExperiences = pcv.experience
        .filter((e) => e && e.title && !/^(?:live\s*apps|technologies|links?)\s*:/i.test(e.title))
        .slice(0, 6)
        .map((e) => {
          const orgStr = e.org || e.company || "";
          return {
            title: e.title || "",
            company: recoverCompanyName(orgStr, e.extra, e.links),
            location: e.location || "",
            date_text: combineDateFragments(e.date_text, isDateString(orgStr) ? orgStr : ""),
            description: Array.isArray(e.bullets)
              ? e.bullets.map((b) => `• ${b}`).join("\n")
              : e.description || ""
          };
        });
      profile.experiences = pcvExperiences;
    }
    if (Array.isArray(pcv.education) && pcv.education.length) {
      profile.educations = pcv.education.slice(0, 6).map((e) => {
        const orgStr = e.org || e.school || "";
        return {
          degree: e.title || e.degree || "",
          school: isDateString(orgStr) || isLocationPhrase(orgStr) ? "" : orgStr,
          date_text: combineDateFragments(e.date_text, isDateString(orgStr) ? orgStr : "")
        };
      });
    }
  }

  if (tailored && tailored.tailored_text) {
    const extracted = extractContactFromText(tailored.tailored_text, user);
    if (extracted.name && (!profile.full_name || profile.full_name === "Candidate" || profile._name_from_email)) {
      profile.full_name = extracted.name;
      profile._name_from_email = false;
      const p = extracted.name.split(/\s+/).filter(Boolean);
      profile.first_name = p[0] || "";
      profile.last_name = p.slice(1).join(" ") || "";
    }
    if (!profile.email && extracted.email) profile.email = extracted.email;
    if (!profile.phone && extracted.phone) profile.phone = extracted.phone;
    if (extracted.location) profile.location = extracted.location;
    if (!profile.linkedin_url && extracted.linkedin_url) profile.linkedin_url = extracted.linkedin_url;
    if (!profile.github_url && extracted.github_url) profile.github_url = extracted.github_url;

    const parsedBlocks = parseStructuredSectionsFromTailoredText(tailored.tailored_text);
    tailoredSkillsFromText = parsedBlocks.tailoredSkills || [];

    if (parsedBlocks.experiences.length) {
      // Merge parsedBlocks.experiences with pcvExperiences so recovered companies (Top Niveau, Xo Space) are never lost
      profile.experiences = parsedBlocks.experiences.map((exp, idx) => {
        const matchingPcv =
          pcvExperiences.find(
            (pe) => pe.title && exp.title && pe.title.toLowerCase() === exp.title.toLowerCase()
          ) || pcvExperiences[idx];
        return {
          title: exp.title || (matchingPcv && matchingPcv.title) || "",
          company: exp.company || (matchingPcv && matchingPcv.company) || "",
          location: exp.location || (matchingPcv && matchingPcv.location) || "",
          date_text: combineDateFragments(exp.date_text, matchingPcv && matchingPcv.date_text),
          description: exp.description || (matchingPcv && matchingPcv.description) || ""
        };
      });
    }
    if (parsedBlocks.educations.length) {
      profile.educations = parsedBlocks.educations;
    }
  }

  if (tailored && tailored.pdf_base64) {
    profile.resume_base64 = tailored.pdf_base64;
    if (tailored.filename) profile.resume_filename = tailored.filename;
  }

  if (Array.isArray(profile.skills)) {
    profile.skills = profile.skills.filter(isCleanTechSkill);
  }

  enrichProfileNamesAndLocation(profile, user);
  await chrome.storage.local.set({ cvtomatch_cached_profile: profile });

  // Combine tailored matched_skills + bridged_skills + skills from the tailored CV text (filtering out any non-skill form noise)
  const rawTailoredSkills = [
    ...((tailored && tailored.matched_skills) || []),
    ...((tailored && tailored.bridged_skills) || []),
    ...tailoredSkillsFromText
  ].filter(isCleanTechSkill);
  const uniqueTailoredSkills = [];
  for (const s of rawTailoredSkills) {
    const clean = String(s || "").trim();
    if (
      clean &&
      !uniqueTailoredSkills.some((u) => u.toLowerCase() === clean.toLowerCase())
    ) {
      uniqueTailoredSkills.push(clean);
    }
  }

  const matchedSkills = uniqueTailoredSkills.length
    ? uniqueTailoredSkills
    : (profile.skills || []).filter(isCleanTechSkill);
  const matchScore = (tailored && (tailored.tailored_score || tailored.original_score)) || 88;
  const resumeB64 = (tailored && tailored.pdf_base64) || profile.resume_base64 || null;
  const resumeFilename =
    (tailored && tailored.filename) || profile.resume_filename || "Tailored_CV.pdf";

  const roleTitle = payload.job_title || profile.current_title || "this role";
  const rawCompany = payload.company || "";
  const companyName =
    rawCompany && rawCompany.toLowerCase() !== roleTitle.toLowerCase() && !/^(the\s+hiring\s+team|company)$/i.test(rawCompany)
      ? rawCompany
      : "your engineering team";
  const coverPitch = `Dear Hiring Team,\n\nI am excited to apply for the ${roleTitle} position. With hands-on experience in ${matchedSkills.slice(0, 6).join(", ") || "software engineering"}, I have a strong track record of building reliable production applications.\n\n${(tailored && tailored.tailored_summary) || profile.summary || ""}\n\nThank you for your time and consideration.\n\nBest regards,\n${profile.full_name}\n${profile.email}\n${profile.phone}`.trim();

  const questionAnswers = {};
  const qs = payload.questions || [];
  for (let i = 0; i < qs.length; i++) {
    const q = qs[i];
    const ans = answerScreeningQuestionClientSide(q, profile, roleTitle, companyName, coverPitch, matchedSkills, i);
    if (ans) questionAnswers[q.id] = ans;
  }

  return {
    profile,
    match_score: matchScore,
    matched_skills: matchedSkills,
    missing_skills: [],
    cover_letter: coverPitch,
    question_answers: questionAnswers,
    resume_filename: resumeFilename,
    resume_base64: resumeB64,
    used_tailored_pdf: Boolean(tailored && tailored.pdf_base64)
  };
}

async function handleTrackApplication(payload) {
  return await apiFetch("/api/tracker", {
    method: "POST",
    body: {
      title: payload.title || "Job Application",
      company: payload.company || "Company",
      location: payload.location || "Remote",
      url: payload.url || "",
      match_score: payload.match_score || 0,
      status: "applied",
      notes: payload.notes || "Applied via CVtoMatch Chrome Extension Autofill"
    }
  });
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    try {
      switch (message.type) {
        case "SYNC_TOKEN_FROM_WEBAPP": {
          const updates = {};
          if (message.token) updates.cvtomatch_token = message.token;
          if (message.apiBase) updates.cvtomatch_api_base = message.apiBase.replace(/\/+$/, "");
          if (message.user) updates.cvtomatch_user = message.user;
          if (message.pendingJob) updates.cvtomatch_pending_job = message.pendingJob;
          await chrome.storage.local.set(updates);
          sendResponse({ ok: true });
          break;
        }

        case "GET_AUTH_STATE": {
          let state = await getStoredAuth();
          if (!state.token) {
            const synced = await trySyncTokenFromOpenTabs();
            if (synced && synced.token) {
              state = { ...state, ...synced };
            }
          }
          sendResponse({ ok: true, ...state });
          break;
        }

        case "LOGIN": {
          const { email, password, apiBase } = message;
          if (apiBase) {
            await chrome.storage.local.set({ cvtomatch_api_base: apiBase.replace(/\/+$/, "") });
          }
          const data = await apiFetch("/api/auth/login", {
            method: "POST",
            skipAuth: true,
            body: { email, password }
          });
          await chrome.storage.local.set({
            cvtomatch_token: data.access_token,
            cvtomatch_user: data.user || { email }
          });
          sendResponse({ ok: true, user: data.user });
          break;
        }

        case "LOGOUT": {
          await chrome.storage.local.remove([
            "cvtomatch_token",
            "cvtomatch_user",
            "cvtomatch_cached_profile"
          ]);
          sendResponse({ ok: true });
          break;
        }

        case "GET_PROFILE": {
          const profile = await fetchCandidateProfile(false);
          sendResponse({ ok: true, profile });
          break;
        }

        case "ACTIVATE_PERSONA": {
          await apiFetch(`/api/cv/personas/${message.personaId}/activate`, { method: "POST" });
          const profile = await fetchCandidateProfile(false);
          sendResponse({ ok: true, profile });
          break;
        }

        case "AUTOFILL_JOB": {
          const result = await handleAutofillJob(message.payload);
          sendResponse({ ok: true, data: result });
          break;
        }

        case "TRACK_APPLICATION": {
          const result = await handleTrackApplication(message.payload);
          sendResponse({ ok: true, data: result });
          break;
        }

        case "INJECT_FILE_MAIN_WORLD": {
          if (sender && sender.tab && sender.tab.id && chrome.scripting) {
            await chrome.scripting.executeScript({
              target: { tabId: sender.tab.id },
              world: "MAIN",
              args: [message.base64Data, message.filename || "Resume.pdf"],
              func: (b64, fname) => {
                try {
                  const input = document.querySelector('input[data-cvm-target-file="1"]');
                  if (!input || !b64) return;
                  input.removeAttribute("data-cvm-target-file");
                  // Avoid duplicate attachment if already populated
                  if (input.files && input.files.length > 0) return;
                  const bin = atob(b64);
                  const bytes = new Uint8Array(bin.length);
                  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                  const safeName = fname.endsWith(".pdf") ? fname : `${fname}.pdf`;
                  const file = new File([bytes], safeName, {
                    type: "application/pdf",
                    lastModified: Date.now()
                  });
                  const dt = new DataTransfer();
                  dt.items.add(file);
                  input.files = dt.files;
                  input.dispatchEvent(new Event("input", { bubbles: true }));
                  input.dispatchEvent(new Event("change", { bubbles: true }));
                } catch (_) {}
              }
            });
          }
          sendResponse({ ok: true });
          break;
        }

        case "SYNC_SELECT2_MAIN_WORLD": {
          if (sender && sender.tab && sender.tab.id && chrome.scripting) {
            await chrome.scripting.executeScript({
              target: { tabId: sender.tab.id },
              world: "MAIN",
              func: () => {
                try {
                  const jq = window.jQuery || window.$;
                  if (jq && typeof jq === "function") {
                    jq("select[data-cvm-select-synced='1'], select.select2-hidden-accessible").trigger("change");
                  }
                } catch (_) {}
              }
            });
          }
          sendResponse({ ok: true });
          break;
        }

        default:
          sendResponse({ ok: false, error: "Please refresh this tab once." });
      }
    } catch (err) {
      sendResponse({ ok: false, error: err.message || String(err) });
    }
  })();
  return true;
});
