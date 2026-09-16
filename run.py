import csv
from jobspy import scrape_jobs

def main():
    print("Scraping jobs with verbose logging... please wait.")
    
    jobs = scrape_jobs(
        site_name=["indeed", "zip_recruiter", "google"],
        search_term="software engineer",
        google_search_term="software engineer jobs in San Francisco, CA since yesterday",
        location="San Francisco, CA",
        results_wanted=5,
        verbose=2, # Enable detailed INFO and WARNING logs
    )
    
    print(f"\nFound {len(jobs)} jobs in total:")
    if not jobs.empty:
        print(jobs[["site", "title", "company", "location"]])
        jobs.to_csv("jobs.csv", index=False)
        print("\nResults saved to jobs.csv!")
    else:
        print("No jobs found or requests were blocked.")

if __name__ == "__main__":
    main()
