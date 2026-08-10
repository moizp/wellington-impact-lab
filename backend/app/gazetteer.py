"""Static Wellington-region place-name list, used only for keyword-matching
MetService warnings — the one official source with no coordinates at all
(confirmed empirically) and a nationwide, not region-specific, feed.

Deliberately approximate: an unlisted place name gets missed. A named, honest
limitation (see FINETUNE_PLAN.md), not a hidden gap. Not exhaustive — extend
as gaps are noticed.
"""

WELLINGTON_PLACE_NAMES = [
    "wellington",
    # Wellington City suburbs
    "ngaio", "khandallah", "wadestown", "kelburn", "karori", "brooklyn",
    "island bay", "newtown", "mount victoria", "mount cook", "thorndon",
    "miramar", "seatoun", "kilbirnie", "lyall bay", "johnsonville",
    "tawa", "churton park", "grenada", "aro valley", "berhampore",
    "hataitai", "roseneath", "oriental bay", "vogeltown", "highbury",
    # Hutt Valley
    "lower hutt", "upper hutt", "petone", "wainuiomata", "eastbourne",
    "stokes valley", "taita", "naenae", "avalon",
    # Porirua / Kapiti
    "porirua", "titahi bay", "whitby", "paremata", "plimmerton",
    "kapiti", "paraparaumu", "waikanae", "otaki",
    # Wairarapa
    "wairarapa", "masterton", "carterton", "greytown", "featherston",
    # Roads/landmarks frequently named in warnings
    "remutaka", "rimutaka", "ngauranga gorge", "centennial highway",
    "hutt road", "state highway 1", "sh1", "sh2",
]


def mentions_wellington_region(text: str) -> bool:
    """Case-insensitive substring match against the gazetteer list."""
    lowered = text.lower()
    return any(name in lowered for name in WELLINGTON_PLACE_NAMES)


# Approximate suburb/town centroids — used to resolve a public report's
# lat/lon when the submitter only gives a suburb name, not coordinates.
# Demo-scale accuracy only (good enough for a 10-20km relevance radius), not
# precision geocoding.
#
# This must stay a superset-by-name of the suburb entries in
# WELLINGTON_PLACE_NAMES above. It drifted out of sync: several names the
# keyword matcher recognised (Hataitai among them) had no centroid here, so a
# report from one of those suburbs resolved to no coordinates at all — which
# both excluded it from the dashboard map and skipped every distance-based
# official-source match for it. Add to both lists when adding a suburb.
WELLINGTON_SUBURB_COORDS: dict[str, tuple[float, float]] = {
    "wellington": (-41.2865, 174.7762),
    "ngaio": (-41.2408, 174.7645),
    "khandallah": (-41.2472, 174.7857),
    "kelburn": (-41.2870, 174.7647),
    "karori": (-41.2833, 174.7333),
    "brooklyn": (-41.3024, 174.7677),
    "island bay": (-41.3387, 174.7726),
    "newtown": (-41.3106, 174.7789),
    "mount victoria": (-41.2936, 174.7867),
    "thorndon": (-41.2765, 174.7756),
    "miramar": (-41.3167, 174.8167),
    "seatoun": (-41.3306, 174.8306),
    "kilbirnie": (-41.3222, 174.7944),
    "johnsonville": (-41.2100, 174.8058),
    "tawa": (-41.1728, 174.8306),
    "churton park": (-41.1919, 174.8167),
    "porirua": (-41.1333, 174.8500),
    "titahi bay": (-41.1000, 174.8333),
    "kapiti": (-40.9167, 174.9958),
    "paraparaumu": (-40.9167, 174.9958),
    "waikanae": (-40.8756, 175.0625),
    "lower hutt": (-41.2122, 174.9056),
    "upper hutt": (-41.1264, 175.0728),
    "petone": (-41.2261, 174.8697),
    "wainuiomata": (-41.2589, 174.9522),
    "masterton": (-40.9597, 175.6575),
    # Added to close the drift against WELLINGTON_PLACE_NAMES described above.
    # Wellington City
    "hataitai": (-41.3078, 174.7955),
    "wadestown": (-41.2664, 174.7679),
    "aro valley": (-41.2946, 174.7614),
    "berhampore": (-41.3186, 174.7746),
    "mount cook": (-41.3036, 174.7726),
    "lyall bay": (-41.3286, 174.7969),
    "roseneath": (-41.2925, 174.8022),
    "oriental bay": (-41.2925, 174.7930),
    "vogeltown": (-41.3175, 174.7657),
    "highbury": (-41.2947, 174.7539),
    "grenada": (-41.2036, 174.8231),
    # Hutt Valley
    "eastbourne": (-41.2925, 174.9008),
    "stokes valley": (-41.1750, 174.9800),
    "taita": (-41.1789, 174.9614),
    "naenae": (-41.1972, 174.9469),
    "avalon": (-41.1919, 174.9394),
    # Porirua / Kapiti
    "whitby": (-41.1183, 174.8931),
    "paremata": (-41.1017, 174.8672),
    "plimmerton": (-41.0839, 174.8642),
    "otaki": (-40.7558, 175.1386),
    # Wairarapa
    "carterton": (-41.0233, 175.5228),
    "greytown": (-41.0794, 175.4614),
    "featherston": (-41.1147, 175.3239),
}
