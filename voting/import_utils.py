import re


def split_name(name):
    """Split a full name into (first_name, last_name).

    Everything before the first space is the first name; everything
    after is the last name. A name with no space has an empty last name.
    """
    parts = name.strip().split(' ', 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ''
    return first_name, last_name


def normalize_nrc_last4(nrc):
    """Strip every non-digit character from nrc and return the last 4 digits.

    Returns None if fewer than 4 digits remain after stripping.
    """
    digits = re.sub(r'\D', '', nrc)
    if len(digits) < 4:
        return None
    return digits[-4:]


def generate_password(first_name, nrc):
    """Generate a password: capitalized first 3 letters of first_name, a
    literal hyphen, then the last 4 digits of nrc (see normalize_nrc_last4).

    Returns None if nrc doesn't have at least 4 digits after normalization.
    """
    last4 = normalize_nrc_last4(nrc)
    if last4 is None:
        return None
    letters = first_name.strip()[:3]
    name_part = letters[:1].upper() + letters[1:].lower()
    return f"{name_part}-{last4}"
