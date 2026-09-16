#!/usr/bin/env python3
"""
cv_matcher.py  v3 — Maximum-accuracy CV ↔ Job matching engine.

Scoring model (6 factors):
  ① Tech skills match      40 %  — 400+ skill DB, required×2, freq-weighted, section-boosted
  ② BM25 + TF-IDF ensemble 30 %  — two complementary relevance models averaged
  ③ Role / seniority fit   15 %  — title + level (senior/junior/lead) alignment
  ④ Soft-skills match       8 %  — leadership, communication, etc.
  ⑤ Domain / industry fit   4 %  — fintech, healthtech, ecommerce, etc.
  ⑥ Education match         3 %  — degree level comparison

Bonuses / Penalties:
  • Skills in CV "Skills" section  → ×1.5
  • Required / must-have skills    → ×2.0 weight in JD
  • Skill freq in JD ≥3            → ×1.4 weight
  • Experience gap                 → up to −15 pts
  • Education gap                  → −5 pts
"""
from __future__ import annotations

import math
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════════
#  Knowledge Bases
# ═══════════════════════════════════════════════════════════════════════════════

TECH_SKILLS: set = {
    # Languages
    "python","java","javascript","typescript","c","c++","c#","ruby","go","golang",
    "rust","swift","kotlin","scala","php","r","matlab","perl","bash","shell",
    "powershell","vba","fortran","cobol","assembly","dart","elixir","erlang",
    "haskell","lua","groovy","objective-c","f#","clojure","solidity","prolog",
    "lisp","racket","ocaml","nim","julia","crystal","coffeescript","abap","sas",
    # Front-end
    "html","css","react","angular","vue","nextjs","nuxtjs","svelte","gatsby",
    "tailwind","bootstrap","sass","less","webpack","vite","babel","jquery",
    "redux","mobx","storybook","cypress","jest","playwright","selenium",
    "vitest","zustand","rxjs","emotion","styled-components","shadcn","radix",
    "tanstack","react query","framer motion","three.js","d3",
    # Back-end
    "django","flask","fastapi","aiohttp","tornado","spring","springboot",
    "express","nodejs","nestjs","rails","laravel","symfony","asp.net","dotnet",
    "gin","fiber","echo","actix","rocket","quarkus","micronaut","strapi",
    "hapi","koa","phoenix","ktor",
    # APIs & protocols
    "rest","restful","graphql","grpc","soap","websocket","openapi","swagger",
    "postman","oauth","oauth2","jwt","sso","saml","ldap","api gateway","odata",
    # Data science / ML / AI
    "machine learning","deep learning","nlp","natural language processing",
    "computer vision","reinforcement learning","transfer learning",
    "tensorflow","pytorch","keras","scikit-learn","sklearn","pandas","numpy",
    "scipy","matplotlib","seaborn","plotly","jupyter","opencv","transformers",
    "bert","gpt","llm","langchain","huggingface","xgboost","lightgbm","catboost",
    "feature engineering","model deployment","mlops","a/b testing",
    "statistical analysis","regression","classification","clustering",
    "time series","forecasting","recommendation","neural network",
    "data analysis","data visualization","statistical modeling",
    "hypothesis testing","bayesian","random forest","gradient boosting",
    "pca","automl","prompt engineering","rag","vector search","embeddings",
    "data mining","anomaly detection","survival analysis","causal inference",
    "generative ai","stable diffusion","llama","mistral","gemini","claude",
    # Databases
    "sql","mysql","postgresql","postgres","mongodb","redis","elasticsearch",
    "cassandra","dynamodb","oracle","sqlite","firebase","supabase","neo4j",
    "influxdb","snowflake","bigquery","redshift","hive","hbase","couchdb",
    "mariadb","cockroachdb","pinecone","weaviate","chroma","milvus","qdrant",
    "timescaledb","clickhouse","duckdb","presto","trino","spanner","cosmos db",
    "fauna","planetscale","neon","turso","arangodb","rethinkdb",
    # Big data / pipelines
    "spark","apache spark","hadoop","kafka","airflow","dbt","flink",
    "databricks","data pipeline","etl","elt","data warehouse","data lake",
    "data lakehouse","nifi","beam","pulsar","rabbitmq","activemq",
    "celery","luigi","prefect","dagster","mage","great expectations",
    # Cloud
    "aws","amazon web services","azure","gcp","google cloud",
    "ec2","s3","lambda","rds","eks","ecs","fargate","sagemaker","cloudformation",
    "azure devops","azure functions","gke","cloud run","cloud functions",
    "cloudflare","vercel","netlify","heroku","digitalocean","linode","fly.io",
    "serverless","iaas","paas","terraform cloud","pulumi",
    # DevOps / Infrastructure
    "docker","kubernetes","k8s","terraform","ansible","puppet","chef",
    "jenkins","github actions","gitlab ci","circleci","travis ci","ci/cd",
    "devops","sre","linux","unix","nginx","apache","microservices","helm",
    "istio","service mesh","prometheus","grafana","elk","datadog",
    "new relic","splunk","pagerduty","vault","consul","argocd","flux",
    "kustomize","skaffold","buildkite","tekton","drone ci","argo workflows",
    # Mobile
    "ios","android","react native","flutter","xamarin","ionic","expo",
    "swiftui","jetpack compose","kotlin multiplatform","capacitor",
    # Security
    "cybersecurity","penetration testing","soc","siem","owasp","ssl","tls",
    "encryption","cryptography","vulnerability assessment","devsecops",
    "zero trust","iam","pki","waf","sast","dast","threat modeling",
    "security audit","compliance","gdpr","hipaa","soc2","iso27001",
    # BI & Analytics
    "tableau","powerbi","looker","qlik","excel","google analytics",
    "mixpanel","amplitude","segment","metabase","superset","redash","domo",
    "sisense","mode","hex","apache superset",
    # Tools
    "git","github","gitlab","bitbucket","jira","confluence","figma","sketch",
    "adobe xd","notion","slack","trello","asana","linear","monday",
    "miro","lucidchart","postman","insomnia","charles proxy","fiddler",
    # Architecture / concepts
    "agile","scrum","kanban","waterfall","tdd","bdd","ddd","solid",
    "oop","functional programming","design patterns","data structures",
    "algorithms","system design","distributed systems","high availability",
    "scalability","performance optimization","clean code","refactoring",
    "code review","caching","message queue","event driven","cqrs",
    "event sourcing","saga","api design","twelve factor","hexagonal architecture",
    "clean architecture","domain driven","reactive programming",
    # Testing
    "unit testing","integration testing","e2e testing","load testing",
    "performance testing","regression testing","test automation","qa",
    # Domains
    "fintech","healthtech","edtech","ecommerce","blockchain","web3","defi",
    "iot","embedded systems","robotics","ar","vr","gaming","adtech","martech",
    "legaltech","proptech","insurtech","cleantech","biotech",
}

SOFT_SKILLS: set = {
    "leadership","communication","teamwork","collaboration",
    "problem solving","critical thinking","creativity","adaptability",
    "time management","project management","stakeholder management",
    "analytical","detail oriented","self-motivated","proactive",
    "mentoring","coaching","presentation","negotiation","empathy",
    "conflict resolution","decision making","strategic thinking",
    "cross-functional","multitasking","organizational","planning",
    "research","documentation","technical writing","fast learner",
    "innovative","initiative","accountability","ownership","curiosity",
    "customer focused","data-driven","results oriented","agile mindset",
    "self-directed","autonomous","collaborative","persuasive","articulate",
}

ROLE_KEYWORDS: set = {
    "engineer","developer","programmer","architect","analyst","scientist",
    "designer","manager","director","lead","head","principal","senior","junior",
    "intern","consultant","specialist","administrator","devops","frontend",
    "backend","fullstack","full-stack","mobile","ios","android","data","ml",
    "ai","cloud","security","qa","sre","platform","infrastructure","product",
    "project","program","technical","software","hardware","research","bi",
    "etl","dba","embedded","blockchain","web3","reliability","staff",
}

SENIORITY: dict = {
    "intern": 0, "trainee": 0, "graduate": 1, "junior": 1, "associate": 1,
    "mid": 2, "intermediate": 2, "mid-level": 2,
    "senior": 3, "sr": 3, "experienced": 3,
    "lead": 4, "principal": 4, "staff": 4,
    "head": 5, "director": 5, "vp": 5, "architect": 4, "manager": 3,
}

DOMAIN_KEYWORDS: dict = {
    "fintech":      ["fintech","finance","banking","payments","trading","investment","insurance","lending","wealth","crypto"],
    "healthtech":   ["health","healthcare","medical","clinical","pharma","biotech","patient","hospital","ehr","fhir"],
    "edtech":       ["education","edtech","elearning","learning","school","university","curriculum","student","academic"],
    "ecommerce":    ["ecommerce","retail","marketplace","commerce","shop","product","catalog","checkout","logistics"],
    "adtech":       ["advertising","adtech","marketing","campaign","media","audience","programmatic","dsp","ssp"],
    "gaming":       ["gaming","game","unity","unreal","simulation","vr","ar","esports","metaverse"],
    "iot":          ["iot","embedded","firmware","hardware","sensor","microcontroller","raspberry","arduino","rtos"],
    "cybersecurity":["security","cybersecurity","infosec","soc","siem","compliance","audit","penetration","vulnerability"],
    "blockchain":   ["blockchain","crypto","defi","nft","web3","smart contract","ethereum","solidity","dao"],
    "ai":           ["ai","artificial intelligence","machine learning","deep learning","llm","nlp","computer vision","generative"],
}

EDUCATION_LEVELS: dict = {
    "phd": 4, "doctorate": 4, "doctoral": 4, "d.phil": 4,
    "master": 3, "msc": 3, "mba": 3, "m.s": 3, "m.eng": 3, "meng": 3,
    "bachelor": 2, "bsc": 2, "b.s": 2, "b.eng": 2, "undergraduate": 2, "degree": 2,
    "associate": 1, "diploma": 1, "certificate": 1, "bootcamp": 1, "hnd": 1,
}

ALIASES: dict = {
    "reactjs":"react","react.js":"react","vue.js":"vue","vuejs":"vue",
    "node.js":"nodejs","node js":"nodejs","next.js":"nextjs","next js":"nextjs",
    "nuxt.js":"nuxtjs","nest.js":"nestjs","angular.js":"angular","angularjs":"angular",
    "spring boot":"springboot","scikit learn":"scikit-learn","scikit_learn":"scikit-learn",
    "k8s":"kubernetes","postgres":"postgresql","pg":"postgresql",
    "gcp":"google cloud","amazon aws":"aws","microsoft azure":"azure",
    "power bi":"powerbi","deep neural network":"deep learning","dnn":"deep learning",
    "natural language processing":"nlp",".net":"dotnet","asp.net":"dotnet",
    "golang":"go","c-sharp":"c#","node js":"nodejs","next js":"nextjs",
    "large language model":"llm","large language models":"llm",
    "retrieval augmented generation":"rag","generative ai":"generative ai",
    "convolutional neural network":"neural network","recurrent neural network":"neural network",
    "random forests":"random forest","gradient boosted":"gradient boosting",
    "xgb":"xgboost","lgbm":"lightgbm",
}

_STOPWORDS = frozenset({
    "a","an","the","and","or","but","in","on","at","to","of","for","with",
    "is","are","was","were","be","been","being","have","has","had","do","does",
    "did","will","would","could","should","may","might","shall","that","this",
    "these","those","it","its","they","them","their","we","our","you","your",
    "he","she","his","her","i","my","me","us","not","by","from","up","about",
    "into","through","during","including","until","while","per","between",
    "however","also","both","each","more","than","then","just","because",
    "as","over","such","if","no","so","out","only","same","too","very","what",
    "when","where","who","which","how","all","any","other","some","new","work",
    "working","use","using","used","experience","years","year","strong","good",
    "excellent","ability","skills","skill","knowledge","team","role","position",
    "join","looking","seeking","candidate","opportunity","responsible",
    "responsibilities","requirements","required","preferred","plus","including",
    "etc","eg","ie","well","highly","able","within","must","nice","have",
    "proficiency","proficient","familiar","background","help","build","maintain",
    "develop","support","design","implement","ensure","create","manage",
    "provide","drive","deliver","define","apply","minimum","least",
})

# ═══════════════════════════════════════════════════════════════════════════════
#  Text Utilities
# ═══════════════════════════════════════════════════════════════════════════════

def _clean(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s\+\#\-\./]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def _apply_aliases(text: str) -> str:
    for alias in sorted(ALIASES, key=len, reverse=True):
        text = re.sub(r"\b" + re.escape(alias) + r"\b", ALIASES[alias], text)
    return text

def _normalize(text: str) -> str:
    return _apply_aliases(_clean(text))

def _tokenize(text: str) -> List[str]:
    return [w for w in text.split() if w not in _STOPWORDS and len(w) > 2]

def _extract_skills(text: str, skill_set: set) -> set:
    text_n = _normalize(text)
    return {s for s in skill_set
            if re.search(r"\b" + re.escape(_clean(s)) + r"\b", text_n)}

def _skill_freq_in_text(text: str, skill: str) -> int:
    return len(re.findall(r"\b" + re.escape(_clean(skill)) + r"\b", _normalize(text)))

def _extract_years(text: str) -> int:
    vals = []
    for p in [r"(\d+)\s*\+?\s*years?\s+(?:of\s+)?(?:professional\s+)?experience",
              r"(\d+)\s*\+?\s*years?\s+(?:in|of|with)",
              r"experience\s+of\s+(\d+)\s*\+?\s*years?",
              r"(\d+)\s*\+\s*yrs"]:
        vals += [int(m) for m in re.findall(p, text.lower())]
    return max(vals, default=0)

def _extract_education(text: str) -> int:
    tl = text.lower()
    return max((lvl for kw, lvl in EDUCATION_LEVELS.items()
                if re.search(r"\b" + re.escape(kw) + r"\b", tl)), default=0)

def _detect_seniority(text: str) -> int:
    tl = text.lower()
    found = [lvl for kw, lvl in SENIORITY.items()
             if re.search(r"\b" + re.escape(kw) + r"\b", tl)]
    return max(found, default=-1)

def _detect_domain(text: str) -> Optional[str]:
    text_n = _normalize(text)
    best, best_score = None, 0
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if re.search(r"\b" + re.escape(kw) + r"\b", text_n))
        if score > best_score:
            best, best_score = domain, score
    return best if best_score >= 2 else None

# ─── CV Section Parser ─────────────────────────────────────────────────────────

_SECTION_HEADERS = {
    "skills":      re.compile(r"^(technical\s+)?skills?\b", re.I),
    "summary":     re.compile(r"^(professional\s+)?(summary|objective|profile|about)\b", re.I),
    "experience":  re.compile(r"^(work\s+)?(experience|employment|history)\b", re.I),
    "education":   re.compile(r"^education\b", re.I),
    "projects":    re.compile(r"^(projects?|portfolio)\b", re.I),
    "certif":      re.compile(r"^certif", re.I),
}

def _parse_cv_sections(cv_text: str) -> Dict[str, str]:
    """Split CV into labelled sections."""
    sections: Dict[str, List[str]] = {k: [] for k in _SECTION_HEADERS}
    sections["other"] = []
    current = "other"
    for line in cv_text.split("\n"):
        stripped = line.strip()
        matched = False
        if stripped and len(stripped) < 60:
            for name, pat in _SECTION_HEADERS.items():
                if pat.match(stripped):
                    current = name
                    matched = True
                    break
        sections[current].append(line)
    return {k: "\n".join(v) for k, v in sections.items()}

def _section_weight(skill: str, sections: Dict[str, str]) -> float:
    """Return boost multiplier based on which CV section a skill appears in."""
    weights = {"skills": 1.5, "summary": 1.3, "projects": 1.2,
               "experience": 1.0, "certif": 1.1, "education": 0.9, "other": 0.8}
    skill_pat = r"\b" + re.escape(_clean(skill)) + r"\b"
    for sec, text in sections.items():
        if re.search(skill_pat, _normalize(text)):
            return weights.get(sec, 1.0)
    return 0.0  # not found

# ─── Required-skill extraction ─────────────────────────────────────────────────

_REQUIRED_PATTERNS = re.compile(
    r"(required|must[\s\-]have|essential|mandatory|must be|you (must|will need)|"
    r"we (require|need|expect)|key (requirements?|qualifications?)|minimum qualifications?)",
    re.I
)

def _required_skills_from_jd(job_text: str, skill_set: set) -> set:
    required = set()
    for m in _REQUIRED_PATTERNS.finditer(job_text):
        window = job_text[m.start(): m.start() + 300]
        required |= _extract_skills(window, skill_set)
    return required

# ═══════════════════════════════════════════════════════════════════════════════
#  Retrieval Models
# ═══════════════════════════════════════════════════════════════════════════════

def _tfidf_sim(text_a: str, text_b: str) -> float:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity as cs
        vect = TfidfVectorizer(stop_words="english", ngram_range=(1, 2),
                               min_df=1, max_features=12000, sublinear_tf=True)
        mat = vect.fit_transform([text_a, text_b])
        return float(cs(mat[0:1], mat[1:2])[0][0])
    except Exception:
        a, b = set(_tokenize(text_a)), set(_tokenize(text_b))
        return len(a & b) / len(a | b) if a | b else 0.0

def _bm25_sim(query_tokens: List[str], doc_tokens: List[str],
              k1: float = 1.5, b: float = 0.75,
              avg_dl: float = 150.0) -> float:
    """BM25 score normalised to [0, 1]."""
    if not query_tokens or not doc_tokens:
        return 0.0
    doc_freq   = Counter(doc_tokens)
    doc_len    = len(doc_tokens)
    N          = 1  # single-document approximation
    score      = 0.0
    for term in set(query_tokens):
        tf = doc_freq.get(term, 0)
        if tf == 0:
            continue
        idf = math.log(1 + (N - 0 + 0.5) / (0 + 0.5))  # simplified
        tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / avg_dl))
        score += idf * tf_norm
    # Normalise: max possible ≈ len(unique query terms) * log(2) * (k1+1)
    max_score = len(set(query_tokens)) * math.log(2) * (k1 + 1)
    return min(1.0, score / max_score) if max_score > 0 else 0.0

def _ensemble_sim(cv_n: str, job_n: str) -> float:
    """Weighted average of TF-IDF and BM25."""
    cv_tok  = _tokenize(cv_n)
    job_tok = _tokenize(job_n)
    tfidf   = _tfidf_sim(cv_n, job_n)
    bm25    = _bm25_sim(job_tok, cv_tok)
    return tfidf * 0.6 + bm25 * 0.4

# ═══════════════════════════════════════════════════════════════════════════════
#  Tips Generator
# ═══════════════════════════════════════════════════════════════════════════════

def _generate_tips(bd: dict, job_text: str = "") -> List[str]:
    tips   = []
    score  = bd.get("overall", 0)
    tech   = bd.get("tech_score", 0)
    sem    = bd.get("semantic_score", 0)
    title  = bd.get("title_score", 0)
    soft   = bd.get("soft_score", 0)
    domain = bd.get("domain_score", 0)
    m_tech = bd.get("matched_tech", [])
    x_tech = bd.get("missing_tech", [])
    x_soft = bd.get("missing_soft", [])
    req    = set(bd.get("required_skills", []))
    exp_p  = bd.get("exp_penalty", 0)
    cv_exp = bd.get("cv_exp_years", 0)
    job_exp= bd.get("job_exp_years", 0)
    edu_g  = bd.get("education_gap", False)
    no_sec = bd.get("skills_not_in_section", [])
    seniority_gap = bd.get("seniority_gap", False)

    # Required missing skills (highest priority)
    req_missing = [s for s in x_tech if s in req]
    if req_missing:
        tips.append(
            f"🔴 REQUIRED by employer — learn or highlight these: "
            f"{', '.join(req_missing[:5])}. These are explicitly mandatory.")

    # Optional missing tech skills
    opt_missing = [s for s in x_tech if s not in req][:5]
    if opt_missing:
        tips.append(
            f"📚 Boost your score by adding: {', '.join(opt_missing)}. "
            "Even listing these as 'familiar with' helps.")

    # Skills matched but not in dedicated section
    if no_sec:
        tips.append(
            f"📋 Move to a dedicated 'Skills' section (weighted ×1.5): "
            f"{', '.join(no_sec[:4])}.")

    # Low semantic score → language mismatch
    if sem < 30:
        tips.append(
            "📝 Strong language mismatch. Mirror the exact phrases from the job "
            "description in your CV (e.g. if they say 'data pipeline', use that term).")
    elif sem < 50:
        tips.append(
            "📝 Add a tailored professional summary that echoes the job description's "
            "key phrases and technologies.")

    # Seniority mismatch
    if seniority_gap:
        tips.append(
            "🏷️ There may be a seniority level mismatch (e.g. job needs Senior but CV "
            "shows Junior). Quantify impact and scope of your projects to close the gap.")
    elif title < 40:
        tips.append(
            "🏷️ Your CV role titles don't closely match this job. "
            "Update your current title or professional summary to reflect the target role.")

    # Soft skills
    if x_soft:
        tips.append(
            f"🤝 Add these to your CV summary or bullet points: "
            f"{', '.join(x_soft[:3])}.")

    # Domain mismatch
    if domain < 30:
        tips.append(
            "🏢 Domain gap detected. Highlight any relevant domain projects or knowledge "
            "in your summary to signal industry familiarity.")

    # Experience
    if exp_p > 0:
        tips.append(
            f"📅 Experience gap: you show ~{cv_exp} yrs, job asks for {job_exp}+. "
            "Quantify achievements to appear more experienced, or target roles "
            f"requiring {max(1, job_exp - 2)}+ years.")

    # Education
    if edu_g:
        tips.append(
            "🎓 The job may require a higher degree. "
            "Complete your education section and highlight any advanced courses or certs.")

    # High score encouragement
    if score >= 80:
        top3 = ", ".join(m_tech[:3]) if m_tech else "your skills"
        tips.append(
            f"✨ Excellent match! Lead with {top3} in your opening paragraph and "
            "apply with a personalised cover letter.")
    elif score >= 60 and not tips:
        tips.append(
            "💡 Good match. Focus on the missing skills above and tailor your "
            "professional summary to the exact job title.")

    if not tips:
        tips.append(
            "💡 Add a dedicated Skills section, mirror the JD's language, "
            "and quantify each achievement with metrics.")

    return tips

# ═══════════════════════════════════════════════════════════════════════════════
#  Main Scoring Function
# ═══════════════════════════════════════════════════════════════════════════════

def compute_match(cv_text: str, job_text: str, job_title: str = "") -> Tuple[int, Dict]:
    """
    High-accuracy match score (0-100) + rich breakdown dict.
    """
    cv_n  = _normalize(cv_text)
    job_n = _normalize(job_text)
    job_full_n = _normalize(f"{job_title} {job_title} {job_text}")

    # ── Section-aware CV parsing ─────────────────────────────────────────────
    cv_sections = _parse_cv_sections(cv_text)

    # ── ① Tech skills (40%) ──────────────────────────────────────────────────
    cv_tech  = _extract_skills(cv_n, TECH_SKILLS)
    job_tech = _extract_skills(job_n, TECH_SKILLS)
    required = _required_skills_from_jd(job_text, job_tech)

    matched_tech = cv_tech & job_tech
    missing_tech = job_tech - cv_tech

    skills_in_section, skills_not_in_section = [], []
    if job_tech:
        total_w   = 0.0
        matched_w = 0.0
        for skill in job_tech:
            # JD weight: required × 2, freq-based ×1.4 if mentioned 3+ times
            jd_freq  = _skill_freq_in_text(job_text, skill)
            req_mult = 2.0 if skill in required else 1.0
            freq_mult= 1.4 if jd_freq >= 3 else (1.2 if jd_freq == 2 else 1.0)
            w = req_mult * freq_mult
            total_w += w

            if skill in matched_tech:
                sec_w = _section_weight(skill, cv_sections)
                if sec_w >= 1.3:
                    skills_in_section.append(skill)
                elif sec_w < 1.0:
                    skills_not_in_section.append(skill)
                # CV freq: up to ×1.3 for skills mentioned ≥3 times
                cv_freq   = _skill_freq_in_text(cv_text, skill)
                cv_f_mult = 1.0 + min(cv_freq - 1, 2) * 0.15
                matched_w += w * sec_w * cv_f_mult

        tech_score = min(100, int(matched_w / total_w * 100)) if total_w > 0 else 55
    else:
        tech_score = 55

    # ── ② Ensemble retrieval (30%) ────────────────────────────────────────────
    raw_sim        = _ensemble_sim(cv_n, job_full_n)
    # Calibrate: raw cosine rarely > 0.4 for distinct docs → scale ×220 then cap
    semantic_score = min(100, int(raw_sim * 220))

    # ── ③ Role / seniority fit (15%) ─────────────────────────────────────────
    job_role_kw = _tokenize(_clean(job_title or job_text[:80])) 
    job_role_kw = [w for w in job_role_kw if w in ROLE_KEYWORDS]
    if job_role_kw:
        hits = sum(1 for kw in job_role_kw
                   if re.search(r"\b" + re.escape(kw) + r"\b", cv_n))
        title_score = min(100, int(hits / len(job_role_kw) * 100))
    else:
        title_score = 50

    # Seniority comparison
    cv_sen  = _detect_seniority(cv_text)
    job_sen = _detect_seniority(f"{job_title} {job_text}")
    seniority_gap = (job_sen >= 0 and cv_sen >= 0 and abs(cv_sen - job_sen) >= 2)

    # ── ④ Soft skills (8%) ────────────────────────────────────────────────────
    cv_soft   = _extract_skills(cv_n, SOFT_SKILLS)
    job_soft  = _extract_skills(job_n, SOFT_SKILLS)
    matched_s = cv_soft & job_soft
    missing_s = job_soft - cv_soft
    soft_score = (min(100, int(len(matched_s) / len(job_soft) * 100))
                  if job_soft else 50)

    # ── ⑤ Domain fit (4%) ─────────────────────────────────────────────────────
    job_domain = _detect_domain(f"{job_title} {job_text}")
    cv_domain  = _detect_domain(cv_text)
    if job_domain and cv_domain:
        domain_score = 100 if job_domain == cv_domain else 30
    elif not job_domain:
        domain_score = 60  # neutral
    else:
        domain_score = 20  # job has domain, CV shows none

    # ── ⑥ Education (3%) ─────────────────────────────────────────────────────
    cv_edu  = _extract_education(cv_text)
    job_edu = _extract_education(job_text)
    if job_edu == 0:
        edu_score = 70       # neutral
    elif cv_edu >= job_edu:
        edu_score = 100
    else:
        edu_score = max(0, 100 - (job_edu - cv_edu) * 25)
    edu_gap = (job_edu > 0 and cv_edu < job_edu)

    # ── Weighted total ────────────────────────────────────────────────────────
    overall = int(
        tech_score     * 0.40 +
        semantic_score * 0.30 +
        title_score    * 0.15 +
        soft_score     * 0.08 +
        domain_score   * 0.04 +
        edu_score      * 0.03
    )

    # ── Penalties ─────────────────────────────────────────────────────────────
    cv_exp  = _extract_years(cv_text)
    job_exp = _extract_years(job_text)
    exp_penalty = 0
    if job_exp > 0 and cv_exp > 0 and cv_exp < job_exp:
        exp_penalty = min(15, (job_exp - cv_exp) * 4)
        overall -= exp_penalty
    if edu_gap:
        overall -= 5

    overall = max(0, min(100, overall))

    bd = {
        "overall":              overall,
        "tech_score":           tech_score,
        "semantic_score":       semantic_score,
        "title_score":          title_score,
        "soft_score":           soft_score,
        "domain_score":         domain_score,
        "edu_score":            edu_score,
        "exp_penalty":          exp_penalty,
        "cv_exp_years":         cv_exp,
        "job_exp_years":        job_exp,
        "education_gap":        edu_gap,
        "seniority_gap":        seniority_gap,
        "cv_seniority":         cv_sen,
        "job_seniority":        job_sen,
        "matched_tech":         sorted(matched_tech),
        "missing_tech":         sorted(missing_tech),
        "required_skills":      sorted(required),
        "matched_soft":         sorted(matched_s),
        "missing_soft":         sorted(missing_s),
        "skills_in_section":    skills_in_section,
        "skills_not_in_section":skills_not_in_section,
        "cv_skills":            sorted(cv_tech),
        "job_skills":           sorted(job_tech),
        "cv_domain":            cv_domain,
        "job_domain":           job_domain,
    }
    bd["tips"] = _generate_tips(bd, job_text)
    return overall, bd


def batch_match(cv_text: str, rows: List[Dict],
                max_workers: int = 6) -> List[Tuple[int, Dict]]:
    """Parallel batch match of a CV against multiple job rows."""
    def _match_one(row: Dict) -> Tuple[int, Dict]:
        return compute_match(cv_text, row.get("text", ""), row.get("title", ""))

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(_match_one, rows))


# ═══════════════════════════════════════════════════════════════════════════════
#  Recruiter Mode: Snippet-Optimised Candidate Matching
#  Designed for 100-word LinkedIn profile snippets (not full CVs)
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_location(text: str) -> str:
    """Try to pull a city/country mention from text."""
    location_patterns = [
        r"Location:\s*([^\n·•|]+)",
        r"\b(london|paris|berlin|amsterdam|dubai|toronto|new york|san francisco|"
        r"singapore|sydney|barcelona|madrid|rome|milan|zurich|geneva|brussels|"
        r"amsterdam|stockholm|oslo|copenhagen|helsinki|warsaw|prague|vienna|"
        r"mumbai|delhi|bangalore|hyderabad|chennai|cairo|lagos|nairobi|"
        r"montreal|vancouver|chicago|boston|austin|seattle|los angeles)\b",
    ]
    for pat in location_patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1 if "Location" in pat else 0).strip().lower()
    return ""

_AVAILABILITY_SIGNALS = [
    "open to work", "open to opportunities", "looking for", "seeking",
    "available", "actively looking", "job search", "open for work",
]

def _check_availability(text: str) -> bool:
    tl = text.lower()
    return any(sig in tl for sig in _AVAILABILITY_SIGNALS)

def _snippet_keyword_overlap(snippet: str, jd: str) -> float:
    """Jaccard overlap of non-stopword terms between snippet and JD."""
    s_tokens = set(_tokenize(_normalize(snippet)))
    j_tokens = set(_tokenize(_normalize(jd)))
    if not j_tokens:
        return 0.0
    # Recall: how many JD keywords appear in the snippet
    recall = len(s_tokens & j_tokens) / len(j_tokens)
    return min(1.0, recall * 3)   # Scale: 33% recall → 100 score


def compute_candidate_match(
    snippet: str,
    headline: str,
    job_text: str,
    job_title: str = "",
    required_location: str = "",
) -> Tuple[int, Dict]:
    """
    Snippet-optimised scoring for LinkedIn profiles (recruiter mode).

    Factors (tailored for 100–200 word inputs):
      ① Skill recall          50%  — % of required JD skills found in snippet+headline
      ② Title / seniority     25%  — headline vs job title word overlap + level match
      ③ Keyword density       15%  — Jaccard recall of JD keywords in snippet
      ④ Location match        10%  — candidate location vs required location
      Bonus: +5 pts if candidate is "open to work"
    """
    full_cand = f"{headline}\n{headline}\n{snippet}"   # double-weight headline
    cand_n    = _normalize(full_cand)
    job_n     = _normalize(job_text)
    jtitle_n  = _normalize(job_title)

    # ── ① Skill recall (50%) ─────────────────────────────────────────────────
    job_tech  = _extract_skills(job_n, TECH_SKILLS)
    cand_tech = _extract_skills(cand_n, TECH_SKILLS)
    required  = _required_skills_from_jd(job_text, job_tech)

    matched_tech = cand_tech & job_tech
    missing_tech = job_tech - cand_tech

    if job_tech:
        # Weight required skills ×2 in the denominator / numerator
        total_w   = sum(2.0 if s in required else 1.0 for s in job_tech)
        matched_w = sum(2.0 if s in required else 1.0 for s in matched_tech)
        skill_score = min(100, int(matched_w / total_w * 100))
    else:
        skill_score = 40  # neutral if JD has no detectable tech skills

    # ── ② Title / seniority fit (25%) ────────────────────────────────────────
    job_role_words = [w for w in _tokenize(jtitle_n) if w in ROLE_KEYWORDS]
    if job_role_words:
        hits = sum(1 for w in job_role_words
                   if re.search(r"\b" + re.escape(w) + r"\b", cand_n))
        title_score = min(100, int(hits / len(job_role_words) * 100))
    else:
        title_score = 50

    # Seniority bonus/penalty
    cand_sen = _detect_seniority(full_cand)
    job_sen  = _detect_seniority(f"{job_title} {job_text}")
    seniority_gap = (job_sen >= 0 and cand_sen >= 0 and abs(cand_sen - job_sen) >= 2)
    if seniority_gap:
        title_score = max(0, title_score - 20)

    # ── ③ Keyword density (15%) ───────────────────────────────────────────────
    kw_score = int(_snippet_keyword_overlap(full_cand, job_text) * 100)

    # ── ④ Location (10%) ─────────────────────────────────────────────────────
    if required_location:
        cand_loc  = _extract_location(full_cand)
        req_loc_n = required_location.lower().strip()
        if cand_loc and (req_loc_n in cand_loc or cand_loc in req_loc_n):
            loc_score = 100
        elif cand_loc:
            loc_score = 20   # has a location but it's wrong
        else:
            loc_score = 50   # unknown location — neutral
    else:
        loc_score = 70       # no location filter — give benefit of doubt

    # ── Weighted total ────────────────────────────────────────────────────────
    overall = int(
        skill_score * 0.50 +
        title_score * 0.25 +
        kw_score    * 0.15 +
        loc_score   * 0.10
    )

    # Availability bonus
    available = _check_availability(full_cand)
    if available:
        overall = min(100, overall + 5)

    # ── Also get soft skills for the breakdown popup ──────────────────────────
    job_soft  = _extract_skills(job_n, SOFT_SKILLS)
    cand_soft = _extract_skills(cand_n, SOFT_SKILLS)

    bd = {
        "overall":          overall,
        "tech_score":       skill_score,
        "semantic_score":   kw_score,
        "title_score":      title_score,
        "soft_score":       int(len(cand_soft & job_soft) / len(job_soft) * 100) if job_soft else 50,
        "domain_score":     70,   # not computed for snippets
        "edu_score":        70,   # not computed for snippets
        "exp_penalty":      0,
        "cv_exp_years":     _extract_years(full_cand),
        "job_exp_years":    _extract_years(job_text),
        "education_gap":    False,
        "seniority_gap":    seniority_gap,
        "cv_seniority":     cand_sen,
        "job_seniority":    job_sen,
        "matched_tech":     sorted(matched_tech),
        "missing_tech":     sorted(missing_tech),
        "required_skills":  sorted(required),
        "matched_soft":     sorted(cand_soft & job_soft),
        "missing_soft":     sorted(job_soft - cand_soft),
        "skills_in_section":[],
        "skills_not_in_section":[],
        "cv_skills":        sorted(cand_tech),
        "job_skills":       sorted(job_tech),
        "cv_domain":        _detect_domain(full_cand),
        "job_domain":       _detect_domain(job_text),
        "available":        available,
        "tips":             [],
    }
    bd["tips"] = _generate_tips(bd, job_text)
    return overall, bd


def batch_candidate_match(
    candidates: List[Dict],
    job_text: str,
    job_title: str = "",
    required_location: str = "",
    max_workers: int = 8,
) -> List[Tuple[int, Dict]]:
    """
    Parallel candidate matching for recruiter mode.
    Each candidate dict must have: 'snippet', 'headline'.
    """
    def _one(cand: Dict) -> Tuple[int, Dict]:
        return compute_candidate_match(
            cand.get("snippet", ""),
            cand.get("headline", ""),
            job_text,
            job_title,
            required_location,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(_one, candidates))

