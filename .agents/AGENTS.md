# Workspace Rules for Envoy Rainmaker Flight Time Converter

## Command Trigger: "go"
- Whenever the user says "go" (or asks to process/run the scraper), execute `./go` or `./run.sh` immediately.
- The script automatically checks for virtualenv setup, processes all PDFs in `new/`, appends flight records to `logten pro format/logten_pro_import.csv`, and archives processed PDFs to `scraped/`.
