from typing import Optional

# NOTE: volumes 1 to 11 print Parliament No 1 in the sitting header, but their reports carry Parliament 0, so they map to 0.
VOLUME_TO_PARLIAMENT: dict[int, int] = {
    1: 0, 2: 0, 3: 0, 4: 0, 6: 0, 7: 0, 8: 0, 9: 0, 11: 0,
    12: 0, 13: 0, 14: 0, 15: 0, 16: 0, 17: 0, 18: 0, 19: 0,
    20: 0, 21: 0, 22: 0, 23: 0,
    24: 1, 25: 1, 26: 1,
    27: 2, 28: 2, 29: 2, 30: 2, 31: 2,
    32: 3, 33: 3, 34: 3, 35: 3,
    36: 4, 37: 4, 38: 4, 39: 4,
    40: 5, 41: 5, 42: 5, 43: 5, 44: 5,
    45: 6, 46: 6, 47: 6, 48: 6, 49: 6, 50: 6, 51: 6,
    52: 7, 53: 7, 54: 7, 55: 7, 56: 7, 57: 7, 58: 7,
    59: 8, 60: 8, 61: 8, 62: 8, 63: 8, 64: 8, 65: 8, 66: 8,
    67: 9, 68: 9, 69: 9, 70: 9, 71: 9, 72: 9, 73: 9,
    74: 10, 75: 10, 76: 10, 77: 10, 78: 10, 79: 10, 80: 10, 81: 10,
    82: 11, 83: 11, 84: 11, 85: 11, 86: 11, 87: 11,
    88: 12, 89: 12,
}


def infer_parliament(parliament_number: Optional[int], volume_number: Optional[int]) -> Optional[int]:
    if parliament_number is not None:
        return parliament_number
    return VOLUME_TO_PARLIAMENT.get(volume_number)  # type: ignore[arg-type]
