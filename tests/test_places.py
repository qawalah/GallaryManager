"""Sorting by country and city - and every way that could quietly be wrong.

The feature is easy; the honesty is not. A photograph's coordinates do not name
a place, they name a POINT, and the nearest town in a table of towns is a guess
dressed up as a fact. In a city it is right to within a kilometre. On a mountain
it is forty kilometres away and possibly across a border - and `Italy/Rome` for
a photograph taken in San Marino is exactly the kind of wrong answer this app
exists not to give.

So most of what is tested here is the refusing: the distance limits, the town
that is not claimed, the country that is not claimed either, and the photograph
left exactly where it was.
"""

import datetime as dt
import os
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R              # noqa: E402
import app.tasks                           # noqa: E402,F401
from app.tasks.bydate import UNSURE, folder_for, wants_place   # noqa: E402
from core import countries, places         # noqa: E402
from core import settings as S             # noqa: E402
from core.store import store_path          # noqa: E402
from tests.test_tags import app1_xmp, app13_iptc, jpeg_with     # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")

TOWNS = [
    ("Rome", 41.8933, 12.4829, "IT", 2872800),
    ("Milan", 45.4643, 9.1895, "IT", 1350680),
    ("Doha", 25.2854, 51.5310, "QA", 1450000),
    ("Marrakesh", 31.6315, -7.9898, "MA", 928850),
    ("San Marino", 43.9361, 12.4467, "SM", 4500),
    ("Tromso", 69.6489, 18.9551, "NO", 65000),
]


def geonames_line(name, lat, lon, cc, pop):
    """The dump's 19 tab-separated columns, of which four are wanted."""
    bits = [""] * 19
    bits[0] = "1"
    bits[1] = bits[2] = name
    bits[4], bits[5] = f"{lat}", f"{lon}"
    bits[6], bits[7] = "P", "PPL"
    bits[8] = cc
    bits[14] = str(pop)
    return "\t".join(bits)


def write_dump(path, towns=TOWNS):
    with open(path, "w", encoding="utf-8") as fh:
        for t in towns:
            fh.write(geonames_line(*t) + "\n")
    return path


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="places-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.dump = write_dump(os.path.join(self.dir, "cities15000.txt"))
        self.store = os.path.join(self.dir, "places.tsv")

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def table(self):
        places.import_dump(self.dump, self.store)
        return places.load(self.store)


# ------------------------------------------------------------------- the table

class Importing(Base):
    def test_a_dump_becomes_a_store(self):
        got = places.import_dump(self.dump, self.store)
        self.assertEqual(got["towns"], len(TOWNS))
        self.assertEqual(got["countries"], 5)
        self.assertTrue(os.path.isfile(self.store))

    def test_the_zip_is_read_as_downloaded(self):
        """Asking somebody to unzip a file first is a step to get wrong at 11pm."""
        zipped = os.path.join(self.dir, "cities15000.zip")
        with zipfile.ZipFile(zipped, "w") as zf:
            zf.write(self.dump, "cities15000.txt")
        got = places.import_dump(zipped, self.store)
        self.assertEqual(got["towns"], len(TOWNS))

    def test_the_wrong_file_says_so_rather_than_importing_nothing(self):
        wrong = os.path.join(self.dir, "notes.txt")
        open(wrong, "w").write("this is not a city table\n")
        with self.assertRaises(ValueError) as e:
            places.import_dump(wrong, self.store)
        self.assertIn("geonames", str(e.exception).lower())

    def test_no_store_is_an_empty_table_not_a_crash(self):
        t = places.load(os.path.join(self.dir, "nothing.tsv"))
        self.assertEqual(len(t), 0)
        self.assertFalse(places.from_coordinates(t, 41.9, 12.5))

    def test_country_names_can_be_replaced_from_geonames_own_file(self):
        info = os.path.join(self.dir, "countryInfo.txt")
        with open(info, "w", encoding="utf-8") as fh:
            fh.write("#ISO\tISO3\tnum\tfips\tCountry\n")
            fh.write("IT\tITA\t380\tIT\tItalian Republic\n")
        places.import_dump(self.dump, self.store, names_file=info)
        t = places.load(self.store)
        self.assertEqual(t.country_name("IT"), "Italian Republic")
        self.assertEqual(t.country_name("QA"), "Qatar")        # still the built-in


class Nearest(Base):
    def test_a_town_you_are_standing_in(self):
        got = places.from_coordinates(self.table(), 41.9028, 12.4964)
        self.assertEqual((got.country, got.city), ("Italy", "Rome"))
        self.assertLess(got.km, 5)

    def test_the_nearest_is_the_nearest_not_the_biggest(self):
        """San Marino has 4,500 people and Rome has three million. Twelve
        kilometres away, the small one is the answer."""
        got = places.from_coordinates(self.table(), 43.9424, 12.4578)
        self.assertEqual(got.city, "San Marino")
        self.assertEqual(got.country, "San Marino")

    def test_far_from_any_town_the_town_is_not_claimed(self):
        got = places.from_coordinates(self.table(), 31.0, -8.0)
        self.assertEqual(got.country, "Morocco")
        self.assertEqual(got.city, "")
        self.assertIn("Marrakesh", got.how)
        self.assertGreater(got.km, 30)

    def test_and_far_from_everything_nothing_is_claimed(self):
        """Mid-ocean, the nearest name we know is not evidence of anything."""
        got = places.from_coordinates(self.table(), -33.9, 151.2)
        self.assertFalse(got)
        self.assertEqual(got.country, "")
        self.assertIn("too far", got.how)

    def test_the_limits_are_the_callers_to_set(self):
        t = self.table()
        loose = places.from_coordinates(t, 31.0, -8.0, city_within_km=100)
        self.assertEqual(loose.city, "Marrakesh")
        tight = places.from_coordinates(t, 41.9028, 12.4964, city_within_km=1)
        self.assertEqual(tight.city, "")
        self.assertEqual(tight.country, "Italy")

    def test_nonsense_coordinates_are_refused(self):
        t = self.table()
        self.assertFalse(places.from_coordinates(t, 0.0, 0.0))       # null island
        self.assertFalse(places.from_coordinates(t, 91.0, 400.0))

    def test_the_answer_does_not_depend_on_the_search_band(self):
        """The lookup widens a band of latitude and stops early. Stopping is only
        safe because nothing outside the band can be closer than the band itself
        - get that wrong and the answer changes with how far north you are."""
        t = self.table()
        for lat, lon, want in ((69.7, 19.0, "Tromso"), (25.32, 51.53, "Doha"),
                               (45.47, 9.19, "Milan")):
            self.assertEqual(places.from_coordinates(t, lat, lon).city, want)

    def test_a_town_just_outside_the_first_band_still_wins(self):
        """The trap in searching a band of latitude: a town half a degree north
        can be inside the band and 250 km away, while the real nearest is one
        degree north and 90 km away. Answering from the first band that holds
        anything gives the wrong town, confidently."""
        dump = write_dump(os.path.join(self.dir, "band.txt"), [
            ("Sideways", 40.4, 15.5, "IT", 20000),      # 0.4 deg north, ~260 km
            ("Northerly", 40.8, 12.0, "IT", 20000),     # 0.8 deg north, ~89 km
        ])
        places.import_dump(dump, self.store)
        got = places.from_coordinates(places.load(self.store), 40.0, 12.0,
                                      city_within_km=200)
        self.assertEqual(got.city, "Northerly")


class BiggerTowns(Base):
    """"Stick to the places I would name myself."" A village three kilometres
    away is the honest nearest name and often not the one you want on a folder -
    a week in Tuscany becomes eleven hamlets rather than one Florence."""

    def setUp(self):
        super().setUp()
        write_dump(self.dump, TOWNS + [("Frascati", 41.8090, 12.6800, "IT", 22000)])

    def test_the_village_wins_when_nothing_is_asked_for(self):
        got = places.from_coordinates(self.table(), 41.81, 12.68)
        self.assertEqual(got.city, "Frascati")

    def test_and_the_city_wins_when_a_size_is(self):
        got = places.from_coordinates(self.table(), 41.81, 12.68, city_within_km=50,
                                      at_least=100_000)
        self.assertEqual(got.city, "Rome")

    def test_when_nothing_big_is_near_it_says_so_rather_than_picking_one(self):
        got = places.from_coordinates(self.table(), 69.7, 19.0, at_least=1_000_000)
        self.assertEqual(got.city, "")
        self.assertEqual(got.country, "Norway")
        self.assertIn("no town over 1,000,000 people", got.how)
        self.assertIn("Tromso", got.how)

    def test_an_old_store_admits_it_cannot_do_this(self):
        """v1 held no population. Filtering against a column of zeros would
        report that nowhere on earth qualifies."""
        places.import_dump(self.dump, self.store)
        with open(self.store, encoding="utf-8") as fh:
            text = fh.read()
        with open(self.store, "w", encoding="utf-8") as fh:
            fh.write(text.replace(places.STORE_HEADER, places.OLD_HEADERS[0]))
        t = places.load(self.store)
        self.assertTrue(len(t))                  # it still works for everything else
        self.assertFalse(t.has_population)
        self.assertTrue(places.store_info(self.store)["ok"])
        self.assertFalse(places.store_info(self.store)["population"])


class Renaming(unittest.TestCase):
    def test_the_name_you_would_have_written(self):
        got = places.rename(places.Place(country="Morocco", city="Marrakesh"),
                            places.read_renames("Marrakesh = Marrakech"))
        self.assertEqual(got.city, "Marrakech")

    def test_a_country_can_be_renamed_too(self):
        got = places.rename(places.Place(country="Czechia", city="Prague"),
                            places.read_renames("czechia = Czech Republic"))
        self.assertEqual(got.country, "Czech Republic")

    def test_several_lines_and_junk_between_them(self):
        got = places.read_renames("Marrakesh = Marrakech\nnot a rename\n = \n"
                                  "Roma=Rome")
        self.assertEqual(got, {"marrakesh": "Marrakech", "roma": "Rome"})

    def test_nothing_asked_for_changes_nothing(self):
        was = places.Place(country="Italy", city="Rome")
        self.assertEqual(places.rename(was, {}).city, "Rome")


# ------------------------------------------------------- what the file itself says

class WrittenIn(Base):
    def test_xmp_inside_a_jpeg(self):
        photo = jpeg_with(os.path.join(self.dir, "a.jpg"), app1_xmp(
            '<rdf:Description photoshop:City="Rome" photoshop:Country="Italy"/>'))
        got = places.written_place(photo)
        self.assertEqual((got.country, got.city), ("Italy", "Rome"))

    def test_iptc_city_and_country(self):
        photo = jpeg_with(os.path.join(self.dir, "b.jpg"),
                          _iptc_place("Doha", "Qatar"))
        got = places.written_place(photo)
        self.assertEqual((got.country, got.city), ("Qatar", "Doha"))

    def test_a_sidecar_beats_the_file(self):
        photo = jpeg_with(os.path.join(self.dir, "c.jpg"), app1_xmp(
            '<rdf:Description photoshop:City="Rome" photoshop:Country="Italy"/>'))
        with open(os.path.join(self.dir, "c.xmp"), "w", encoding="utf-8") as fh:
            fh.write('<rdf:Description photoshop:City="Milan" '
                     'photoshop:Country="Italy"/>')
        self.assertEqual(places.written_place(photo).city, "Milan")

    def test_a_country_code_is_turned_into_a_name(self):
        photo = jpeg_with(os.path.join(self.dir, "d.jpg"), app1_xmp(
            '<rdf:Description photoshop:City="Doha" '
            'Iptc4xmpCore:CountryCode="QA"/>'))
        self.assertEqual(places.written_place(photo).country, "Qatar")

    def test_a_file_that_says_nothing(self):
        self.assertFalse(places.written_place(os.path.join(FIX, "plain.jpg")))

    def test_three_letter_codes_are_looked_up_never_truncated(self):
        """TCD is Chad. Its first two letters are the Turks and Caicos Islands,
        and a shortcut that right often enough is how that file gets there."""
        self.assertEqual(countries.code_of("USA"), "US")
        self.assertEqual(countries.code_of("ITA"), "IT")
        self.assertEqual(countries.code_of("TCD"), "")
        self.assertEqual(countries.code_of("Italy"), "IT")


def _iptc_place(city, country):
    datasets = b""
    for key, value in (((2, 90), city), ((2, 101), country)):
        raw = value.encode("utf-8")
        datasets += bytes([0x1C, key[0], key[1]]) + struct.pack(">H", len(raw)) + raw
    resource = (b"8BIM" + struct.pack(">H", 0x0404) + b"\x00\x00"
                + struct.pack(">I", len(datasets)) + datasets)
    if len(datasets) % 2:
        resource += b"\x00"
    body = b"Photoshop 3.0\x00" + resource
    return b"\xff\xed" + struct.pack(">H", len(body) + 2) + body


# ------------------------------------------------------------------ the shapes

class Shapes(unittest.TestCase):
    WHEN = dt.datetime(2022, 7, 14, 18, 3)

    def place(self, country="Italy", city="Rome"):
        return places.Place(country=country, city=city)

    def test_every_place_shape(self):
        want = {
            "place_country": "Italy",
            "place_city": "Rome",
            "place_country_city": os.path.join("Italy", "Rome"),
            "place_country_dash_city": "Italy - Rome",
            "place_country_year_city": os.path.join("Italy", "2022", "Rome"),
            "place_country_city_month": os.path.join("Italy", "Rome", "2022-07"),
            "place_city_year": os.path.join("Rome", "2022"),
            "place_year_city": os.path.join("2022", "Rome"),
            "place_year_country_city": os.path.join("2022", "Italy - Rome"),
            "place_year_month_place": os.path.join("2022", "07", "Italy - Rome"),
        }
        for shape, expect in want.items():
            self.assertEqual(folder_for(self.WHEN, shape, place=self.place()),
                             expect, shape)

    def test_every_shape_offered_is_a_shape_that_works(self):
        """A dropdown entry that produces nothing is worse than one that is not
        offered: you pick it, press the button, and the app says it did nothing."""
        from app.tasks.bydate import SHAPES
        for value, label, group in SHAPES:
            if value == "custom":
                continue                  # yours: it makes whatever you write
            got = folder_for(self.WHEN, value, place=self.place())
            self.assertTrue(got, f"{label} ({value}) produced no folder")
            self.assertIn(group, ("By date", "By date, Hijri", "By place", "Kept"))

    def test_the_shapes_are_written_as_country_and_city(self):
        """Not as Italy and Rome. An example is read as an example, and more
        than one person has wondered whether the folder would say Rome."""
        from app.tasks.bydate import SHAPES
        for value, label, _group in SHAPES:
            if value.startswith("place"):
                self.assertNotIn("Italy", label)
                self.assertNotIn("Rome", label)

    def test_a_country_without_a_town_goes_to_unsure(self):
        got = folder_for(self.WHEN, "place_country_city",
                         place=self.place(city=""))
        self.assertEqual(got, os.path.join("Italy", UNSURE))

    def test_and_the_country_only_shape_does_not_care(self):
        self.assertEqual(folder_for(self.WHEN, "place_country",
                                    place=self.place(city="")), "Italy")

    def test_no_place_at_all_gives_no_folder(self):
        """An empty answer, never a folder name - it cannot be mistaken for one,
        and the caller leaves the photograph exactly where it is."""
        self.assertEqual(folder_for(self.WHEN, "place_country_city",
                                    place=places.Place()), "")
        self.assertEqual(folder_for(self.WHEN, "place_country_city", place=None), "")

    def test_the_date_shapes_are_untouched_by_any_of_this(self):
        self.assertEqual(folder_for(self.WHEN, "year_month"),
                         os.path.join("2022", "07"))
        self.assertEqual(folder_for(self.WHEN, "flat_day"), "2022-07-14")

    def test_a_slash_in_a_place_name_cannot_make_a_folder(self):
        got = folder_for(self.WHEN, "place_country_city",
                         place=places.Place(country="Italy", city="Reggio/Emilia"))
        self.assertEqual(got, os.path.join("Italy", "Reggio Emilia"))

    def test_which_shapes_need_a_place(self):
        self.assertTrue(wants_place("place_country"))
        self.assertFalse(wants_place("year_month"))


# --------------------------------------------------------------- the whole task

class Sorting(Base):
    def setUp(self):
        super().setUp()
        self.lib = os.path.join(self.dir, "Photos")
        self.shoot = os.path.join(self.lib, "dump")
        os.makedirs(self.shoot)
        S.save({"library": self.lib})
        places.import_dump(self.dump, store_path("places.tsv"))

    def photo(self, name, city="", country="", when="2022:07:14 18:03:22"):
        """A JPEG carrying a capture time, and optionally a written place."""
        path = os.path.join(self.shoot, name)
        shutil.copy(os.path.join(FIX, "plain.jpg"), path)
        if city or country:
            with open(os.path.splitext(path)[0] + ".xmp", "w",
                      encoding="utf-8") as fh:
                fh.write(f'<rdf:Description photoshop:City="{city}" '
                         f'photoshop:Country="{country}" '
                         f'exif:DateTimeOriginal="{when}"/>')
        return path

    def run_plan(self, **over):
        t = R.get("bydate")
        p = t.make_plan({"folder": self.lib, "raw": "", "previews": "",
                         "mirror": False, **over})
        return t, p

    def targets(self, p):
        return {os.path.basename(r.source): os.path.relpath(
            os.path.dirname(r.target), self.lib) for r in p.rows}

    def test_a_written_place_files_a_photo_with_no_coordinates_at_all(self):
        self.photo("a.jpg", city="Rome", country="Italy")
        _t, p = self.run_plan(shape="place_country_city")
        self.assertEqual(self.targets(p)["a.jpg"], os.path.join("Italy", "Rome"))

    def test_a_photo_with_neither_is_left_exactly_where_it_is(self):
        """And the row says WHY. "Nothing to file it under" is true of a photo
        with no location and of one whose coordinates were too far from any town
        to name, and those are two different problems with two different fixes."""
        self.photo("b.jpg")
        _t, p = self.run_plan(shape="place_country_city")
        self.assertEqual(p.rows, [])
        why = " ".join(w for _n, w in p.skipped)
        self.assertIn("no location", why)
        self.assertIn("left exactly where it is", why)

    def test_and_when_nothing_at_all_could_be_placed_it_refuses(self):
        """Silently moving nothing looks identical to having nothing to do."""
        self.photo("c.jpg")
        _t, p = self.run_plan(shape="place_country_city")
        self.assertTrue(p.blocked)
        self.assertIn("Not one photo", p.blocked)

    def test_with_no_table_imported_it_says_so_first(self):
        os.remove(store_path("places.tsv"))
        self.photo("d.jpg", city="Rome", country="Italy")
        _t, p = self.run_plan(shape="place_country_city")
        self.assertIn("No place table", p.notes[0])
        # and the written place still works without any table at all
        self.assertEqual(self.targets(p)["d.jpg"], os.path.join("Italy", "Rome"))

    def test_the_row_says_where_the_answer_came_from(self):
        self.photo("e.jpg", city="Rome", country="Italy")
        _t, p = self.run_plan(shape="place_country_city")
        self.assertIn("Italy / Rome", p.rows[0].detail)

    def test_coordinates_name_the_town_when_the_file_names_only_the_country(self):
        """Two halves from two sources. Perfectly fine - as long as the row says
        so rather than presenting it as one answer."""
        path = os.path.join(self.shoot, "i.jpg")
        shutil.copy(os.path.join(FIX, "phone_doha.jpg"), path)
        with open(os.path.join(self.shoot, "i.xmp"), "w", encoding="utf-8") as fh:
            fh.write('<rdf:Description photoshop:Country="Qatar"/>')
        _t, p = self.run_plan(shape="place_country_city")
        self.assertEqual(self.targets(p)["i.jpg"], os.path.join("Qatar", "Doha"))

    def test_a_file_that_disagrees_with_its_own_coordinates_says_so(self):
        """Whoever typed it was there, so they win - but one of the two is wrong
        about a photograph, and settling that quietly is how it stays wrong.

        Reached when the file names the COUNTRY and not the town, which is what
        half-catalogued libraries look like. A file naming both is taken at its
        word without reading its coordinates at all."""
        path = os.path.join(self.shoot, "j.jpg")
        shutil.copy(os.path.join(FIX, "phone_doha.jpg"), path)
        with open(os.path.join(self.shoot, "j.xmp"), "w", encoding="utf-8") as fh:
            fh.write('<rdf:Description photoshop:Country="Italy"/>')
        _t, p = self.run_plan(shape="place_country_city")
        self.assertEqual(self.targets(p)["j.jpg"], os.path.join("Italy", UNSURE))
        said = [r.detail for r in p.rows if r.name == "j.jpg"][0]
        self.assertIn("Doha", said)                # the disagreement is on the row

    def test_a_file_naming_both_is_taken_at_its_word(self):
        path = os.path.join(self.shoot, "m.jpg")
        shutil.copy(os.path.join(FIX, "phone_doha.jpg"), path)
        with open(os.path.join(self.shoot, "m.xmp"), "w", encoding="utf-8") as fh:
            fh.write('<rdf:Description photoshop:City="Rome" '
                     'photoshop:Country="Italy"/>')
        _t, p = self.run_plan(shape="place_country_city")
        self.assertEqual(self.targets(p)["m.jpg"], os.path.join("Italy", "Rome"))

    def test_a_shoot_in_one_place_is_looked_up_once(self):
        """A folder is hundreds of frames standing in the same spot. Asking the
        table hundreds of times for one answer is the difference between a scan
        that finishes and one somebody kills."""
        for n in range(4):
            shutil.copy(os.path.join(FIX, "phone_doha.jpg"),
                        os.path.join(self.shoot, f"k{n}.jpg"))
        table = places.load(store_path("places.tsv"))
        asked = []
        real = table.nearest
        table.nearest = lambda *a, **k: (asked.append(1), real(*a, **k))[1]
        known = {}
        from app.tasks.bydate import _look_up
        for n in range(4):
            _look_up(os.path.join(self.shoot, f"k{n}.jpg"), table, known, 30, 200)
        self.assertEqual(len(asked), 1, "the table was asked more than once")

    def test_the_places_it_found_are_listed_for_you_to_correct(self):
        self.photo("n1.jpg", city="Marrakesh", country="Morocco")
        self.photo("n2.jpg", city="Marrakesh", country="Morocco")
        _t, p = self.run_plan(shape="place_country_city")
        names = {i["name"]: i["count"] for i in p.picks["items"]}
        self.assertEqual(names, {"Morocco": 2, "Marrakesh": 2})
        self.assertEqual(p.picks["option"], "place_names")

    def test_several_folders_are_sorted_into_the_one_they_sit_in(self):
        """Not into each of them: picking January and February and getting
        January/2022/07 beside February/2022/07 is the same mess with more
        folders in it."""
        one = os.path.join(self.lib, "card 1")
        two = os.path.join(self.lib, "card 2")
        os.makedirs(one)
        os.makedirs(two)
        for where, name in ((one, "a.jpg"), (two, "b.jpg")):
            shutil.copy(os.path.join(FIX, "plain.jpg"), os.path.join(where, name))
        t = R.get("bydate")
        p = t.make_plan({"folder": one + "\n" + two, "shape": "year_month",
                         "mirror": False, "raw": "", "previews": ""})
        self.assertFalse(p.blocked, p.blocked)
        self.assertEqual(self.targets(p),
                         {"a.jpg": os.path.join("2022", "07"),
                          "b.jpg": os.path.join("2022", "07")})
        self.assertTrue(any("2 folders" in n for n in p.notes))

    def test_a_folder_inside_another_picked_one_is_not_read_twice(self):
        one = os.path.join(self.lib, "trip")
        two = os.path.join(one, "day 1")
        os.makedirs(two)
        shutil.copy(os.path.join(FIX, "plain.jpg"), os.path.join(two, "c.jpg"))
        t = R.get("bydate")
        p = t.make_plan({"folder": one + "\n" + two, "shape": "year_month",
                         "mirror": False, "raw": "", "previews": ""})
        self.assertEqual(len([r for r in p.rows if r.name == "c.jpg"]), 1)

    def test_folders_with_nothing_above_them_are_refused(self):
        """The common folder of two libraries on different drives is the top of
        the machine, and building 2022/07 there is not a sorted library."""
        elsewhere = tempfile.mkdtemp(prefix="other-")
        try:
            t = R.get("bydate")
            p = t.make_plan({"folder": self.lib + "\n" + elsewhere,
                             "shape": "year_month", "mirror": False,
                             "raw": "", "previews": ""})
            self.assertTrue(p.blocked)
            self.assertIn("separate runs", p.blocked)
        finally:
            shutil.rmtree(elsewhere, ignore_errors=True)

    def test_and_a_rename_is_obeyed(self):
        self.photo("n3.jpg", city="Marrakesh", country="Morocco")
        _t, p = self.run_plan(shape="place_country_city",
                              place_names="Marrakesh = Marrakech")
        self.assertEqual(self.targets(p)["n3.jpg"],
                         os.path.join("Morocco", "Marrakech"))
        self.assertTrue(any("Renamed" in n for n in p.notes))

    def test_a_clip_is_sorted_with_the_photographs_it_was_taken_among(self):
        """Sorting the library moves the photographs somewhere new, so a clip
        has to follow them to where they are GOING, not to where they were."""
        from tests.test_video_time import has, make_clip
        if not has("ffmpeg"):
            self.skipTest("no ffmpeg here to make a real clip with")
        self.photo("p1.jpg", city="Rome", country="Italy")
        make_clip(os.path.join(self.shoot, "CLIP.MP4"), "2022-07-14T18:03:30Z")
        _t, p = self.run_plan(shape="place_country_city")
        self.assertEqual(self.targets(p)["CLIP.MP4"],
                         os.path.join("Italy", "Rome"))
        said = [r.detail for r in p.rows if r.name == "CLIP.MP4"][0]
        self.assertIn("with the photos going to", said)

    def test_and_a_clip_that_matches_nothing_is_left_where_it_is(self):
        """A clip carries no place of its own, so a place sort has nothing to go
        on when no shoot matches - and inventing one would be the whole point of
        this app being got wrong."""
        from tests.test_video_time import has, make_clip
        if not has("ffmpeg"):
            self.skipTest("no ffmpeg here to make a real clip with")
        self.photo("p2.jpg", city="Rome", country="Italy")
        make_clip(os.path.join(self.shoot, "LATER.MP4"), "2023-01-05T09:00:00Z")
        _t, p = self.run_plan(shape="place_country_city")
        self.assertNotIn("LATER.MP4", self.targets(p))
        self.assertTrue(any("LATER.MP4" in n and "video" in w
                            for n, w in p.skipped), p.skipped)

    def test_a_date_sort_still_works_and_asks_for_no_place(self):
        self.photo("f.jpg")
        _t, p = self.run_plan(shape="year_month")
        self.assertEqual(self.targets(p)["f.jpg"], os.path.join("2022", "07"))

    def test_the_sidecar_travels_with_the_photo(self):
        """A rating written last week must not be left behind in the old folder."""
        self.photo("g.jpg", city="Rome", country="Italy")
        _t, p = self.run_plan(shape="place_country_city")
        moved = {os.path.basename(r.source) for r in p.rows}
        self.assertEqual(moved, {"g.jpg", "g.xmp"})

    def test_applying_it_puts_the_files_there(self):
        self.photo("h.jpg", city="Doha", country="Qatar")
        t, p = self.run_plan(shape="place_country_year_city")
        result = t.apply(p)
        self.assertEqual(result.failed, 0)
        self.assertTrue(os.path.isfile(
            os.path.join(self.lib, "Qatar", "2022", "Doha", "h.jpg")))
        self.assertFalse(os.path.isdir(self.shoot))       # emptied, tidied away


if __name__ == "__main__":
    unittest.main()
