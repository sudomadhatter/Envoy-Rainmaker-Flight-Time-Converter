"""
IATA airport -> IANA timezone lookup and local-to-UTC flight block conversion
for Envoy Air / American Airlines North America, Caribbean, Mexico & Central America routes.
Uses Python's built-in zoneinfo module (zero external dependencies).
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")

AIRPORT_TZ = {
    # US Eastern (America/New_York)
    **{code: "America/New_York" for code in (
        "MIA", "EYW", "FLL", "PBI", "RSW", "TPA", "SRQ", "PIE", "PGD", "MCO", "SFB",
        "DAB", "MLB", "JAX", "GNV", "TLH", "ATL", "SAV", "AGS", "BQK", "VLD", "ABY",
        "CSG", "CHS", "MYR", "CAE", "GSP", "FLO", "HHH", "CLT", "RDU", "GSO", "ILM",
        "FAY", "EWN", "OAJ", "AVL", "PGV", "TRI", "ROA", "RIC", "ORF", "PHF", "CHO",
        "LYH", "SHD", "DCA", "IAD", "BWI", "SBY", "HGR", "PHL", "ABE", "MDT", "AVP",
        "IPT", "ERI", "PIT", "SCE", "JST", "LBE", "EWR", "JFK", "LGA", "ISP", "HPN",
        "SWF", "ACY", "ALB", "SYR", "ROC", "BUF", "ITH", "ELM", "BGM", "ART", "PBG",
        "IAG", "SLK", "BDL", "HVN", "PVD", "BOS", "ORH", "ACK", "MVY", "HYA", "PWM",
        "BGR", "AUG", "PQI", "BTV", "MHT", "PSM", "LEB", "CVG", "DAY", "CMH", "LCK",
        "CLE", "CAK", "TOL", "YNG", "DTW", "GRR", "LAN", "FNT", "MBS", "AZO", "MKG",
        "TVC", "PLN", "CIU", "MQT", "CMX", "APN", "ESC", "IMT", "IWD", "IND", "FWA",
        "SBN", "LAF", "SDF", "LEX", "CRW", "HTS", "CKB", "MGW", "LWB", "TYS", "CHA",
    )},
    # US Central (America/Chicago)
    **{code: "America/Chicago" for code in (
        "PNS", "VPS", "ECP", "EVV", "BNA", "MEM", "MKL", "HSV", "BHM", "MOB", "MGM",
        "DHN", "CSG", "GTR", "TUP", "JAN", "GPT", "MEI", "PIB", "GLH", "MSY", "BTR",
        "LFT", "LCH", "AEX", "SHV", "MLU", "LIT", "XNA", "FSM", "TXK", "HOT", "ELD",
        "ORD", "MDW", "RFD", "MLI", "PIA", "BMI", "CMI", "SPI", "DEC", "MWA", "UIN",
        "BLV", "STL", "MCI", "SGF", "COU", "JLN", "STJ", "CGI", "TBN", "MKE", "MSN",
        "GRB", "ATW", "CWA", "EAU", "LSE", "RHI", "MSP", "RST", "DLH", "BRD", "BJI",
        "HIB", "INL", "STC", "FAR", "GFK", "BIS", "MOT", "JMS", "DVL", "XWA", "FSD",
        "ABR", "ATY", "PIR", "DSM", "CID", "DBQ", "ALO", "MCW", "SUX", "FOD", "BRL",
        "OMA", "LNK", "GRI", "EAR", "LBF", "ICT", "MHK", "HYS", "SLN", "DDC", "GCK",
        "LBL", "TUL", "OKC", "LAW", "SWO", "DFW", "DAL", "IAH", "HOU", "AUS", "SAT",
        "CRP", "BRO", "HRL", "MFE", "LRD", "ACT", "TYR", "GGG", "TXK", "ABI", "SJT",
        "SPS", "LBB", "AMA", "MAF", "CLL", "GRK", "BPT", "VCT", "DRT", "ROW",
    )},
    # Fix ROW / CSG overlaps cleanly
    "CSG": "America/New_York",
    "IMT": "America/Menominee",
    "IWD": "America/Menominee",
    # US Mountain (America/Denver)
    **{code: "America/Denver" for code in (
        "DEN", "COS", "ASE", "EGE", "HDN", "GJT", "MTJ", "DRO", "PUB", "ALS", "GUC",
        "SLC", "PVU", "OGD", "SGU", "CDC", "CNY", "VEL", "BOI", "IDA", "PIH", "SUN",
        "TWF", "BZN", "MSO", "BIL", "FCA", "GTF", "HLN", "BTM", "WYS", "JAC", "COD",
        "CPR", "CYS", "LAR", "RKS", "GCC", "SHR", "RIW", "RAP", "DIK", "ISN", "BFF",
        "ABQ", "SAF", "ROW", "HOB", "CNM", "ELP",
    )},
    # US Mountain - no DST (America/Phoenix)
    **{code: "America/Phoenix" for code in ("PHX", "AZA", "TUS", "FLG", "YUM", "PRC", "SOW")},
    # US Pacific (America/Los_Angeles)
    **{code: "America/Los_Angeles" for code in (
        "LAX", "SAN", "SNA", "ONT", "BUR", "LGB", "PSP", "SBA", "SBP", "SMX", "MRY",
        "FAT", "BFL", "SCK", "MOD", "SMF", "SFO", "SJC", "OAK", "STS", "RDD", "ACV",
        "OTH", "EUG", "MFR", "RDM", "PDX", "SLE", "SEA", "PAE", "GEG", "PSC", "ALW",
        "EAT", "YKM", "PUW", "BLI", "RNO", "LAS", "LWS",
    )},
    # Alaska & Hawaii
    **{code: "America/Anchorage" for code in ("ANC", "FAI", "JNU", "KTN", "SIT")},
    **{code: "Pacific/Honolulu" for code in ("HNL", "OGG", "KOA", "LIH", "ITO")},
    # Bahamas (observes US Eastern DST)
    **{code: "America/Nassau" for code in (
        "NAS", "FPO", "MHH", "ELH", "GGT", "ZSA", "BIM", "GHB", "TCB", "RSD", "MYG",
    )},
    # Atlantic Standard Time (UTC-4 year-round, no DST)
    **{code: "America/Puerto_Rico" for code in (
        "SJU", "BQN", "PSE", "STT", "STX", "AXA", "EIS", "DOM", "SXM", "ANU", "SKB",
        "NEV", "UVF", "SLU", "BGI", "GND", "SVD", "POS", "TAB", "FDF", "PTP", "AUA",
        "CUR", "BON", "SDQ", "PUJ", "STI", "POP", "LRM", "AZS",
    )},
    # Atlantic / Caribbean with DST
    "PLS": "America/Grand_Turk",
    "PAP": "America/Port-au-Prince",
    "BDA": "Atlantic/Bermuda",
    # Caribbean / Central & South America (UTC-5 year-round, no DST)
    **{code: "America/Jamaica" for code in ("MBJ", "KIN", "OCJ")},
    "GCM": "America/Cayman",
    "PTY": "America/Panama",
    **{code: "America/Bogota" for code in ("BOG", "CTG", "MDE", "CLO", "BAQ", "PEI")},
    **{code: "America/Cancun" for code in ("CUN", "CZM", "TQO")},
    # Canada
    **{code: "America/Toronto" for code in ("YYZ", "YTZ", "YOW", "YUL", "YQB", "YXU", "YKF", "YHM")},
    **{code: "America/Halifax" for code in ("YHZ", "YQM", "YSJ", "YFC", "YYG")},
    "YYT": "America/St_Johns",
    **{code: "America/Winnipeg" for code in ("YWG", "YQT")},
    "YQR": "America/Regina",
    "YXE": "America/Regina",
    **{code: "America/Edmonton" for code in ("YYC", "YEG", "YMM", "YLW")},
    "YLW": "America/Vancouver",
    **{code: "America/Vancouver" for code in ("YVR", "YYJ", "YXX")},
    # Mexico & Central America
    **{code: "America/Mexico_City" for code in (
        "MEX", "NLU", "TLC", "GDL", "BJX", "QRO", "SLP", "AGU", "ZIH", "OAX", "ACA",
        "VER", "MID", "PVR", "PBC", "MLM", "ZCL", "TAM", "CME", "VSA", "TGZ", "HUX",
    )},
    **{code: "America/Monterrey" for code in ("MTY", "TRC", "CUU", "DGO")},
    **{code: "America/Mazatlan" for code in ("SJD", "LAP", "LTO", "MZT", "CUL")},
    "HMO": "America/Hermosillo",
    **{code: "America/Tijuana" for code in ("TIJ", "MXL")},
    "CJS": "America/Ciudad_Juarez",
    "BZE": "America/Belize",
    "GUA": "America/Guatemala",
    "SAL": "America/El_Salvador",
    **{code: "America/Tegucigalpa" for code in ("SAP", "TGU", "XPL", "RTB")},
    "MGA": "America/Managua",
    **{code: "America/Costa_Rica" for code in ("SJO", "LIR")},
}


def hhmm_to_minutes(hhmm):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def convert_leg_local_to_utc(date_str, org, dst, atd, ata, act_dur):
    """
    Convert a flight leg's local (date_str, atd, ata) to UTC (utc_date_str, utc_out, utc_in).
    Uses exact IANA airport timezones when known, and falls back to the known hub + ActDur
    if one endpoint is an unmapped charter airport.
    """
    org_tz_name = AIRPORT_TZ.get(org)
    dst_tz_name = AIRPORT_TZ.get(dst)
    dur_mins = hhmm_to_minutes(act_dur)

    if org_tz_name and dst_tz_name:
        org_tz = ZoneInfo(org_tz_name)
        dst_tz = ZoneInfo(dst_tz_name)
        base_dep_naive = datetime.strptime(f"{date_str} {atd}", "%Y-%m-%d %H:%M")
        base_arr_naive = datetime.strptime(f"{date_str} {ata}", "%Y-%m-%d %H:%M")

        fallback_result = None
        for dep_fold in (0, 1):
            for arr_fold in (0, 1):
                dep_local = base_dep_naive.replace(tzinfo=org_tz, fold=dep_fold)
                arr_local = base_arr_naive.replace(tzinfo=dst_tz, fold=arr_fold)
                dep_utc = dep_local.astimezone(UTC)
                arr_utc = arr_local.astimezone(UTC)
                while arr_utc < dep_utc:
                    arr_local = (arr_local.replace(tzinfo=None) + timedelta(days=1)).replace(
                        tzinfo=dst_tz, fold=arr_fold
                    )
                    arr_utc = arr_local.astimezone(UTC)
                candidate = (
                    dep_utc.strftime("%Y-%m-%d"),
                    dep_utc.strftime("%H:%M"),
                    arr_utc.strftime("%H:%M"),
                )
                if fallback_result is None:
                    fallback_result = candidate
                calc_mins = int((arr_utc - dep_utc).total_seconds() // 60)
                if calc_mins == dur_mins:
                    return candidate
        return fallback_result

    if org_tz_name:
        dep_local = datetime.strptime(f"{date_str} {atd}", "%Y-%m-%d %H:%M").replace(
            tzinfo=ZoneInfo(org_tz_name)
        )
        dep_utc = dep_local.astimezone(UTC)
        arr_utc = dep_utc + timedelta(minutes=dur_mins)
        return dep_utc.strftime("%Y-%m-%d"), dep_utc.strftime("%H:%M"), arr_utc.strftime("%H:%M")

    if dst_tz_name:
        arr_local = datetime.strptime(f"{date_str} {ata}", "%Y-%m-%d %H:%M").replace(
            tzinfo=ZoneInfo(dst_tz_name)
        )
        arr_utc = arr_local.astimezone(UTC)
        dep_utc = arr_utc - timedelta(minutes=dur_mins)
        return dep_utc.strftime("%Y-%m-%d"), dep_utc.strftime("%H:%M"), arr_utc.strftime("%H:%M")

    return date_str, atd, ata
