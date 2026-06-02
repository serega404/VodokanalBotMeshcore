FULL_CYR2LAT = {
    'а': 'a',
    'б': 'b',
    'в': 'v',
    'г': 'g',
    'д': 'd',
    'е': 'e',
    'ё': 'yo',
    'ж': 'zh',
    'з': 'z',
    'и': 'i',
    'й': 'y',
    'к': 'k',
    'л': 'l',
    'м': 'm',
    'н': 'n',
    'о': 'o',
    'п': 'p',
    'р': 'r',
    'с': 's',
    'т': 't',
    'у': 'u',
    'ф': 'f',
    'х': 'h',
    'ц': 'ts',
    'ч': 'ch',
    'ш': 'sh',
    'щ': 'sch',
    'ъ': '',
    'ы': 'y',
    'ь': '',
    'э': 'e',
    'ю': 'yu',
    'я': 'ya',
}

SOFT_CYR2LAT = {
    'а': 'a',
    'е': 'e',
    'о': 'o',
    'р': 'p',
    'с': 'c',
    'у': 'y',
    'х': 'x',
    'А': 'A',
    'В': 'B',
    'Е': 'E',
    'К': 'K',
    'М': 'M',
    'Н': 'H',
    'О': 'O',
    'Р': 'P',
    'С': 'C',
    'Т': 'T',
    'Х': 'X',
    'З': '3',
}

CYR2LAT_MODES = {
    'full': FULL_CYR2LAT,
    'off': None,
    'soft': SOFT_CYR2LAT,
}


def apply_case(replacement, char):
    if char.isupper():
        return replacement.capitalize()

    return replacement


def cyr2lat(message, mode='full'):
    if mode not in CYR2LAT_MODES:
        raise ValueError("Unknown cyr2lat mode: " + mode)

    if mode == 'off':
        return message

    mapping = CYR2LAT_MODES[mode]
    result = []
    for char in message:
        if mode == 'soft':
            result.append(mapping.get(char, char))
            continue

        replacement = mapping.get(char.lower())
        if replacement is None:
            result.append(char)
        else:
            result.append(apply_case(replacement, char))

    return ''.join(result)
