"""Curated nonprofit registration schemes. There is no official global list; any free text is accepted too."""

SCHEMES: list[tuple[str, str]] = [
    ("IRS-EIN", "United States: IRS Employer Identification Number (EIN)"),
    ("CA-CRA", "Canada: CRA charity registration number"),
    ("MX-CLUNI", "Mexico: CLUNI (Registro Federal de OSC)"),
    ("BR-CNPJ", "Brazil: CNPJ"),
    ("GB-CHC", "England and Wales: Charity Commission number"),
    ("GB-SC", "Scotland: OSCR charity number"),
    ("GB-NIC", "Northern Ireland: Charity Commission NI number"),
    ("IE-RCN", "Ireland: Charities Regulator registered charity number"),
    ("FR-RNA", "France: RNA number (association)"),
    ("DE-VR", "Germany: Vereinsregister number"),
    ("NL-KVK", "Netherlands: KVK number"),
    ("ES-NIF", "Spain: NIF / Registro Nacional de Asociaciones"),
    ("IT-RUNTS", "Italy: RUNTS registration"),
    ("KE-NGOB", "Kenya: NGO Coordination Board registration"),
    ("UG-NGOB", "Uganda: NGO Bureau registration"),
    ("NG-CAC", "Nigeria: CAC incorporated trustees number"),
    ("GH-DSW", "Ghana: Department of Social Welfare registration"),
    ("ZA-NPO", "South Africa: NPO number (Dept. of Social Development)"),
    ("IN-DARPAN", "India: NGO Darpan unique ID"),
    ("IN-FCRA", "India: FCRA registration number"),
    ("PH-SEC", "Philippines: SEC registration"),
    ("AU-ABN", "Australia: ABN (ACNC registered)"),
    ("NZ-CC", "New Zealand: Charities Services registration number"),
]

SCHEME_CODES = {c for c, _ in SCHEMES}
