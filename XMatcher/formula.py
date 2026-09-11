"""Formula-composition helpers used to constrain XRD database searches."""

from __future__ import annotations

from fractions import Fraction
import math
import re
from typing import Dict, Tuple


_SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_NUMBER = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)")


def formula_ratio_key(formula: str) -> Tuple[Tuple[str, int], ...]:
    """Return a reduced element-ratio key, independent of formula ordering.

    For example, ``Fe2O3``, ``O3Fe2`` and ``Fe4O6`` all become
    ``((\"Fe\", 2), (\"O\", 3))``. Parenthesised groups are supported.
    """
    text = str(formula or "").translate(_SUBSCRIPTS).strip().replace(" ", "")
    if not text:
        raise ValueError("Chemical formula is empty")

    def parse_group(index: int, closing: bool = False) -> tuple[Dict[str, Fraction], int]:
        amounts: Dict[str, Fraction] = {}
        while index < len(text):
            token = text[index]
            if token == ")":
                if not closing:
                    raise ValueError(f"Unexpected ')' in chemical formula: {formula}")
                return amounts, index + 1
            if token == "(":
                nested, index = parse_group(index + 1, closing=True)
                multiplier, index = read_number(index)
                for element, amount in nested.items():
                    amounts[element] = amounts.get(element, Fraction(0)) + amount * multiplier
                continue
            if not token.isupper():
                raise ValueError(f"Invalid chemical formula: {formula}")
            element = token
            index += 1
            if index < len(text) and text[index].islower():
                element += text[index]
                index += 1
            multiplier, index = read_number(index)
            amounts[element] = amounts.get(element, Fraction(0)) + multiplier
        if closing:
            raise ValueError(f"Unclosed '(' in chemical formula: {formula}")
        return amounts, index

    def read_number(index: int) -> tuple[Fraction, int]:
        match = _NUMBER.match(text, index)
        if not match:
            return Fraction(1), index
        value = Fraction(match.group())
        if value <= 0:
            raise ValueError(f"Element amounts must be positive: {formula}")
        return value, match.end()

    amounts, end = parse_group(0)
    if end != len(text) or not amounts:
        raise ValueError(f"Invalid chemical formula: {formula}")
    denominator = 1
    for amount in amounts.values():
        denominator = denominator * amount.denominator // math.gcd(denominator, amount.denominator)
    integers = {element: int(amount * denominator) for element, amount in amounts.items()}
    divisor = 0
    for amount in integers.values():
        divisor = math.gcd(divisor, amount)
    return tuple(sorted((element, amount // divisor) for element, amount in integers.items()))
