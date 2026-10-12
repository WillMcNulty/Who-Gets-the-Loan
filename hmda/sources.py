"""Where each year of Virginia HMDA data comes from. Three eras, three publishers, three formats.

- 2004-2006: the Federal Reserve's national "Final" LAR files, archived by the National Archives (NARA, series
  NAID 2456161). One fixed-width 80-byte record per application, the whole country in one file; Virginia is
  state code 51. "Final" is the edition published the year after the data year (NARA also keeps a later
  "Ultimate" edition with resubmissions); the CFPB's 2007-2017 files are its own snapshot of each year.
- 2007-2017: the CFPB's historic HMDA files, nationwide "all records" with numeric codes, filtered here to
  Virginia. (The CFPB page also links per-state files, but those return 404 as of 2026-10-12; the nationwide files
  work.) These carry census-tract context (population, minority share, income ratio) from the FFIEC census files.
- 2018 onward: the CFPB's HMDA Data Browser API, Virginia CSV per year, under the 2015 rule's expanded fields.
"""

FIRST_YEAR, LAST_YEAR = 2004, 2025
STATE_FIPS, STATE = "51", "VA"

NARA_FINAL = {
    2004: "https://catalog.archives.gov/medialz/electronic-records/rg-082/hmda/FLAR04/f2004lar.public.dat.zip",
    2005: "https://catalog.archives.gov/medialz/electronic-records/rg-082/hmda/FLAR0506/LARS.FINAL.2005.DAT.zip",
    2006: "https://catalog.archives.gov/medialz/electronic-records/rg-082/hmda/FLAR0506/LARS.FINAL.2006.DAT.zip",
}
NARA_LAYOUT = "https://catalog.archives.gov/medialz/electronic-records/rg-082/hmda/FLAR0506/Public_LARs_-_2004_Forward.final.6.14.2007.pdf"
CFPB_HISTORIC = "https://files.consumerfinance.gov/hmda-historic-loan-data/hmda_{year}_nationwide_all-records_codes.zip"
DATA_BROWSER = "https://ffiec.cfpb.gov/v2/data-browser-api/view/csv?states=VA&years={year}"


# The analysis eras (not the same as the sources): boom and crash on 2000-census tracts, the post-crisis years on
# 2010-census tracts, and the expanded 2018 reporting rule.
ERAS = {"2004-2011": (2004, 2011), "2012-2017": (2012, 2017), "2018-2025": (2018, LAST_YEAR)}


def era(year):
    return next(k for k, (a, b) in ERAS.items() if a <= year <= b)


def source(year):
    """(url, local file name, publisher) for one year's raw file."""
    if year in NARA_FINAL:
        url = NARA_FINAL[year]
        return url, f"nara_final_lar_{year}.zip", "Federal Reserve Board via the National Archives (NAID 2456161)"
    if year <= 2017:
        return CFPB_HISTORIC.format(year=year), f"cfpb_historic_nationwide_{year}.zip", "CFPB historic HMDA data"
    return DATA_BROWSER.format(year=year), f"cfpb_databrowser_va_{year}.csv", "CFPB HMDA Data Browser"


# Tract boundaries in force for each year's census-tract codes (the FFIEC switches with the data year).
def tract_vintage(year):
    if year <= 2011:
        return 2000
    if year <= 2021:
        return 2010
    return 2020
