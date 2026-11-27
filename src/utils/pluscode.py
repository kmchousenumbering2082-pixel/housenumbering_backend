from __future__ import annotations

import math

SEPARATOR = "+"
SEPARATOR_POSITION = 8
PADDING_CHARACTER = "0"
CODE_ALPHABET = "23456789CFGHJMPQRVWX"
ENCODING_BASE = len(CODE_ALPHABET)
LATITUDE_MAX = 90
LONGITUDE_MAX = 180
MAX_DIGIT_COUNT = 15
PAIR_CODE_LENGTH = 10
GRID_COLUMNS = 4
GRID_ROWS = 5
PAIR_FIRST_PLACE_VALUE = ENCODING_BASE ** (PAIR_CODE_LENGTH // 2 - 1)
PAIR_PRECISION = ENCODING_BASE**3
GRID_CODE_LENGTH = MAX_DIGIT_COUNT - PAIR_CODE_LENGTH
FINAL_LAT_PRECISION = PAIR_PRECISION * GRID_ROWS**GRID_CODE_LENGTH
FINAL_LNG_PRECISION = PAIR_PRECISION * GRID_COLUMNS**GRID_CODE_LENGTH


def clip_latitude(latitude: float) -> float:
    return min(90.0, max(-90.0, latitude))


def normalize_longitude(longitude: float) -> float:
    while longitude < -180:
        longitude += 360
    while longitude >= 180:
        longitude -= 360
    return longitude


def compute_latitude_precision(code_length: int) -> float:
    if code_length <= 10:
        return math.pow(20, math.floor((code_length / -2) + 2))
    return math.pow(20, -3) / math.pow(GRID_ROWS, code_length - 10)


def encode(
    latitude: float, longitude: float, code_length: int = PAIR_CODE_LENGTH
) -> str:
    """Encode a latitude/longitude pair into an Open Location Code."""
    if code_length < 2 or (code_length < PAIR_CODE_LENGTH and code_length % 2 == 1):
        raise ValueError(f"Invalid Open Location Code length - {code_length}")

    code_length = min(code_length, MAX_DIGIT_COUNT)
    latitude = clip_latitude(latitude)
    longitude = normalize_longitude(longitude)

    if latitude == 90:
        latitude -= compute_latitude_precision(code_length)

    code = ""
    lat_val = int(round((latitude + LATITUDE_MAX) * FINAL_LAT_PRECISION, 6))
    lng_val = int(round((longitude + LONGITUDE_MAX) * FINAL_LNG_PRECISION, 6))

    if code_length > PAIR_CODE_LENGTH:
        for _ in range(0, MAX_DIGIT_COUNT - PAIR_CODE_LENGTH):
            lat_digit = lat_val % GRID_ROWS
            lng_digit = lng_val % GRID_COLUMNS
            ndx = lat_digit * GRID_COLUMNS + lng_digit
            code = CODE_ALPHABET[ndx] + code
            lat_val //= GRID_ROWS
            lng_val //= GRID_COLUMNS
    else:
        lat_val //= pow(GRID_ROWS, GRID_CODE_LENGTH)
        lng_val //= pow(GRID_COLUMNS, GRID_CODE_LENGTH)

    for _ in range(0, PAIR_CODE_LENGTH // 2):
        code = CODE_ALPHABET[lng_val % ENCODING_BASE] + code
        code = CODE_ALPHABET[lat_val % ENCODING_BASE] + code
        lat_val //= ENCODING_BASE
        lng_val //= ENCODING_BASE

    code = code[:SEPARATOR_POSITION] + SEPARATOR + code[SEPARATOR_POSITION:]

    if code_length >= SEPARATOR_POSITION:
        return code[: code_length + 1]

    return (
        code[:code_length]
        + PADDING_CHARACTER.zfill(SEPARATOR_POSITION - code_length)
        + SEPARATOR
    )
