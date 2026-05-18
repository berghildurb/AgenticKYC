# Hardcoded profiles for the synthetic stress test.
# Risk levels are driven by behaviour and context, not nationality or ethnicity.
# Profile 5 uses a real publicly sanctioned individual (Viktor Bout) so the
# OSINT layer surfaces genuine adverse findings. All other profiles are
# entirely fictional.

SYNTHETIC_PROFILES = [
    # ── 1. Low risk — Nigerian nurse, salary income, low volume ───────────────
    # Demonstrates that FATF-listed nationality alone does not drive the score.
    {
        "full_name":                    "Adaeze Obi",
        "date_of_birth":                "1991-03-22",
        "nationality":                  "Nigerian",
        "country_of_birth":             "Nigeria",
        "country_of_residence":         "Denmark",
        "occupation":                   "Registered Nurse",
        "employer":                     "Rigshospitalet",
        "source_of_funds":              (
            "Monthly salary from full-time nursing employment at Rigshospitalet "
            "(Copenhagen University Hospital). Approximately €3,500 per month net."
        ),
        "expected_transaction_volume":  "Under €1,000",
        "pep_status":                   False,
        "beneficial_ownership":         "I am acting entirely on my own behalf.",
    },

    # ── 2. Medium risk — German freelancer, vague self-employed income ────────
    # European name and nationality; behavioural flags elevate the risk.
    {
        "full_name":                    "Thomas Weber",
        "date_of_birth":                "1983-11-05",
        "nationality":                  "German",
        "country_of_birth":             "Germany",
        "country_of_residence":         "Germany",
        "occupation":                   "Freelance IT Consultant",
        "employer":                     "Self-employed",
        "source_of_funds":              (
            "Project-based consulting income from various clients across Europe. "
            "Revenue fluctuates month to month depending on active contracts."
        ),
        "expected_transaction_volume":  "€5,000 – €10,000",
        "pep_status":                   False,
        "beneficial_ownership":         "Acting on my own behalf.",
    },

    # ── 3. High risk — Dutch commodity broker, opaque funds, high volume ──────
    # UAE residence is not FATF-listed. Risk is purely behavioural:
    # very high volume + structured finance language + unclear beneficial ownership.
    {
        "full_name":                    "Markus van der Berg",
        "date_of_birth":                "1979-07-30",
        "nationality":                  "Dutch",
        "country_of_birth":             "Netherlands",
        "country_of_residence":         "United Arab Emirates",
        "occupation":                   "Commodity Broker",
        "employer":                     "Self-employed",
        "source_of_funds":              (
            "Returns from commodity trading operations and structured finance "
            "arrangements across international markets."
        ),
        "expected_transaction_volume":  "Over €100,000",
        "pep_status":                   False,
        "beneficial_ownership":         (
            "Some transactions are conducted on behalf of associated investors "
            "and trading counterparties."
        ),
    },

    # ── 4. Critical — Belgian PEP, South Sudan residence, high volume ─────────
    # PEP declaration + FATF greylist residence (South Sudan) + very high volume
    # + opaque mixed beneficial ownership (trust + business entities).
    {
        "full_name":                    "Claudette Martin",
        "date_of_birth":                "1970-09-18",
        "nationality":                  "Belgian",
        "country_of_birth":             "Belgium",
        "country_of_residence":         "South Sudan",
        "occupation":                   "Senior Government Policy Advisor",
        "employer":                     "Ministry of Finance, Government of South Sudan",
        "source_of_funds":              (
            "Government salary, international consultancy fees from multilateral "
            "organisations, and distributions from a family investment trust."
        ),
        "expected_transaction_volume":  "Over €100,000",
        "pep_status":                   True,
        "beneficial_ownership":         (
            "Transactions are conducted on behalf of my own account, a family "
            "investment trust, and associated business entities."
        ),
    },

    # ── 5. Real sanctioned individual — Viktor Bout ────────────────────────────
    # Russian arms dealer. Convicted in the US 2011, released in the 2022
    # Griner prisoner swap. OFAC-designated. OSINT will surface real findings.
    {
        "full_name":                    "Viktor Bout",
        "date_of_birth":                "1967-01-13",
        "nationality":                  "Russian",
        "country_of_birth":             "Russia",
        "country_of_residence":         "Russia",
        "occupation":                   "Logistics and Trade Consultant",
        "employer":                     "Self-employed",
        "source_of_funds":              (
            "Consulting fees from logistics coordination and international "
            "trade advisory services."
        ),
        "expected_transaction_volume":  "€50,000 – €100,000",
        "pep_status":                   False,
        "beneficial_ownership":         "Acting on my own behalf.",
    },
]
