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


def normalize_nrc(nrc):
    """Strip every non-digit character from nrc.

    Returns None if no digits remain after stripping.
    """
    digits = re.sub(r'\D', '', nrc)
    if not digits:
        return None
    return digits


def generate_password(nrc):
    """Generate a password: nrc's digits only, slashes/spaces/other
    separators stripped (see normalize_nrc).

    Returns None if nrc has no digits after normalization.
    """
    return normalize_nrc(nrc)
