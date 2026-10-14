/**
 * Shared Search, Filter & Location Constants
 * Extracted from UI components to keep React modules pure for Vite Fast Refresh (HMR).
 */

export const QUICK_ROLES = [
  'Flutter Developer',
  'React / Next.js',
  'Python AI Engineer',
  'Full Stack Developer',
  'Node.js Backend',
  'DevOps Engineer',
]

export const DEFAULT_POST_FILTERS = {
  sortBy: 'relevant', // 'relevant' | 'recent'
  datePosted: 'all',  // '24h', 'week', 'month', 'all'
  emailOnly: false,
}

export const COMPANY_PRESETS = [
  'Canonical', 'Proxify', 'Quik Hire Staffing', 'Hire Feed',
  'YO IT Consulting', 'Hired', 'crewlia', 'Aptura', 'Restream', 'Recruitment Room - Global',
]

export const SECTOR_PRESETS = [
  'IT Services and IT Consulting',
  'Software Development',
  'Computer and Network Security',
  'Technology, Information and Media',
  'Staffing and Recruiting',
  'Internet and Information Technology',
  'Business Consulting and Services',
  'Marketing Services',
  'Financial Services',
  'Information Services',
]

export const FUNCTION_PRESETS = [
  'Engineering',
  'Information Technology',
  'Product Management',
  'Administrative',
  'Design & Creative',
  'Research & Analytics',
  'Sales',
  'Business Development',
  'Consulting',
  'Customer Support',
]

export const TITLE_PRESETS = [
  'Software Engineer',
  'Full Stack Engineer',
  'Senior Developer',
  'Senior Software Engineer',
  'Engineering Manager / Director',
  'JavaScript Developer',
  'Mobile Engineer',
  'Android Developer',
  'Python Developer',
  'DevOps / Systems Engineer',
]

export const COMMITMENT_PRESETS = [
  'Diversity, Equity & Inclusion',
  'Environmental Sustainability',
  'Social Impact',
  'Work-Life Balance',
  'Career Growth & Learning',
]

export const DEFAULT_FILTERS = {
  sortBy: 'relevant',
  datePosted: 'all',
  experience: [],
  companies: [],
  jobTypes: [],
  workplaceType: [],
  easyApply: false,
  verifiedInfoOnly: false,
  internationalOnly: false,
  sectors: [],
  functions: [],
  jobTitles: [],
  under10Applicants: false,
  inYourNetwork: false,
  commitments: [],
}

export const POPULAR_COUNTRIES = [
  { code: 'Worldwide', label: 'Worldwide', flag: '🌐' },
  { code: 'USA', label: 'USA', flag: '🇺🇸' },
  { code: 'UAE', label: 'UAE', flag: '🇦🇪' },
  { code: 'UK', label: 'UK', flag: '🇬🇧' },
  { code: 'Canada', label: 'Canada', flag: '🇨🇦' },
  { code: 'Germany', label: 'Germany', flag: '🇩🇪' },
  { code: 'France', label: 'France', flag: '🇫🇷' },
  { code: 'Netherlands', label: 'Netherlands', flag: '🇳🇱' },
  { code: 'Morocco', label: 'Morocco', flag: '🇲🇦' },
  { code: 'Singapore', label: 'Singapore', flag: '🇸🇬' },
]

export const ALL_COUNTRY_SUGGESTIONS = [
  // Global & Work Modes
  { label: 'Worldwide', value: 'Worldwide', icon: '🌐', region: 'Global', popular: true },
  { label: '100% Remote / WFH', value: 'Remote', icon: '💻', region: 'Global', popular: true },
  { label: 'Remote (US & Americas)', value: 'Remote US', icon: '🏠', region: 'Global' },
  { label: 'Remote (Europe / EMEA)', value: 'Remote Europe', icon: '🌍', region: 'Global' },
  { label: 'Remote (MENA / Gulf)', value: 'Remote MENA', icon: '🕌', region: 'Global' },
  { label: 'Remote (Asia / APAC)', value: 'Remote APAC', icon: '🌏', region: 'Global' },

  // North America
  { label: 'United States', value: 'United States', icon: '🇺🇸', region: 'North America', popular: true },
  { label: 'Canada', value: 'Canada', icon: '🇨🇦', region: 'North America', popular: true },
  { label: 'Mexico', value: 'Mexico', icon: '🇲🇽', region: 'North America' },

  // Europe (EMEA)
  { label: 'United Kingdom', value: 'United Kingdom', icon: '🇬🇧', region: 'Europe', popular: true },
  { label: 'Germany', value: 'Germany', icon: '🇩🇪', region: 'Europe', popular: true },
  { label: 'France', value: 'France', icon: '🇫🇷', region: 'Europe', popular: true },
  { label: 'Netherlands', value: 'Netherlands', icon: '🇳🇱', region: 'Europe', popular: true },
  { label: 'Switzerland', value: 'Switzerland', icon: '🇨🇭', region: 'Europe', popular: true },
  { label: 'Spain', value: 'Spain', icon: '🇪🇸', region: 'Europe', popular: true },
  { label: 'Ireland', value: 'Ireland', icon: '🇮🇪', region: 'Europe' },
  { label: 'Italy', value: 'Italy', icon: '🇮🇹', region: 'Europe' },
  { label: 'Poland', value: 'Poland', icon: '🇵🇱', region: 'Europe' },
  { label: 'Sweden', value: 'Sweden', icon: '🇸🇪', region: 'Europe' },
  { label: 'Belgium', value: 'Belgium', icon: '🇧🇪', region: 'Europe' },
  { label: 'Austria', value: 'Austria', icon: '🇦🇹', region: 'Europe' },
  { label: 'Denmark', value: 'Denmark', icon: '🇩🇰', region: 'Europe' },
  { label: 'Norway', value: 'Norway', icon: '🇳🇴', region: 'Europe' },
  { label: 'Portugal', value: 'Portugal', icon: '🇵🇹', region: 'Europe' },

  // Middle East & North Africa (MENA / GCC)
  { label: 'UAE / Dubai', value: 'UAE', icon: '🇦🇪', region: 'MENA', popular: true },
  { label: 'Saudi Arabia', value: 'Saudi Arabia', icon: '🇸🇦', region: 'MENA', popular: true },
  { label: 'Morocco', value: 'Morocco', icon: '🇲🇦', region: 'MENA', popular: true },
  { label: 'Egypt', value: 'Egypt', icon: '🇪🇬', region: 'MENA', popular: true },
  { label: 'Qatar', value: 'Qatar', icon: '🇶🇦', region: 'MENA' },
  { label: 'Kuwait', value: 'Kuwait', icon: '🇰🇼', region: 'MENA' },
  { label: 'Bahrain', value: 'Bahrain', icon: '🇧🇭', region: 'MENA' },
  { label: 'Oman', value: 'Oman', icon: '🇴🇲', region: 'MENA' },
  { label: 'Jordan', value: 'Jordan', icon: '🇯🇴', region: 'MENA' },

  // Asia & Pacific (APAC)
  { label: 'Singapore', value: 'Singapore', icon: '🇸🇬', region: 'APAC', popular: true },
  { label: 'Australia', value: 'Australia', icon: '🇦🇺', region: 'APAC', popular: true },
  { label: 'New Zealand', value: 'New Zealand', icon: '🇳🇿', region: 'APAC' },
  { label: 'India', value: 'India', icon: '🇮🇳', region: 'APAC' },
  { label: 'Japan', value: 'Japan', icon: '🇯🇵', region: 'APAC' },
  { label: 'South Korea', value: 'South Korea', icon: '🇰🇷', region: 'APAC' },
  { label: 'Malaysia', value: 'Malaysia', icon: '🇲🇾', region: 'APAC' },
  { label: 'Philippines', value: 'Philippines', icon: '🇵🇭', region: 'APAC' },
  { label: 'Indonesia', value: 'Indonesia', icon: '🇮🇩', region: 'APAC' },

  // Latin America (LATAM)
  { label: 'Brazil', value: 'Brazil', icon: '🇧🇷', region: 'LATAM' },
  { label: 'Argentina', value: 'Argentina', icon: '🇦🇷', region: 'LATAM' },
  { label: 'Colombia', value: 'Colombia', icon: '🇨🇴', region: 'LATAM' },
  { label: 'Chile', value: 'Chile', icon: '🇨🇱', region: 'LATAM' },
]

export const REGION_CATEGORIES = [
  { id: 'all', label: 'All Regions' },
  { id: 'popular', label: '⭐ Top Suggestions' },
  { id: 'Europe', label: '🇪🇺 Europe' },
  { id: 'MENA', label: '🕌 MENA & Gulf' },
  { id: 'North America', label: '🇺🇸 North America' },
  { id: 'APAC', label: '🌏 Asia-Pacific' },
  { id: 'LATAM', label: '🌎 Latin America' },
]
