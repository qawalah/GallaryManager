"""Two-letter country codes, and the name a folder should be called.

A city table gives a country CODE - `IT`, `QA`, `MA`. A folder called `IT` is a
folder nobody recognises at a glance, which defeats the point of sorting by
place at all.

Names are the plain English short form and deliberately ASCII: these become
folder names on a Synology, reached over SMB from Windows, and an accent in a
path is the kind of thing that works for years and then does not. `Ivory Coast`
rather than `Cote d'Ivoire`, `Curacao` rather than `Curaçao`.

The table can be OVERRIDDEN by GeoNames' own `countryInfo.txt` at import time.
It is written out here so the app works with only the city file downloaded, and
overridable so a name that is wrong or out of date is a file you can drop in
rather than a bug you have to wait for.
"""

from __future__ import annotations

NAMES = {
    "AD": "Andorra", "AE": "United Arab Emirates", "AF": "Afghanistan",
    "AG": "Antigua and Barbuda", "AI": "Anguilla", "AL": "Albania",
    "AM": "Armenia", "AO": "Angola", "AQ": "Antarctica", "AR": "Argentina",
    "AS": "American Samoa", "AT": "Austria", "AU": "Australia", "AW": "Aruba",
    "AX": "Aland Islands", "AZ": "Azerbaijan", "BA": "Bosnia and Herzegovina",
    "BB": "Barbados", "BD": "Bangladesh", "BE": "Belgium", "BF": "Burkina Faso",
    "BG": "Bulgaria", "BH": "Bahrain", "BI": "Burundi", "BJ": "Benin",
    "BL": "Saint Barthelemy", "BM": "Bermuda", "BN": "Brunei", "BO": "Bolivia",
    "BQ": "Caribbean Netherlands", "BR": "Brazil", "BS": "Bahamas",
    "BT": "Bhutan", "BV": "Bouvet Island", "BW": "Botswana", "BY": "Belarus",
    "BZ": "Belize", "CA": "Canada", "CC": "Cocos Islands",
    "CD": "Democratic Republic of the Congo", "CF": "Central African Republic",
    "CG": "Republic of the Congo", "CH": "Switzerland", "CI": "Ivory Coast",
    "CK": "Cook Islands", "CL": "Chile", "CM": "Cameroon", "CN": "China",
    "CO": "Colombia", "CR": "Costa Rica", "CU": "Cuba", "CV": "Cape Verde",
    "CW": "Curacao", "CX": "Christmas Island", "CY": "Cyprus",
    "CZ": "Czechia", "DE": "Germany", "DJ": "Djibouti", "DK": "Denmark",
    "DM": "Dominica", "DO": "Dominican Republic", "DZ": "Algeria",
    "EC": "Ecuador", "EE": "Estonia", "EG": "Egypt", "EH": "Western Sahara",
    "ER": "Eritrea", "ES": "Spain", "ET": "Ethiopia", "FI": "Finland",
    "FJ": "Fiji", "FK": "Falkland Islands", "FM": "Micronesia",
    "FO": "Faroe Islands", "FR": "France", "GA": "Gabon",
    "GB": "United Kingdom", "GD": "Grenada", "GE": "Georgia",
    "GF": "French Guiana", "GG": "Guernsey", "GH": "Ghana", "GI": "Gibraltar",
    "GL": "Greenland", "GM": "Gambia", "GN": "Guinea", "GP": "Guadeloupe",
    "GQ": "Equatorial Guinea", "GR": "Greece",
    "GS": "South Georgia and the South Sandwich Islands", "GT": "Guatemala",
    "GU": "Guam", "GW": "Guinea-Bissau", "GY": "Guyana", "HK": "Hong Kong",
    "HM": "Heard Island and McDonald Islands", "HN": "Honduras",
    "HR": "Croatia", "HT": "Haiti", "HU": "Hungary", "ID": "Indonesia",
    "IE": "Ireland", "IL": "Israel", "IM": "Isle of Man", "IN": "India",
    "IO": "British Indian Ocean Territory", "IQ": "Iraq", "IR": "Iran",
    "IS": "Iceland", "IT": "Italy", "JE": "Jersey", "JM": "Jamaica",
    "JO": "Jordan", "JP": "Japan", "KE": "Kenya", "KG": "Kyrgyzstan",
    "KH": "Cambodia", "KI": "Kiribati", "KM": "Comoros",
    "KN": "Saint Kitts and Nevis", "KP": "North Korea", "KR": "South Korea",
    "KW": "Kuwait", "KY": "Cayman Islands", "KZ": "Kazakhstan", "LA": "Laos",
    "LB": "Lebanon", "LC": "Saint Lucia", "LI": "Liechtenstein",
    "LK": "Sri Lanka", "LR": "Liberia", "LS": "Lesotho", "LT": "Lithuania",
    "LU": "Luxembourg", "LV": "Latvia", "LY": "Libya", "MA": "Morocco",
    "MC": "Monaco", "MD": "Moldova", "ME": "Montenegro",
    "MF": "Saint Martin", "MG": "Madagascar", "MH": "Marshall Islands",
    "MK": "North Macedonia", "ML": "Mali", "MM": "Myanmar", "MN": "Mongolia",
    "MO": "Macao", "MP": "Northern Mariana Islands", "MQ": "Martinique",
    "MR": "Mauritania", "MS": "Montserrat", "MT": "Malta", "MU": "Mauritius",
    "MV": "Maldives", "MW": "Malawi", "MX": "Mexico", "MY": "Malaysia",
    "MZ": "Mozambique", "NA": "Namibia", "NC": "New Caledonia", "NE": "Niger",
    "NF": "Norfolk Island", "NG": "Nigeria", "NI": "Nicaragua",
    "NL": "Netherlands", "NO": "Norway", "NP": "Nepal", "NR": "Nauru",
    "NU": "Niue", "NZ": "New Zealand", "OM": "Oman", "PA": "Panama",
    "PE": "Peru", "PF": "French Polynesia", "PG": "Papua New Guinea",
    "PH": "Philippines", "PK": "Pakistan", "PL": "Poland",
    "PM": "Saint Pierre and Miquelon", "PN": "Pitcairn Islands",
    "PR": "Puerto Rico", "PS": "Palestine", "PT": "Portugal", "PW": "Palau",
    "PY": "Paraguay", "QA": "Qatar", "RE": "Reunion", "RO": "Romania",
    "RS": "Serbia", "RU": "Russia", "RW": "Rwanda", "SA": "Saudi Arabia",
    "SB": "Solomon Islands", "SC": "Seychelles", "SD": "Sudan", "SE": "Sweden",
    "SG": "Singapore", "SH": "Saint Helena", "SI": "Slovenia",
    "SJ": "Svalbard and Jan Mayen", "SK": "Slovakia", "SL": "Sierra Leone",
    "SM": "San Marino", "SN": "Senegal", "SO": "Somalia", "SR": "Suriname",
    "SS": "South Sudan", "ST": "Sao Tome and Principe", "SV": "El Salvador",
    "SX": "Sint Maarten", "SY": "Syria", "SZ": "Eswatini",
    "TC": "Turks and Caicos Islands", "TD": "Chad",
    "TF": "French Southern Territories", "TG": "Togo", "TH": "Thailand",
    "TJ": "Tajikistan", "TK": "Tokelau", "TL": "Timor-Leste",
    "TM": "Turkmenistan", "TN": "Tunisia", "TO": "Tonga", "TR": "Turkey",
    "TT": "Trinidad and Tobago", "TV": "Tuvalu", "TW": "Taiwan",
    "TZ": "Tanzania", "UA": "Ukraine", "UG": "Uganda",
    "UM": "United States Minor Outlying Islands", "US": "United States",
    "UY": "Uruguay", "UZ": "Uzbekistan", "VA": "Vatican City",
    "VC": "Saint Vincent and the Grenadines", "VE": "Venezuela",
    "VG": "British Virgin Islands", "VI": "United States Virgin Islands",
    "VN": "Vietnam", "VU": "Vanuatu", "WF": "Wallis and Futuna",
    "WS": "Samoa", "XK": "Kosovo", "YE": "Yemen", "YT": "Mayotte",
    "ZA": "South Africa", "ZM": "Zambia", "ZW": "Zimbabwe",
}

# IPTC's country field is alpha-3, XMP's is usually alpha-2, and cameras write
# whichever their firmware felt like.
#
# Listed explicitly, never derived by taking the first two letters. That shortcut
# is right often enough to look like it works and then files Chad (TCD) under the
# Turks and Caicos Islands (TC). A code that is not here is reported as UNKNOWN,
# which costs nothing: the photograph's coordinates answer the same question, and
# an honest blank falls through to them.
_ALPHA3 = {
    "ARE": "AE", "BGD": "BD", "BHS": "BS", "BRB": "BB", "BWA": "BW",
    "CHE": "CH", "CHL": "CL", "CHN": "CN", "CIV": "CI", "CRI": "CR",
    "DEU": "DE", "DNK": "DK", "ESP": "ES", "GBR": "GB", "GRC": "GR",
    "HRV": "HR", "IRL": "IE", "IRQ": "IQ", "ISL": "IS", "JPN": "JP",
    "KHM": "KH", "KOR": "KR", "LKA": "LK", "MAR": "MA", "MCO": "MC",
    "MDV": "MV", "MEX": "MX", "MYS": "MY", "NLD": "NL", "PHL": "PH",
    "PRT": "PT", "SGP": "SG", "SVK": "SK", "SVN": "SI", "SWE": "SE",
    "THA": "TH", "TUR": "TR", "TUN": "TN", "USA": "US", "VNM": "VN",
    "ZAF": "ZA", "ARG": "AR", "AUS": "AU", "AUT": "AT", "BEL": "BE",
    "BRA": "BR", "CAN": "CA", "CZE": "CZ", "EGY": "EG", "FIN": "FI",
    "FRA": "FR", "IDN": "ID", "IND": "IN", "ISR": "IL", "ITA": "IT",
    "JOR": "JO", "KWT": "KW", "NOR": "NO", "NZL": "NZ", "OMN": "OM",
    "POL": "PL", "QAT": "QA", "RUS": "RU", "SAU": "SA",
}

_BY_NAME = {v.lower(): k for k, v in NAMES.items()}


def name_of(code: str, extra: dict | None = None) -> str:
    """The folder name for a country code. Falls back to the code itself.

    Falling back to the CODE rather than to "Unknown" is deliberate: a folder
    called `XZ` is odd enough to ask about and tells you exactly what to look up,
    where a folder called `Unknown` hides which country it was.
    """
    code = (code or "").strip().upper()
    if not code:
        return ""
    if extra and code in extra:
        return extra[code]
    return NAMES.get(code, code)


def code_of(text: str) -> str:
    """A country code from whatever a photo actually wrote in the field.

    Cameras and cataloguing programs write two letters, three letters, or the
    country's name in English - all three turn up in the same library.
    """
    text = (text or "").strip()
    if not text:
        return ""
    up = text.upper()
    if len(up) == 2 and up in NAMES:
        return up
    if len(up) == 3 and up in _ALPHA3:
        return _ALPHA3[up]
    found = _BY_NAME.get(text.lower())
    return found or ""
