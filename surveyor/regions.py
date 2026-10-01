"""Stable territorial IDs shared by statistical sources and inspection inputs."""

REGIONS = [
    ("all", "Вся страна", "Butun mamlakat", "Nationwide"),
    ("1735", "Каракалпакстан", "Qoraqalpog‘iston", "Karakalpakstan"),
    ("1703", "Андижанская область", "Andijon viloyati", "Andijan region"),
    ("1706", "Бухарская область", "Buxoro viloyati", "Bukhara region"),
    ("1708", "Джизакская область", "Jizzax viloyati", "Jizzakh region"),
    ("1710", "Кашкадарьинская область", "Qashqadaryo viloyati", "Kashkadarya region"),
    ("1712", "Навоийская область", "Navoiy viloyati", "Navoi region"),
    ("1714", "Наманганская область", "Namangan viloyati", "Namangan region"),
    ("1718", "Самаркандская область", "Samarqand viloyati", "Samarkand region"),
    ("1722", "Сурхандарьинская область", "Surxondaryo viloyati", "Surkhandarya region"),
    ("1724", "Сырдарьинская область", "Sirdaryo viloyati", "Syrdarya region"),
    ("1727", "Ташкентская область", "Toshkent viloyati", "Tashkent region"),
    ("1730", "Ферганская область", "Farg‘ona viloyati", "Fergana region"),
    ("1733", "Хорезмская область", "Xorazm viloyati", "Khorezm region"),
    ("1726", "Ташкент", "Toshkent", "Tashkent city"),
]
ALIASES = {name.casefold(): row[0] for row in REGIONS for name in row}
ALIASES.update({"1700": "all", "город ташкент": "1726", "республика каракалпакстан": "1735"})


def region_code(value):
    return ALIASES.get(value.casefold().strip(), value.strip())
