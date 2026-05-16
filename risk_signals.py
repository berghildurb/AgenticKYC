# FATF jurisdiction lists — updated June 2024
# https://www.fatf-gafi.org/en/topics/high-risk-and-other-monitored-jurisdictions.html

FATF_BLACKLIST = {
    "north korea",
    "iran",
    "myanmar",
}

FATF_GREYLIST = {
    "bulgaria",
    "burkina faso",
    "cameroon",
    "croatia",
    "democratic republic of congo",
    "drc",
    "haiti",
    "jamaica",
    "kenya",
    "mali",
    "mozambique",
    "namibia",
    "nigeria",
    "philippines",
    "senegal",
    "south africa",
    "south sudan",
    "syria",
    "tanzania",
    "turkey",
    "türkiye",
    "uganda",
    "vietnam",
    "yemen",
}

# Occupations/sectors that carry elevated ML/TF risk
HIGH_RISK_OCCUPATIONS = {
    "cryptocurrency",
    "crypto",
    "gambling",
    "casino",
    "arms",
    "weapons",
    "defence",
    "defense",
    "shell company",
    "offshore",
    "real estate",
    "estate agent",
    "money service",
    "msb",
    "forex",
    "currency exchange",
    "pawnbroker",
    "jeweller",
    "jewelry",
    "art dealer",
    "auction",
}


def fatf_flags(countries: list[str]) -> list[tuple[str, str]]:
    """Return (country, list_type) tuples for any FATF-listed countries."""
    flags = []
    for country in countries:
        normalised = country.strip().lower()
        if normalised in FATF_BLACKLIST:
            flags.append((country, "FATF blacklist"))
        elif normalised in FATF_GREYLIST:
            flags.append((country, "FATF greylist"))
    return flags


def high_risk_occupation_flags(occupation: str, employer: str) -> list[str]:
    """Return any high-risk sector keywords found in occupation or employer fields."""
    text = f"{occupation} {employer}".lower()
    return [kw for kw in HIGH_RISK_OCCUPATIONS if kw in text]
